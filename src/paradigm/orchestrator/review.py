"""Review and peer-review handler for the orchestration engine."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from paradigm.journal.paper import (
    PaperDraft,
    parse_review_feedback,
    parse_sections_from_markdown,
    sanitize_unicode_math,
    strip_agent_scaffolding,
)
from paradigm.journal.publication import reject_paper
from paradigm.journal.review import (
    PeerReview,
    encode_figures_for_review,
    parse_peer_review,
    score_categories_from_criteria,
    synthesize_decision,
)
from paradigm.orchestrator.constants import (
    _FIGURE_REVIEW_PROMPT,
    _MIN_PAPER_LENGTH,
    _PAPER_CONTEXT_LIMIT,
    _PEER_REVIEW_METADATA_LIMIT,
    _PHASE_INSTRUCTIONS,
    _REVIEW_MAX_TOKENS,
    _WRITING_MAX_TOKENS,
)
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


_INTERNAL_REVIEW_MAX_RETRIES = 2

# If the editor's required-change count fails to decrease for this many consecutive
# revise iterations, the writer isn't converging — stop early instead of burning the
# remaining rounds on a paper that won't reach "accept".
_REVIEW_STALL_LIMIT = 2

# Injected into the internal-editor and peer-review prompts when a cycle produced no
# experimental results (no figures, no successful code). The default review checklists
# assume an experimental paper and demand data figures + quantitative evidence; for a
# literature-synthesis / theoretical paper that bar is unmeetable, which drove the
# `revision_exhausted` deaths observed on the VM. This re-frames the bar to scholarship
# and citation quality without lowering rigor.
_LITERATURE_PAPER_REVIEW_DIRECTIVE = (
    "\n\n## Paper Type: Literature / Theoretical Contribution\n"
    "This research cycle did NOT run experiments — the paper has no original "
    "experimental data, computed quantitative results, or data figures, and is not "
    "expected to. It is a literature-synthesis or theoretical contribution. Review it "
    "on that basis:\n"
    "- **Do NOT require** experimental figures, original datasets, computed statistics, "
    "or quantitative results the cycle did not produce. Their absence is NOT a defect, "
    "NOT a required change, and NOT grounds for a lower score.\n"
    "- **Claim–evidence alignment** here means each major claim is grounded in CITED "
    "LITERATURE and sound logical/theoretical argument — not original numbers. Judge the "
    "relevance, accuracy, and sufficiency of the citations and reasoning.\n"
    "- **Anti-confabulation / execution-fact-sheet checks are N/A** — there is no "
    "experiment output to cross-reference, so do not penalize its absence.\n"
    "- A **conceptual figure or schematic (or no figure) is acceptable**; only flag a "
    "figure the text references but that does not exist.\n"
    "Hold the paper to a high standard of scholarship, synthesis, and clarity — just not "
    "to an experimental-results standard it was never meant to meet."
)


class ReviewHandler:
    """Handles internal review, submission, peer review, and revision phases."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine
        self.review_log: list[dict[str, Any]] = []

    def reset_cycle(self) -> None:
        """Reset review state for a new cycle."""
        self.review_log = []

    def _is_literature_only(self) -> bool:
        """True when this cycle produced no experimental results to defend.

        A literature-synthesis / theoretical paper legitimately has no original
        data figures or computed quantitative results, but the editor/peer
        checklists (which assume an experimental paper) otherwise demand evidence
        it cannot have — the failure mode behind the ``revision_exhausted`` deaths
        on the VM. Keyed on the absence of BOTH execution figures and successful
        experiment code (an experiments-attempted-but-empty cycle aborts before
        WRITING via ``abort_on_execution_failure``, so reaching review with neither
        means the paper is genuinely non-experimental).
        """
        state = self._engine.state
        return not state.execution_figures and not state.successful_code

    def _get_review_categories(self) -> list[str] | None:
        """Get review score categories from domain profile.

        Returns:
            List of category name strings, or None to use defaults.
        """
        profile = self._engine._profile
        if profile is not None and profile.document_template.review_criteria:
            return score_categories_from_criteria(profile.document_template.review_criteria)
        return None

    def _build_score_format(self) -> str:
        """Build the score format string for the peer review prompt.

        Uses domain review criteria if available, otherwise falls back
        to the default science categories.

        Returns:
            Formatted score line like "Novelty: X/10\\nRigor: X/10\\n..."
        """
        categories = self._get_review_categories()
        if categories is None:
            from paradigm.journal.review import SCORE_CATEGORIES

            categories = SCORE_CATEGORIES
        return "\n".join(f"{cat.replace('_', ' ').title()}: X/10" for cat in categories)

    def _build_execution_metadata(self) -> str:
        """Build execution metadata section for peer reviewers.

        Combines execution caveats and a truncated version of the raw
        experiment output so reviewers can verify claims against evidence.

        Returns:
            Formatted metadata string (empty if no execution data).
        """
        parts: list[str] = []

        if self._engine.state.execution_caveats:
            parts.append(
                "## Execution Caveats (from the experiment pipeline)\n"
                + "\n".join(f"- {c}" for c in self._engine.state.execution_caveats)
            )

        if self._engine.state.execution_context:
            context = self._engine.state.execution_context
            if len(context) > _PEER_REVIEW_METADATA_LIMIT:
                context = (
                    context[:_PEER_REVIEW_METADATA_LIMIT] + "\n... (experiment output truncated)"
                )
            parts.append("## Raw Experiment Output\n" + context)

        if not parts:
            return ""

        return (
            "---\n"
            "**The following execution metadata is provided for your review. "
            "Use it to verify the paper's quantitative claims.**\n\n"
            + "\n\n".join(parts)
            + "\n\n---\n\n"
        )

    @staticmethod
    def _count_mandatory_check_failures(review_text: str) -> int:
        """Count how many mandatory checklist items the editor marked as failed.

        Looks for indicators of failure (FAILED, violated, missing, not met,
        not found, absent) near each of the 5 mandatory check categories.

        Args:
            review_text: Editor's review response text.

        Returns:
            Number of failed checks (0-5).
        """
        # Trust an explicit "the mandatory checks passed" statement. The proximity
        # heuristic below otherwise false-positives when the review DISCUSSES the
        # (passed) categories: the indicator "confabulat" matches the CATEGORY NAME
        # "anti-confabulation", and words like "violations" (e.g. of LaTeX rules,
        # not the checks) sit near a category. A single spurious count of >=4 wrongly
        # escalates a "revise" to a "reject" — a good paper was rejected this way.
        # But only an AFFIRMATIVE statement counts: "was NOT passed", "only 1 of 5
        # passed", or "3 of 5 passed" must fall through to the per-category count.
        passed_match = re.search(
            r"(mandatory|verification|checklist)[^.]{0,160}\bpass(?:ed|es)?\b",
            review_text,
            re.IGNORECASE,
        )
        if passed_match is not None:
            window = review_text[max(0, passed_match.start() - 40) : passed_match.end()]
            negated = re.search(
                r"\b(not|no|none|fail\w*|only|except|partial\w*|unmet|missing)\b|n't\b",
                window,
                re.IGNORECASE,
            )
            fraction = re.search(r"\b(\d+)\s+(?:out\s+)?of\s+(\d+)\b", window)
            partial = fraction is not None and fraction.group(1) != fraction.group(2)
            if negated is None and not partial:
                return 0

        categories = [
            r"internal\s+consistency",
            r"data\s+integrity",
            r"figure\s+reference",
            r"claim.evidence\s+alignment",
            r"anti.confabulation",
        ]
        # Explicit failure verdicts only — NOT the topic nouns "confabulation" /
        # "fabrication" (which are the category names themselves).
        failure_indicators = re.compile(
            r"\b(FAIL(?:ED|S|URE)?|violated|missing|not met|not found|absent|"
            r"no evidence|cannot be traced|fabricated|confabulated)\b",
            re.IGNORECASE,
        )

        failures = 0
        for cat_pattern in categories:
            # Find the category mention and check nearby text (200 chars window),
            # excluding the matched category name so it can't self-trigger.
            cat_re = re.compile(cat_pattern, re.IGNORECASE)
            match = cat_re.search(review_text)
            if match is None:
                continue
            start = max(0, match.start() - 50)
            end = min(len(review_text), match.end() + 200)
            window = review_text[start : match.start()] + review_text[match.end() : end]
            if failure_indicators.search(window):
                failures += 1
        return failures

    @staticmethod
    def _resolve_internal_recommendation(
        recommendation: str,
        required_changes: int,
        check_failures: int,
        *,
        explicit: bool = True,
    ) -> str:
        """Resolve the editor's internal-review recommendation.

        - "revise" with >=4 failed mandatory checks -> "reject" (revision can't fix
          fundamental issues).
        - "revise" with no required changes -> "accept" ONLY when the recommendation
          was explicit (a real ## Recommendation section with nothing actionable to
          revise — lets the loop converge instead of looping on an empty revision).

        When ``explicit`` is False the review was incomplete (e.g. the editor's reply
        was truncated before its recommendation, so it defaulted to "revise"): do NOT
        convert that to an accept — keep "revise" so the paper isn't rubber-stamped on
        a review the editor never actually finished.

        Other recommendations pass through unchanged.
        """
        if recommendation == "revise":
            if check_failures >= 4:
                return "reject"
            if required_changes == 0 and explicit:
                return "accept"
        return recommendation

    @staticmethod
    def _review_keep_going(
        prev_required: int | None,
        required: int,
        iteration: int,
        max_iterations: int,
        hard_cap: int,
        stall_count: int,
    ) -> tuple[bool, int]:
        """Decide whether internal review keeps revising, and the new stall count.

        - First pass (no prior): revise within the normal cap.
        - Diverging (``required > prev``): stop now — revisions are making it worse.
        - Flat plateau (``required == prev``): stop after ``_REVIEW_STALL_LIMIT``
          consecutive flat iterations, else continue within the normal cap.
        - Strictly improving (``required < prev``): the paper is converging, so
          extend past the normal cap up to ``hard_cap``.
        """
        if prev_required is None:
            return iteration < max_iterations, stall_count
        if required > prev_required:
            return False, stall_count
        if required == prev_required:
            stall_count += 1
            return (stall_count < _REVIEW_STALL_LIMIT and iteration < max_iterations), stall_count
        # strictly improving — converging
        return iteration < hard_cap, 0

    async def _run_figure_review(self) -> str:
        """Visually inspect the paper's figures with a vision model (P2-VLM, default-off).

        Returns concrete figure findings to inject into the editor's review, or "" when
        disabled, when there are no figures, or on any error (graceful degradation —
        e.g. the configured model isn't vision-capable).
        """
        cfg = self._engine._config.orchestrator
        if not cfg.enable_multimodal_review:
            return ""
        figures = self._engine.state.execution_figures
        if not figures:
            return ""
        encoded = encode_figures_for_review(figures, max_figures=cfg.max_review_figures)
        if not encoded:
            return ""
        try:
            provider, model, extra_body = self._engine._config.get_provider_and_model_for_role(
                cfg.multimodal_review_role
            )
            if not hasattr(provider, "build_image_message"):
                return ""
            figure_list = "\n".join(
                f"{i}. {name}" for i, (name, _mt, _data) in enumerate(encoded, 1)
            )
            prompt = _FIGURE_REVIEW_PROMPT.format(n_figures=len(encoded), figure_list=figure_list)
            message = provider.build_image_message(prompt, [(mt, data) for _n, mt, data in encoded])
            text, input_tokens, output_tokens = await asyncio.to_thread(
                provider.complete,
                model=model,
                system="You are a meticulous scientific figure-quality reviewer.",
                messages=[message],
                max_tokens=1024,
                extra_body=extra_body,
            )
            self._engine._db.record_token_usage(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thread_id=self._engine.state.thread_id,
            )
            return text.strip()
        except Exception as e:  # noqa: BLE001 — figure review is best-effort, never fatal
            self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
            return ""

    async def run_review_phase(self, draft: PaperDraft) -> None:
        """Run the INTERNAL_REVIEW phase: editor reviews, optionally loop back.

        Args:
            draft: PaperDraft to review.
        """
        # Belt-and-suspenders: don't review empty/tiny papers
        current_body = draft.assembled_body or draft.to_markdown()
        if len(current_body) < _MIN_PAPER_LENGTH:
            self._engine._display.review_too_short(len(current_body))
            return

        max_iterations = self._engine._config.orchestrator.max_review_iterations

        # P2-VLM: visually inspect figures once up front (figures are stable across
        # revisions); inject findings into each editor review below.
        figure_findings = await self._run_figure_review()

        # Trajectory-aware budget (backlog #4): a strictly-converging paper may run a
        # few iterations past max_iterations (up to hard_cap); a diverging/stalled one
        # stops early — instead of every paper dying at the same fixed cap.
        hard_cap = max_iterations + self._engine._config.orchestrator.review_convergence_extra
        prev_required_count: int | None = None
        stall_count = 0
        iteration = 0
        # Anti-moving-target: the editor's open blocking items, re-shown each
        # iteration so later rounds track them instead of surfacing new nits.
        prior_blocking: list[str] = []
        # Last parsed review, for the budget-exhaustion rescue below: a paper
        # with only MINOR items open must not die as revision_exhausted.
        last_feedback = None
        last_review_text = ""

        while iteration < hard_cap:
            iteration += 1
            self._engine._display.review_iteration(iteration, max_iterations)
            self._engine._literature.search_count_this_round = 0

            # Editor reviews
            editor = self._engine._find_agent_by_role("editor")
            if editor is None:
                self._engine._display.review_no_editor()
                return

            template = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["editor_review"]
            prompt = template.format(
                seed_prompt=self._engine.state.seed_prompt,
                current_draft=current_body[:_PAPER_CONTEXT_LIMIT],  # Truncate for context window
            )

            # Literature/theory papers have no experimental results — re-frame the
            # checklist so the editor doesn't demand figures/quantitative evidence the
            # cycle never produced (the revision_exhausted failure mode).
            if self._is_literature_only():
                prompt += _LITERATURE_PAPER_REVIEW_DIRECTIVE

            # Inject caveats so editor verifies the paper acknowledges them
            if self._engine.state.execution_caveats:
                prompt += (
                    "\n\n## Execution Caveats to Verify\n"
                    "The EXECUTION phase identified these limitations. "
                    "Check that the paper explicitly acknowledges each one. "
                    "If the paper presents synthetic/placeholder data as real "
                    "observational results, this is a CRITICAL issue requiring "
                    "revision. If claims contradict known limitations, flag them.\n"
                    + "\n".join(f"- {c}" for c in self._engine.state.execution_caveats)
                )

            # Inject execution fact sheet for claim verification
            fact_sheet = self._engine._writing._build_execution_fact_sheet()
            if fact_sheet:
                prompt += (
                    "\n\n" + fact_sheet + "\n\n"
                    "Cross-reference every quantitative claim in the paper against "
                    "the Actual Output blocks above. Flag any number that cannot be "
                    "traced to an experiment output."
                )

            # Inject forbidden claims block for the editor
            forbidden_block = self._engine._writing._build_forbidden_claims_block()
            if forbidden_block:
                prompt += forbidden_block

            # Inject reference quality warnings
            ref_warnings = self._engine._writing._check_reference_quality(current_body)
            if ref_warnings:
                prompt += (
                    "\n\n## Reference Quality Alerts\n"
                    + "\n".join(f"- {w}" for w in ref_warnings)
                    + "\nFlag these issues in your review."
                )

            # Semantic claim↔citation audit: possible MISATTRIBUTIONS (right-looking
            # but wrong-paper references) surfaced for the editor to verify.
            citation_alerts = await self._engine._citation_handler.audit_citation_claims(
                current_body
            )
            if citation_alerts:
                prompt += (
                    "\n\n## AUTOMATED CITATION ALERTS (possible misattributions)\n"
                    "Verify each against the paper; add a Required Change for any "
                    "real one:\n" + "\n".join(f"- {w}" for w in citation_alerts)
                )

            # Inject figure existence warnings
            fig_warnings = self._engine._writing._validate_figure_references(current_body)
            if fig_warnings:
                prompt += (
                    "\n\n## Figure Existence Alerts\n"
                    + "\n".join(f"- {w}" for w in fig_warnings)
                    + "\n**Required:** Remove references to non-existent figures, "
                    "or replace with descriptive text (e.g., 'a visualization would show...')."
                )

            # Inject automated forbidden claims violations if detected
            if self._engine.state.forbidden_claims_violations:
                prompt += (
                    "\n\n## AUTOMATED VIOLATION ALERTS\n"
                    "The following potential forbidden claim violations were "
                    "detected automatically. Verify each one:\n"
                    + "\n".join(f"- {v}" for v in self._engine.state.forbidden_claims_violations)
                )

            # P2-VLM: inject visual figure-review findings (default-off).
            if figure_findings:
                prompt += (
                    "\n\n## Figure Review (visual inspection of the actual figures)\n"
                    + figure_findings
                    + "\nIncorporate any real figure issues above into your required changes."
                )

            # Hold the paper to the user's explicit asks: a requested deliverable
            # must be delivered or honestly acknowledged, never silently dropped.
            prompt += self._engine._writing.requirements_block(audience="editor")

            # Anti-moving-target: later iterations verify the FIRST review's
            # blocking items rather than raising fresh blockers for pre-existing
            # nits (the churn that exhausts revision budgets).
            if prior_blocking:
                prompt += (
                    "\n\n## Previously Required (Blocking) Changes\n"
                    "Verify each was addressed. Do NOT add new blocking items unless "
                    "the revision itself introduced them — a pre-existing issue you "
                    "only just noticed belongs under Minor Changes.\n"
                    + "\n".join(f"- {c}" for c in prior_blocking)
                )

            response = None
            last_error = None
            for retry in range(_INTERNAL_REVIEW_MAX_RETRIES + 1):
                try:
                    # Honor a larger per-role config (e.g. headroom for a thinking
                    # editor) — the floor here only protects against tiny defaults.
                    role_cap = getattr(editor, "max_tokens", 0)
                    if not isinstance(role_cap, int):
                        role_cap = 0
                    response = await editor.generate(
                        prompt, max_tokens=max(_REVIEW_MAX_TOKENS, role_cap)
                    )
                    # An empty review is a failed review, not a lenient one: a
                    # thinking editor that exhausts its budget returns "" (seen
                    # live: 16384/16384 tokens, no text), which would parse to
                    # "revise / 0 changes" and trigger a BLIND full revision.
                    if not response.content.strip():
                        response = None
                        raise ValueError(
                            "editor returned an empty review (output budget "
                            "likely exhausted before any visible text)"
                        )
                    break
                except Exception as e:
                    last_error = e
                    self._engine._logger.log_error(
                        e, agent_id=editor.agent_id, thread_id=self._engine.state.thread_id
                    )
                    if retry < _INTERNAL_REVIEW_MAX_RETRIES:
                        self._engine._display.review_editor_retry(retry + 1, e)
                        await asyncio.sleep(2**retry)  # Exponential backoff: 1s, 2s
                    else:
                        self._engine._display.review_editor_error(last_error)
                        return

            if response is None:
                self._engine._display.review_editor_error(last_error)
                return

            self._engine._log_agent_response(
                editor.agent_id, response, ResearchPhase.INTERNAL_REVIEW, "review"
            )
            await self._engine._literature.process_search_requests(
                editor.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            await self._engine._literature.process_literature_actions(
                editor.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            self.review_log.append(
                {
                    "type": "internal_review",
                    "reviewer_id": editor.agent_id,
                    "text": response.content,
                    "iteration": iteration,
                }
            )

            # Parse review feedback
            feedback = parse_review_feedback(response.content)

            # Override the editor's recommendation: escalate to reject when mandatory
            # checks fail, or accept when "revise" lists nothing to revise (see helper).
            if feedback.recommendation == "revise":
                feedback.recommendation = self._resolve_internal_recommendation(
                    feedback.recommendation,
                    len(feedback.required_changes),
                    self._count_mandatory_check_failures(response.content),
                    explicit=feedback.recommendation_explicit,
                )

            self._engine._display.review_recommendation(
                feedback.recommendation, len(feedback.required_changes)
            )
            self._engine.emit_event(
                "review.iteration",
                {
                    "iteration": iteration,
                    "recommendation": feedback.recommendation,
                    "n_required_changes": len(feedback.required_changes),
                    "n_blocking": len(feedback.blocking_changes),
                    "stage": "internal",
                },
            )
            last_feedback = feedback
            last_review_text = response.content
            if feedback.recommendation_explicit:
                prior_blocking = list(feedback.blocking_changes)

            if feedback.recommendation == "reject":
                # Paper fundamentally flawed — stop immediately
                self._engine._display.review_rejected()
                thread = self._engine._db.get_thread(self._engine.state.thread_id)
                if thread and thread.get("current_draft_id"):
                    self._engine._db.update_paper(
                        thread["current_draft_id"], status="review_rejected"
                    )
                self._engine._db.update_thread(
                    self._engine.state.thread_id, status="review_rejected"
                )
                return

            if feedback.recommendation == "accept":
                # Gate leak guard (D): "accept" while explicit BLOCKING issues
                # are still open is contradictory — a live run accepted a paper
                # with one blocking item outstanding. Downgrade to a revision so
                # the blockers are addressed first. Gated on `tiered` so a legacy
                # accept-with-required-changes (editor's call) is untouched.
                if feedback.tiered and feedback.blocking_changes:
                    self._engine._display.info(
                        f"[review] editor said accept but {len(feedback.blocking_changes)} "
                        "blocking issue(s) remain — treating as revise."
                    )
                    feedback.recommendation = "revise"
                else:
                    # Paper accepted — update status
                    thread = self._engine._db.get_thread(self._engine.state.thread_id)
                    if thread and thread.get("current_draft_id"):
                        self._engine._db.update_paper(thread["current_draft_id"], status="reviewed")
                    return

            # Accept-with-minor-revisions: "revise" with ZERO blocking items means
            # the science stands — apply the cosmetic fixes in ONE final polish
            # pass and accept, instead of burning (and possibly exhausting) the
            # revision budget on nits. (A real paper died revision_exhausted one
            # rounding-range sentence away from acceptance.)
            if (
                feedback.recommendation == "revise"
                and feedback.recommendation_explicit
                and not feedback.blocking_changes
                and feedback.minor_changes
            ):
                await self._accept_with_minor_fixes(
                    draft, current_body, response.content, len(feedback.minor_changes)
                )
                return

            # Trajectory-aware budget (see _review_keep_going): extend a converging
            # paper past the normal cap, cut a diverging/stalled one early.
            required_count = len(feedback.required_changes)
            if feedback.recommendation_explicit:
                keep_going, stall_count = self._review_keep_going(
                    prev_required_count,
                    required_count,
                    iteration,
                    max_iterations,
                    hard_cap,
                    stall_count,
                )
                prev_required_count = required_count
            else:
                # A truncated/unparseable review carries NO convergence signal —
                # its 0 required changes must not read as "improving" and EXTEND
                # the budget (a token-starved editor did exactly that live).
                # Treat it as a stalled iteration; prev_required_count keeps the
                # last real signal.
                stall_count += 1
                keep_going = stall_count < _REVIEW_STALL_LIMIT and iteration < max_iterations
            if not keep_going:
                break

            # Revision needed — writer revises (the budget gate above already decided).
            self._engine._display.review_revising()
            current_body = await self.run_revision(current_body, response.content)
            draft.assembled_body = current_body

            # Update paper in database and on disk
            thread = self._engine._db.get_thread(self._engine.state.thread_id)
            if thread and thread.get("current_draft_id"):
                paper_id = thread["current_draft_id"]
                self._engine._db.update_paper(
                    paper_id,
                    body=current_body,
                    status="revised",
                )
                # Offloaded: save_paper_file may pre-compile the PDF (LaTeX
                # subprocess) — keep it off the event loop so the UI never stalls.
                await asyncio.to_thread(
                    self._engine._writing.save_paper_file, paper_id, current_body
                )

        # Loop ended without editor acceptance (max iterations or stalled revisions).
        # Rescue: if the LAST review found no blocking issues, the paper is
        # scientifically sound — accept with a final polish pass rather than
        # letting the budget cap convert open cosmetics into a fatal rejection.
        if (
            last_feedback is not None
            and last_feedback.recommendation_explicit
            and not last_feedback.blocking_changes
        ):
            await self._accept_with_minor_fixes(
                draft, current_body, last_review_text, len(last_feedback.minor_changes)
            )
            return
        self._engine._display.review_max_iterations()
        thread = self._engine._db.get_thread(self._engine.state.thread_id)
        if thread and thread.get("current_draft_id"):
            self._engine._db.update_paper(thread["current_draft_id"], status="revision_exhausted")
        self._engine._db.update_thread(self._engine.state.thread_id, status="revision_exhausted")

    async def _accept_with_minor_fixes(
        self,
        draft: PaperDraft,
        current_body: str,
        review_text: str,
        n_minor: int,
    ) -> None:
        """Accept a paper whose only open items are cosmetic.

        Applies the minor changes in ONE final revision pass (no re-review — by
        construction none of them can change a conclusion) and marks the paper
        reviewed. Peer review still follows as usual.
        """
        self._engine._display.info(
            f"Editor: no blocking issues ({n_minor} minor) — applying a final polish "
            "pass and accepting."
        )
        self._engine.emit_event("review.accept_minor", {"n_minor": n_minor, "stage": "internal"})
        if n_minor > 0:
            revised = await self.run_revision(current_body, review_text)
            # A failed/degenerate polish must not shrink the accepted paper.
            if len(revised) >= _MIN_PAPER_LENGTH:
                current_body = revised
        draft.assembled_body = current_body
        thread = self._engine._db.get_thread(self._engine.state.thread_id)
        if thread and thread.get("current_draft_id"):
            paper_id = thread["current_draft_id"]
            self._engine._db.update_paper(paper_id, body=current_body, status="reviewed")
            self._engine._writing.refresh_paper_title(paper_id, current_body)  # C
            await asyncio.to_thread(self._engine._writing.save_paper_file, paper_id, current_body)

    async def run_revision(self, current_body: str, review_text: str) -> str:
        """Writer revises the paper based on review feedback.

        Args:
            current_body: Current paper markdown.
            review_text: Editor's review text.

        Returns:
            Revised paper body.
        """
        writer = self._engine._find_agent_by_role("writer")
        if writer is None:
            return current_body

        checkpoint_context = ""
        if self._engine.state.checkpoint:
            checkpoint_context = self._engine.state.checkpoint.to_context_string() + "\n\n"

        template = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["revision"]
        prompt = template.format(
            seed_prompt=self._engine.state.seed_prompt,
            checkpoint_context=checkpoint_context,
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
            review_feedback=review_text[:_PAPER_CONTEXT_LIMIT],
        )

        # Inject execution fact sheet to prevent re-introduction of fabricated claims
        fact_sheet = self._engine._writing._build_execution_fact_sheet()
        if fact_sheet:
            prompt += (
                "\n\n" + fact_sheet + "\n\n"
                "When revising, do NOT introduce new quantitative claims that are "
                "not in the Actual Output blocks above."
            )

        # Same citation allow-list the drafting prompts carried — a revision replaces the
        # whole body, so without it the writer has no valid [N] targets to cite from.
        if self._engine._writing._citation_allowlist_block:
            prompt += self._engine._writing._citation_allowlist_block

        try:
            response = await writer.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            self._engine._log_agent_response(
                writer.agent_id, response, ResearchPhase.INTERNAL_REVIEW, "revision"
            )
            await self._engine._literature.process_search_requests(
                writer.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            await self._engine._literature.process_literature_actions(
                writer.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            # Re-sanitize: the initial assembly converts Unicode math to LaTeX, but a
            # revision can reintroduce Unicode symbols (μ, ∑, α, subscripts). Without this,
            # the editor flags "mathematical notation violations" every iteration and the
            # review loop never converges (see paper-b94ddf: all 5 rounds "Revise").
            # Then re-apply the citation net — the rewrite bypasses the assembly-time
            # compile/strip, so fabricated cites could otherwise re-enter here (ADR-013).
            revised = sanitize_unicode_math(strip_agent_scaffolding(response.content))
            return self._engine._writing.apply_citation_net(revised)
        except Exception as e:
            self._engine._logger.log_error(
                e, agent_id=writer.agent_id, thread_id=self._engine.state.thread_id
            )
            self._engine._display.revision_error(e)
            return current_body

    async def run_submission_phase(self, draft: PaperDraft) -> bool:
        """Run the SUBMITTED phase: desk review by editor-in-chief.

        Args:
            draft: Paper draft to submit.

        Returns:
            True if paper passes desk review, False if desk-rejected.
        """
        self._engine.state.phase_manager.transition_to(ResearchPhase.SUBMITTED)
        self._engine._log_phase_transition(ResearchPhase.INTERNAL_REVIEW, ResearchPhase.SUBMITTED)
        self._engine.state.messages = []
        self._engine._display.phase_transition(ResearchPhase.SUBMITTED)

        # Update submitted_at in database
        thread = self._engine._db.get_thread(self._engine.state.thread_id)
        if thread and thread.get("current_draft_id"):
            self._engine._db.update_paper(
                thread["current_draft_id"],
                status="submitted",
                submitted_at=datetime.now(UTC).isoformat(),
            )

        # Editor desk review
        editor = self._engine._find_agent_by_role("editor")
        if editor is None:
            self._engine._display.desk_review_no_editor()
            return True

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.SUBMITTED]["desk_review"]
        prompt = template.format(
            seed_prompt=self._engine.state.seed_prompt,
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
        )

        try:
            response = await editor.generate(prompt)
        except Exception as e:
            self._engine._logger.log_error(
                e, agent_id=editor.agent_id, thread_id=self._engine.state.thread_id
            )
            self._engine._display.desk_review_error(e)
            return True

        self._engine._log_agent_response(
            editor.agent_id, response, ResearchPhase.SUBMITTED, "desk_review"
        )

        # Parse desk review decision from ## Decision section only
        sections = parse_sections_from_markdown(response.content)
        decision_text = sections.get("decision", "").strip().lower()

        # Fall back to full-text scan only if no ## Decision section found
        if not decision_text:
            decision_text = response.content.lower()

        is_desk_reject = "desk_reject" in decision_text or "desk reject" in decision_text

        _desk_decision = "desk_reject" if is_desk_reject else "send_to_review"
        self.review_log.append(
            {
                "type": "desk_review",
                "reviewer_id": editor.agent_id,
                "text": response.content,
                "decision": _desk_decision,
            }
        )

        if is_desk_reject:
            self._engine._display.desk_review_result(False)
            # Desk rejection — create a minimal review for graveyard
            desk_review = PeerReview(
                reviewer_id=editor.agent_id,
                summary="Desk rejection by editor-in-chief.",
                weaknesses=["Did not pass desk review"],
                recommendation="reject",
            )
            thread = self._engine._db.get_thread(self._engine.state.thread_id)
            if thread and thread.get("current_draft_id"):
                reject_paper(
                    thread["current_draft_id"],
                    self._engine._db,
                    [desk_review],
                    self._engine._logger,
                )
            self._engine.state.phase_manager.transition_to(ResearchPhase.REJECTED)
            self._engine._log_phase_transition(ResearchPhase.SUBMITTED, ResearchPhase.REJECTED)
            # Surface the terminal phase to the live UI (the tracker + terminal
            # screen key off current_phase) — without this the run looks stuck on
            # "Submitted" after a desk rejection.
            self._engine._display.phase_transition(ResearchPhase.REJECTED)
            return False

        self._engine._display.desk_review_result(True)
        return True

    async def run_peer_review_phase(self, draft: PaperDraft) -> tuple[str, list[PeerReview]]:
        """Run the PEER_REVIEW phase: create reviewers, collect reviews, synthesize decision.

        Args:
            draft: Paper draft to review.

        Returns:
            Tuple of (decision string, list of PeerReview objects).
        """
        self._engine.state.phase_manager.transition_to(ResearchPhase.PEER_REVIEW)
        self._engine._log_phase_transition(ResearchPhase.SUBMITTED, ResearchPhase.PEER_REVIEW)
        self._engine.state.messages = []
        num_reviewers = self._engine._config.orchestrator.num_reviewers
        self._engine._display.phase_transition(ResearchPhase.PEER_REVIEW)
        self._engine._display.peer_review_start(num_reviewers)

        # Create fresh reviewer agents (not reusing team agents)
        reviewer_roles = ["reviewer"] * num_reviewers
        reviewer_agents = self._engine._factory.create_team(reviewer_roles, skill_mode="default")

        # Give each reviewer a unique ID to avoid collision with team IDs
        for i, agent in enumerate(reviewer_agents):
            agent.agent_id = f"peer-reviewer-{i}"

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.PEER_REVIEW]["review"]

        # Inject domain-specific score format into the review prompt
        score_format = self._build_score_format()
        template = template.replace(
            "Novelty: X/10\nRigor: X/10\nClarity: X/10\nSignificance: X/10",
            score_format,
        )

        self._engine._literature.search_count_this_round = 0

        # Build execution metadata for reviewers
        execution_metadata = self._build_execution_metadata()

        # Get domain-specific review categories for score parsing
        review_categories = self._get_review_categories()

        reviews: list[PeerReview] = []
        for agent in reviewer_agents:
            prompt = template.format(
                seed_prompt=self._engine.state.seed_prompt,
                current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
                execution_metadata=execution_metadata,
            )

            # Same literature/theory re-framing for peer review, so the fix doesn't
            # just move the bottleneck from internal review to peer review.
            if self._is_literature_only():
                prompt += _LITERATURE_PAPER_REVIEW_DIRECTIVE

            try:
                response = await agent.generate(prompt)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent.agent_id, thread_id=self._engine.state.thread_id
                )
                self._engine._display.peer_review_error(agent.agent_id, e)
                continue

            self._engine._log_agent_response(
                agent.agent_id, response, ResearchPhase.PEER_REVIEW, "review"
            )
            await self._engine._literature.process_search_requests(
                agent.agent_id, response.content, ResearchPhase.PEER_REVIEW
            )
            await self._engine._literature.process_literature_actions(
                agent.agent_id, response.content, ResearchPhase.PEER_REVIEW
            )

            review = parse_peer_review(
                agent.agent_id, response.content, categories=review_categories
            )
            reviews.append(review)
            self.review_log.append(
                {
                    "type": "peer_review",
                    "reviewer_id": agent.agent_id,
                    "text": response.content,
                    "review": review,
                }
            )
            avg_score = sum(review.scores.values()) / len(review.scores) if review.scores else 0
            self._engine._display.peer_review_result(
                agent.agent_id, review.recommendation, avg_score
            )

        # Synthesize decision
        decision = synthesize_decision(reviews)
        self.review_log.append(
            {
                "type": "decision",
                "decision": decision,
            }
        )
        self._engine._display.peer_review_decision(decision)
        self._engine.emit_event(
            "review.iteration",
            {
                "recommendation": decision,
                "n_required_changes": None,
                "stage": "peer",
                "n_reviewers": len(reviews),
            },
        )

        return decision, reviews

    async def run_revision_phase(
        self,
        draft: PaperDraft,
        reviews: list[PeerReview],
        extra_feedback: str = "",
    ) -> PaperDraft:
        """Run the REVISION phase: writer revises based on peer feedback.

        Args:
            draft: Current paper draft.
            reviews: Peer reviews with feedback.
            extra_feedback: Additional revision context (e.g. the PI's note that
                NEW experiments were run for a deep revision — R2).

        Returns:
            Updated PaperDraft with revised body.
        """
        self._engine.state.phase_manager.transition_to(ResearchPhase.REVISION)
        self._engine._log_phase_transition(ResearchPhase.PEER_REVIEW, ResearchPhase.REVISION)
        self._engine.state.messages = []
        self._engine._literature.search_count_this_round = 0
        self._engine._display.revision_start()

        writer = self._engine._find_agent_by_role("writer")
        if writer is None:
            self._engine._display.revision_no_writer()
            # Re-submit without changes
            self._engine.state.phase_manager.transition_to(ResearchPhase.SUBMITTED)
            self._engine._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)
            return draft

        # Build review feedback text
        review_parts = []
        for review in reviews:
            parts = [f"### Reviewer: {review.reviewer_id}"]
            if review.summary:
                parts.append(f"Summary: {review.summary}")
            if review.weaknesses:
                parts.append("Weaknesses:\n" + "\n".join(f"- {w}" for w in review.weaknesses))
            if review.suggestions:
                parts.append("Suggestions:\n" + "\n".join(f"- {s}" for s in review.suggestions))
            if review.scores:
                scores_str = ", ".join(f"{k}: {v}/10" for k, v in review.scores.items())
                parts.append(f"Scores: {scores_str}")
            parts.append(f"Recommendation: {review.recommendation}")
            review_parts.append("\n".join(parts))
        review_feedback = "\n\n".join(review_parts)
        if extra_feedback:
            review_feedback += "\n\n" + extra_feedback

        checkpoint_context = ""
        if self._engine.state.checkpoint:
            checkpoint_context = self._engine.state.checkpoint.to_context_string() + "\n\n"

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.REVISION]["revise"]
        prompt = template.format(
            seed_prompt=self._engine.state.seed_prompt,
            checkpoint_context=checkpoint_context,
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
            review_feedback=review_feedback[:_PAPER_CONTEXT_LIMIT],
        )

        # Same citation allow-list the drafting prompts carried — a revision replaces the
        # whole body, so without it the writer has no valid [N] targets to cite from.
        if self._engine._writing._citation_allowlist_block:
            prompt += self._engine._writing._citation_allowlist_block

        try:
            response = await writer.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
        except Exception as e:
            self._engine._logger.log_error(
                e, agent_id=writer.agent_id, thread_id=self._engine.state.thread_id
            )
            self._engine._display.revision_phase_error(e)
            # Transition back to SUBMITTED so peer review can re-run
            self._engine.state.phase_manager.transition_to(ResearchPhase.SUBMITTED)
            self._engine._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)
            return draft

        self._engine._log_agent_response(
            writer.agent_id, response, ResearchPhase.REVISION, "revision"
        )
        await self._engine._literature.process_search_requests(
            writer.agent_id, response.content, ResearchPhase.REVISION
        )
        await self._engine._literature.process_literature_actions(
            writer.agent_id, response.content, ResearchPhase.REVISION
        )
        self.review_log.append(
            {
                "type": "revision",
                "reviewer_id": writer.agent_id,
            }
        )

        # Update draft (strip any agent meta-text before saving), then re-apply the
        # citation net — the rewrite bypasses the assembly-time compile/strip, so
        # fabricated cites could otherwise re-enter here (ADR-013).
        revised_body = self._engine._writing.apply_citation_net(
            strip_agent_scaffolding(response.content)
        )
        draft.assembled_body = revised_body

        # Update paper in database and on disk
        thread = self._engine._db.get_thread(self._engine.state.thread_id)
        if thread and thread.get("current_draft_id"):
            paper_id = thread["current_draft_id"]
            self._engine._db.update_paper(paper_id, body=revised_body, status="revised")
            self._engine._writing.refresh_paper_title(paper_id, revised_body)  # C
            self._engine._writing.save_paper_file(paper_id, revised_body)

        self._engine._display.revision_complete()

        # Transition back to SUBMITTED for re-review
        self._engine.state.phase_manager.transition_to(ResearchPhase.SUBMITTED)
        self._engine._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)

        return draft
