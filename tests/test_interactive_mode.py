"""Interactive mode v1: per-cycle interactive flag + structured decisions.

Covers the DB/CycleStore persistence of the ``interactive`` flag, the
SessionManager's structured-decision round trip (request → GUI response with
notes/modifications), and the engine's decision points (hypothesis selection,
experiment-plan approval) via method-level stubs.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.api.models.research import CycleStatus, ResearchCycleResponse
from backend.api.services.cycle_store import CycleStore
from backend.api.services.session_manager import SessionManager
from paradigm.knowledge.models import Hypothesis
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.storage.database import Database


@pytest.fixture
def db():
    return Database(Path(tempfile.mkdtemp()) / "cycles.db")


# --- interactive flag persistence -------------------------------------------


def test_db_interactive_flag_roundtrip(db):
    db.create_cycle("c1", "prompt", "directed", "pending", interactive=True)
    db.create_cycle("c2", "prompt", "directed", "pending")
    assert db.get_cycle("c1")["interactive"] == 1
    assert not db.get_cycle("c2")["interactive"]


def test_cycle_store_interactive_roundtrip(db):
    store = CycleStore(db)
    cycle = ResearchCycleResponse(
        cycle_id="c-int",
        seed_prompt="study red noise",
        mode="directed",
        status=CycleStatus.PENDING,
        interactive=True,
        created_at=datetime.now(UTC),
    )
    store.create(cycle)
    loaded = store.get("c-int")
    assert loaded is not None and loaded.interactive is True
    # Default stays off.
    store.create(cycle.model_copy(update={"cycle_id": "c-auto", "interactive": False}))
    assert store.get("c-auto").interactive is False


@pytest.mark.asyncio
async def test_create_session_stores_interactive_meta():
    mgr = SessionManager()
    state = await mgr.create_session("cyc-1", "prompt", interactive=True)
    assert mgr._cycle_metadata[state.session_id]["interactive"] is True


# --- structured decision round trip (SessionManager) ------------------------


@pytest.mark.asyncio
async def test_request_decision_returns_full_response():
    mgr = SessionManager()
    session_id = "sess-1"
    mgr._ws_connections[session_id] = set()

    task = asyncio.create_task(
        mgr._request_decision(
            session_id,
            "hypothesis_selection",
            {"title": "Pick", "choices": [{"id": "h1", "label": "H1"}], "multi_select": True},
        )
    )
    # Let the request register its event, then answer like the GUI would.
    while not mgr._intervention_events:
        await asyncio.sleep(0.01)
    request_id = next(iter(mgr._intervention_events))
    assert request_id.startswith("decision-")
    await mgr.respond_to_approval(
        request_id, "continue", notes="focus on h1", modifications={"selected_ids": ["h1"]}
    )

    response = await asyncio.wait_for(task, timeout=5)
    assert response["decision"] == "continue"
    assert response["notes"] == "focus on h1"
    assert response["modifications"] == {"selected_ids": ["h1"]}


@pytest.mark.asyncio
async def test_request_approval_still_returns_plain_decision():
    mgr = SessionManager()
    session_id = "sess-2"
    mgr._ws_connections[session_id] = set()

    task = asyncio.create_task(mgr._request_approval(session_id, "t1", "ideation", "planning"))
    while not mgr._intervention_events:
        await asyncio.sleep(0.01)
    request_id = next(iter(mgr._intervention_events))
    await mgr.respond_to_approval(request_id, "pause")

    assert await asyncio.wait_for(task, timeout=5) == "pause"


@pytest.mark.asyncio
async def test_respond_to_approval_sanitizes_bad_decision():
    mgr = SessionManager()
    await mgr.respond_to_approval("req-x", "explode", notes="n")
    assert mgr._intervention_responses["req-x"]["decision"] == "continue"


@pytest.mark.asyncio
async def test_decision_request_broadcasts_choices():
    """The GUI message carries the structured fields (choices/default_ids)."""
    mgr = SessionManager()
    session_id = "sess-3"
    sent: list[str] = []

    class _WS:
        async def send_text(self, text: str) -> None:
            sent.append(text)

    mgr._ws_connections[session_id] = {_WS()}
    task = asyncio.create_task(
        mgr._request_decision(
            session_id,
            "hypothesis_selection",
            {
                "title": "Pick hypotheses",
                "choices": [{"id": "h1", "label": "H1", "score": 1520}],
                "multi_select": True,
                "default_ids": ["h1"],
            },
        )
    )
    while not sent:
        await asyncio.sleep(0.01)
    msg = json.loads(sent[0])
    assert msg["type"] == "approval_request"
    assert msg["decision_type"] == "hypothesis_selection"
    assert msg["choices"] == [{"id": "h1", "label": "H1", "score": 1520}]
    assert msg["default_ids"] == ["h1"]
    assert msg["multi_select"] is True
    await mgr.respond_to_approval(msg["request_id"], "continue")
    await asyncio.wait_for(task, timeout=5)


# --- engine decision points (method-level, stubbed engine) -------------------


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return _record

    def named(self, name: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == name]


def _engine_stub(decision_hook):
    """A minimal stand-in exposing exactly what the decision methods touch."""
    stub = SimpleNamespace()
    stub._decision_hook = decision_hook
    stub.state = SimpleNamespace(
        thread_id="t1",
        planning_action_items="1. Fit the PSD slope",
        selected_hypotheses=[],
    )
    stub._logger = _Recorder()
    stub._db = _Recorder()
    stub._display = _Recorder()
    stub._pending_guidance = []
    stub.emit_event = lambda *a, **k: None
    # Bind the real engine methods onto the stub.
    stub._check_decision = OrchestrationEngine._check_decision.__get__(stub)
    stub._apply_decision_action = OrchestrationEngine._apply_decision_action.__get__(stub)
    stub._decide_hypothesis_selection = OrchestrationEngine._decide_hypothesis_selection.__get__(
        stub
    )
    stub._decide_experiment_plan = OrchestrationEngine._decide_experiment_plan.__get__(stub)
    return stub


def _hyps(n=3):
    return [
        Hypothesis(id=f"h{i}", statement=f"Hypothesis {i}", elo_rating=1500 + i) for i in range(n)
    ]


@pytest.mark.asyncio
async def test_check_decision_without_hook_continues():
    stub = _engine_stub(None)
    assert await stub._check_decision("x", {}) == {"decision": "continue"}


@pytest.mark.asyncio
async def test_check_decision_sanitizes_bad_hook_output():
    stub = _engine_stub(lambda *a: "garbage")
    assert await stub._check_decision("x", {}) == {"decision": "continue"}
    stub = _engine_stub(lambda *a: {"decision": "explode"})
    assert await stub._check_decision("x", {}) == {"decision": "continue"}


@pytest.mark.asyncio
async def test_check_decision_survives_raising_hook():
    def _boom(*a):
        raise RuntimeError("ws died")

    stub = _engine_stub(_boom)
    assert await stub._check_decision("x", {}) == {"decision": "continue"}


@pytest.mark.asyncio
async def test_hypothesis_selection_applies_user_subset_and_notes():
    ranked = _hyps(3)
    seen_payloads: list[dict] = []

    def hook(thread_id, decision_type, payload):
        seen_payloads.append(payload)
        return {
            "decision": "continue",
            "notes": "prefer the second one",
            "modifications": {"selected_ids": ["h1"]},
        }

    stub = _engine_stub(hook)
    stub._tournament = SimpleNamespace(ranked_hypotheses=lambda: ranked)
    winners = ranked[:2]

    selected = await stub._decide_hypothesis_selection(winners)

    assert [h.id for h in selected] == ["h1"]
    assert stub._pending_guidance == ["prefer the second one"]
    # The full ranked field was offered, winners preselected.
    assert [c["id"] for c in seen_payloads[0]["choices"]] == ["h0", "h1", "h2"]
    assert seen_payloads[0]["default_ids"] == ["h0", "h1"]


@pytest.mark.asyncio
async def test_hypothesis_selection_keeps_winners_without_modifications():
    ranked = _hyps(3)
    stub = _engine_stub(lambda *a: {"decision": "continue"})
    stub._tournament = SimpleNamespace(ranked_hypotheses=lambda: ranked)
    winners = ranked[:2]
    assert await stub._decide_hypothesis_selection(winners) == winners


@pytest.mark.asyncio
async def test_hypothesis_selection_abort_stops_cycle():
    ranked = _hyps(2)
    stub = _engine_stub(lambda *a: {"decision": "abort"})
    stub._tournament = SimpleNamespace(ranked_hypotheses=lambda: ranked)
    assert await stub._decide_hypothesis_selection(ranked) is None
    assert ("update_thread", ("t1",), {"status": "aborted"}) in stub._db.calls


@pytest.mark.asyncio
async def test_experiment_plan_notes_become_operator_directive():
    stub = _engine_stub(lambda *a: {"decision": "continue", "notes": "use log bins"})
    stopped = await stub._decide_experiment_plan()
    assert stopped is False
    assert stub.state.planning_action_items.startswith("1. Fit the PSD slope")
    assert "OPERATOR DIRECTIVE (must be honored): use log bins" in stub.state.planning_action_items


@pytest.mark.asyncio
async def test_experiment_plan_pause_stops_cycle():
    stub = _engine_stub(lambda *a: {"decision": "pause"})
    assert await stub._decide_experiment_plan() is True
    assert ("update_thread", ("t1",), {"status": "paused"}) in stub._db.calls
