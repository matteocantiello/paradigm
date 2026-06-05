"""Tests for real human steering: GUI guidance reaches the running cycle.

Before this, the backend dropped ``user_message``/``user_intervention`` on the
floor. Now they queue into a per-session inbox that the engine drains at each
round boundary and injects into agent prompts.
"""

from __future__ import annotations

import json

import pytest
from helpers import patch_config_provider

from paradigm.config import Config
from paradigm.logging.events import EventType
from paradigm.orchestrator.engine import OrchestrationEngine


@pytest.fixture
def guidance_config(tmp_path):
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 2,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": False,
            "enable_experimentation": False,
        },
    )
    patch_config_provider(config)
    return config


@pytest.mark.asyncio
async def test_guidance_injected_into_agent_prompts(
    guidance_config, tmp_db, tmp_logger, mock_factory, mock_corpus
):
    """Guidance returned by the provider lands in agent prompts + is logged."""
    drained = {"n": 0}

    async def guidance_provider() -> list[str]:
        drained["n"] += 1
        # Deliver guidance only on the very first drain.
        return ["Focus on red-noise systematics"] if drained["n"] == 1 else []

    engine = OrchestrationEngine(
        config=guidance_config,
        database=tmp_db,
        corpus=mock_corpus,
        logger=tmp_logger,
        agent_factory=mock_factory,
        guidance_provider=guidance_provider,
    )

    await engine.run_research_cycle(seed_prompt="Test stellar variability", mode="directed")

    # The guidance reached at least one agent's prompt, under the operator header.
    prompts = [
        call.args[0]
        for agent in engine.state.agents.values()
        for call in agent.generate.call_args_list
        if call.args
    ]
    assert any(
        "HUMAN GUIDANCE" in p and "red-noise systematics" in p for p in prompts
    ), "guidance was not injected into any agent prompt"

    # It only applied for the round it was drained — not re-injected forever.
    hits = sum("red-noise systematics" in p for p in prompts)
    assert hits < len(prompts), "guidance should not appear in every single prompt"

    # And a USER_GUIDANCE event was logged for the activity timeline.
    logged = tmp_logger.log_path.read_text().splitlines()
    types = [json.loads(line).get("event_type") for line in logged if line.strip()]
    assert EventType.USER_GUIDANCE.value in types


@pytest.mark.asyncio
async def test_no_guidance_provider_is_a_noop(
    guidance_config, tmp_db, tmp_logger, mock_factory, mock_corpus
):
    """The CLI path (no provider) behaves exactly as before — no guidance block."""
    engine = OrchestrationEngine(
        config=guidance_config,
        database=tmp_db,
        corpus=mock_corpus,
        logger=tmp_logger,
        agent_factory=mock_factory,
    )
    await engine.run_research_cycle(seed_prompt="Test", mode="directed")
    prompts = [
        call.args[0]
        for agent in engine.state.agents.values()
        for call in agent.generate.call_args_list
        if call.args
    ]
    assert prompts and not any("HUMAN GUIDANCE" in p for p in prompts)


@pytest.mark.asyncio
async def test_session_manager_guidance_inbox_round_trip():
    """queue_user_guidance stages a line; the provider drains and empties it."""
    from backend.api.services.session_manager import SessionManager

    mgr = SessionManager()
    sid = "s-guide"
    provider = mgr._make_guidance_provider(sid)

    assert await provider() == []  # empty inbox

    await mgr.queue_user_guidance(sid, "Try a lower learning rate", target_agent=None)
    await mgr.queue_user_guidance(sid, "Check the GP kernel", target_agent="analyst-1")

    drained = await provider()
    assert drained == ["Try a lower learning rate", "(to analyst-1) Check the GP kernel"]
    # Inbox is emptied after a drain (applied once).
    assert await provider() == []


@pytest.mark.asyncio
async def test_queue_user_guidance_ignores_blank():
    from backend.api.services.session_manager import SessionManager

    mgr = SessionManager()
    await mgr.queue_user_guidance("s", "   ", None)
    assert await mgr._make_guidance_provider("s")() == []
