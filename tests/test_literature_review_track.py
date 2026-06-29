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
