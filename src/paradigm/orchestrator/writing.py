"""Writing-phase handler for the orchestration engine."""

from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from paradigm.journal.paper import (
    SECTION_ASSIGNMENTS,
    PaperDraft,
    PaperSection,
    SectionDraft,
    parse_sections_from_markdown,
    sanitize_unicode_math,
    section_assignments_from_template,
    strip_agent_scaffolding,
)
from paradigm.literature.citation_validation import (
    build_citation_allowlist,
    compile_allowlist_citations,
    validate_and_strip_citations,
)
from paradigm.logging.events import EventType
from paradigm.orchestrator.constants import (
    _CODE_BLOCK_RE,
    _CONCEPTUAL_FIGURE_MAX_TOKENS,
    _CONCEPTUAL_FIGURE_PROMPT,
    _CONCEPTUAL_FIGURE_TIMEOUT,
    _MIN_PAPER_LENGTH,
    _MODE_WRITING_OVERRIDES,
    _PHASE_INSTRUCTIONS,
    _WRITING_MAX_TOKENS,
    DIGEST_CONTEXT_LIMIT,
    DIGEST_MAX_TOKENS,
    DIGEST_PROMPT,
)
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine

_FIG_WORDS = {"fig", "figure", "plot", "chart", "graph", "diagram"}


def _humanize_figure_name(exp_name: str) -> str:
    """Turn an experiment/figure name into a short, human-readable caption.

    ``mass_luminosity_fit`` -> ``Mass luminosity fit``. Used as the figure
    caption so the PDF reads "Figure 1: Mass luminosity fit" instead of the old
    "Figure 1: Figure 1". Returns "" if nothing meaningful remains.
    """
    name = re.sub(r"\.(png|pdf|jpe?g|svg)$", "", exp_name or "", flags=re.IGNORECASE)
    name = name.replace("_", " ").replace("-", " ")
    words = [w for w in name.split() if w.lower() not in _FIG_WORDS]
    name = " ".join(words).strip()
    return name[0].upper() + name[1:] if name else ""


_FIGURE_IMG_RE = re.compile(r"!\[[^\]]*\]\(figures/([^)]+)\)[ \t]*\n?")


def _strip_missing_figure_refs(body: str, paper_dir: Path) -> str:
    """Remove ``![...](figures/X)`` tags whose file isn't present in ``paper_dir``.

    Writers sometimes reference a figure that was never generated (a hallucinated
    "graphical abstract", a wrong filename). Such a tag leaves an empty float and —
    worse — makes \\includegraphics abort the whole PDF compile. Call this AFTER the
    real figures are copied into ``paper_dir/figures`` so only genuinely-missing
    references are dropped.
    """
    figures_dir = paper_dir / "figures"

    def _keep(m: re.Match) -> str:
        return m.group(0) if (figures_dir / m.group(1)).exists() else ""

    return _FIGURE_IMG_RE.sub(_keep, body)


class WritingHandler:
    """Encapsulates writing-phase logic extracted from OrchestrationEngine."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine
        # Corpus citation allow-list for this writing phase (populated by
        # _build_citation_allowlist when corpus_grounded_citations is on; "" / [] otherwise).
        self._citation_allowlist_block: str = ""
        self._citation_allowlist_entries: list[tuple[str, str, str]] = []
        # paper_id -> source url for NON-arXiv entries (ext-… ids), so they render
        # with a real link instead of a fabricated arXiv form.
        self._citation_allowlist_urls: dict[str, str] = {}

    def _build_citation_allowlist(self) -> None:
        """Compute the corpus citation allow-list once per writing phase.

        When ``corpus_grounded_citations`` is on, build a numbered ``[N]`` allow-list from
        the cycle's discovered papers (``LiteratureHandler.discovered_papers``) and stash
        both the writer-facing block (appended to every WRITING prompt) and the entries
        (for deterministic bibliography compilation). No-op when the flag is off or no
        papers were discovered.
        """
        self._citation_allowlist_block = ""
        self._citation_allowlist_entries = []
        self._citation_allowlist_urls = {}
        if not self._engine._config.citation.corpus_grounded_citations:
            return
        papers = list(getattr(self._engine._literature, "discovered_papers", []) or [])
        self._citation_allowlist_urls = dict(
            getattr(self._engine._literature, "discovered_fulltext", {}) or {}
        )
        block, entries = build_citation_allowlist(
            papers,
            self._engine._config.citation.max_allowlist_papers,
            self._citation_allowlist_urls,
        )
        self._citation_allowlist_block = block
        self._citation_allowlist_entries = entries

    def refresh_allowlist_numbering(self, cited: list[tuple[str, str, str]]) -> None:
        """Re-order the allow-list after a bibliography compile so its ``[N]`` numbering
        matches the markers now embedded in the paper body.

        ``compile_allowlist_citations`` renumbers markers by first appearance, so after
        assembly (and after every revision compile) the body's ``[1]..[k]`` refer to
        ``cited`` — NOT to the original discovery order. Putting the cited entries first
        (uncited ones after, still citable) keeps the block shown to the REVISING writer
        consistent with the draft it is editing.
        """
        if not self._citation_allowlist_entries or not cited:
            return
        cited_ids = {e[0] for e in cited}
        rest = [e for e in self._citation_allowlist_entries if e[0] not in cited_ids]
        entries = list(cited) + rest
        block, entries = build_citation_allowlist(
            entries, len(entries), self._citation_allowlist_urls
        )
        self._citation_allowlist_block = block
        self._citation_allowlist_entries = entries

    def apply_citation_net(self, body: str) -> str:
        """Re-apply the citation invariant to a REWRITTEN paper body (revisions).

        Assembly runs the allow-list compile + fabricated-id strip once (`run_writing_phase`),
        but every revision replaces the whole body with the writer's raw output — without
        this, a revised paper can re-acquire fabricated arXiv ids or out-of-range ``[N]``
        markers and ship (ADR-013 would hold only for never-revised papers). Best-effort:
        a failure here returns the body unchanged rather than breaking the review loop.
        """
        config = self._engine._config.citation
        if config.corpus_grounded_citations and self._citation_allowlist_entries:
            try:
                body, _refs_md, cited = compile_allowlist_citations(
                    body, self._citation_allowlist_entries, self._citation_allowlist_urls
                )
                self.refresh_allowlist_numbering(cited)
                self._engine._logger.log(
                    EventType.CITATION_GROUNDING,
                    content={
                        "event": "corpus_grounded_citations_revision",
                        "num_citations": len(cited),
                        "allowlist_size": len(self._citation_allowlist_entries),
                    },
                    thread_id=self._engine.state.thread_id,
                )
            except Exception as e:
                self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
        if config.strip_ungrounded_citations:
            try:
                valid_ids = set(getattr(self._engine._literature, "seen_paper_ids", set()) or set())
                body, stats = validate_and_strip_citations(body, valid_ids)
                if stats["fabricated_arxiv_stripped"] or stats["unverifiable_author_year"]:
                    self._engine._logger.log(
                        EventType.CITATION_GROUNDING,
                        content={"event": "citation_safety_net_revision", **stats},
                        thread_id=self._engine.state.thread_id,
                    )
            except Exception as e:
                self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
        return body

    def _build_execution_fact_sheet(self) -> str:
        """Build an anti-confabulation execution fact sheet for writing prompts.

        Partitions experiments into successful (use these) and failed (do not use)
        sections. Each successful experiment gets a structured block showing its
        actual output. Failed experiments are listed with failure reasons and
        explicit "do not cite" markers.

        Returns:
            Formatted fact sheet string, or empty string if no experiments ran.
        """
        metadata = self._engine.state.experiment_metadata
        if not metadata:
            return ""

        successful: list[dict] = []
        failed: list[dict] = []
        for entry in metadata:
            if entry.get("status") == "success":
                successful.append(entry)
            else:
                failed.append(entry)

        lines = [
            "\n\n## Execution Fact Sheet",
            "### CRITICAL ANTI-CONFABULATION RULE",
            "Every number you write MUST come from an Actual Output block below. "
            "If an experiment FAILED, you MUST NOT describe it as producing results.",
            "",
        ]

        # --- Successful experiments ---
        lines.append("### Successful Results (USE THESE)")
        if successful:
            for entry in successful:
                name = entry.get("name", "unnamed")
                has_figs = "Yes" if entry.get("has_figures") else "No"
                lines.append(f"#### Experiment: {name}")
                lines.append(f"**Status:** success | **Figures:** {has_figs}")
                stdout_full = str(entry.get("stdout_full", entry.get("stdout_preview", "")))
                lines.append(f"**Actual Output:**\n```\n{stdout_full}\n```")
                lines.append("Cite ONLY these numbers. Do NOT invent additional values.")
                lines.append("")
        else:
            lines.append("*(No experiments succeeded.)*")
            lines.append("")

        # --- Failed experiments ---
        lines.append("### FAILED Experiments (DO NOT USE)")
        if failed:
            for entry in failed:
                name = entry.get("name", "unnamed")
                failure_reason = entry.get("failure_reason", "Unknown error")
                lines.append(f"- **{name}**: {failure_reason}")
                lines.append(
                    "  DO NOT describe this experiment as having produced results. "
                    "DO NOT fabricate numbers for this experiment."
                )
            lines.append("")
        else:
            lines.append("*(All experiments succeeded.)*")
            lines.append("")

        # --- Pre-registered verdicts (1A) ---
        verdicts = self._engine.state.prereg_verdicts
        if verdicts:
            lines.append("### Pre-Registered Verdicts (report honestly)")
            for v in verdicts:
                lines.append(
                    f"- **{v.get('metric', '?')}**: "
                    f"{v.get('verdict', '?').upper()} — {v.get('detail', '')}"
                )
                rc = v.get("refutation_condition")
                if rc:
                    lines.append(f"  (refutation condition: {rc})")
            lines.append(
                "A REFUTED or INCONCLUSIVE prediction is a valid, publishable result — "
                "report it as such; do NOT spin it as confirmation."
            )
            lines.append("")

        # --- Verification ledger (1B) ---
        records = self._engine.state.verification_records
        if records:
            lines.append("### Verification Ledger (re-execution)")
            for r in records:
                err = (
                    f", max rel error {r.max_rel_error:.2e}" if r.max_rel_error is not None else ""
                )
                lines.append(f"- **{r.experiment_name}**: {r.status.upper()}{err} — {r.detail}")
            lines.append(
                "Only ACCEPTED experiments reproduced under re-execution. Do NOT report "
                "numbers from experiments that did not verify."
            )
            lines.append("")

        lines.append(
            "**If you write a number not found in any Actual Output block above, "
            "you are confabulating. Cross-check every quantitative claim.**"
        )
        return "\n".join(lines)

    def _filter_successful_execution_context(self) -> str:
        """Filter execution context to only include blocks from successful experiments.

        Parses the markdown execution context (which has ``### Experiment:`` headers)
        and returns only the blocks whose experiment name appears in the successful
        experiment metadata.

        Returns:
            Filtered execution context string, or original if parsing fails.
        """
        ctx = self._engine.state.execution_context
        if not ctx:
            return ""

        metadata = self._engine.state.experiment_metadata
        if not metadata:
            return ctx

        successful_names = {
            entry.get("name", "").lower() for entry in metadata if entry.get("status") == "success"
        }
        if not successful_names:
            return ""

        # Split on experiment headers and keep only successful blocks
        blocks = re.split(r"(?=^### Experiment:)", ctx, flags=re.MULTILINE)
        kept: list[str] = []
        for block in blocks:
            header_match = re.match(r"^### Experiment:\s*(.+?)$", block, re.MULTILINE)
            if header_match:
                name = header_match.group(1).strip().lower()
                if name in successful_names:
                    kept.append(block)
            elif block.strip():
                # Preamble text before any experiment header — keep it
                kept.append(block)

        return "\n".join(kept) if kept else ctx

    def _extract_forbidden_claims(self) -> list[str]:
        """Extract FORBIDDEN claims from POST_EXECUTION synthesis and experiment metadata.

        Collects explicit FORBIDDEN entries from the synthesis text and
        auto-generates entries for failed experiments.

        Returns:
            List of forbidden claim strings.
        """
        forbidden: list[str] = []

        # From POST_EXECUTION synthesis
        synthesis = self._engine.state.phase_synthesis.get(str(ResearchPhase.POST_EXECUTION), "")
        for line in synthesis.split("\n"):
            line = line.strip()
            if line.upper().startswith("- FORBIDDEN:"):
                claim = line[len("- FORBIDDEN:") :].strip()
                if claim:
                    forbidden.append(claim)

        # Auto-generate from failed experiments
        for entry in self._engine.state.experiment_metadata:
            if entry.get("status") != "success":
                name = entry.get("name", "unnamed")
                reason = str(entry.get("failure_reason", "unknown error"))[:100]
                forbidden.append(
                    f"Do NOT describe experiment '{name}' as having produced results "
                    f"(it FAILED: {reason})"
                )

        # Auto-generate from refuted pre-registered predictions (1A): a refuted
        # hypothesis must not be presented as supported.
        for v in self._engine.state.prereg_verdicts:
            if v.get("verdict") == "refuted":
                forbidden.append(
                    f"Do NOT claim the hypothesis behind pre-registered metric "
                    f"'{v.get('metric', '?')}' is supported — it was REFUTED "
                    f"({v.get('detail', '')})."
                )

        return forbidden

    def _build_forbidden_claims_block(self) -> str:
        """Build a prominent forbidden-claims block for writer/editor prompts.

        Returns:
            Formatted forbidden claims block, or empty string if none.
        """
        forbidden = self._extract_forbidden_claims()
        if not forbidden:
            return ""

        lines = [
            "\n\n## FORBIDDEN CLAIMS — HARD CONSTRAINT",
            "The following claims MUST NOT appear in the paper under any circumstances. "
            "If you write ANY of these, the paper will be rejected:",
            "",
        ]
        for i, claim in enumerate(forbidden, 1):
            lines.append(f"{i}. {claim}")
        lines.append("")
        lines.append(
            "**Violation of any forbidden claim is an automatic rejection. "
            "Cross-check your draft against this list before submitting.**"
        )
        return "\n".join(lines)

    def _build_data_origin_statement(self) -> str:
        """Build explicit data origin statement from execution caveats."""
        caveats = self._engine.state.execution_caveats
        if not caveats:
            return ""

        caveat_text = " ".join(caveats).lower()
        synthetic_keywords = ["synthetic", "simulated", "generated", "placeholder", "mock"]
        is_synthetic = any(kw in caveat_text for kw in synthetic_keywords)

        if not is_synthetic:
            return ""

        return (
            "\n\n## DATA ORIGIN — CRITICAL CONSTRAINT\n"
            "**ALL data in this study is SYNTHETIC / SIMULATED.**\n"
            "You MUST NOT describe the data pipeline as if real observational "
            "data was used. Do NOT mention retrieving data from archives "
            "(MAST, Vizier, etc.), cross-matching with surveys (Gaia, GALAH, etc.), "
            "or analyzing real light curves UNLESS the execution caveats explicitly "
            "confirm real data was successfully accessed.\n\n"
            "The Methods section MUST clearly state that synthetic data was generated "
            "and describe HOW it was generated, not describe a real observational workflow.\n\n"
            "**Violation of this constraint is grounds for immediate rejection.**"
        )

    def _check_reference_quality(self, body: str) -> list[str]:
        """Check reference quality and return warnings."""
        warnings: list[str] = []

        # Find references section
        ref_match = re.search(r"^## References\s*\n(.*)", body, re.MULTILINE | re.DOTALL)
        if not ref_match:
            return warnings

        ref_text = ref_match.group(1)
        lines = [line.strip() for line in ref_text.split("\n") if line.strip()]

        # Count bare URLs (lines that are just a URL with no author/title metadata)
        bare_url_pattern = re.compile(r"^\[?\d*\]?\s*https?://")
        bare_urls = [line for line in lines if bare_url_pattern.match(line) and len(line) < 200]

        if len(bare_urls) > len(lines) * 0.5 and len(bare_urls) > 5:
            warnings.append(
                f"Reference quality: {len(bare_urls)}/{len(lines)} references are bare URLs "
                "without proper citation metadata (author, title, year)."
            )

        if len(lines) > 80:
            warnings.append(
                f"Reference count ({len(lines)}) is unusually high. "
                "Many may be irrelevant to the research topic."
            )

        return warnings

    def _check_forbidden_claims_violations(self, paper_text: str) -> list[str]:
        """Check assembled paper for violations of forbidden claims.

        Uses keyword matching to flag potential violations where a failed
        experiment name appears near success-indicating words.

        Args:
            paper_text: The assembled paper markdown text.

        Returns:
            List of warning strings describing potential violations.
        """
        if not self._engine.state.experiment_metadata:
            return []

        violations: list[str] = []
        paper_lower = paper_text.lower()

        # Check each failed experiment — is it described as producing results?
        for entry in self._engine.state.experiment_metadata:
            if entry.get("status") == "success":
                continue
            name = str(entry.get("name", "")).lower()
            # Skip very short/generic names
            if len(name) < 5:
                continue
            # Check if the experiment name appears near success-indicating words
            keywords = name.split("_")[:3]
            for kw in keywords:
                if len(kw) <= 4 or kw not in paper_lower:
                    continue
                idx = paper_lower.find(kw)
                context = paper_lower[max(0, idx - 100) : idx + 100]
                success_words = [
                    "computed",
                    "obtained",
                    "yielded",
                    "produced",
                    "show",
                    "demonstrate",
                    "reveals",
                    "confirms",
                ]
                if any(sw in context for sw in success_words):
                    snippet = paper_text[max(0, idx - 50) : idx + 50]
                    violations.append(
                        f"Possible forbidden claim violation: failed experiment "
                        f"'{entry.get('name')}' may be described as successful "
                        f"near: '...{snippet}...'"
                    )
                    break  # One violation per experiment is enough

        return violations

    @staticmethod
    def _extract_numerical_claims(text: str) -> list[tuple[str, str, str]]:
        """Extract numerical claims from paper text.

        Finds patterns like "r = -0.31", "correlation of -0.695", "N = 1000",
        "p < 0.05", etc. and returns them with their metric keyword and section.

        Args:
            text: Paper markdown text.

        Returns:
            List of (section_name, metric_keyword, value_string) tuples.
        """
        # Split into sections by ## headers
        section_pattern = re.compile(r"^##\s+(.+)", re.MULTILINE)
        sections: list[tuple[str, str]] = []
        matches = list(section_pattern.finditer(text))
        for i, m in enumerate(matches):
            name = m.group(1).strip().lower()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append((name, text[start:end]))

        # If no sections found, treat entire text as one section
        if not sections:
            sections = [("body", text)]

        # Pattern to find "keyword = value" or "keyword of value" constructs
        claim_pattern = re.compile(
            r"(?:^|[^a-zA-Z])"
            r"(correlation|slope|intercept|mean|median|std|sigma|"
            r"p-value|chi-squared|chi2|rmse|rms|mae|r-squared|r2|"
            r"coefficient|amplitude|period|frequency|sample\s+size|"
            r"[rRnNpP])"
            r"\s*(?:=|≈|~|of|:)\s*"
            r"([<>≤≥]?\s*-?[\d]+\.?[\d]*(?:\s*[×x]\s*10\^?-?[\d]+)?)",
            re.IGNORECASE,
        )

        claims: list[tuple[str, str, str]] = []
        for section_name, section_text in sections:
            for m in claim_pattern.finditer(section_text):
                keyword = m.group(1).strip().lower()
                value = m.group(2).strip()
                claims.append((section_name, keyword, value))

        return claims

    @staticmethod
    def _find_numerical_discrepancies(claims: list[tuple[str, str, str]]) -> str:
        """Find numerical discrepancies across sections.

        Groups claims by metric keyword and flags groups where the same
        metric has different values in different sections.

        Args:
            claims: List of (section_name, metric_keyword, value_string) tuples.

        Returns:
            Markdown report of discrepancies, or empty string if none found.
        """
        from collections import defaultdict

        # Group by keyword
        by_keyword: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for section, keyword, value in claims:
            by_keyword[keyword].append((section, value))

        discrepancies: list[str] = []
        for keyword, occurrences in by_keyword.items():
            if len(occurrences) < 2:
                continue
            # Check if values differ across sections
            values = {v for _, v in occurrences}
            if len(values) > 1:
                details = ", ".join(f"{section}: {value}" for section, value in occurrences)
                discrepancies.append(f"- **{keyword}**: {details}")

        if not discrepancies:
            return ""

        return (
            "\n\n## Numerical Inconsistencies Detected\n"
            "The following metrics have different values across sections. "
            "You MUST harmonize these — use the value from the Execution Fact Sheet "
            "as the single source of truth:\n" + "\n".join(discrepancies)
        )

    @staticmethod
    def _extract_reference_values(fact_sheet: str) -> str:
        """Extract lines with numbers from Actual Output blocks in the fact sheet.

        Provides a compact "cheat sheet" of reference values that section
        writers can use to ensure numerical consistency across sections.

        Args:
            fact_sheet: The execution fact sheet string.

        Returns:
            Formatted reference values block, or empty string if none found.
        """
        # Find all "Actual Output" code blocks and extract lines with numbers
        pattern = re.compile(r"\*\*Actual Output:\*\*\s*\n```\n(.*?)```", re.DOTALL)
        value_lines: list[str] = []
        for match in pattern.finditer(fact_sheet):
            block = match.group(1)
            for line in block.strip().split("\n"):
                line = line.strip()
                # Keep lines that contain numbers (digits with optional decimals)
                if line and re.search(r"\d+\.?\d*", line):
                    value_lines.append(f"- {line}")
                    if len(value_lines) >= 20:
                        break
            if len(value_lines) >= 20:
                break

        if not value_lines:
            return ""

        return (
            "\n\n## Reference Values — Use These Exact Numbers\n"
            "The following values come directly from experiment output. "
            "Use these exact numbers in your section — do NOT round, "
            "re-derive, or approximate them:\n" + "\n".join(value_lines)
        )

    def _get_section_assignments(self) -> dict[str, list[str]]:
        """Get role → section name assignments from profile or fallback.

        Returns:
            Dict mapping role name to list of section name strings.
        """
        profile = self._engine._profile
        if profile is not None:
            # Check mode-specific template first
            mode_template = profile.mode_templates.get(self._engine.state.mode)
            if mode_template is not None and mode_template.sections:
                return section_assignments_from_template(mode_template.sections)
            if profile.document_template.sections:
                return section_assignments_from_template(profile.document_template.sections)
        # Fallback to hardcoded science assignments
        return {role: [s.value for s in secs] for role, secs in SECTION_ASSIGNMENTS.items()}

    def _get_section_order(self) -> list[str]:
        """Get ordered list of section names from profile or fallback.

        Returns:
            List of section name strings in document order.
        """
        profile = self._engine._profile
        if profile is not None:
            # Check mode-specific template first
            mode_template = profile.mode_templates.get(self._engine.state.mode)
            if mode_template is not None and mode_template.sections:
                return [s.name for s in mode_template.sections]
            if profile.document_template.sections:
                return [s.name for s in profile.document_template.sections]
        return [s.value for s in PaperSection]

    async def run_writing_phase(self) -> PaperDraft | None:
        """Run the WRITING phase: section drafting, assembly, optional refinement.

        Returns:
            PaperDraft with assembled paper, or None if writing failed
            (e.g. all agents errored and the paper is empty/too short).
        """
        draft = PaperDraft(section_order=self._get_section_order())

        # Build the corpus citation allow-list BEFORE drafting so every writer prompt can
        # carry it (no-op unless corpus_grounded_citations is on).
        self._build_citation_allowlist()

        # Round 1: Section Drafting — each agent drafts their assigned sections
        self._engine._display.writing_section_drafting()
        await self.run_section_drafting(draft)

        # Round 2: Assembly — writer combines all sections
        self._engine._display.writing_assembly()
        assembled_body = await self.run_assembly(draft)

        # Post-process: ensure figure image tags are embedded inline
        assembled_body = self.embed_figures_inline(assembled_body)

        # Generate conceptual figures if EXECUTION was skipped
        assembled_body = await self.generate_conceptual_figures(assembled_body)

        # Convert Unicode math to LaTeX before internal review sees the paper
        assembled_body = sanitize_unicode_math(assembled_body)
        draft.assembled_body = assembled_body

        # Post-assembly: check for forbidden claims violations
        violations = self._check_forbidden_claims_violations(assembled_body)
        if violations:
            self._engine.state.forbidden_claims_violations = violations
        else:
            self._engine.state.forbidden_claims_violations = []

        # Citations. When corpus-grounded citations are on, the writer cited only [N]
        # markers from the injected allow-list — compile a deterministic, fully
        # corpus-backed bibliography (no network) and SKIP the Perplexity path. Otherwise
        # fall back to the optional post-hoc Perplexity grounding. Non-fatal on failure.
        config = self._engine._config.citation
        if config.corpus_grounded_citations and self._citation_allowlist_entries:
            try:
                draft = await self._engine._citation_handler.ground_from_allowlist(
                    draft, self._citation_allowlist_entries
                )
            except Exception as e:
                self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
                self._engine._display.citation_grounding_error(e)
        elif config.enable_citation_grounding:
            try:
                draft = await self._engine._citation_handler.run_citation_grounding(draft)
            except Exception as e:
                self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
                self._engine._display.citation_grounding_error(e)

        # Always-on safety net (independent of the flag): strip fabricated inline arXiv ids
        # (not in the cycle's corpus) and log unverifiable "(Author, Year)" cites.
        if config.strip_ungrounded_citations:
            valid_ids = set(getattr(self._engine._literature, "seen_paper_ids", set()) or set())
            cleaned, stats = validate_and_strip_citations(draft.assembled_body, valid_ids)
            draft.assembled_body = cleaned
            if stats["fabricated_arxiv_stripped"] or stats["unverifiable_author_year"]:
                self._engine._logger.log(
                    EventType.CITATION_GROUNDING,
                    content={"event": "citation_safety_net", **stats},
                    thread_id=self._engine.state.thread_id,
                )

        # Validate paper length — if all agents failed, the draft is empty
        if len(draft.assembled_body) < _MIN_PAPER_LENGTH:
            self._engine._display.paper_too_short(len(draft.assembled_body), _MIN_PAPER_LENGTH)
            self._engine._logger.log_error(
                ValueError(
                    f"Writing phase produced insufficient content "
                    f"({len(draft.assembled_body)} chars < {_MIN_PAPER_LENGTH})"
                ),
                thread_id=self._engine.state.thread_id,
            )
            self._engine._db.update_thread(
                self._engine.state.thread_id, status="writing_incomplete"
            )
            return None

        # Extract title from assembled body
        for line in assembled_body.split("\n"):
            if line.startswith("# "):
                draft.title = line[2:].strip()
                break

        # Persist paper to database
        paper_id = f"paper-{uuid.uuid4().hex[:12]}"
        abstract = ""
        if "abstract" in draft.sections:
            abstract = draft.sections["abstract"].content[:1000]

        authors = list(self._engine.state.agents.keys())
        self._engine._db.create_paper(
            paper_id=paper_id,
            title=draft.title or self._engine.state.seed_prompt[:200],
            abstract=abstract,
            authors=authors,
            body=draft.assembled_body,
            status="draft",
        )
        self._engine._db.update_thread(self._engine.state.thread_id, current_draft_id=paper_id)

        # Write markdown file to papers directory. Offloaded: save_paper_file may
        # shell out to a LaTeX engine to pre-compile the PDF (so the download link
        # is instant), which must not block the event loop / stall the live UI.
        await asyncio.to_thread(self.save_paper_file, paper_id, draft.assembled_body)

        paper_path = ""
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is not None:
            paper_path = str(papers_dir / paper_id / f"{paper_id}.md")
        self._engine._display.paper_saved(paper_id, paper_path=paper_path)
        self._engine.emit_event(
            "paper.assembled",
            {
                "paper_id": paper_id,
                "title": draft.title or "",
                "word_count": len(draft.assembled_body.split()),
                "n_figures": len(self._engine.state.execution_figures),
                "n_sections": len(draft.sections),
            },
        )
        return draft

    async def run_section_drafting(self, draft: PaperDraft) -> None:
        """Round 1 of writing: each agent drafts their assigned sections.

        Args:
            draft: PaperDraft to populate with section drafts.
        """
        self._engine._literature.search_count_this_round = 0
        checkpoint_context = ""
        if self._engine.state.checkpoint:
            checkpoint_context = self._engine.state.checkpoint.to_context_string() + "\n\n"

        # Check mode-specific writing overrides first
        mode_writing = _MODE_WRITING_OVERRIDES.get(self._engine.state.mode, {})
        template = mode_writing.get(
            "section_drafting",
            _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["section_drafting"],
        )

        # Get section assignments from profile or fallback
        assignments = self._get_section_assignments()

        for agent_id, agent in self._engine.state.agents.items():
            role = agent.skill_profile
            assigned = assignments.get(role)
            if not assigned:
                continue  # Roles without section assignments skip this round

            section_list = ", ".join(s.replace("_", " ").title() for s in assigned)
            prompt = template.format(
                seed_prompt=self._engine.state.seed_prompt,
                checkpoint_context=checkpoint_context,
                assigned_sections=section_list,
            )

            # Inject the corpus citation allow-list (cite ONLY [N]); no-op when flag off.
            if self._citation_allowlist_block:
                prompt += self._citation_allowlist_block

            # Inject execution fact sheet so writers know which experiments succeeded
            fact_sheet = self._build_execution_fact_sheet()
            if fact_sheet:
                prompt += fact_sheet
                # Also inject compact reference values for numerical consistency
                ref_values = self._extract_reference_values(fact_sheet)
                if ref_values:
                    prompt += ref_values

            # Inject forbidden claims block to prevent confabulation
            forbidden_block = self._build_forbidden_claims_block()
            if forbidden_block:
                prompt += forbidden_block

            # Inject data origin statement — especially critical for Methods
            data_origin = self._build_data_origin_statement()
            if data_origin:
                prompt += data_origin

            # Inject execution context for results and methods sections
            # (filtered to successful experiments only)
            results_like = {"results"}
            methods_like = {"methods"}
            filtered_exec_ctx = self._filter_successful_execution_context()
            if filtered_exec_ctx and (results_like & set(assigned) or methods_like & set(assigned)):
                exec_label = (
                    "computational results"
                    if results_like & set(assigned)
                    else "computational methods"
                )
                prompt += (
                    f"\n\n## Computational Experiment Results\n"
                    f"The following {exec_label} were produced during the "
                    f"EXECUTION phase. You MUST thoroughly discuss these results "
                    f"in your section. Include specific numbers, statistical "
                    f"measures, and quantitative comparisons. Do NOT merely "
                    f"summarize — analyze and interpret the data:\n\n"
                    f"{filtered_exec_ctx}"
                )

            # Inject execution caveats for ALL section writers — every part of
            # the paper must be consistent with known limitations
            if self._engine.state.execution_caveats:
                prompt += (
                    "\n\n## MANDATORY Execution Caveats\n"
                    "The following limitations were identified during the EXECUTION phase. "
                    "These are NOT optional — the paper MUST NOT make claims that "
                    "contradict or ignore these caveats. If data is synthetic, say so "
                    "explicitly. If models failed, do not present fallback results as "
                    "if they were the intended analysis.\n"
                    + "\n".join(f"- **{c}**" for c in self._engine.state.execution_caveats)
                )

            # Inject available figures so section writers can reference them
            if self._engine.state.execution_figures:
                fig_lines = ["\n\n## Available Figures"]
                fig_lines.append(
                    "The following figures were produced by experiments. "
                    "Reference them in your section text where relevant "
                    "(e.g., 'as shown in Figure 1'):"
                )
                for i, (exp_name, fpath) in enumerate(self._engine.state.execution_figures, 1):
                    dest_name = self.figure_dest_name(exp_name, fpath)
                    cap = _humanize_figure_name(exp_name)
                    alt = f"Figure {i}: {cap}" if cap else f"Figure {i}"
                    fig_lines.append(f"- Figure {i} ({exp_name}): `![{alt}](figures/{dest_name})`")
                fig_lines.append(
                    f"\nYou have exactly {len(self._engine.state.execution_figures)} figures. "
                    "Do NOT reference any Figure number beyond this count."
                )
                prompt += "\n".join(fig_lines)
            elif (
                self._engine._config.orchestrator.enable_conceptual_figures
                and self._engine._config.sandbox.enabled
            ):
                prompt += (
                    "\n\n## Conceptual Figures\n"
                    "No experiments were run, but you MAY reference up to "
                    f"{self._engine._config.orchestrator.max_conceptual_figures} "
                    "conceptual figures (e.g., 'as shown in Figure 1') for "
                    "diagrams that would help readers — flow charts, taxonomies, "
                    "annotated curves, concept maps, etc. These will be "
                    "auto-generated as matplotlib schematics after assembly."
                )
            else:
                prompt += (
                    "\n\n## NO FIGURES AVAILABLE\n"
                    "No figure files were produced by the experiments. "
                    "Do NOT reference any Figure numbers in your text. "
                    "Describe results in text only. You may mention that "
                    "visualization would be informative for future work."
                )

            # Inject POST_EXECUTION team assessment — the research team's
            # critical evaluation of what the results actually show
            if self._engine.state.post_execution_summary:
                prompt += "\n\n" + self._engine.state.post_execution_summary

            # Phase C: announce the sections this agent is about to draft so the
            # live paper shows them as "writing…" placeholders before text lands.
            for section_name in assigned:
                self._engine._display.draft_section(
                    section_name,
                    section_name.replace("_", " ").title(),
                    "",
                    agent_id,
                    "drafting",
                )

            try:
                response = await agent.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent_id, thread_id=self._engine.state.thread_id
                )
                self._engine._display.agent_error(agent_id, e)
                continue

            # Parse sections from response
            parsed = parse_sections_from_markdown(response.content)
            for section_name in assigned:
                content = parsed.get(section_name, "")
                if not content:
                    # Try title-cased header
                    content = parsed.get(section_name.title().lower(), "")
                if content:
                    draft.add_section(
                        SectionDraft(section=section_name, content=content, author=agent_id)
                    )
                    self._engine._display.draft_section(
                        section_name,
                        section_name.replace("_", " ").title(),
                        content,
                        agent_id,
                        "drafted",
                    )
                    self._engine.emit_event(
                        "section.drafted",
                        {"section": section_name, "word_count": len(content.split())},
                        agent=agent_id,
                    )

            self._engine._log_agent_response(
                agent_id, response, ResearchPhase.WRITING, "section_draft"
            )
            await self._engine._literature.process_search_requests(
                agent_id, response.content, ResearchPhase.WRITING
            )
            await self._engine._literature.process_literature_actions(
                agent_id, response.content, ResearchPhase.WRITING
            )

    def _fallback_assembly(self, draft: PaperDraft) -> str:
        """Emergency fallback: concatenate section drafts when assembly API fails.

        Args:
            draft: PaperDraft with section drafts.

        Returns:
            Concatenated section content.
        """
        parts = []
        for section_name in draft.section_order:
            if section_name in draft.sections:
                parts.append(draft.sections[section_name].content)
        return "\n\n".join(parts)

    def _validate_figure_references(self, body: str) -> list[str]:
        """Check that figures referenced in text have corresponding files.

        Returns list of warning strings.
        """
        warnings: list[str] = []

        # Find all Figure N references in text
        fig_refs = set(int(m.group(1)) for m in re.finditer(r"\b(?:Figure|Fig\.?)\s+(\d+)\b", body))

        # How many actual figure files do we have?
        actual_count = (
            len(self._engine.state.execution_figures) if self._engine.state.execution_figures else 0
        )

        if fig_refs and actual_count == 0:
            warnings.append(
                f"Paper references {len(fig_refs)} figures "
                f"(Figure {', '.join(str(n) for n in sorted(fig_refs))}) "
                f"but NO figure files were produced by experiments. "
                f"Remove figure references or describe them as planned/conceptual."
            )
        elif fig_refs:
            missing = {n for n in fig_refs if n > actual_count}
            if missing:
                warnings.append(
                    f"Paper references Figure(s) "
                    f"{', '.join(str(n) for n in sorted(missing))} "
                    f"but only {actual_count} figure file(s) exist."
                )

        return warnings

    async def run_assembly(self, draft: PaperDraft) -> str:
        """Round 2 of writing: writer assembles all sections into a coherent paper.

        Args:
            draft: PaperDraft with section drafts.

        Returns:
            Assembled paper body as markdown.
        """
        # Find writer agent
        writer_agent = self._engine._find_agent_by_role("writer")
        if writer_agent is None:
            # Fallback: render from sections directly
            self._engine._display.writing_no_writer()
            return draft.to_markdown()

        checkpoint_context = ""
        if self._engine.state.checkpoint:
            checkpoint_context = self._engine.state.checkpoint.to_context_string() + "\n\n"

        # Build section drafts text
        section_drafts_text = ""
        section_order = self._get_section_order()
        for section_name in section_order:
            if section_name in draft.sections:
                sd = draft.sections[section_name]
                heading = section_name.replace("_", " ").title()
                section_drafts_text += f"## {heading} (by {sd.author})\n\n{sd.content}\n\n"

        mode_writing = _MODE_WRITING_OVERRIDES.get(self._engine.state.mode, {})
        template = mode_writing.get(
            "assembly",
            _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["assembly"],
        )
        prompt = template.format(
            seed_prompt=self._engine.state.seed_prompt,
            checkpoint_context=checkpoint_context,
            section_drafts=section_drafts_text,
        )

        # Inject the corpus citation allow-list (cite ONLY [N]); no-op when flag off.
        if self._citation_allowlist_block:
            prompt += self._citation_allowlist_block

        # Inject execution fact sheet into assembly
        fact_sheet = self._build_execution_fact_sheet()
        if fact_sheet:
            prompt += fact_sheet

        # Inject forbidden claims block into assembly
        forbidden_block = self._build_forbidden_claims_block()
        if forbidden_block:
            prompt += forbidden_block

        # Inject data origin statement into assembly
        data_origin = self._build_data_origin_statement()
        if data_origin:
            prompt += data_origin

        # Detect and inject numerical discrepancies across section drafts
        claims = self._extract_numerical_claims(section_drafts_text)
        discrepancy_report = self._find_numerical_discrepancies(claims)
        if discrepancy_report:
            prompt += discrepancy_report

        # Inject caveats into assembly so the assembler doesn't overclaim
        if self._engine.state.execution_caveats:
            prompt += (
                "\n\n## MANDATORY Execution Caveats\n"
                "When assembling the paper, ensure the title, abstract, and conclusions "
                "do NOT overclaim. These limitations apply:\n"
                + "\n".join(f"- **{c}**" for c in self._engine.state.execution_caveats)
            )

        # Add figure references if experiments produced output files
        if self._engine.state.execution_figures:
            fig_lines = ["\n\n## Figures from Computational Experiments"]
            fig_lines.append("Include these figures in the paper using the markdown syntax shown:")
            for i, (exp_name, fpath) in enumerate(self._engine.state.execution_figures, 1):
                dest_name = self.figure_dest_name(exp_name, fpath)
                cap = _humanize_figure_name(exp_name)
                alt = f"Figure {i}: {cap}" if cap else f"Figure {i}"
                fig_lines.append(f"- Figure {i} ({exp_name}): `![{alt}](figures/{dest_name})`")
            fig_lines.append(
                f"\nIMPORTANT: Only {len(self._engine.state.execution_figures)} figures exist. "
                "Do NOT reference Figure numbers beyond this count. "
                "Remove any references to non-existent figures from the section drafts."
            )
            prompt += "\n".join(fig_lines)
        elif (
            self._engine._config.orchestrator.enable_conceptual_figures
            and self._engine._config.sandbox.enabled
        ):
            prompt += (
                "\n\n## Conceptual Figures\n"
                "Preserve any 'Figure N' references from the section drafts. "
                "These conceptual diagrams (flow charts, taxonomies, annotated "
                "curves) will be auto-generated after assembly. Do NOT remove "
                "figure references or add `![Figure N](...)` image tags — the "
                "system will handle figure generation and embedding."
            )
        else:
            # No figures were produced — warn the writer
            prompt += (
                "\n\n## WARNING: No Figures Available\n"
                "The experiments did NOT produce any figures (.png/.pdf files). "
                "Do NOT reference 'Figure 1', 'Figure 2', etc. in the paper text "
                "unless you include the actual generation code. If you reference "
                "a figure, you must describe the data it would show and note that "
                "the visualization was not generated."
            )

        _assembly_max_retries = 1
        assembled_text = None
        for attempt in range(_assembly_max_retries + 1):
            try:
                response = await writer_agent.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
                self._engine._log_agent_response(
                    writer_agent.agent_id, response, ResearchPhase.WRITING, "assembly"
                )
                assembled_text = strip_agent_scaffolding(response.content)
                break
            except Exception as e:
                self._engine._logger.log_error(
                    e,
                    agent_id=writer_agent.agent_id,
                    thread_id=self._engine.state.thread_id,
                )
                if attempt < _assembly_max_retries:
                    self._engine._display.writing_assembly_retry(attempt + 1, e)
                    await asyncio.sleep(5)
                else:
                    self._engine._display.writing_assembly_error(e)
                    assembled_text = self._fallback_assembly(draft)

        return assembled_text or draft.to_markdown()

    @staticmethod
    def _extract_figure_references(body: str) -> list[tuple[int, str]]:
        """Extract Figure N references from paper text with surrounding context.

        Args:
            body: Paper markdown body.

        Returns:
            Sorted, deduplicated list of (figure_number, context_snippet) tuples.
        """
        seen: dict[int, str] = {}
        for m in re.finditer(r"\b(?:Figure|Fig\.?)\s+(\d+)\b", body):
            fig_num = int(m.group(1))
            if fig_num in seen:
                continue
            # Extract surrounding paragraph as context (capped at 500 chars)
            start = max(0, m.start() - 200)
            end = min(len(body), m.end() + 300)
            context = body[start:end].strip()
            seen[fig_num] = context
        return sorted(seen.items())

    @staticmethod
    def _strip_orphan_figure_references(body: str) -> str:
        """Remove orphan figure image tags that have no corresponding files.

        Removes ``![Figure N](figures/...)`` markdown image tags. Preserves
        textual "Figure N" mentions in prose.

        Args:
            body: Paper markdown body.

        Returns:
            Body with orphan image tags removed and empty lines cleaned up.
        """
        # Remove ![Figure N](figures/...) image tags
        body = re.sub(
            r"!\[(?:Figure|Fig\.?)\s*\d+[^\]]*\]\(figures/[^)]+\)\s*\n?",
            "",
            body,
        )
        # Clean up resulting double+ blank lines
        body = re.sub(r"\n{3,}", "\n\n", body)
        return body

    async def generate_conceptual_figures(self, assembled_body: str) -> str:
        """Generate matplotlib-based conceptual figures for Figure N references.

        Called after paper assembly when EXECUTION was skipped. Uses the writer
        agent to produce matplotlib code, executes it in the sandbox, and
        collects the output PNGs.

        Args:
            assembled_body: The assembled paper markdown body.

        Returns:
            Updated body with figures embedded (or orphan refs stripped on failure).
        """
        engine = self._engine

        # Guard: already have execution figures
        if engine.state.execution_figures:
            return assembled_body

        # Guard: sandbox disabled or feature disabled
        if not engine._config.sandbox.enabled:
            return assembled_body
        if not engine._config.orchestrator.enable_conceptual_figures:
            return assembled_body

        # Guard: no writer agent
        writer_agent = engine._find_agent_by_role("writer")
        if writer_agent is None:
            return assembled_body

        # Guard: no figure references in paper
        figure_refs = self._extract_figure_references(assembled_body)
        if not figure_refs:
            return assembled_body

        max_figs = engine._config.orchestrator.max_conceptual_figures
        figure_refs = figure_refs[:max_figs]

        engine._display.conceptual_figures_start(len(figure_refs))

        # Set up workspace and executor (same pattern as ExperimentationHandler)
        from paradigm.sandbox.executor import CodeExecutor
        from paradigm.sandbox.models import ExecutionRequest

        workspace_dir = engine._config.storage.data_dir / "workspaces" / engine.state.thread_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        executor = CodeExecutor(
            config=engine._config.sandbox,
            logger=engine._logger,
            data_dir=engine._config.storage.data_dir,
            workspace_dir=workspace_dir,
        )

        generated_figures: list[tuple[str, Path]] = []
        try:
            for fig_num, context in figure_refs:
                engine._display.conceptual_figure_generating(fig_num)

                # Ask writer agent to generate matplotlib code
                prompt = _CONCEPTUAL_FIGURE_PROMPT.format(
                    figure_num=fig_num,
                    figure_context=context,
                )
                try:
                    response = await writer_agent.generate(
                        prompt, max_tokens=_CONCEPTUAL_FIGURE_MAX_TOKENS
                    )
                except Exception as e:
                    engine._display.conceptual_figure_error(fig_num, e)
                    continue

                # Extract python code block from response
                code_match = _CODE_BLOCK_RE.search(response.content)
                if code_match is None:
                    engine._display.conceptual_figure_no_code(fig_num)
                    continue

                code = code_match.group(1).strip()

                # Execute in sandbox
                try:
                    result = await asyncio.wait_for(
                        executor.execute(
                            ExecutionRequest(
                                code=code,
                                agent_id=writer_agent.agent_id,
                                thread_id=engine.state.thread_id,
                            )
                        ),
                        timeout=_CONCEPTUAL_FIGURE_TIMEOUT,
                    )
                except TimeoutError:
                    engine._display.conceptual_figure_failed(fig_num, "timeout")
                    continue
                except Exception as e:
                    engine._display.conceptual_figure_error(fig_num, e)
                    continue

                # Collect output PNG
                png_files = [f for f in (result.output_files or []) if f.filename.endswith(".png")]
                if not png_files:
                    engine._display.conceptual_figure_no_output(fig_num)
                    continue

                fig_path = Path(png_files[0].path)
                generated_figures.append((f"conceptual_fig_{fig_num}", fig_path))
                engine.state.successful_code.append((f"conceptual_fig_{fig_num}", code))
                engine._display.conceptual_figure_success(fig_num)

            # Post-loop: update engine state and embed figures
            if generated_figures:
                engine.state.execution_figures = generated_figures
                assembled_body = self.embed_figures_inline(assembled_body)
                engine._display.conceptual_figures_complete(len(generated_figures))
            else:
                # All attempts failed — strip orphan image refs to prevent editor deadlock
                assembled_body = self._strip_orphan_figure_references(assembled_body)
                engine._display.conceptual_figures_none()

        finally:
            await executor.cleanup()

        return assembled_body

    def embed_figures_inline(self, body: str) -> str:
        """Post-process paper markdown to embed figure image tags inline.

        The writer agent is asked to include ``![Figure N](figures/...)``
        tags, but may omit them or use the wrong filename.  This method
        scans the body for textual "Figure N" references and, when no
        corresponding image tag already exists nearby, inserts one after
        the paragraph that first references it.

        Args:
            body: Paper markdown body.

        Returns:
            Body with ``![Figure N](figures/...)`` tags embedded.
        """
        if not self._engine.state.execution_figures:
            return body

        # Build ordered mapping: figure number -> (destination filename, caption)
        fig_map: dict[int, tuple[str, str]] = {}
        for i, (exp_name, fpath) in enumerate(self._engine.state.execution_figures, 1):
            fig_map[i] = (self.figure_dest_name(exp_name, fpath), _humanize_figure_name(exp_name))

        # Regex to detect existing image tags like ![Figure 1](figures/...)
        existing_img_re = re.compile(r"!\[(?:Figure|Fig\.?)\s*(\d+)[^\]]*\]\(figures/[^)]+\)")

        # Which figures already have image tags?
        already_embedded: set[int] = set()
        for m in existing_img_re.finditer(body):
            already_embedded.add(int(m.group(1)))

        # For each figure not yet embedded, find its first textual reference
        # and insert the image tag after that paragraph.
        for fig_num, (dest_name, caption) in fig_map.items():
            if fig_num in already_embedded:
                continue

            # Pattern to match "Figure N" or "Fig. N" (not inside an image tag)
            ref_pattern = re.compile(rf"(?<!!)(?<!\[)\b(?:Figure|Fig\.?)\s*{fig_num}\b")

            match = ref_pattern.search(body)
            if match is None:
                # No textual reference — skip (don't force-append unreferenced figures)
                continue

            alt = f"Figure {fig_num}: {caption}" if caption else f"Figure {fig_num}"
            # Find the end of the paragraph containing the reference
            pos = match.end()
            # Look for the next blank line (paragraph boundary)
            next_blank = body.find("\n\n", pos)
            if next_blank == -1:
                # Reference is in the last paragraph
                body = body.rstrip() + f"\n\n![{alt}](figures/{dest_name})\n"
            else:
                # Insert after the blank line
                insert_pos = next_blank + 2  # after the \n\n
                tag = f"![{alt}](figures/{dest_name})\n\n"
                body = body[:insert_pos] + tag + body[insert_pos:]

        # Strip orphan image tags referencing figures beyond our count
        max_fig = len(fig_map)
        orphan_re = re.compile(r"\n*!\[(?:Figure|Fig\.?)\s*(\d+)[^\]]*\]\(figures/[^)]+\)\n*")

        def _strip_orphan(m: re.Match) -> str:
            num = int(m.group(1))
            return "" if num > max_fig else m.group(0)

        body = orphan_re.sub(_strip_orphan, body)

        return body

    def save_paper_file(self, paper_id: str, body: str) -> None:
        """Write paper markdown to the papers directory.

        Always uses subdirectory layout: papers/paper_id/paper_id.md
        Figures (if any) go into papers/paper_id/figures/

        Args:
            paper_id: Paper identifier (used as filename).
            body: Paper markdown content.
        """
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return

        paper_dir = papers_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / f"{paper_id}.md"
        # Ensure figure image tags are embedded before writing
        body = self.embed_figures_inline(body)
        # Convert any remaining Unicode math to LaTeX
        body = sanitize_unicode_math(body)
        # Populate figures/ FIRST, then drop image tags pointing at a figure file
        # that isn't actually there (e.g. a writer-invented "graphical abstract").
        # A missing image otherwise leaves an empty float and aborts PDF compilation.
        if self._engine.state.execution_figures:
            self.copy_figures_to_paper_dir(paper_id)
        body = _strip_missing_figure_refs(body, paper_dir)
        path.write_text(body)

        # Optional journal-ready LaTeX/PDF output (Phase 2, default-off toggle).
        journal_cfg = self._engine._config.journal
        if journal_cfg.enable_latex_output:
            try:
                from paradigm.journal.latex import write_paper_latex

                result = write_paper_latex(
                    paper_dir,
                    paper_id,
                    body,
                    journal=journal_cfg.latex_journal,
                    compile_to_pdf=journal_cfg.compile_pdf,
                )
                msg = f"LaTeX output written: {result.get('tex_path')}"
                if journal_cfg.compile_pdf:
                    msg += f" | PDF: {result.get('pdf_message')}"
                self._engine._display.info(msg)
            except Exception as e:  # noqa: BLE001 — an output format must never break the cycle
                self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)

    async def _generate_and_save_digest(self, paper_id: str, body: str) -> None:
        """Generate a plain-language 'Digest' (layman summary) from the finished paper
        and write it to ``papers/<id>/<id>-digest.md``.

        Best-effort and config-gated (``journal.enable_digest``): a summary artifact must
        never break or block a cycle. Grounded in the paper body, so it cannot introduce
        claims the paper does not make.
        """
        if not self._engine._config.journal.enable_digest:
            return
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return
        writer = self._engine._find_agent_by_role("writer")
        if writer is None:
            return
        try:
            prompt = DIGEST_PROMPT.format(paper_body=body[:DIGEST_CONTEXT_LIMIT])
            response = await writer.generate(prompt, max_tokens=DIGEST_MAX_TOKENS)
            self._engine._log_agent_response(
                writer.agent_id, response, ResearchPhase.WRITING, "digest"
            )
            digest = strip_agent_scaffolding(response.content).strip()
            if not digest:
                return
            paper_dir = papers_dir / paper_id
            paper_dir.mkdir(parents=True, exist_ok=True)
            (paper_dir / f"{paper_id}-digest.md").write_text(digest)
            self._engine._display.info(f"Digest written: {paper_id}-digest.md")
            self._engine.emit_event(
                "paper.digest",
                {"paper_id": paper_id, "word_count": len(digest.split())},
            )
        except Exception as e:  # noqa: BLE001 — a summary artifact must never break the cycle
            self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)

    async def finalize_digest(self, paper_id: str) -> None:
        """Generate the Digest from the FINAL paper body (read from the DB) at cycle
        finalization — AFTER all review/revision — so it summarizes the version the
        reader actually sees, not the pre-review draft.
        """
        # Same contract as _generate_and_save_digest: a summary artifact must NEVER
        # break cycle finalization — guard the DB read too (e.g. a locked SQLite here
        # would otherwise abort run_cycle after publication).
        try:
            paper = self._engine._db.get_paper(paper_id)
        except Exception as e:
            self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
            return
        body = (paper or {}).get("body") or ""
        if body:
            await self._generate_and_save_digest(paper_id, body)

    def copy_figures_to_paper_dir(self, paper_id: str) -> None:
        """Copy execution output figures to the paper's figures/ directory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return

        figures_dir = papers_dir / paper_id / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)

        for exp_name, src_path in self._engine.state.execution_figures:
            if not src_path.exists():
                self._engine._logger.log_error(
                    FileNotFoundError(f"Figure from '{exp_name}' not found: {src_path}"),
                    thread_id=self._engine.state.thread_id,
                )
                continue
            dest_name = self.figure_dest_name(exp_name, src_path)
            dest_path = figures_dir / dest_name
            shutil.copy2(src_path, dest_path)
            self._engine._display.figure_copied(dest_path.name)

    @staticmethod
    def figure_dest_name(exp_name: str, src_path: Path) -> str:
        """Compute the destination filename for a figure.

        This must match the naming logic in ``copy_figures_to_paper_dir``
        so that the markdown image tags point to the correct files.

        Args:
            exp_name: Experiment name.
            src_path: Original source path of the figure.

        Returns:
            Sanitised destination filename.
        """
        safe_name = re.sub(r"[^\w\-.]", "_", exp_name)
        return f"{safe_name}_{src_path.name}"
