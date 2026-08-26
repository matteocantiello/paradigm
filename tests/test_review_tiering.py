"""Tiered internal review (Prompt 249, improvement A) + thin-output retry (B).

A real paper died `revision_exhausted` one cosmetic sentence away from
acceptance: the editor said "revise" three times over rounding/labeling nits
and the iteration cap converted that into a fatal rejection. Now only
BLOCKING (science-invalidating) changes can prevent acceptance; minor items
are applied in one final polish pass without re-review.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from helpers import LONG_RESPONSE, make_mock_agent, patch_config_provider

from paradigm.agents.base import AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.journal.paper import parse_review_feedback
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.phases import ResearchPhase
from paradigm.orchestrator.review import ReviewHandler
from paradigm.orchestrator.scheduler import Scheduler

# ---------------------------------------------------------------------------
# parse_review_feedback: tier parsing
# ---------------------------------------------------------------------------

_TIERED_MINOR_ONLY = (
    "## Recommendation\nrevise\n\n"
    "## Blocking Changes\n- None\n\n"
    "## Minor Changes\n- Round 0.4832 to 0.483 in Section 4.\n"
    "- Clarify the n=1716 sample label.\n\n"
    "## Strengths\n- Solid.\n\n## Weaknesses\n- Minor polish.\n"
)

_TIERED_WITH_BLOCKING = (
    "## Recommendation\nrevise\n\n"
    "## Blocking Changes\n- Figure 3 is referenced but does not exist.\n\n"
    "## Minor Changes\n- Reword the abstract's second sentence.\n\n"
    "## Strengths\n- Good data.\n\n## Weaknesses\n- Figures.\n"
)

_LEGACY_REVIEW = (
    "## Recommendation\nrevise\n\n"
    "## Required Changes\n- Fix the duplicated table rows.\n- Add error bars.\n\n"
    "## Strengths\n- Interesting.\n\n## Weaknesses\n- See changes.\n"
)


def test_parse_tiered_minor_only():
    fb = parse_review_feedback(_TIERED_MINOR_ONLY)
    assert fb.blocking_changes == []
    assert len(fb.minor_changes) == 2
    # Combined list drives the legacy convergence budget.
    assert fb.required_changes == fb.minor_changes
    assert fb.recommendation == "revise" and fb.recommendation_explicit


def test_parse_tiered_with_blocking():
    fb = parse_review_feedback(_TIERED_WITH_BLOCKING)
    assert len(fb.blocking_changes) == 1
    assert len(fb.minor_changes) == 1
    assert fb.required_changes == fb.blocking_changes + fb.minor_changes


def test_parse_legacy_review_is_conservatively_blocking():
    """Un-tiered reviews keep the old semantics: everything blocks."""
    fb = parse_review_feedback(_LEGACY_REVIEW)
    assert len(fb.required_changes) == 2


def test_blocking_none_with_prose_is_empty():
    """'None' + explanatory prose must count as ZERO blocking — not one item per
    line (which killed a clean paper on a revision-exhaustion technicality)."""
    review = (
        "## Recommendation\naccept\n\n"
        "## Blocking Changes\n"
        "None. All previously-flagged issues have been resolved in this revision.\n"
        "The abstract and results are now internally consistent.\n\n"
        "## Minor Changes\n- None\n"
    )
    fb = parse_review_feedback(review)
    assert fb.blocking_changes == []
    assert fb.recommendation == "accept"


def test_blocking_item_starting_with_none_is_kept():
    """A genuine blocking item that happens to start with 'None' is preserved."""
    review = (
        "## Recommendation\nrevise\n\n"
        "## Blocking Changes\n- None of the three figures referenced in Section 4 exist.\n\n"
        "## Minor Changes\n- None\n"
    )
    fb = parse_review_feedback(review)
    assert len(fb.blocking_changes) == 1
    assert fb.blocking_changes == fb.required_changes
    assert fb.minor_changes == []


# ---------------------------------------------------------------------------
# run_review_phase: accept-with-minor path
# ---------------------------------------------------------------------------


def _review_engine(editor_reviews: list[str], max_iterations: int = 2):
    """MagicMock engine wired enough to drive the internal-review loop."""
    engine = MagicMock()
    engine._config.orchestrator.max_review_iterations = max_iterations
    engine._config.orchestrator.review_convergence_extra = 0
    engine._config.orchestrator.enable_multimodal_review = False
    engine.state.execution_figures = []
    engine.state.successful_code = [("exp", "print(1)")]  # not literature-only
    engine.state.execution_caveats = []
    engine.state.forbidden_claims_violations = []
    engine.state.seed_prompt = "microturbulence across the HRD"
    engine.state.thread_id = "thread-test"
    engine.state.checkpoint = None
    engine._writing._build_execution_fact_sheet.return_value = ""
    engine._writing._build_forbidden_claims_block.return_value = ""
    engine._writing._check_reference_quality.return_value = []
    engine._writing._validate_figure_references.return_value = []
    engine._writing.requirements_block.return_value = ""
    engine._writing._citation_allowlist_block = ""
    engine._writing.apply_citation_net.side_effect = lambda body: body
    engine._literature.process_search_requests = AsyncMock()
    engine._literature.process_literature_actions = AsyncMock()
    engine._citation_handler.audit_citation_claims = AsyncMock(return_value=[])
    engine._db.get_thread.return_value = {"current_draft_id": "paper-1"}

    editor = make_mock_agent("editor-0", "editor")
    editor.generate = AsyncMock(
        side_effect=[
            AgentResponse(
                content=r,
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="m",
            )
            for r in editor_reviews
        ]
    )
    writer = make_mock_agent("writer-0", "writer", content=LONG_RESPONSE)

    def _by_role(role):
        return {"editor": editor, "writer": writer}.get(role)

    engine._find_agent_by_role.side_effect = _by_role
    return engine, editor, writer


def _draft():
    draft = MagicMock()
    draft.assembled_body = LONG_RESPONSE
    return draft


@pytest.mark.asyncio
async def test_minor_only_review_accepts_with_polish_pass():
    engine, editor, writer = _review_engine([_TIERED_MINOR_ONLY])
    await ReviewHandler(engine).run_review_phase(_draft())

    # One editor pass, one writer polish pass, accepted — never re-reviewed.
    assert editor.generate.await_count == 1
    assert writer.generate.await_count == 1
    statuses = [c.kwargs.get("status") for c in engine._db.update_paper.call_args_list]
    assert "reviewed" in statuses
    assert "revision_exhausted" not in statuses
    events = [c.args[0] for c in engine.emit_event.call_args_list]
    assert "review.accept_minor" in events


@pytest.mark.asyncio
async def test_blocking_then_minor_accepts_and_tracks_prior_blockers():
    engine, editor, writer = _review_engine([_TIERED_WITH_BLOCKING, _TIERED_MINOR_ONLY])
    await ReviewHandler(engine).run_review_phase(_draft())

    # Iteration 2's prompt re-shows iteration 1's blocking item (anti-moving-target).
    second_prompt = editor.generate.await_args_list[1].args[0]
    assert "Previously Required (Blocking) Changes" in second_prompt
    assert "Figure 3 is referenced but does not exist" in second_prompt

    statuses = [c.kwargs.get("status") for c in engine._db.update_paper.call_args_list]
    assert "reviewed" in statuses
    assert "revision_exhausted" not in statuses


@pytest.mark.asyncio
async def test_legacy_blocking_reviews_still_exhaust():
    """Regression guard: un-tiered 'revise' every round keeps the old outcome."""
    engine, editor, writer = _review_engine([_LEGACY_REVIEW] * 4, max_iterations=2)
    await ReviewHandler(engine).run_review_phase(_draft())

    statuses = [c.kwargs.get("status") for c in engine._db.update_paper.call_args_list]
    assert "revision_exhausted" in statuses
    assert "reviewed" not in statuses


# ---------------------------------------------------------------------------
# Thin-output retry in discussion turns (improvement B)
# ---------------------------------------------------------------------------


@pytest.fixture
def thin_config(tmp_path):
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={"max_rounds_per_phase": 1, "enable_checkpointing": False},
    )
    patch_config_provider(config)
    return config


def _response(content: str) -> AgentResponse:
    return AgentResponse(
        content=content,
        usage=TokenUsage(input_tokens=50, output_tokens=10, total_tokens=60),
        model="m",
    )


@pytest.mark.asyncio
async def test_thin_turn_is_retried_and_recovery_adopted(
    thin_config, tmp_db, tmp_logger, mock_corpus
):
    engine = OrchestrationEngine(
        config=thin_config,
        database=tmp_db,
        corpus=mock_corpus,
        logger=tmp_logger,
        agent_factory=MagicMock(),
    )
    engine.state.thread_id = "thread-thin"
    engine.state.seed_prompt = "test"
    good = "A substantive contribution. " * 20  # well over the 200-char bar
    agent = make_mock_agent("theorist-0", "theorist")
    agent.generate = AsyncMock(side_effect=[_response("ok."), _response(good)])
    engine.state.agents = {"theorist-0": agent}

    await engine._run_round(ResearchPhase.IDEATION, 2, Scheduler([agent]))

    assert agent.generate.await_count == 2
    assert engine.state.messages[-1]["content"] == good


@pytest.mark.asyncio
async def test_substantive_turn_is_not_retried(thin_config, tmp_db, tmp_logger, mock_corpus):
    engine = OrchestrationEngine(
        config=thin_config,
        database=tmp_db,
        corpus=mock_corpus,
        logger=tmp_logger,
        agent_factory=MagicMock(),
    )
    engine.state.thread_id = "thread-ok"
    engine.state.seed_prompt = "test"
    agent = make_mock_agent("theorist-0", "theorist", long_response=True)
    engine.state.agents = {"theorist-0": agent}

    await engine._run_round(ResearchPhase.IDEATION, 2, Scheduler([agent]))

    assert agent.generate.await_count == 1


@pytest.mark.asyncio
async def test_action_only_turn_is_not_retried(thin_config, tmp_db, tmp_logger, mock_corpus):
    """A short turn carrying action tags is intentional — never discarded."""
    engine = OrchestrationEngine(
        config=thin_config,
        database=tmp_db,
        corpus=mock_corpus,
        logger=tmp_logger,
        agent_factory=MagicMock(),
    )
    engine.state.thread_id = "thread-tags"
    engine.state.seed_prompt = "test"
    agent = make_mock_agent("theorist-0", "theorist")
    agent.generate = AsyncMock(return_value=_response("Ideas [SEARCH: convection data]"))
    engine.state.agents = {"theorist-0": agent}

    await engine._run_round(ResearchPhase.IDEATION, 2, Scheduler([agent]))

    assert agent.generate.await_count == 1
