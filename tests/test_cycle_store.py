"""Phase 2: research cycles persist to the DB and orphaned runs are marked
interrupted on startup. Covers the DB cycle methods + the CycleStore wrapper.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.api.models.research import CycleStatus, ResearchCycleResponse
from backend.api.services.cycle_store import CycleStore
from paradigm.storage.database import Database


@pytest.fixture
def db():
    return Database(Path(tempfile.mkdtemp()) / "cycles.db")


def _cycle(cid="cyc-1", status=CycleStatus.PENDING, **kw):
    return ResearchCycleResponse(
        cycle_id=cid,
        seed_prompt="study red noise",
        mode="directed",
        status=status,
        team_roles=["theorist", "analyst"],
        created_at=datetime.now(UTC),
        **kw,
    )


# --- raw DB layer ----------------------------------------------------------
def test_db_cycle_crud_roundtrip(db):
    db.create_cycle("c1", "prompt", "directed", "running", team_roles=["a", "b"])
    row = db.get_cycle("c1")
    assert row["status"] == "running"
    assert row["team_roles"] == ["a", "b"]  # deserialized
    db.update_cycle("c1", status="completed", thread_id="t1", paper_id="p1")
    row = db.get_cycle("c1")
    assert (row["status"], row["thread_id"], row["paper_id"]) == ("completed", "t1", "p1")
    db.delete_cycle("c1")
    assert db.get_cycle("c1") is None


def test_db_mark_interrupted_only_hits_in_progress(db):
    db.create_cycle("done", "p", "directed", "completed")
    db.create_cycle("run", "p", "directed", "running")
    db.create_cycle("paused", "p", "directed", "paused")
    db.create_cycle("pend", "p", "directed", "pending")
    n = db.mark_running_cycles_interrupted()
    assert n == 2  # only running + paused
    assert db.get_cycle("run")["status"] == "interrupted"
    assert db.get_cycle("paused")["status"] == "interrupted"
    assert db.get_cycle("done")["status"] == "completed"  # untouched
    assert db.get_cycle("pend")["status"] == "pending"  # still startable


# --- CycleStore (DB-backed) ------------------------------------------------
def test_store_db_backed_roundtrip(db):
    store = CycleStore(db)
    assert store.persistent
    store.create(_cycle("c1"))
    got = store.get("c1")
    assert got is not None and got.status == CycleStatus.PENDING
    assert got.team_roles == ["theorist", "analyst"]

    store.update("c1", status=CycleStatus.COMPLETED, paper_id="paper-9")
    got = store.get("c1")
    assert got.status == CycleStatus.COMPLETED
    assert got.paper_id == "paper-9"

    store.create(_cycle("c2", status=CycleStatus.RUNNING))
    assert {c.cycle_id for c in store.list()} == {"c1", "c2"}

    store.delete("c1")
    assert store.get("c1") is None


def test_store_survives_new_instance_same_db(db):
    """A fresh CycleStore over the same DB sees prior cycles (restart resilience)."""
    CycleStore(db).create(_cycle("persist-me", status=CycleStatus.RUNNING))
    reborn = CycleStore(db)
    got = reborn.get("persist-me")
    assert got is not None and got.status == CycleStatus.RUNNING
    # And startup marking flips the orphaned run to interrupted.
    assert reborn.mark_interrupted_on_startup() == 1
    assert reborn.get("persist-me").status == CycleStatus.INTERRUPTED


def test_store_interrupted_status_maps_to_enum(db):
    db.create_cycle("x", "p", "directed", "interrupted")
    got = CycleStore(db).get("x")
    assert got.status == CycleStatus.INTERRUPTED


# --- CycleStore (in-memory fallback) --------------------------------------
def test_store_in_memory_fallback_when_no_db():
    store = CycleStore(None)
    assert not store.persistent
    cid = "cyc-mem-test-xyz"
    store.delete(cid)  # ensure clean
    try:
        store.create(_cycle(cid, status=CycleStatus.RUNNING))
        got = store.get(cid)
        assert got is not None and got.status == CycleStatus.RUNNING
        store.update(cid, status=CycleStatus.COMPLETED, session_id="s1")
        got = store.get(cid)
        assert got.status == CycleStatus.COMPLETED and got.session_id == "s1"
        # mark_interrupted is a no-op without a DB.
        assert store.mark_interrupted_on_startup() == 0
    finally:
        store.delete(cid)
