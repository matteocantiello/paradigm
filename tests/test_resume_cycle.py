"""Phase 3: resume/continue a cycle from its checkpoint with optional steering.

The resume endpoint builds a continuation note from the prior thread's checkpoint
+ the operator comment, creates a linked continuation cycle, and delivers the
note to the new run via the steering inbox (reusing the Phase-99 guidance path).
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.models.research import CycleStatus, ResearchCycleResponse, ResumeRequest
from backend.api.routes.research import (
    _build_continuation_note,
    _json_list,
    resume_research_cycle,
)
from backend.api.services.cycle_store import CycleStore
from paradigm.storage.database import Database


@pytest.fixture
def db():
    return Database(Path(tempfile.mkdtemp()) / "resume.db")


class FakeManager:
    """Records guidance + hands back a session, without running the engine."""

    def __init__(self):
        self.guidance: list[tuple[str, str]] = []
        self.started: list[str] = []
        self._n = 0

    async def create_session(self, cycle_id, seed_prompt, mode, team_roles):
        self._n += 1
        return SimpleNamespace(
            session_id=f"sess-{self._n}",
            status=SimpleNamespace(value="running"),
            thread_id=None,
            current_phase=None,
            created_at=datetime.now(UTC),
        )

    async def queue_user_guidance(self, session_id, note):
        self.guidance.append((session_id, note))

    async def start_session(self, session_id):
        self.started.append(session_id)

    def get_state(self, session_id):
        return None  # no live overlay needed for the test


def _request(store, mgr, db):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(cycle_store=store, session_manager=mgr, database=db))
    )


# --- helpers ---------------------------------------------------------------
def test_json_list_coerces_json_and_lists():
    assert _json_list('["a", "b"]') == ["a", "b"]
    assert _json_list(["x", 1]) == ["x", "1"]
    assert _json_list(None) == []
    assert _json_list("not json{") == []


def test_continuation_note_without_thread_or_comment():
    prior = ResearchCycleResponse(
        cycle_id="c", seed_prompt="s", mode="directed",
        status=CycleStatus.INTERRUPTED, current_phase=None, created_at=datetime.now(UTC),
    )
    note = _build_continuation_note(None, prior, "")
    assert "CONTINUING" in note and "an earlier phase" in note


# --- the resume endpoint ---------------------------------------------------
@pytest.mark.asyncio
async def test_resume_creates_linked_continuation_and_queues_guidance(db):
    db.create_thread("thread-old", "study red noise", "directed", ["theorist"])
    db.update_thread(
        "thread-old",
        hypothesis="Red noise traces convection",
        key_findings=["nu_char scales with Teff"],
        next_steps=["fit a broken power law"],
        checkpoint_summary="Reached writing with a draft outline.",
        current_phase="writing",
    )
    store = CycleStore(db)
    # Mirror the real lifecycle: created minimal, then enriched during the run.
    store.create(ResearchCycleResponse(
        cycle_id="cyc-old", seed_prompt="study red noise", mode="directed",
        status=CycleStatus.PENDING, team_roles=["theorist", "analyst"],
        created_at=datetime.now(UTC),
    ))
    store.update(
        "cyc-old", status=CycleStatus.INTERRUPTED, thread_id="thread-old", current_phase="writing"
    )
    mgr = FakeManager()
    request = _request(store, mgr, db)

    new = await resume_research_cycle("cyc-old", request, ResumeRequest(comment="focus on the LMC sample"))

    # A NEW continuation cycle, linked + running, preserving prompt/team.
    assert new.cycle_id != "cyc-old"
    assert new.resumed_from == "cyc-old"
    assert new.status == CycleStatus.RUNNING
    assert new.session_id is not None
    assert new.seed_prompt == "study red noise"
    assert new.team_roles == ["theorist", "analyst"]

    # The continuation context (checkpoint + steering) was queued as guidance for
    # the new run, before it started.
    assert len(mgr.guidance) == 1 and mgr.started == [new.session_id]
    sid, note = mgr.guidance[0]
    assert sid == new.session_id
    assert "Established hypothesis: Red noise traces convection" in note
    assert "nu_char scales with Teff" in note
    assert "focus on the LMC sample" in note

    # Persisted with lineage; the original is untouched.
    assert store.get(new.cycle_id).resumed_from == "cyc-old"
    assert store.get("cyc-old").status == CycleStatus.INTERRUPTED


@pytest.mark.asyncio
async def test_resume_unknown_cycle_404(db):
    store = CycleStore(db)
    with pytest.raises(HTTPException) as exc:
        await resume_research_cycle("nope", _request(store, FakeManager(), db), None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_resume_works_without_checkpoint_or_comment(db):
    """A cycle with no thread/checkpoint still resumes (continuation, no prior context)."""
    store = CycleStore(db)
    store.create(ResearchCycleResponse(
        cycle_id="bare", seed_prompt="topic", mode="directed",
        status=CycleStatus.FAILED, created_at=datetime.now(UTC),
    ))
    mgr = FakeManager()
    new = await resume_research_cycle("bare", _request(store, mgr, db), None)
    assert new.resumed_from == "bare" and new.status == CycleStatus.RUNNING
    assert len(mgr.guidance) == 1  # still queues the continuation preamble
