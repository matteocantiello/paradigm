"""Tests for the ExperimentationHandler and ExperimentationResult."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from helpers import make_mock_agent, patch_config_provider

from paradigm.agents.base import Agent, AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.experimentation import ExperimentationResult
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from paradigm.storage.database import Database


class TestExperimentationResultDefaults:
    def test_defaults(self):
        result = ExperimentationResult()
        assert result.execution_context == ""
        assert result.execution_figures == []

    def test_custom_values(self):
        figs = [("exp_1", Path("/tmp/fig.png"))]
        result = ExperimentationResult(execution_context="ctx", execution_figures=figs)
        assert result.execution_context == "ctx"
        assert result.execution_figures == figs

    def test_mutable_default_independence(self):
        r1 = ExperimentationResult()
        r2 = ExperimentationResult()
        r1.execution_figures.append(("a", Path("/tmp/a.png")))
        assert r2.execution_figures == []


class TestExperimentationHandlerReturnsResult:
    @pytest.mark.asyncio
    async def test_handler_returns_result(self, tmp_path):
        """Mock engine, verify the handler returns an ExperimentationResult."""
        config = Config(
            api_key="fake",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "max_experiment_rounds": 1,
                "enable_checkpointing": False,
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        db = Database(tmp_path / "test.db")
        from paradigm.logging.events import EventLogger

        logger = EventLogger(tmp_path / "events.jsonl")
        factory = MagicMock()
        corpus = MagicMock()

        # Create experimentalist agent that returns code
        exp_agent = MagicMock(spec=Agent)
        exp_agent.agent_id = "experimentalist-0"
        exp_agent.skill_profile = "experimentalist"
        exp_agent.generate = AsyncMock(
            return_value=AgentResponse(
                content="```python\n# EXPERIMENT: test_calc\nprint(42)\n```\n",
                usage=TokenUsage(input_tokens=50, output_tokens=80, total_tokens=130),
                model="claude-sonnet-4-5-20250929",
            )
        )
        exp_agent.format_message = MagicMock()

        factory.create_team = MagicMock(return_value=[exp_agent])

        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        engine._agents = {"experimentalist-0": exp_agent}
        engine._thread_id = "test-thread"
        engine._seed_prompt = "test"
        engine._resolved_resources = []
        engine._code_context = ""
        engine._data_context = ""
        engine._checkpoint = None

        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="42\n",
            duration_seconds=0.5,
        )

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_ce:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(return_value=mock_exec_result)
            mock_instance.cleanup = AsyncMock()
            mock_ce.return_value = mock_instance

            result = await engine._experimentation.run_experimentation_phase()

        assert isinstance(result, ExperimentationResult)
        assert "42" in result.execution_context
        db.close()


class TestExperimentationHandlerNoAgent:
    @pytest.mark.asyncio
    async def test_no_agent_skips(self, tmp_path):
        """When no experimentalist or analyst agent exists, returns empty result."""
        config = Config(
            api_key="fake",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "max_experiment_rounds": 1,
                "enable_checkpointing": False,
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        db = Database(tmp_path / "test.db")
        from paradigm.logging.events import EventLogger

        logger = EventLogger(tmp_path / "events.jsonl")
        factory = MagicMock()
        corpus = MagicMock()

        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        # Only a writer agent (no experimentalist or analyst)
        writer = make_mock_agent("writer-0", "writer")
        engine._agents = {"writer-0": writer}
        engine._thread_id = "test-thread"
        engine._seed_prompt = "test"
        engine._resolved_resources = []
        engine._code_context = ""
        engine._data_context = ""
        engine._checkpoint = None

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_ce:
            mock_instance = AsyncMock()
            mock_instance.cleanup = AsyncMock()
            mock_ce.return_value = mock_instance

            result = await engine._experimentation.run_experimentation_phase()

        assert result.execution_context == ""
        assert result.execution_figures == []
        db.close()


class TestExperimentationHandlerCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_on_error(self, tmp_path):
        """executor.cleanup() is called even when an exception occurs."""
        config = Config(
            api_key="fake",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "max_experiment_rounds": 1,
                "enable_checkpointing": False,
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        db = Database(tmp_path / "test.db")
        from paradigm.logging.events import EventLogger

        logger = EventLogger(tmp_path / "events.jsonl")
        factory = MagicMock()
        corpus = MagicMock()

        # Create agent that raises on generate
        exp_agent = MagicMock(spec=Agent)
        exp_agent.agent_id = "experimentalist-0"
        exp_agent.skill_profile = "experimentalist"
        exp_agent.generate = AsyncMock(side_effect=RuntimeError("LLM error"))

        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        engine._agents = {"experimentalist-0": exp_agent}
        engine._thread_id = "test-thread"
        engine._seed_prompt = "test"
        engine._resolved_resources = []
        engine._code_context = ""
        engine._data_context = ""
        engine._checkpoint = None

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_ce:
            mock_instance = AsyncMock()
            mock_instance.cleanup = AsyncMock()
            mock_ce.return_value = mock_instance

            # Should not raise — error is caught inside the handler
            result = await engine._experimentation.run_experimentation_phase()

            # cleanup() must be called even after error
            mock_instance.cleanup.assert_called_once()

        assert result.execution_context == ""
        db.close()
