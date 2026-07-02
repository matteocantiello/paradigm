"""Tests for the literature-only review track (Step 0).

When a cycle produces no experimental results, the editor/peer-review prompts are
re-framed so they don't demand experimental figures / quantitative evidence the
paper cannot have — the failure mode behind the `revision_exhausted` deaths seen
on the VM (no-experimentalist runs: breast-milk, OLED-v1).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from helpers import LONG_RESPONSE, make_mock_agent

from paradigm.orchestrator.review import (
    _LITERATURE_PAPER_REVIEW_DIRECTIVE,
    ReviewHandler,
)

# An editor review that accepts cleanly (no "revise"/"reject" words) so
# run_review_phase returns after a single iteration.
_ACCEPT_REVIEW = (
    "## Strengths\n- Strong literature synthesis.\n\n"
    "## Weaknesses\n- None significant.\n\n"
    "## Required Changes\n- None.\n\n"
    "## Recommendation\naccept\n"
)


# ---------------------------------------------------------------------------
# _is_literature_only predicate
# ---------------------------------------------------------------------------


class TestIsLiteratureOnly:
    def _handler(self, *, figures, code) -> ReviewHandler:
        engine = MagicMock()
        engine.state.execution_figures = figures
        engine.state.successful_code = code
        return ReviewHandler(engine)

    def test_no_results_is_literature(self):
        assert self._handler(figures=[], code=[])._is_literature_only() is True

    def test_figures_present_is_not_literature(self):
        h = self._handler(figures=[("exp", Path("/tmp/f.png"))], code=[])
        assert h._is_literature_only() is False

    def test_code_present_is_not_literature(self):
        h = self._handler(figures=[], code=[("exp", "print(1)")])
        assert h._is_literature_only() is False

    def test_both_present_is_not_literature(self):
        h = self._handler(figures=[("exp", Path("/tmp/f.png"))], code=[("exp", "code")])
        assert h._is_literature_only() is False


# ---------------------------------------------------------------------------
# Directive content
# ---------------------------------------------------------------------------


class TestDirectiveContent:
    def test_directive_reframes_the_bar(self):
        d = _LITERATURE_PAPER_REVIEW_DIRECTIVE
        assert "Literature / Theoretical Contribution" in d
        assert "Do NOT require" in d  # no experimental figures / quantitative results
        assert "CITED LITERATURE" in d  # claim-evidence reframed to citations
        assert "N/A" in d  # anti-confabulation / fact-sheet checks


# ---------------------------------------------------------------------------
# Internal editor review — prompt injection (end-to-end through run_review_phase)
# ---------------------------------------------------------------------------


def _build_review_engine(*, figures, code):
    """A MagicMock engine wired just enough to drive one internal-review iteration."""
    engine = MagicMock()
    engine._config.orchestrator.max_review_iterations = 1
    engine._config.orchestrator.review_convergence_extra = 0
    engine._config.orchestrator.enable_multimodal_review = False
    engine.state.execution_figures = figures
    engine.state.successful_code = code
    engine.state.execution_caveats = []
    engine.state.forbidden_claims_violations = []
    engine.state.seed_prompt = "Why does breast milk support a baby's immune system?"
    engine.state.thread_id = "thread-test"
    # Injection blocks that would otherwise concat MagicMocks into the prompt.
    engine._writing._build_execution_fact_sheet.return_value = ""
    engine._writing._build_forbidden_claims_block.return_value = ""
    engine._writing._check_reference_quality.return_value = []
    engine._writing._validate_figure_references.return_value = []
    # Awaited literature hooks must be async.
    engine._literature.process_search_requests = AsyncMock()
    engine._literature.process_literature_actions = AsyncMock()
    editor = make_mock_agent("editor-0", "editor", content=_ACCEPT_REVIEW)
    engine._find_agent_by_role.return_value = editor
    return engine, editor


def _draft():
    draft = MagicMock()
    draft.assembled_body = LONG_RESPONSE
    return draft


@pytest.mark.asyncio
async def test_literature_paper_review_gets_directive():
    engine, editor = _build_review_engine(figures=[], code=[])
    await ReviewHandler(engine).run_review_phase(_draft())

    prompt = editor.generate.call_args.args[0]
    assert _LITERATURE_PAPER_REVIEW_DIRECTIVE in prompt
    assert "Literature / Theoretical Contribution" in prompt


@pytest.mark.asyncio
async def test_experimental_paper_review_omits_directive():
    engine, editor = _build_review_engine(figures=[("exp", Path("/tmp/f.png"))], code=[])
    await ReviewHandler(engine).run_review_phase(_draft())

    prompt = editor.generate.call_args.args[0]
    assert _LITERATURE_PAPER_REVIEW_DIRECTIVE not in prompt
    assert "Literature / Theoretical Contribution" not in prompt


class TestReviewKeepGoing:
    """Trajectory-aware internal-review budget (backlog #4).

    Convention in these cases: max_iterations=3, hard_cap=6, _REVIEW_STALL_LIMIT=2.
    """

    KG = staticmethod(ReviewHandler._review_keep_going)

    def test_first_pass_within_cap(self):
        assert self.KG(None, 10, 1, 3, 6, 0) == (True, 0)

    def test_first_pass_at_cap_stops(self):
        assert self.KG(None, 10, 1, 1, 4, 0)[0] is False

    def test_diverging_breaks_immediately(self):
        # required 12 > prev 9 → stop now, even mid-budget (iteration 2 of 3)
        assert self.KG(9, 12, 2, 3, 6, 0) == (False, 0)

    def test_converging_extends_past_cap(self):
        # improving (4 < 14) at iteration == max (3) → keep going toward hard_cap
        assert self.KG(14, 4, 3, 3, 6, 0) == (True, 0)

    def test_converging_stops_at_hard_cap(self):
        assert self.KG(4, 1, 6, 3, 6, 0) == (False, 0)

    def test_plateau_stalls_after_limit(self):
        assert self.KG(5, 5, 2, 5, 8, 0) == (True, 1)  # first flat
        assert self.KG(5, 5, 3, 5, 8, 1) == (False, 2)  # second flat → stall limit

    def test_improving_resets_stall(self):
        assert self.KG(5, 3, 2, 5, 8, 1) == (True, 0)

    def test_single_flat_within_cap_continues(self):
        assert self.KG(5, 5, 1, 5, 8, 0) == (True, 1)


class TestResolveInternalRecommendation:
    """The truncated-review false-accept guard (editor rubber-stamp fix)."""

    R = staticmethod(ReviewHandler._resolve_internal_recommendation)

    def test_explicit_revise_zero_changes_accepts(self):
        # Genuine "revise" with nothing to revise → accept (loop converges).
        assert self.R("revise", 0, 0, explicit=True) == "accept"

    def test_truncated_revise_zero_changes_stays_revise(self):
        # Defaulted "revise" from a truncated review (no Recommendation section) →
        # do NOT auto-accept; keep revise so the paper isn't rubber-stamped.
        assert self.R("revise", 0, 0, explicit=False) == "revise"

    def test_revise_with_changes_unaffected(self):
        assert self.R("revise", 5, 0, explicit=True) == "revise"
        assert self.R("revise", 5, 0, explicit=False) == "revise"

    def test_many_check_failures_reject(self):
        assert self.R("revise", 0, 4, explicit=True) == "reject"
        assert self.R("revise", 0, 4, explicit=False) == "reject"

    def test_accept_passes_through(self):
        assert self.R("accept", 0, 0, explicit=False) == "accept"


class TestCountMandatoryCheckFailures:
    """Guard against false 'mandatory check failed' counts that wrongly reject
    good papers (the breast-milk run: editor said Revise + 'checks passed', but a
    spurious 5-failure count escalated it to reject)."""

    CF = staticmethod(ReviewHandler._count_mandatory_check_failures)

    def test_explicit_pass_returns_zero(self):
        review = (
            "All mandatory verification checklist items (internal consistency, data "
            "integrity, figure references, claim-evidence alignment, anti-confabulation) "
            "have passed. However, the LaTeX math notation violations must be fixed."
        )
        assert self.CF(review) == 0

    def test_category_name_does_not_self_trigger(self):
        # "anti-confabulation" (the category) must not match the "confabulat" indicator.
        review = "The anti-confabulation review is thorough and everything checks out."
        assert self.CF(review) == 0

    def test_genuine_failures_still_counted(self):
        review = (
            "## Internal consistency: FAILED — the abstract contradicts the results.\n"
            "## Data integrity: missing values throughout the tables.\n"
            "## Figure references: figure 3 is absent."
        )
        assert self.CF(review) >= 3

    def test_latex_violations_near_passed_categories_not_counted(self):
        # The real failure mode: "violations" of LaTeX rules near passed category names.
        review = (
            "internal consistency, data integrity, figure references, claim-evidence "
            "alignment, anti-confabulation — all pass. The identified violations of "
            "LaTeX math mode notation rules must be addressed."
        )
        assert self.CF(review) == 0

    def test_negated_pass_statement_not_trusted(self):
        # "was NOT passed" must fall through to the per-category count, not return 0.
        review = (
            "The verification checklist was not passed. Internal consistency: FAILED — "
            "the abstract contradicts section 4. Data integrity: FAILED. Figure "
            "references: FAILED. Claim-evidence alignment: FAILED."
        )
        assert self.CF(review) >= 4

    def test_only_n_of_m_passed_not_trusted(self):
        review = (
            "Only 1 of 5 mandatory checks passed. Internal consistency: FAILED. "
            "Data integrity: FAILED. Figure references: FAILED. "
            "Claim-evidence alignment: FAILED."
        )
        assert self.CF(review) >= 4

    def test_partial_fraction_passed_not_trusted(self):
        # "3 of 5 ... passed" (no "only") is still a partial pass.
        review = (
            "3 of 5 mandatory checks passed. Internal consistency FAILED because the "
            "tables disagree, and data integrity FAILED."
        )
        assert self.CF(review) >= 2

    def test_several_not_passed_with_failures_counted(self):
        review = (
            "Several mandatory checklist items have NOT passed: data integrity FAILED, "
            "anti-confabulation FAILED, figure references FAILED, internal "
            "consistency FAILED."
        )
        assert self.CF(review) >= 4

    def test_full_fraction_passed_is_trusted(self):
        review = "5 of 5 mandatory verification checks passed. Minor style edits needed."
        assert self.CF(review) == 0
