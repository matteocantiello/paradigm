"""Tests for research-cycle enrichment.

The in-memory cycle row is only written at create/start, so without enrichment
it shows "running" forever and never learns its paper. `_enrich_cycle` backfills
the live terminal status + produced paper from the session state and DB thread,
which is what makes the research tab honest and the end-of-run "View paper"
action work.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from backend.api.models.research import CycleStatus, ResearchCycleResponse
from backend.api.models.session import SessionStatus
from backend.api.routes.research import _enrich_cycle


def _request(*, state=None, thread=None):
    mgr = SimpleNamespace(get_state=lambda _sid: state)
    db = SimpleNamespace(get_thread=lambda _tid: thread)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_manager=mgr, database=db)))


def _cycle(**kw) -> ResearchCycleResponse:
    base = dict(
        cycle_id="c1",
        seed_prompt="x",
        mode="directed",
        status=CycleStatus.RUNNING,
        session_id="s1",
        created_at=datetime.now(UTC),
    )
    base.update(kw)
    return ResearchCycleResponse(**base)


def test_enrich_backfills_terminal_status_and_paper():
    state = SimpleNamespace(
        status=SessionStatus.COMPLETED, thread_id="thread-1", current_phase="writing"
    )
    thread = {"current_draft_id": "paper-1", "current_phase": "writing"}
    cycle = _enrich_cycle(_cycle(), _request(state=state, thread=thread))
    assert cycle.status == CycleStatus.COMPLETED
    assert cycle.thread_id == "thread-1"
    assert cycle.paper_id == "paper-1"
    assert cycle.current_phase == "writing"


def test_enrich_ignores_unmappable_status():
    # SessionStatus.STARTING has no CycleStatus member — must not raise, must keep prior.
    state = SimpleNamespace(status=SessionStatus.STARTING, thread_id=None, current_phase=None)
    cycle = _enrich_cycle(_cycle(status=CycleStatus.RUNNING), _request(state=state))
    assert cycle.status == CycleStatus.RUNNING


def test_enrich_no_session_is_noop():
    cycle = _enrich_cycle(_cycle(session_id=None, status=CycleStatus.PENDING), _request(state=None))
    assert cycle.status == CycleStatus.PENDING
    assert cycle.paper_id is None


def test_enrich_failure_state_without_paper():
    state = SimpleNamespace(status=SessionStatus.FAILED, thread_id="thread-9", current_phase="execution")
    cycle = _enrich_cycle(_cycle(), _request(state=state, thread={"current_draft_id": None}))
    assert cycle.status == CycleStatus.FAILED
    assert cycle.paper_id is None
