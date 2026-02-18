"""Writing-phase handler for the orchestration engine."""

from __future__ import annotations

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
from paradigm.orchestrator.constants import (
    _MIN_PAPER_LENGTH,
    _PHASE_INSTRUCTIONS,
    _WRITING_MAX_TOKENS,
)
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


class WritingHandler:
    """Encapsulates writing-phase logic extracted from OrchestrationEngine."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    def _build_execution_fact_sheet(self) -> str:
        """Build an anti-confabulation execution fact sheet for writing prompts.

        Each experiment gets a structured block showing its actual output
        (for successes) or failure reason (for failures), with strict rules
        that prevent writers from fabricating results.

        Returns:
            Formatted fact sheet string, or empty string if no experiments ran.
        """
        metadata = self._engine._experiment_metadata
        if not metadata:
            return ""

        lines = [
            "\n\n## Execution Fact Sheet",
            "### CRITICAL ANTI-CONFABULATION RULE",
            "Every number you write MUST come from an Actual Output block below. "
            "If an experiment FAILED, you MUST NOT describe it as producing results.",
            "",
        ]
        for entry in metadata:
            name = entry.get("name", "unnamed")
            status = entry.get("status", "unknown")
            has_figs = "Yes" if entry.get("has_figures") else "No"

            lines.append(f"#### Experiment: {name}")
            lines.append(f"**Status:** {status} | **Figures:** {has_figs}")

            if status == "success":
                stdout_full = str(entry.get("stdout_full", entry.get("stdout_preview", "")))
                lines.append(f"**Actual Output:**\n```\n{stdout_full}\n```")
                lines.append("Cite ONLY these numbers. Do NOT invent additional values.")
            else:
                failure_reason = entry.get("failure_reason", "Unknown error")
                lines.append(f"**Failure Reason:** {failure_reason}")
                lines.append(
                    "Do NOT describe this experiment as having produced results. "
                    "Do NOT fabricate numbers for this experiment."
                )
            lines.append("")

        lines.append(
            "**If you write a number not found in any Actual Output block above, "
            "you are confabulating. Cross-check every quantitative claim.**"
        )
        return "\n".join(lines)

    def _extract_forbidden_claims(self) -> list[str]:
        """Extract FORBIDDEN claims from POST_EXECUTION synthesis and experiment metadata.

        Collects explicit FORBIDDEN entries from the synthesis text and
        auto-generates entries for failed experiments.

        Returns:
            List of forbidden claim strings.
        """
        forbidden: list[str] = []

        # From POST_EXECUTION synthesis
        synthesis = self._engine._phase_synthesis.get(str(ResearchPhase.POST_EXECUTION), "")
        for line in synthesis.split("\n"):
            line = line.strip()
            if line.upper().startswith("- FORBIDDEN:"):
                claim = line[len("- FORBIDDEN:") :].strip()
                if claim:
                    forbidden.append(claim)

        # Auto-generate from failed experiments
        for entry in self._engine._experiment_metadata:
            if entry.get("status") != "success":
                name = entry.get("name", "unnamed")
                reason = str(entry.get("failure_reason", "unknown error"))[:100]
                forbidden.append(
                    f"Do NOT describe experiment '{name}' as having produced results "
                    f"(it FAILED: {reason})"
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

    def _check_forbidden_claims_violations(self, paper_text: str) -> list[str]:
        """Check assembled paper for violations of forbidden claims.

        Uses keyword matching to flag potential violations where a failed
        experiment name appears near success-indicating words.

        Args:
            paper_text: The assembled paper markdown text.

        Returns:
            List of warning strings describing potential violations.
        """
        if not self._engine._experiment_metadata:
            return []

        violations: list[str] = []
        paper_lower = paper_text.lower()

        # Check each failed experiment — is it described as producing results?
        for entry in self._engine._experiment_metadata:
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
        if profile is not None and profile.document_template.sections:
            return section_assignments_from_template(profile.document_template.sections)
        # Fallback to hardcoded science assignments
        return {role: [s.value for s in secs] for role, secs in SECTION_ASSIGNMENTS.items()}

    def _get_section_order(self) -> list[str]:
        """Get ordered list of section names from profile or fallback.

        Returns:
            List of section name strings in document order.
        """
        profile = self._engine._profile
        if profile is not None and profile.document_template.sections:
            return [s.name for s in profile.document_template.sections]
        return [s.value for s in PaperSection]

    async def run_writing_phase(self) -> PaperDraft | None:
        """Run the WRITING phase: section drafting, assembly, optional refinement.

        Returns:
            PaperDraft with assembled paper, or None if writing failed
            (e.g. all agents errored and the paper is empty/too short).
        """
        draft = PaperDraft(section_order=self._get_section_order())

        # Round 1: Section Drafting — each agent drafts their assigned sections
        self._engine._display.writing_section_drafting()
        await self.run_section_drafting(draft)

        # Round 2: Assembly — writer combines all sections
        self._engine._display.writing_assembly()
        assembled_body = await self.run_assembly(draft)

        # Post-process: ensure figure image tags are embedded inline
        assembled_body = self.embed_figures_inline(assembled_body)
        draft.assembled_body = assembled_body

        # Post-assembly: check for forbidden claims violations
        violations = self._check_forbidden_claims_violations(assembled_body)
        if violations:
            self._engine._forbidden_claims_violations = violations
        else:
            self._engine._forbidden_claims_violations = []

        # Citation grounding (non-fatal on failure)
        if self._engine._config.citation.enable_citation_grounding:
            try:
                draft = await self._engine._citation_handler.run_citation_grounding(draft)
            except Exception as e:
                self._engine._logger.log_error(e, thread_id=self._engine._thread_id)
                self._engine._display.citation_grounding_error(e)

        # Validate paper length — if all agents failed, the draft is empty
        if len(draft.assembled_body) < _MIN_PAPER_LENGTH:
            self._engine._display.paper_too_short(len(draft.assembled_body), _MIN_PAPER_LENGTH)
            self._engine._logger.log_error(
                ValueError(
                    f"Writing phase produced insufficient content "
                    f"({len(draft.assembled_body)} chars < {_MIN_PAPER_LENGTH})"
                ),
                thread_id=self._engine._thread_id,
            )
            self._engine._db.update_thread(self._engine._thread_id, status="writing_failed")
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

        authors = list(self._engine._agents.keys())
        self._engine._db.create_paper(
            paper_id=paper_id,
            title=draft.title or self._engine._seed_prompt[:200],
            abstract=abstract,
            authors=authors,
            body=draft.assembled_body,
            status="draft",
        )
        self._engine._db.update_thread(self._engine._thread_id, current_draft_id=paper_id)

        # Write markdown file to papers directory
        self.save_paper_file(paper_id, draft.assembled_body)

        paper_path = ""
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is not None:
            paper_path = str(papers_dir / paper_id / f"{paper_id}.md")
        self._engine._display.paper_saved(paper_id, paper_path=paper_path)
        return draft

    async def run_section_drafting(self, draft: PaperDraft) -> None:
        """Round 1 of writing: each agent drafts their assigned sections.

        Args:
            draft: PaperDraft to populate with section drafts.
        """
        self._engine._literature.search_count_this_round = 0
        checkpoint_context = ""
        if self._engine._checkpoint:
            checkpoint_context = self._engine._checkpoint.to_context_string() + "\n\n"

        template = _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["section_drafting"]

        # Get section assignments from profile or fallback
        assignments = self._get_section_assignments()

        for agent_id, agent in self._engine._agents.items():
            role = agent.skill_profile
            assigned = assignments.get(role)
            if not assigned:
                continue  # Roles without section assignments skip this round

            section_list = ", ".join(s.replace("_", " ").title() for s in assigned)
            prompt = template.format(
                seed_prompt=self._engine._seed_prompt,
                checkpoint_context=checkpoint_context,
                assigned_sections=section_list,
            )

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

            # Inject execution context for results and methods sections
            results_like = {"results"}
            methods_like = {"methods"}
            if self._engine._execution_context and (
                results_like & set(assigned) or methods_like & set(assigned)
            ):
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
                    f"{self._engine._execution_context}"
                )

            # Inject execution caveats for ALL section writers — every part of
            # the paper must be consistent with known limitations
            if self._engine._execution_caveats:
                prompt += (
                    "\n\n## MANDATORY Execution Caveats\n"
                    "The following limitations were identified during the EXECUTION phase. "
                    "These are NOT optional — the paper MUST NOT make claims that "
                    "contradict or ignore these caveats. If data is synthetic, say so "
                    "explicitly. If models failed, do not present fallback results as "
                    "if they were the intended analysis.\n"
                    + "\n".join(f"- **{c}**" for c in self._engine._execution_caveats)
                )

            # Inject available figures so section writers can reference them
            if self._engine._execution_figures:
                fig_lines = ["\n\n## Available Figures"]
                fig_lines.append(
                    "The following figures were produced by experiments. "
                    "Reference them in your section text where relevant "
                    "(e.g., 'as shown in Figure 1'):"
                )
                for i, (exp_name, fpath) in enumerate(self._engine._execution_figures, 1):
                    dest_name = self.figure_dest_name(exp_name, fpath)
                    fig_lines.append(
                        f"- Figure {i} ({exp_name}): `![Figure {i}](figures/{dest_name})`"
                    )
                prompt += "\n".join(fig_lines)

            # Inject POST_EXECUTION team assessment — the research team's
            # critical evaluation of what the results actually show
            if self._engine._post_execution_summary:
                prompt += "\n\n" + self._engine._post_execution_summary

            try:
                response = await agent.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent_id, thread_id=self._engine._thread_id
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

            self._engine._log_agent_response(
                agent_id, response, ResearchPhase.WRITING, "section_draft"
            )
            await self._engine._literature.process_search_requests(
                agent_id, response.content, ResearchPhase.WRITING
            )
            await self._engine._literature.process_literature_actions(
                agent_id, response.content, ResearchPhase.WRITING
            )

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
        if self._engine._checkpoint:
            checkpoint_context = self._engine._checkpoint.to_context_string() + "\n\n"

        # Build section drafts text
        section_drafts_text = ""
        section_order = self._get_section_order()
        for section_name in section_order:
            if section_name in draft.sections:
                sd = draft.sections[section_name]
                heading = section_name.replace("_", " ").title()
                section_drafts_text += f"## {heading} (by {sd.author})\n\n{sd.content}\n\n"

        template = _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["assembly"]
        prompt = template.format(
            seed_prompt=self._engine._seed_prompt,
            checkpoint_context=checkpoint_context,
            section_drafts=section_drafts_text,
        )

        # Inject execution fact sheet into assembly
        fact_sheet = self._build_execution_fact_sheet()
        if fact_sheet:
            prompt += fact_sheet

        # Inject forbidden claims block into assembly
        forbidden_block = self._build_forbidden_claims_block()
        if forbidden_block:
            prompt += forbidden_block

        # Detect and inject numerical discrepancies across section drafts
        claims = self._extract_numerical_claims(section_drafts_text)
        discrepancy_report = self._find_numerical_discrepancies(claims)
        if discrepancy_report:
            prompt += discrepancy_report

        # Inject caveats into assembly so the assembler doesn't overclaim
        if self._engine._execution_caveats:
            prompt += (
                "\n\n## MANDATORY Execution Caveats\n"
                "When assembling the paper, ensure the title, abstract, and conclusions "
                "do NOT overclaim. These limitations apply:\n"
                + "\n".join(f"- **{c}**" for c in self._engine._execution_caveats)
            )

        # Add figure references if experiments produced output files
        if self._engine._execution_figures:
            fig_lines = ["\n\n## Figures from Computational Experiments"]
            fig_lines.append("Include these figures in the paper using the markdown syntax shown:")
            for i, (exp_name, fpath) in enumerate(self._engine._execution_figures, 1):
                dest_name = self.figure_dest_name(exp_name, fpath)
                fig_lines.append(f"- Figure {i} ({exp_name}): `![Figure {i}](figures/{dest_name})`")
            prompt += "\n".join(fig_lines)
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

        try:
            response = await writer_agent.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            self._engine._log_agent_response(
                writer_agent.agent_id, response, ResearchPhase.WRITING, "assembly"
            )
            return strip_agent_scaffolding(response.content)
        except Exception as e:
            self._engine._logger.log_error(
                e, agent_id=writer_agent.agent_id, thread_id=self._engine._thread_id
            )
            self._engine._display.writing_assembly_error(e)
            return draft.to_markdown()

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
        if not self._engine._execution_figures:
            return body

        # Build ordered mapping: figure number -> destination filename
        fig_map: dict[int, str] = {}
        for i, (exp_name, fpath) in enumerate(self._engine._execution_figures, 1):
            fig_map[i] = self.figure_dest_name(exp_name, fpath)

        # Regex to detect existing image tags like ![Figure 1](figures/...)
        existing_img_re = re.compile(r"!\[(?:Figure|Fig\.?)\s*(\d+)[^\]]*\]\(figures/[^)]+\)")

        # Which figures already have image tags?
        already_embedded: set[int] = set()
        for m in existing_img_re.finditer(body):
            already_embedded.add(int(m.group(1)))

        # For each figure not yet embedded, find its first textual reference
        # and insert the image tag after that paragraph.
        for fig_num, dest_name in fig_map.items():
            if fig_num in already_embedded:
                continue

            # Pattern to match "Figure N" or "Fig. N" (not inside an image tag)
            ref_pattern = re.compile(rf"(?<!!)(?<!\[)\b(?:Figure|Fig\.?)\s*{fig_num}\b")

            match = ref_pattern.search(body)
            if match is None:
                # No textual reference — append at end of body
                body = body.rstrip() + f"\n\n![Figure {fig_num}](figures/{dest_name})\n"
                continue

            # Find the end of the paragraph containing the reference
            pos = match.end()
            # Look for the next blank line (paragraph boundary)
            next_blank = body.find("\n\n", pos)
            if next_blank == -1:
                # Reference is in the last paragraph
                body = body.rstrip() + f"\n\n![Figure {fig_num}](figures/{dest_name})\n"
            else:
                # Insert after the blank line
                insert_pos = next_blank + 2  # after the \n\n
                tag = f"![Figure {fig_num}](figures/{dest_name})\n\n"
                body = body[:insert_pos] + tag + body[insert_pos:]

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
        path.write_text(body)
        if self._engine._execution_figures:
            self.copy_figures_to_paper_dir(paper_id)

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

        for exp_name, src_path in self._engine._execution_figures:
            if not src_path.exists():
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
