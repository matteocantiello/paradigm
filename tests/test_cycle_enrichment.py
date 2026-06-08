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

import pytest

from backend.api.models.research import CycleStatus, ResearchCycleResponse
from backend.api.models.session import SessionStatus
from backend.api.routes.research import _enrich_cycle, research_stats, router


def _request(*, state=None, thread=None, token_usage=None):
    mgr = SimpleNamespace(get_state=lambda _sid: state)
    db = SimpleNamespace(
        get_thread=lambda _tid: thread,
        get_token_usage=lambda thread_id=None, agent_id=None: token_usage or {"total_tokens": 0},
    )
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(session_manager=mgr, database=db))
    )


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
    state = SimpleNamespace(
        status=SessionStatus.FAILED, thread_id="thread-9", current_phase="execution"
    )
    cycle = _enrich_cycle(_cycle(), _request(state=state, thread={"current_draft_id": None}))
    assert cycle.status == CycleStatus.FAILED
    assert cycle.paper_id is None


def test_enrich_backfills_stats():
    # End-of-run summary stats: tokens (per-thread) + elapsed (created->updated).
    state = SimpleNamespace(
        status=SessionStatus.COMPLETED, thread_id="thread-1", current_phase="published"
    )
    thread = {
        "current_draft_id": "paper-1",
        "created_at": "2026-06-08 00:00:00",
        "updated_at": "2026-06-08 00:05:30",  # 5m30s
    }
    cycle = _enrich_cycle(
        _cycle(), _request(state=state, thread=thread, token_usage={"total_tokens": 123456})
    )
    assert cycle.total_tokens == 123456
    assert cycle.elapsed_seconds == 330


def test_enrich_stats_none_when_unavailable():
    # No timestamps -> elapsed None; zero tokens -> None (treated as "unknown").
    state = SimpleNamespace(
        status=SessionStatus.COMPLETED, thread_id="thread-1", current_phase="writing"
    )
    cycle = _enrich_cycle(
        _cycle(),
        _request(state=state, thread={"current_draft_id": "p"}, token_usage={"total_tokens": 0}),
    )
    assert cycle.elapsed_seconds is None
    assert cycle.total_tokens is None


@pytest.mark.asyncio
async def test_research_stats_counts():
    store = SimpleNamespace(list=lambda: [object(), object(), object()])  # 3 cycles
    db = SimpleNamespace(
        list_papers=lambda status=None, limit=None: (
            [{"id": "p1"}, {"id": "p2"}] if status == "published" else []
        ),
        get_token_usage=lambda: {"total_tokens": 500000},
    )
    req = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(cycle_store=store, database=db))
    )
    stats = await research_stats(req)
    assert stats.total_cycles == 3
    assert stats.papers_published == 2
    assert stats.total_tokens == 500000


def test_stats_route_declared_before_cycle_id():
    # /stats must be registered before /{cycle_id} or "stats" is matched as an id.
    paths = [
        r.path for r in router.routes if getattr(r, "path", "").endswith(("/stats", "/{cycle_id}"))
    ]
    assert paths.index(next(p for p in paths if p.endswith("/stats"))) < paths.index(
        next(p for p in paths if p.endswith("/{cycle_id}"))
    )
