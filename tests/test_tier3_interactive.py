"""Tier 3: PI-proposes-human-disposes reflection + cross-cycle lesson summaries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.memory import MemoryHandler


def _stub(decision: dict):
    stub = SimpleNamespace()
    stub._decision_hook = object()  # non-None → interactive
    stub._check_decision = AsyncMock(return_value=decision)
    stub._apply_decision_action = OrchestrationEngine._apply_decision_action.__get__(stub)
    stub._db = MagicMock()
    stub._display = MagicMock()
    stub._pending_guidance = []
    stub.state = SimpleNamespace(thread_id="t1")
    stub._present_reflection_decision = OrchestrationEngine._present_reflection_decision.__get__(
        stub
    )
    return stub


_PI_LOOP = {
    "verdict": "loop_back",
    "target": "execution",
    "directives": ["add a control sample"],
    "success_criteria": "control shows the effect persists",
    "reason": "no control",
}


@pytest.mark.asyncio
async def test_operator_keeps_pi_proposal():
    stub = _stub(
        {"decision": "continue", "modifications": {"selected_ids": ["loop_back_execution"]}}
    )
    out = await stub._present_reflection_decision(dict(_PI_LOOP))
    assert out["verdict"] == "loop_back" and out["directives"] == ["add a control sample"]
    # The dialog defaulted to the PI's choice.
    payload = stub._check_decision.await_args.args[1]
    assert payload["default_ids"] == ["loop_back_execution"]
    assert [c["id"] for c in payload["choices"]] == [
        "proceed",
        "loop_back_execution",
        "loop_back_planning",
        "call_it",
    ]


@pytest.mark.asyncio
async def test_operator_overrides_to_proceed_with_notes():
    stub = _stub(
        {
            "decision": "continue",
            "notes": "good enough, ship it",
            "modifications": {"selected_ids": ["proceed"]},
        }
    )
    out = await stub._present_reflection_decision(dict(_PI_LOOP))
    assert out == {"verdict": "proceed", "reason": "good enough, ship it"}


@pytest.mark.asyncio
async def test_operator_override_to_loop_back_uses_notes_as_directive():
    stub = _stub(
        {
            "decision": "continue",
            "notes": "test the binary subsample",
            "modifications": {"selected_ids": ["loop_back_planning"]},
        }
    )
    out = await stub._present_reflection_decision({"verdict": "proceed", "reason": "fine"})
    assert out["verdict"] == "loop_back" and out["target"] == "planning"
    assert "test the binary subsample" in out["directives"]


@pytest.mark.asyncio
async def test_operator_abort_stops():
    stub = _stub({"decision": "abort"})
    assert await stub._present_reflection_decision(dict(_PI_LOOP)) is None


@pytest.mark.asyncio
async def test_timeout_keeps_pi_proposal():
    # A 300s timeout returns bare {"decision": "continue"} — the PI's call stands.
    stub = _stub({"decision": "continue"})
    out = await stub._present_reflection_decision(dict(_PI_LOOP))
    assert out["verdict"] == "loop_back"


# --- cross-cycle lesson summary (T3c) ---------------------------------------


def test_outcome_summary_names_datasets_and_scores():
    engine = MagicMock()
    engine._literature.fetched_dataset_ids = {"vizier:J/A+A/701/A297", "zenodo:999"}
    engine.state.experiment_metadata = [
        {"data_provenance": "real"},
        {"data_provenance": "real"},
        {"data_provenance": "derived"},
    ]
    engine.state.loop_backs_used = 1
    engine.state.thread_id = "t1"
    engine._db.get_thread.return_value = {"current_draft_id": "p1"}
    engine._db.get_paper.return_value = {"judge_scores": '{"composite": 6.4}'}
    handler = MemoryHandler(engine)
    s = handler._build_outcome_summary("published")
    assert "published" in s
    assert "vizier:J/A+A/701/A297" in s and "zenodo:999" in s
    assert "2 real" in s and "1 derived" in s
    assert "PI loop-backs used: 1" in s
    assert "6.4/10" in s


def test_outcome_summary_degrades_to_status_only():
    engine = MagicMock()
    engine._literature.fetched_dataset_ids = set()
    engine.state.experiment_metadata = []
    engine.state.loop_backs_used = 0
    engine.state.thread_id = "t1"
    engine._db.get_thread.return_value = None
    s = MemoryHandler(engine)._build_outcome_summary("rejected")
    assert s.startswith("Research cycle ended with status: rejected.")
