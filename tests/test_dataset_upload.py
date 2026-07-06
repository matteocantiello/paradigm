"""Dataset attachment: the raw-body upload endpoint + cycle datasets persistence.

Files land in data/uploads/<cycle_id>/ and are staged into the sandbox shared
data dir (with data-card previews) by the engine when the session starts.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.models.research import CycleStatus, ResearchCycleResponse
from backend.api.routes.research import upload_cycle_dataset
from backend.api.services.cycle_store import CycleStore
from paradigm.storage.database import Database


@pytest.fixture
def db():
    return Database(Path(tempfile.mkdtemp()) / "upload.db")


@pytest.fixture
def store(db):
    return CycleStore(db)


def _cycle(store, status=CycleStatus.PENDING):
    cycle = ResearchCycleResponse(
        cycle_id="cycle-abc",
        seed_prompt="Analyze the data",
        mode="directed",
        status=status,
        created_at=datetime.now(UTC),
    )
    store.create(cycle)
    if status != CycleStatus.PENDING:
        store.update("cycle-abc", status=status)
    return cycle


class FakeRequest:
    def __init__(self, store, data_dir, chunks):
        config = SimpleNamespace(storage=SimpleNamespace(data_dir=data_dir))
        self.app = SimpleNamespace(state=SimpleNamespace(cycle_store=store, config=config))
        self._chunks = chunks

    async def stream(self):
        for c in self._chunks:
            yield c


@pytest.mark.asyncio
async def test_upload_happy_path(store, tmp_path):
    _cycle(store)
    req = FakeRequest(store, tmp_path, [b"star,teff\n", b"HD1,31000\n"])
    updated = await upload_cycle_dataset("cycle-abc", "obs.csv", req)
    assert updated.datasets is not None and len(updated.datasets) == 1
    staged = Path(updated.datasets[0])
    assert staged.exists()
    assert staged.parent == tmp_path / "uploads" / "cycle-abc"
    assert staged.read_bytes() == b"star,teff\nHD1,31000\n"
    # Persisted: survives a store re-read.
    assert store.get("cycle-abc").datasets == [str(staged)]


@pytest.mark.asyncio
async def test_upload_traversal_name_sanitized(store, tmp_path):
    _cycle(store)
    req = FakeRequest(store, tmp_path, [b"x\n"])
    updated = await upload_cycle_dataset("cycle-abc", "../../etc/passwd.csv", req)
    staged = Path(updated.datasets[0])
    assert staged.parent == tmp_path / "uploads" / "cycle-abc"  # no escape
    assert ".." not in staged.name


@pytest.mark.asyncio
async def test_upload_collision_gets_suffix(store, tmp_path):
    _cycle(store)
    await upload_cycle_dataset("cycle-abc", "obs.csv", FakeRequest(store, tmp_path, [b"a\n"]))
    updated = await upload_cycle_dataset(
        "cycle-abc", "obs.csv", FakeRequest(store, tmp_path, [b"b\n"])
    )
    names = [Path(p).name for p in updated.datasets]
    assert len(set(names)) == 2


@pytest.mark.asyncio
async def test_upload_rejected_after_start(store, tmp_path):
    _cycle(store, status=CycleStatus.RUNNING)
    with pytest.raises(HTTPException) as e:
        await upload_cycle_dataset("cycle-abc", "obs.csv", FakeRequest(store, tmp_path, [b"x"]))
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_upload_unknown_cycle_404(store, tmp_path):
    with pytest.raises(HTTPException) as e:
        await upload_cycle_dataset("nope", "obs.csv", FakeRequest(store, tmp_path, [b"x"]))
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_bad_extension_415(store, tmp_path):
    _cycle(store)
    with pytest.raises(HTTPException) as e:
        await upload_cycle_dataset("cycle-abc", "malware.exe", FakeRequest(store, tmp_path, [b"x"]))
    assert e.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_size_cap_413_and_partial_removed(store, tmp_path, monkeypatch):
    import backend.api.routes.research as rr

    monkeypatch.setattr(rr, "_DATASET_MAX_BYTES", 10)
    _cycle(store)
    with pytest.raises(HTTPException) as e:
        await upload_cycle_dataset(
            "cycle-abc", "big.csv", FakeRequest(store, tmp_path, [b"0123456789ABCDEF"])
        )
    assert e.value.status_code == 413
    assert list((tmp_path / "uploads" / "cycle-abc").glob("*")) == []  # partial cleaned


@pytest.mark.asyncio
async def test_upload_empty_body_400(store, tmp_path):
    _cycle(store)
    with pytest.raises(HTTPException) as e:
        await upload_cycle_dataset("cycle-abc", "obs.csv", FakeRequest(store, tmp_path, []))
    assert e.value.status_code == 400
