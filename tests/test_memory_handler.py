"""Tests for the MemoryHandler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from helpers import make_mock_agent, patch_config_provider

from paradigm.config import Config
from paradigm.logging.events import EventLogger
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.storage.database import Database


def _make_engine(tmp_path, memory_store=None):
    """Create a minimal engine for memory handler testing."""
    config = Config(
        api_key="fake",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={"max_rounds_per_phase": 1},
    )
    patch_config_provider(config)
    db = Database(tmp_path / "test.db")
    logger = EventLogger(tmp_path / "events.jsonl")
    factory = MagicMock()
    factory.create_team = MagicMock(return_value=[])
    corpus = MagicMock()
    display = MagicMock()
    engine = OrchestrationEngine(
        config=config,
        database=db,
        corpus=corpus,
        logger=logger,
        agent_factory=factory,
        memory_store=memory_store,
        display=display,
    )
    engine.state.thread_id = "test-thread"
    engine.state.seed_prompt = "test topic"
    engine.state.agents = {"agent-0": make_mock_agent("agent-0", "theorist")}
    return engine, db


class TestMemorySkippedStoreNone:
    @pytest.mark.asyncio
    async def test_skipped_when_store_none(self, tmp_path):
        """Early return when no memory store is provided."""
        engine, db = _make_engine(tmp_path, memory_store=None)
        # Should complete without error — no reflection call
        await engine._memory.run_memory_generation()
        db.close()


class TestMemorySkippedDisabled:
    @pytest.mark.asyncio
    async def test_skipped_when_disabled(self, tmp_path):
        """Early return when memory is disabled in config."""
        mock_store = MagicMock()
        engine, db = _make_engine(tmp_path, memory_store=mock_store)
        engine._config.memory.enabled = False
        await engine._memory.run_memory_generation()
        # add_memories should not be called
        mock_store.add_memories.assert_not_called()
        db.close()


class TestMemoryGenerationCallsReflections:
    @pytest.mark.asyncio
    async def test_calls_generate_reflections(self, tmp_path):
        """Verify generate_reflections is called with correct args."""
        mock_store = MagicMock()
        engine, db = _make_engine(tmp_path, memory_store=mock_store)
        engine._config.memory.enabled = True

        # Create the thread in DB so get_thread works
        db.create_thread(thread_id="test-thread", title="test", mode="directed", participants=[])

        mock_reflection = MagicMock()
        mock_reflection.agent_id = "agent-0"
        mock_reflection.memories = [MagicMock(), MagicMock()]

        with patch(
            "paradigm.agents.memory.generate_reflections",
            new_callable=AsyncMock,
            return_value=[mock_reflection],
        ) as mock_gen:
            await engine._memory.run_memory_generation()
            mock_gen.assert_called_once()
            # Verify memories were stored
            mock_store.add_memories.assert_called_once_with(mock_reflection.memories)
        db.close()


class TestMemoryErrorCaught:
    @pytest.mark.asyncio
    async def test_error_caught(self, tmp_path):
        """Exception in generate_reflections calls display.memory_error()."""
        mock_store = MagicMock()
        engine, db = _make_engine(tmp_path, memory_store=mock_store)
        engine._config.memory.enabled = True

        with patch(
            "paradigm.agents.memory.generate_reflections",
            new_callable=AsyncMock,
            side_effect=RuntimeError("reflection failed"),
        ):
            # Should not raise
            await engine._memory.run_memory_generation()

        # memory_error should have been called on the display
        engine._display.memory_error.assert_called_once()
        db.close()


class TestMemoryGenerationTimeout:
    @pytest.mark.asyncio
    async def test_hanging_reflection_does_not_block(self, tmp_path):
        """A reflection call that hangs is bounded — the cycle can still finalize.

        Without the timeout guard a stuck LLM call here leaves the whole run
        unable to reach its terminal state (the live UI stalls forever).
        """
        import asyncio

        mock_store = MagicMock()
        engine, db = _make_engine(tmp_path, memory_store=mock_store)
        engine._config.memory.enabled = True

        async def _never_returns(*args, **kwargs):
            await asyncio.sleep(60)  # would hang past the (patched) timeout

        with (
            patch("paradigm.orchestrator.memory._REFLECTION_TIMEOUT_S", 0.05),
            patch(
                "paradigm.agents.memory.generate_reflections",
                new=_never_returns,
            ),
        ):
            # Must return promptly (≈ the patched timeout), not hang for 60s.
            await asyncio.wait_for(engine._memory.run_memory_generation(), timeout=5)

        # Timed out -> treated as a (non-fatal) error; no memories stored.
        engine._display.memory_error.assert_called_once()
        mock_store.add_memories.assert_not_called()
        db.close()
