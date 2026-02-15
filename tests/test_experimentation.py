"""Tests for the EXECUTION phase: code extraction, result formatting, and integration."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from helpers import make_mock_agent, patch_config_provider

from paradigm.agents.base import Agent, AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.logging.events import EventLogger
from paradigm.orchestrator.constants import (
    _extract_code_blocks,
    _format_execution_result,
    _is_vacuous_success,
)
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.sandbox.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    OutputFile,
)
from paradigm.storage.database import Database

# --- Fixtures ---


@pytest.fixture
def mock_config(tmp_path):
    """Create a config with experimentation enabled and small round counts."""
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 1,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": False,
            "enable_experimentation": True,
            "max_experiment_rounds": 2,
        },
        sandbox={"enabled": True},
    )
    patch_config_provider(config)
    return config


@pytest.fixture
def mock_config_no_sandbox(tmp_path):
    """Config with sandbox disabled."""
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 1,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": False,
            "enable_experimentation": True,
            "max_experiment_rounds": 2,
        },
        sandbox={"enabled": False},
    )
    patch_config_provider(config)
    return config


def _make_experiment_agent(agent_id: str, role: str) -> Agent:
    """Create a mock experimentalist that returns code blocks."""
    agent = MagicMock(spec=Agent)
    agent.agent_id = agent_id
    agent.skill_profile = role

    code_response = AgentResponse(
        content=(
            "Here is the experiment:\n"
            "```python\n"
            "# EXPERIMENT: test_calc\n"
            "import numpy as np\n"
            "print(np.mean([1, 2, 3]))\n"
            "```\n"
        ),
        usage=TokenUsage(input_tokens=50, output_tokens=80, total_tokens=130),
        model="claude-sonnet-4-5-20250929",
    )
    agent.generate = AsyncMock(return_value=code_response)

    def _format_message(to, thread_id, phase, message_type, content, **kwargs):
        msg = MagicMock()
        msg.model_dump.return_value = {
            "from": agent_id,
            "to": to,
            "thread_id": thread_id,
            "phase": phase,
            "type": message_type,
            "content": content,
            "references": [],
            "metadata": {},
        }
        return msg

    agent.format_message = MagicMock(side_effect=_format_message)
    return agent


@pytest.fixture
def mock_factory_with_code():
    """Create a mock AgentFactory where experimentalists return code blocks."""
    factory = MagicMock()

    def _create_team(roles, skill_mode="default"):
        agents = []
        for role in roles:
            if role == "experimentalist":
                agents.append(_make_experiment_agent(f"{role}-0", role))
            else:
                agents.append(make_mock_agent(f"{role}-0", role))
        return agents

    factory.create_team = MagicMock(side_effect=_create_team)
    return factory


# --- Unit tests: code extraction ---


class TestExtractCodeBlocks:
    def test_single_block_with_name(self):
        text = (
            "Here is my experiment:\n"
            "```python\n"
            "# EXPERIMENT: test_gravity\n"
            "import numpy as np\n"
            "print(np.pi)\n"
            "```\n"
        )
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0][0] == "test_gravity"
        assert "import numpy" in blocks[0][1]

    def test_multiple_blocks(self):
        text = (
            "First experiment:\n"
            "```python\n"
            "# EXPERIMENT: exp_one\n"
            "print('one')\n"
            "```\n"
            "Second experiment:\n"
            "```python\n"
            "# EXPERIMENT: exp_two\n"
            "print('two')\n"
            "```\n"
        )
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 2
        assert blocks[0][0] == "exp_one"
        assert blocks[1][0] == "exp_two"

    def test_no_name_defaults(self):
        text = "```python\nprint('hello')\n```\n"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0][0] == "unnamed_experiment"

    def test_no_code_returns_empty(self):
        text = "I think we should analyze the data carefully."
        blocks = _extract_code_blocks(text)
        assert blocks == []


# --- Unit tests: result formatting ---


class TestFormatExecutionResult:
    def test_success_with_output_files(self):
        request = ExecutionRequest(code="print(1)", agent_id="exp-0", thread_id="t-1")
        result = ExecutionResult(
            request=request,
            status=ExecutionStatus.SUCCESS,
            stdout="Result: 42\n",
            duration_seconds=1.5,
            output_files=[OutputFile(filename="plot.png", path="/tmp/plot.png", size_bytes=1024)],
        )
        formatted = _format_execution_result("gravity_test", result)
        assert "gravity_test" in formatted
        assert "success" in formatted.lower()
        assert "42" in formatted
        assert "plot.png" in formatted

    def test_failure_with_stderr(self):
        request = ExecutionRequest(code="bad code", agent_id="exp-0", thread_id="t-1")
        result = ExecutionResult(
            request=request,
            status=ExecutionStatus.FAILURE,
            stderr="NameError: name 'bad' is not defined",
            error_message="Process exited with code 1",
        )
        formatted = _format_execution_result("bad_exp", result)
        assert "failure" in formatted.lower()
        assert "NameError" in formatted
        assert "Process exited" in formatted


# --- Integration tests: engine with execution phase ---


class TestExecutionPhaseIntegration:
    @pytest.mark.asyncio
    async def test_execution_skipped_no_experimentalist(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Team without experimentalist skips EXECUTION phase."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=mock_factory,
        )

        # Use explicit team without experimentalist
        thread_id = await engine.run_research_cycle(
            seed_prompt="Test directed mode",
            mode="directed",
            team_roles=["theorist", "analyst", "synthesizer", "skeptic", "writer", "editor"],
        )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "planning_complete"
        # Phase should end at planning (no execution transition)
        assert thread["current_phase"] == "planning"

    @pytest.mark.asyncio
    async def test_execution_skipped_sandbox_disabled(
        self, mock_config_no_sandbox, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Even with experimentalist, sandbox disabled means no execution."""
        engine = OrchestrationEngine(
            config=mock_config_no_sandbox,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=mock_factory,
        )

        thread_id = await engine.run_research_cycle(
            seed_prompt="Test sandbox disabled",
            mode="experimental",
        )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "planning_complete"
        assert thread["current_phase"] == "planning"

    @pytest.mark.asyncio
    async def test_execution_phase_runs(
        self, mock_config, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """Full execution phase with mocked CodeExecutor."""
        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="2.0\n",
            duration_seconds=0.5,
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(return_value=mock_exec_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory_with_code,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test execution",
                mode="experimental",
            )

            # Executor was called (experimentalist produces code blocks)
            assert mock_executor_instance.execute.call_count >= 1

            # Experimentalist was called during EXECUTION phase
            exp_agent = engine._find_agent_by_role("experimentalist")
            assert exp_agent is not None
            assert exp_agent.generate.call_count >= 3

        thread = tmp_db.get_thread(thread_id)
        assert thread["current_phase"] in ("execution", "planning")

    @pytest.mark.asyncio
    async def test_retry_on_safety_rejection(
        self, mock_config, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """Safety rejection triggers retry with feedback."""
        rejected_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.REJECTED,
            error_message="Dangerous os.system call detected",
        )
        success_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Mean: 42.3, Std: 5.1, N=1000 samples\n",
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            # First call: rejected, second call: success
            mock_executor_instance.execute = AsyncMock(
                side_effect=[rejected_result, success_result]
            )
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory_with_code,
            )

            # Set config to 1 experiment round so we only get the retry behavior
            mock_config.orchestrator.max_experiment_rounds = 1

            await engine.run_research_cycle(
                seed_prompt="Test retry",
                mode="experimental",
            )

            # Executor should have been called twice (reject + retry success)
            assert mock_executor_instance.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_execution_failure(
        self, mock_config, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """Execution failure triggers retry with error feedback."""
        failure_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.FAILURE,
            stderr="NameError: name 'foo' is not defined",
            error_message="Process exited with code 1",
        )
        success_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Result: 42.3 +/- 5.1 (N=1000)\n",
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(side_effect=[failure_result, success_result])
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory_with_code,
            )

            mock_config.orchestrator.max_experiment_rounds = 1

            await engine.run_research_cycle(
                seed_prompt="Test failure retry",
                mode="experimental",
            )

            assert mock_executor_instance.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_high_failure_rate(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        """Circuit breaker stops execution when >70% of experiments fail in a round."""
        # Agent proposes 3 experiments per round — all will fail
        multi_code_agent = MagicMock(spec=Agent)
        multi_code_agent.agent_id = "experimentalist-0"
        multi_code_agent.skill_profile = "experimentalist"
        multi_code_agent.generate = AsyncMock(
            return_value=AgentResponse(
                content=(
                    "```python\n# EXPERIMENT: exp_a\nprint('a')\n```\n"
                    "```python\n# EXPERIMENT: exp_b\nprint('b')\n```\n"
                    "```python\n# EXPERIMENT: exp_c\nprint('c')\n```\n"
                ),
                usage=TokenUsage(input_tokens=50, output_tokens=80, total_tokens=130),
                model="claude-sonnet-4-5-20250929",
            )
        )
        multi_code_agent.format_message = MagicMock(
            side_effect=lambda to, thread_id, phase, message_type, content, **kw: MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "from": "experimentalist-0",
                        "to": to,
                        "thread_id": thread_id,
                        "phase": phase,
                        "type": message_type,
                        "content": content,
                        "references": [],
                        "metadata": {},
                    }
                )
            )
        )

        factory = MagicMock()
        factory.create_team = MagicMock(
            side_effect=lambda roles, skill_mode="default": [
                multi_code_agent if r == "experimentalist" else make_mock_agent(f"{r}-0", r)
                for r in roles
            ]
        )

        failure_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.FAILURE,
            stderr="NameError: something broke",
            error_message="Process exited with code 1",
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            # All executions fail (including retries)
            mock_executor_instance.execute = AsyncMock(return_value=failure_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            mock_config.orchestrator.max_experiment_rounds = 3

            await engine.run_research_cycle(
                seed_prompt="Test circuit breaker",
                mode="experimental",
            )

            # Circuit breaker fires after round 1: only 1 proposal call in
            # EXECUTION (plus retries and ideation/planning calls).
            # Without circuit breaker, 3 rounds would triple the executor calls.
            round_1_executor_calls = mock_executor_instance.execute.call_count
            # 3 experiments × 3 attempts (1 initial + 2 retries) = 9
            assert round_1_executor_calls == 9
            # With 3 rounds it would be 27 — circuit breaker saved 2 rounds
            assert round_1_executor_calls < 27

    @pytest.mark.asyncio
    async def test_circuit_breaker_minimum_sample(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        """Circuit breaker does NOT fire when sample size < 3 (e.g. 1/1 failure)."""
        # Agent proposes 1 experiment per round — it will fail
        single_code_agent = MagicMock(spec=Agent)
        single_code_agent.agent_id = "experimentalist-0"
        single_code_agent.skill_profile = "experimentalist"
        single_code_agent.generate = AsyncMock(
            return_value=AgentResponse(
                content="```python\n# EXPERIMENT: solo_exp\nprint('fail')\n```\n",
                usage=TokenUsage(input_tokens=50, output_tokens=80, total_tokens=130),
                model="claude-sonnet-4-5-20250929",
            )
        )
        single_code_agent.format_message = MagicMock(
            side_effect=lambda to, thread_id, phase, message_type, content, **kw: MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "from": "experimentalist-0",
                        "to": to,
                        "thread_id": thread_id,
                        "phase": phase,
                        "type": message_type,
                        "content": content,
                        "references": [],
                        "metadata": {},
                    }
                )
            )
        )

        factory = MagicMock()
        factory.create_team = MagicMock(
            side_effect=lambda roles, skill_mode="default": [
                single_code_agent if r == "experimentalist" else make_mock_agent(f"{r}-0", r)
                for r in roles
            ]
        )

        failure_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.FAILURE,
            stderr="NameError: something broke",
            error_message="Process exited with code 1",
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(return_value=failure_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            # 3 rounds: each round has 1 experiment that fails (1/1 = 100% failure)
            # but sample size < 3, so circuit breaker should NOT fire
            mock_config.orchestrator.max_experiment_rounds = 3

            await engine.run_research_cycle(
                seed_prompt="Test circuit breaker minimum sample",
                mode="experimental",
            )

            # All 3 rounds should run (1 experiment × 3 attempts × 3 rounds = 9)
            # If circuit breaker fired on round 1, we'd only get 3 calls
            assert mock_executor_instance.execute.call_count == 9

    @pytest.mark.asyncio
    async def test_execution_context_in_writing(
        self, tmp_path, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """Execution results are injected into WRITING prompts for RESULTS/METHODS sections."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "checkpoint_interval": 1,
                "enable_checkpointing": True,
                "enable_writing": True,
                "enable_experimentation": True,
                "max_experiment_rounds": 1,
                "enable_peer_review": False,
                "max_review_iterations": 0,
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Result: 42\n",
            duration_seconds=1.0,
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(return_value=mock_exec_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory_with_code,
            )

            await engine.run_research_cycle(
                seed_prompt="Test writing with execution context",
                mode="experimental",
            )

        # After execution + writing, the engine should have set _execution_context
        assert engine._execution_context != ""
        assert "Result: 42" in engine._execution_context

    @pytest.mark.asyncio
    async def test_figures_copied(
        self, tmp_path, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """Output figures are copied to the paper directory."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "checkpoint_interval": 1,
                "enable_checkpointing": True,
                "enable_writing": True,
                "enable_experimentation": True,
                "max_experiment_rounds": 1,
                "enable_peer_review": False,
                "max_review_iterations": 0,
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        # Create a fake figure file
        figures_src = tmp_path / "data" / "executions"
        figures_src.mkdir(parents=True, exist_ok=True)
        fake_fig = figures_src / "plot.png"
        fake_fig.write_bytes(b"fake png data")

        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="figure saved\n",
            duration_seconds=0.5,
            output_files=[
                OutputFile(filename="plot.png", path=str(fake_fig), size_bytes=13),
            ],
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(return_value=mock_exec_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory_with_code,
            )

            await engine.run_research_cycle(
                seed_prompt="Test figures",
                mode="experimental",
            )

        # Check that figures were tracked
        assert len(engine._execution_figures) == 1
        exp_name, fig_path = engine._execution_figures[0]
        assert fig_path.name == "plot.png"

        # If writing happened, check figure was copied
        papers_dir = config.storage.papers_dir
        if papers_dir:
            # Look for paper directories with figures
            paper_dirs = list(papers_dir.glob("paper-*/figures"))
            if paper_dirs:
                figure_files = list(paper_dirs[0].glob("*.png"))
                assert len(figure_files) >= 1


# --- Unit tests: figure embedding ---


class TestEmbedFiguresInline:
    """Tests for the _embed_figures_inline post-processing method."""

    def _make_engine(self, tmp_path):
        """Create a minimal engine with mocked dependencies for unit testing."""
        from paradigm.config import Config

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
        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        db.close()
        return engine

    def test_no_figures_returns_unchanged(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine._execution_figures = []
        body = "# Paper\n\n## Abstract\n\nContent."
        assert engine._writing.embed_figures_inline(body) == body

    def test_inserts_missing_figure_tag(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine._execution_figures = [("test_exp", Path("/tmp/plot.png"))]

        body = "# Paper\n\n## Results\n\nAs shown in Figure 1, the data is clear.\n\n## Conclusion\n\nDone."
        result = engine._writing.embed_figures_inline(body)
        assert "![Figure 1](figures/test_exp_plot.png)" in result

    def test_skips_already_embedded(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine._execution_figures = [("test_exp", Path("/tmp/plot.png"))]

        body = "# Paper\n\n![Figure 1](figures/test_exp_plot.png)\n\nSee Figure 1 above."
        result = engine._writing.embed_figures_inline(body)
        # Should not duplicate the tag
        assert result.count("![Figure 1]") == 1

    def test_appends_if_no_text_reference(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine._execution_figures = [("test_exp", Path("/tmp/plot.png"))]

        body = "# Paper\n\n## Abstract\n\nNo figure mention here."
        result = engine._writing.embed_figures_inline(body)
        assert "![Figure 1](figures/test_exp_plot.png)" in result
        # Should be at the end
        assert result.strip().endswith("![Figure 1](figures/test_exp_plot.png)")

    def test_multiple_figures(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine._execution_figures = [
            ("exp_a", Path("/tmp/fig_a.png")),
            ("exp_b", Path("/tmp/fig_b.png")),
        ]

        body = "# Paper\n\nFigure 1 shows X.\n\nFigure 2 shows Y."
        result = engine._writing.embed_figures_inline(body)
        assert "![Figure 1](figures/exp_a_fig_a.png)" in result
        assert "![Figure 2](figures/exp_b_fig_b.png)" in result

    def test_figure_dest_name_sanitizes(self, tmp_path):
        engine = self._make_engine(tmp_path)
        name = engine._writing.figure_dest_name("Test Experiment (v2)", Path("/tmp/plot.png"))
        assert name == "Test_Experiment__v2__plot.png"
        # No spaces or parens
        assert " " not in name
        assert "(" not in name


# --- Unit tests: vacuous success detection ---


class TestIsVacuousSuccess:
    def _make_result(
        self,
        stdout: str = "",
        output_files: list[OutputFile] | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="exp-0", thread_id="t-1"),
            status=ExecutionStatus.SUCCESS,
            stdout=stdout,
            output_files=output_files or [],
        )

    def test_empty_stdout_no_files_is_vacuous(self):
        result = self._make_result(stdout="")
        assert _is_vacuous_success(result) is True

    def test_short_stdout_no_files_is_vacuous(self):
        result = self._make_result(stdout="File not found")
        assert _is_vacuous_success(result) is True

    def test_error_like_stdout_is_vacuous(self):
        result = self._make_result(
            stdout="Error: could not find the file data.csv. Please check the file path."
        )
        assert _is_vacuous_success(result) is True

    def test_real_output_not_vacuous(self):
        result = self._make_result(
            stdout="Mean temperature: 5778.3 K\nStd deviation: 42.1 K\nSample size: 1000"
        )
        assert _is_vacuous_success(result) is False

    def test_output_files_not_vacuous(self):
        result = self._make_result(
            stdout="",
            output_files=[OutputFile(filename="plot.png", path="/tmp/plot.png", size_bytes=1024)],
        )
        assert _is_vacuous_success(result) is False

    def test_file_not_found_in_stdout_is_vacuous(self):
        result = self._make_result(
            stdout="FileNotFoundError: [Errno 2] No such file or directory: '/data/shared/star_data.csv'"
        )
        assert _is_vacuous_success(result) is True


# --- Integration tests: vacuous success retry ---


class TestVacuousSuccessRetry:
    @pytest.mark.asyncio
    async def test_vacuous_success_triggers_retry(
        self, mock_config, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """A vacuous SUCCESS (empty stdout, no files) should be retried."""
        vacuous_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="File not found\n",
        )
        real_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Mean: 42.3\nStd: 5.1\nN=1000 samples\n",
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(side_effect=[vacuous_result, real_result])
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory_with_code,
            )

            mock_config.orchestrator.max_experiment_rounds = 1

            await engine.run_research_cycle(
                seed_prompt="Test vacuous retry",
                mode="experimental",
            )

            # Executor called twice: vacuous result triggered retry
            assert mock_executor_instance.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_file_not_found_injects_listing(
        self, mock_config, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus, tmp_path
    ):
        """FileNotFoundError in stderr should inject file listing into retry feedback."""
        failure_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.FAILURE,
            stderr="FileNotFoundError: [Errno 2] No such file or directory: '/data/shared/nonexistent.csv'",
            error_message="Process exited with code 1",
        )
        success_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Generated synthetic data\nMean: 42.0\nN=500\n",
        )

        with patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(side_effect=[failure_result, success_result])
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory_with_code,
            )

            mock_config.orchestrator.max_experiment_rounds = 1

            await engine.run_research_cycle(
                seed_prompt="Test file not found guidance",
                mode="experimental",
            )

            # Retry was triggered — check that the retry prompt was called
            exp_agent = engine._find_agent_by_role("experimentalist")
            assert exp_agent is not None
            # The agent should have been called with retry prompt containing
            # file-not-found guidance (at least 2 generate calls: proposal + retry)
            retry_calls = [
                call for call in exp_agent.generate.call_args_list if "FILE NOT FOUND" in str(call)
            ]
            assert len(retry_calls) >= 1
