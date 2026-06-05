"""Regression: an empty team_roles list must fall back to the default team.

Bug (prompt 107): the GUI sent team_roles=[] (all roles deselected). The engine
only defaulted on `None`, so it built ZERO agents — every phase raced through
producing nothing and the run died at writing with "insufficient content
(0 chars)". Both [] and None must yield the default team.
"""

from __future__ import annotations

import pytest
from helpers import patch_config_provider

from paradigm.config import Config
from paradigm.orchestrator.engine import OrchestrationEngine


@pytest.fixture
def cfg(tmp_path):
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 1,
            "checkpoint_interval": 1,
            "enable_writing": False,
            "enable_experimentation": False,
        },
    )
    patch_config_provider(config)
    return config


@pytest.mark.asyncio
@pytest.mark.parametrize("team", [[], None])
async def test_empty_or_none_team_uses_default_team(
    team, cfg, tmp_db, tmp_logger, mock_factory, mock_corpus
):
    engine = OrchestrationEngine(
        config=cfg,
        database=tmp_db,
        corpus=mock_corpus,
        logger=tmp_logger,
        agent_factory=mock_factory,
    )
    await engine.run_research_cycle(seed_prompt="test topic", mode="directed", team_roles=team)
    # The team was built from defaults, not left at zero agents.
    assert len(engine.state.agents) > 0
