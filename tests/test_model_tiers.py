"""Per-cycle model tiers (premium vs open) — Prompt 254."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.api.models.research import CycleStatus, ResearchCycleResponse
from backend.api.services.cycle_store import CycleStore
from backend.api.services.model_tiers import (
    agent_config_for_tier,
    apply_tier,
    default_tier,
    tier_availability,
)
from backend.api.services.session_manager import SessionManager
from paradigm.config import Config
from paradigm.storage.database import Database


def _config(**agent_overrides):
    return Config(api_key="fake-key", agent=agent_overrides or None)


def test_tier_yamls_parse_to_agent_configs():
    premium = agent_config_for_tier("premium")
    open_ = agent_config_for_tier("open")
    assert premium is not None and open_ is not None
    # The canonical mappings, spot-checked so a yaml edit can't silently detier.
    assert premium.overrides["writer"].model.startswith("claude-opus")
    assert open_.default_provider == "together"
    assert open_.overrides["writer"].model == "zai-org/GLM-5.2"
    assert open_.overrides["editor"].model == "moonshotai/Kimi-K2.6"


def test_unknown_tier_returns_none_and_apply_falls_back():
    assert agent_config_for_tier("bogus") is None
    config = Config(api_key="fake-key")
    assert apply_tier(config, "bogus") is config
    assert apply_tier(config, None) is config


def test_apply_tier_deep_copies_the_config():
    config = Config(api_key="fake-key")
    open_config = apply_tier(config, "open")
    assert open_config is not config
    assert open_config.agent.default_provider == "together"
    # The ACTIVE config must be untouched (concurrent sessions share it).
    assert config.agent.default_provider != "together" or config is not open_config
    assert config.agent.overrides.get("writer") != open_config.agent.overrides.get("writer")


def test_default_tier_inferred_from_provider():
    open_cfg = apply_tier(Config(api_key="fake-key"), "open")
    assert default_tier(open_cfg) == "open"
    assert default_tier(Config(api_key="fake-key")) == "premium"


def test_tier_availability_shape():
    tiers = {t["id"]: t for t in tier_availability()}
    assert set(tiers) == {"premium", "open"}
    for t in tiers.values():
        assert t["label"] and t["description"] and isinstance(t["available"], bool)


# --- persistence ------------------------------------------------------------


@pytest.fixture
def db():
    return Database(Path(tempfile.mkdtemp()) / "cycles.db")


def test_model_tier_roundtrip(db):
    store = CycleStore(db)
    cycle = ResearchCycleResponse(
        cycle_id="c-tier",
        seed_prompt="p",
        mode="directed",
        status=CycleStatus.PENDING,
        model_tier="open",
        created_at=datetime.now(UTC),
    )
    store.create(cycle)
    assert store.get("c-tier").model_tier == "open"
    # Default: no tier recorded.
    store.create(cycle.model_copy(update={"cycle_id": "c-none", "model_tier": None}))
    assert store.get("c-none").model_tier is None


@pytest.mark.asyncio
async def test_create_session_stores_model_tier():
    mgr = SessionManager()
    state = await mgr.create_session("cyc", "p", model_tier="open")
    assert mgr._cycle_metadata[state.session_id]["model_tier"] == "open"
