"""Tests for the EXECUTION phase: code extraction, result formatting, and integration."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from helpers import make_mock_agent, patch_config_provider

from paradigm.agents.base import Agent, AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.logging.events import EventLogger
from paradigm.orchestrator.constants import (
    CodeBlock,
    _extract_code_blocks,
    _format_execution_result,
    _get_downstream_dependents,
    _is_vacuous_success,
    _topological_sort,
)
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.experimentation import (
    SprintStopReason,
    _categorize_failure,
    _peek_csv_schema,
    _peek_json_schema,
)
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
        assert blocks[0].name == "test_gravity"
        assert "import numpy" in blocks[0].code

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
        assert blocks[0].name == "exp_one"
        assert blocks[1].name == "exp_two"

    def test_no_name_defaults(self):
        text = "```python\nprint('hello')\n```\n"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].name == "unnamed_experiment"

    def test_no_code_returns_empty(self):
        text = "I think we should analyze the data carefully."
        blocks = _extract_code_blocks(text)
        assert blocks == []

    def test_depends_parsing(self):
        text = (
            "```python\n"
            "# EXPERIMENT: analyze\n"
            "# DEPENDS: extract_data\n"
            "import pandas as pd\n"
            "df = pd.read_csv('/data/workspace/data.csv')\n"
            "```\n"
        )
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].name == "analyze"
        assert blocks[0].depends_on == ("extract_data",)

    def test_multiple_depends(self):
        text = (
            "```python\n"
            "# EXPERIMENT: final_plot\n"
            "# DEPENDS: extract_data, run_analysis\n"
            "import matplotlib.pyplot as plt\n"
            "```\n"
        )
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].depends_on == ("extract_data", "run_analysis")

    def test_no_depends_returns_empty_tuple(self):
        text = "```python\n# EXPERIMENT: standalone\nprint('hello')\n```\n"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].depends_on == ()

    def test_code_block_is_frozen(self):
        block = CodeBlock(name="test", code="print(1)", depends_on=())
        with pytest.raises(AttributeError):
            block.name = "other"  # type: ignore[misc]


# --- Unit tests: topological sort ---


class TestTopologicalSort:
    def test_no_deps_preserves_order(self):
        blocks = [
            CodeBlock(name="a", code="print('a')", depends_on=()),
            CodeBlock(name="b", code="print('b')", depends_on=()),
            CodeBlock(name="c", code="print('c')", depends_on=()),
        ]
        result = _topological_sort(blocks)
        assert [b.name for b in result] == ["a", "b", "c"]

    def test_simple_chain(self):
        blocks = [
            CodeBlock(name="plot", code="", depends_on=("analyze",)),
            CodeBlock(name="analyze", code="", depends_on=("extract",)),
            CodeBlock(name="extract", code="", depends_on=()),
        ]
        result = _topological_sort(blocks)
        names = [b.name for b in result]
        assert names.index("extract") < names.index("analyze")
        assert names.index("analyze") < names.index("plot")

    def test_diamond_dependency(self):
        blocks = [
            CodeBlock(name="final", code="", depends_on=("left", "right")),
            CodeBlock(name="left", code="", depends_on=("root",)),
            CodeBlock(name="right", code="", depends_on=("root",)),
            CodeBlock(name="root", code="", depends_on=()),
        ]
        result = _topological_sort(blocks)
        names = [b.name for b in result]
        assert names[0] == "root"
        assert names[-1] == "final"
        assert names.index("left") < names.index("final")
        assert names.index("right") < names.index("final")

    def test_cycle_falls_back_to_original_order(self):
        blocks = [
            CodeBlock(name="a", code="", depends_on=("b",)),
            CodeBlock(name="b", code="", depends_on=("a",)),
        ]
        result = _topological_sort(blocks)
        assert [b.name for b in result] == ["a", "b"]

    def test_external_dep_ignored(self):
        """Dependencies not in current batch are ignored."""
        blocks = [
            CodeBlock(name="b", code="", depends_on=("a_from_prior_round",)),
            CodeBlock(name="c", code="", depends_on=("b",)),
        ]
        result = _topological_sort(blocks)
        assert [b.name for b in result] == ["b", "c"]

    def test_single_block(self):
        blocks = [CodeBlock(name="only", code="print(1)", depends_on=())]
        result = _topological_sort(blocks)
        assert len(result) == 1
        assert result[0].name == "only"

    def test_empty_list(self):
        assert _topological_sort([]) == []


# --- Unit tests: downstream dependents ---


class TestGetDownstreamDependents:
    def test_direct_dependent(self):
        blocks = [
            CodeBlock(name="a", code="", depends_on=()),
            CodeBlock(name="b", code="", depends_on=("a",)),
        ]
        result = _get_downstream_dependents("a", blocks)
        assert result == {"b"}

    def test_transitive_dependents(self):
        blocks = [
            CodeBlock(name="a", code="", depends_on=()),
            CodeBlock(name="b", code="", depends_on=("a",)),
            CodeBlock(name="c", code="", depends_on=("b",)),
        ]
        result = _get_downstream_dependents("a", blocks)
        assert result == {"b", "c"}

    def test_no_dependents(self):
        blocks = [
            CodeBlock(name="a", code="", depends_on=()),
            CodeBlock(name="b", code="", depends_on=()),
        ]
        result = _get_downstream_dependents("a", blocks)
        assert result == set()

    def test_diamond_dependents(self):
        blocks = [
            CodeBlock(name="root", code="", depends_on=()),
            CodeBlock(name="left", code="", depends_on=("root",)),
            CodeBlock(name="right", code="", depends_on=("root",)),
            CodeBlock(name="final", code="", depends_on=("left", "right")),
        ]
        result = _get_downstream_dependents("root", blocks)
        assert result == {"left", "right", "final"}


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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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
        assert thread["current_phase"] in ("execution", "post_execution", "planning")

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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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
        assert engine.state.execution_context != ""
        assert "Result: 42" in engine.state.execution_context

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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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
        assert len(engine.state.execution_figures) == 1
        exp_name, fig_path = engine.state.execution_figures[0]
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
        engine.state.execution_figures = []
        body = "# Paper\n\n## Abstract\n\nContent."
        assert engine._writing.embed_figures_inline(body) == body

    def test_inserts_missing_figure_tag(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = [("test_exp", Path("/tmp/plot.png"))]

        body = "# Paper\n\n## Results\n\nAs shown in Figure 1, the data is clear.\n\n## Conclusion\n\nDone."
        result = engine._writing.embed_figures_inline(body)
        assert "![Figure 1](figures/test_exp_plot.png)" in result

    def test_skips_already_embedded(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = [("test_exp", Path("/tmp/plot.png"))]

        body = "# Paper\n\n![Figure 1](figures/test_exp_plot.png)\n\nSee Figure 1 above."
        result = engine._writing.embed_figures_inline(body)
        # Should not duplicate the tag
        assert result.count("![Figure 1]") == 1

    def test_skips_if_no_text_reference(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = [("test_exp", Path("/tmp/plot.png"))]

        body = "# Paper\n\n## Abstract\n\nNo figure mention here."
        result = engine._writing.embed_figures_inline(body)
        # Unreferenced figures are not force-appended
        assert "![Figure 1]" not in result
        assert result == body

    def test_multiple_figures(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = [
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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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


# --- Unit tests: failure categorization (Fix 1) ---


class TestCategorizeFailure:
    def _make_result(
        self,
        status: ExecutionStatus = ExecutionStatus.FAILURE,
        stderr: str = "",
        stdout: str = "",
        error_message: str = "",
    ) -> ExecutionResult:
        return ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="exp-0", thread_id="t-1"),
            status=status,
            stderr=stderr,
            stdout=stdout,
            error_message=error_message,
        )

    def test_timeout(self):
        result = self._make_result(status=ExecutionStatus.TIMEOUT)
        assert _categorize_failure(result) == "timeout"

    def test_safety_rejection(self):
        result = self._make_result(status=ExecutionStatus.REJECTED)
        assert _categorize_failure(result) == "safety_rejection"

    def test_network_error(self):
        result = self._make_result(stderr="ConnectionRefusedError: [Errno 111] Connection refused")
        assert _categorize_failure(result) == "network_error"

    def test_module_not_found(self):
        result = self._make_result(stderr="ModuleNotFoundError: No module named 'nonexistent'")
        assert _categorize_failure(result) == "module_not_found"

    def test_file_not_found(self):
        result = self._make_result(
            stderr="FileNotFoundError: [Errno 2] No such file or directory: '/data/missing.csv'"
        )
        assert _categorize_failure(result) == "file_not_found"

    def test_vacuous_output(self):
        result = self._make_result(
            status=ExecutionStatus.SUCCESS,
            stdout="",
        )
        assert _categorize_failure(result) == "vacuous_output"

    def test_generic_execution_error(self):
        result = self._make_result(stderr="ZeroDivisionError: division by zero")
        assert _categorize_failure(result) == "execution_error"


# --- Unit tests: experiment metadata (Fix 3) ---


class TestExperimentMetadata:
    @pytest.mark.asyncio
    async def test_metadata_populated(
        self, mock_config, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """After execution, experiment_metadata has correct entries."""
        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Result: 42.0\n",
            duration_seconds=0.5,
            output_files=[
                OutputFile(filename="plot.png", path="/tmp/plot.png", size_bytes=1024),
            ],
        )

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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

            mock_config.orchestrator.max_experiment_rounds = 1

            await engine.run_research_cycle(
                seed_prompt="Test metadata",
                mode="experimental",
            )

            assert len(engine.state.experiment_metadata) >= 1
            entry = engine.state.experiment_metadata[0]
            assert "name" in entry
            assert entry["status"] == "success"
            assert entry["has_figures"] is True
            assert "stdout_preview" in entry


# --- Integration tests: cross-round circuit breaker (Fix 1) ---


class TestCrossRoundCircuitBreaker:
    @pytest.mark.asyncio
    async def test_cross_round_breaker_fires(self, tmp_path, tmp_db, tmp_logger, mock_corpus):
        """Cross-round breaker fires when failure rate > 0.6 with >= 5 experiments."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "checkpoint_interval": 1,
                "enable_checkpointing": True,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 5,
                "cross_round_failure_threshold": 0.6,
                "cross_round_min_experiments": 5,
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        # Agent proposes 2 experiments per round (so 5 rounds = 10 experiments)
        multi_code_agent = MagicMock(spec=Agent)
        multi_code_agent.agent_id = "experimentalist-0"
        multi_code_agent.skill_profile = "experimentalist"
        multi_code_agent.generate = AsyncMock(
            return_value=AgentResponse(
                content=(
                    "```python\n# EXPERIMENT: exp_a\nprint('a')\n```\n"
                    "```python\n# EXPERIMENT: exp_b\nprint('b')\n```\n"
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
            stderr="Error: something broke",
            error_message="Process exited with code 1",
        )

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(return_value=failure_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test cross-round breaker",
                mode="experimental",
            )

            # Per-round breaker won't fire (only 2 experiments per round, < 3 threshold).
            # But 2 experiments per round fail. After round 1: 2/2 = 100% > 60% but < 5 min.
            # After round 2: 4/4 = 100% > 60% but < 5 min.
            # After round 3: 6/6 = 100% > 60% AND >= 5 — cross-round breaker fires!
            # So we expect 3 rounds × 2 experiments × 3 attempts = 18 calls
            # Without cross-round breaker: 5 rounds × 2 × 3 = 30 calls
            total_calls = mock_executor_instance.execute.call_count
            assert total_calls < 30  # Cross-round breaker saved rounds
            assert total_calls == 18  # 3 rounds × 2 experiments × 3 attempts


# --- Integration tests: planning actions in execution (Fix 5) ---


class TestPlanningActionsInExecution:
    @pytest.mark.asyncio
    async def test_planning_actions_injected(
        self, mock_config, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """Planning action items are injected into execution prompts."""
        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Result: 42.0\n",
            duration_seconds=0.5,
        )

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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

            mock_config.orchestrator.max_experiment_rounds = 1

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory_with_code,
            )

            # Create agents (normally done by run_research_cycle)
            agents = mock_factory_with_code.create_team(
                ["experimentalist", "theorist", "analyst"], skill_mode="default"
            )
            engine.state.agents = {a.agent_id: a for a in agents}

            # Manually set planning action items as if PLANNING extracted them
            engine.state.planning_action_items = (
                "1. Run a Monte Carlo simulation\n2. Calculate the period-luminosity relation"
            )

            # Set engine state as if earlier phases ran
            engine.state.thread_id = "test-thread"
            tmp_db.create_thread(
                thread_id="test-thread", title="Test", mode="experimental", participants=[]
            )
            engine.state.seed_prompt = "Test planning actions"
            engine.state.messages = []
            engine.state.checkpoint = None
            engine.state.resolved_resources = []
            engine.state.code_context = ""
            engine.state.data_context = ""

            await engine._experimentation.run_experimentation_phase()

            # Check that experimentalist received the planning actions
            exp_agent = engine._find_agent_by_role("experimentalist")
            assert exp_agent is not None
            prompt_text = str(exp_agent.generate.call_args_list[0])
            assert "Planned Experiments" in prompt_text
            assert "Monte Carlo" in prompt_text


# --- Unit tests: execution sprints ---


class TestSprintConfig:
    """Sprint configuration defaults and overrides."""

    def test_default_disabled(self):
        from paradigm.config import OrchestratorConfig

        c = OrchestratorConfig()
        assert c.enable_execution_sprints is False
        assert c.num_execution_sprints == 3
        assert c.sprint_review_roles == ["theorist", "analyst", "skeptic"]

    def test_custom_roles(self):
        from paradigm.config import OrchestratorConfig

        c = OrchestratorConfig(sprint_review_roles=["theorist", "skeptic"])
        assert c.sprint_review_roles == ["theorist", "skeptic"]


class TestSprintDesignReview:
    """Tests for the _run_sprint_design_review method."""

    @pytest.mark.asyncio
    async def test_design_review_calls_reviewers(self, tmp_path, tmp_db, tmp_logger, mock_corpus):
        """Design review calls experimenter + each review role."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 2,
                "enable_execution_sprints": True,
                "num_execution_sprints": 1,
                "sprint_review_roles": ["theorist", "analyst"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        # Create agents
        experimentalist = make_mock_agent("experimentalist-0", "experimentalist")
        theorist = make_mock_agent("theorist-0", "theorist")
        analyst = make_mock_agent("analyst-0", "analyst")

        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[experimentalist, theorist, analyst])

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        # Set up engine state
        engine.state.agents = {a.agent_id: a for a in [experimentalist, theorist, analyst]}
        engine.state.thread_id = "test-thread"
        tmp_db.create_thread(
            thread_id="test-thread", title="Test", mode="experimental", participants=[]
        )
        engine.state.seed_prompt = "Test sprints"
        engine.state.messages = []
        engine.state.checkpoint = None
        engine.state.resolved_resources = []
        engine.state.code_context = ""
        engine.state.data_context = ""

        feedback = await engine._experimentation._run_sprint_design_review(
            experimenter=experimentalist,
            sprint_num=1,
            num_sprints=3,
            checkpoint_context="",
            previous_results="",
        )

        # Experimenter was called with design proposal prompt
        assert experimentalist.generate.call_count >= 1
        proposal_prompt = str(experimentalist.generate.call_args_list[0])
        assert "DO NOT write code" in proposal_prompt

        # Both reviewers were called
        assert theorist.generate.call_count >= 1
        assert analyst.generate.call_count >= 1

        # Feedback is non-empty
        assert "Design Review Feedback" in feedback

    @pytest.mark.asyncio
    async def test_design_review_skips_missing_agents(
        self, tmp_path, tmp_db, tmp_logger, mock_corpus
    ):
        """Missing reviewer agents are skipped without error."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 2,
                "enable_execution_sprints": True,
                "sprint_review_roles": ["theorist", "nonexistent_role"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        experimentalist = make_mock_agent("experimentalist-0", "experimentalist")
        theorist = make_mock_agent("theorist-0", "theorist")

        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[experimentalist, theorist])

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine.state.agents = {a.agent_id: a for a in [experimentalist, theorist]}
        engine.state.thread_id = "test-thread"
        tmp_db.create_thread(
            thread_id="test-thread", title="Test", mode="experimental", participants=[]
        )
        engine.state.seed_prompt = "Test"
        engine.state.messages = []
        engine.state.checkpoint = None
        engine.state.resolved_resources = []
        engine.state.code_context = ""
        engine.state.data_context = ""

        # Should not raise — nonexistent_role is simply skipped
        await engine._experimentation._run_sprint_design_review(experimentalist, 1, 3, "", "")
        # Only theorist reviewed (nonexistent_role skipped)
        assert theorist.generate.call_count >= 1

    @pytest.mark.asyncio
    async def test_design_review_handles_exceptions(
        self, tmp_path, tmp_db, tmp_logger, mock_corpus
    ):
        """Reviewer exceptions are non-fatal."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 2,
                "enable_execution_sprints": True,
                "sprint_review_roles": ["theorist"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        experimentalist = make_mock_agent("experimentalist-0", "experimentalist")
        theorist = make_mock_agent("theorist-0", "theorist")
        theorist.generate = AsyncMock(side_effect=RuntimeError("API error"))

        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[experimentalist, theorist])

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine.state.agents = {a.agent_id: a for a in [experimentalist, theorist]}
        engine.state.thread_id = "test-thread"
        tmp_db.create_thread(
            thread_id="test-thread", title="Test", mode="experimental", participants=[]
        )
        engine.state.seed_prompt = "Test"
        engine.state.messages = []
        engine.state.checkpoint = None
        engine.state.resolved_resources = []
        engine.state.code_context = ""
        engine.state.data_context = ""

        # Should not raise
        feedback = await engine._experimentation._run_sprint_design_review(
            experimentalist, 1, 3, "", ""
        )
        # Empty feedback because the only reviewer errored
        assert feedback == ""


class TestSprintResultsCheckpoint:
    """Tests for the _run_sprint_results_checkpoint method."""

    @pytest.mark.asyncio
    async def test_checkpoint_detects_sufficient_majority(
        self, tmp_path, tmp_db, tmp_logger, mock_corpus
    ):
        """Majority saying EXPERIMENTS SUFFICIENT triggers early stop."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 6,
                "enable_execution_sprints": True,
                "sprint_review_roles": ["theorist", "analyst", "skeptic"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        theorist = make_mock_agent("theorist-0", "theorist")
        analyst = make_mock_agent("analyst-0", "analyst")
        skeptic = make_mock_agent("skeptic-0", "skeptic")

        # 2 out of 3 say sufficient
        theorist.generate = AsyncMock(
            return_value=AgentResponse(
                content="Results look good. EXPERIMENTS SUFFICIENT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )
        analyst.generate = AsyncMock(
            return_value=AgentResponse(
                content="Good coverage of hypotheses. EXPERIMENTS SUFFICIENT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )
        skeptic.generate = AsyncMock(
            return_value=AgentResponse(
                content="Need more data on edge cases. Continue experiments.",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )

        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[theorist, analyst, skeptic])

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine.state.agents = {a.agent_id: a for a in [theorist, analyst, skeptic]}
        engine.state.thread_id = "test-thread"
        tmp_db.create_thread(
            thread_id="test-thread", title="Test", mode="experimental", participants=[]
        )
        engine.state.seed_prompt = "Test"
        engine.state.messages = []
        engine.state.checkpoint = None
        engine.state.resolved_resources = []
        engine.state.code_context = ""
        engine.state.data_context = ""

        stop_reason = await engine._experimentation._run_sprint_results_checkpoint(
            sprint_num=1, num_sprints=3, checkpoint_context="", sprint_results="Some results"
        )
        assert stop_reason == SprintStopReason.SUFFICIENT

    @pytest.mark.asyncio
    async def test_checkpoint_continues_when_not_sufficient(
        self, tmp_path, tmp_db, tmp_logger, mock_corpus
    ):
        """No majority means continue."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 6,
                "enable_execution_sprints": True,
                "sprint_review_roles": ["theorist", "analyst", "skeptic"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        theorist = make_mock_agent("theorist-0", "theorist")
        analyst = make_mock_agent("analyst-0", "analyst")
        skeptic = make_mock_agent("skeptic-0", "skeptic")

        # Only 1 out of 3 says sufficient
        theorist.generate = AsyncMock(
            return_value=AgentResponse(
                content="EXPERIMENTS SUFFICIENT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )
        analyst.generate = AsyncMock(
            return_value=AgentResponse(
                content="Need more experiments on the second hypothesis.",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )
        skeptic.generate = AsyncMock(
            return_value=AgentResponse(
                content="Insufficient evidence. Continue.",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )

        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[theorist, analyst, skeptic])

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine.state.agents = {a.agent_id: a for a in [theorist, analyst, skeptic]}
        engine.state.thread_id = "test-thread"
        tmp_db.create_thread(
            thread_id="test-thread", title="Test", mode="experimental", participants=[]
        )
        engine.state.seed_prompt = "Test"
        engine.state.messages = []
        engine.state.checkpoint = None
        engine.state.resolved_resources = []
        engine.state.code_context = ""
        engine.state.data_context = ""

        stop_reason = await engine._experimentation._run_sprint_results_checkpoint(
            sprint_num=1, num_sprints=3, checkpoint_context="", sprint_results="Some results"
        )
        assert stop_reason is None


class TestSprintIntegration:
    """Integration tests for sprint-based execution."""

    @pytest.mark.asyncio
    async def test_disabled_sprints_unchanged_behavior(
        self, mock_config, tmp_db, tmp_logger, mock_factory_with_code, mock_corpus
    ):
        """When enable_execution_sprints=False, behavior is identical to before."""
        assert mock_config.orchestrator.enable_execution_sprints is False

        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Mean: 42.3, Std: 5.1, N=1000 samples, chi2=3.14, p=0.07\n",
            duration_seconds=0.5,
        )

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
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

            mock_config.orchestrator.max_experiment_rounds = 2

            await engine.run_research_cycle(
                seed_prompt="Test disabled sprints",
                mode="experimental",
            )

            # Executor was called — normal execution happened
            assert mock_executor_instance.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_enabled_sprints_runs_design_and_checkpoint(
        self, tmp_path, tmp_db, tmp_logger, mock_corpus
    ):
        """With sprints enabled, design review and checkpoint are called."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 4,
                "enable_execution_sprints": True,
                "num_execution_sprints": 2,
                "sprint_review_roles": ["theorist"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        experimentalist = _make_experiment_agent("experimentalist-0", "experimentalist")
        theorist = make_mock_agent("theorist-0", "theorist")
        # Make theorist NOT say sufficient (so both sprints run)
        theorist.generate = AsyncMock(
            return_value=AgentResponse(
                content="Looks reasonable. Continue experiments.",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )

        factory = MagicMock()
        factory.create_team = MagicMock(
            side_effect=lambda roles, skill_mode="default": [
                experimentalist if r == "experimentalist" else theorist for r in roles
            ]
        )

        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Mean: 42.3, Std: 5.1, N=1000 samples, chi2=3.14, p=0.07\n",
            duration_seconds=0.5,
        )

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(return_value=mock_exec_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            engine.state.agents = {a.agent_id: a for a in [experimentalist, theorist]}
            engine.state.thread_id = "test-thread"
            tmp_db.create_thread(
                thread_id="test-thread", title="Test", mode="experimental", participants=[]
            )
            engine.state.seed_prompt = "Test sprints"
            engine.state.messages = []
            engine.state.checkpoint = None
            engine.state.resolved_resources = []
            engine.state.code_context = ""
            engine.state.data_context = ""

            await engine._experimentation.run_experimentation_phase()

            # Experimentalist should have been called for design proposals
            # (at least 2 design proposals for 2 sprints, plus execution prompts)
            exp_calls = experimentalist.generate.call_count
            assert exp_calls >= 4  # 2 design + 2 execution rounds minimum

            # Theorist should have been called for reviews and checkpoint
            # 2 design reviews + 1 checkpoint (only after sprint 1, not last)
            theorist_calls = theorist.generate.call_count
            assert theorist_calls >= 3

    @pytest.mark.asyncio
    async def test_sprint_early_stop(self, tmp_path, tmp_db, tmp_logger, mock_corpus):
        """Early stop when checkpoint returns sufficient."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 6,
                "enable_execution_sprints": True,
                "num_execution_sprints": 3,
                "sprint_review_roles": ["theorist"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        experimentalist = _make_experiment_agent("experimentalist-0", "experimentalist")
        theorist = make_mock_agent("theorist-0", "theorist")
        # Theorist declares sufficient immediately
        theorist.generate = AsyncMock(
            return_value=AgentResponse(
                content="Results are conclusive. EXPERIMENTS SUFFICIENT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )

        factory = MagicMock()
        factory.create_team = MagicMock(
            side_effect=lambda roles, skill_mode="default": [
                experimentalist if r == "experimentalist" else theorist for r in roles
            ]
        )

        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Mean: 42.3, Std: 5.1, N=1000 samples, chi2=3.14, p=0.07\n",
            duration_seconds=0.5,
        )

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(return_value=mock_exec_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            engine.state.agents = {a.agent_id: a for a in [experimentalist, theorist]}
            engine.state.thread_id = "test-thread"
            tmp_db.create_thread(
                thread_id="test-thread", title="Test", mode="experimental", participants=[]
            )
            engine.state.seed_prompt = "Test early stop"
            engine.state.messages = []
            engine.state.checkpoint = None
            engine.state.resolved_resources = []
            engine.state.code_context = ""
            engine.state.data_context = ""

            await engine._experimentation.run_experimentation_phase()

            # With 3 sprints and 6 rounds, ceil(6/3)=2 rounds per sprint.
            # Early stop after sprint 1 means only sprint 1's rounds executed.
            # Sprint 1: 2 execution rounds = 2 executor calls (no retries on success)
            # (Early stop prevents sprints 2 and 3)
            exec_calls = mock_executor_instance.execute.call_count
            # Only rounds from sprint 1 should have run (2 rounds × 1 experiment)
            assert exec_calls <= 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_propagates_through_sprints(
        self, tmp_path, tmp_db, tmp_logger, mock_corpus
    ):
        """Circuit breaker fired in sprint 1 stops all subsequent sprints."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 6,
                "enable_execution_sprints": True,
                "num_execution_sprints": 3,
                "sprint_review_roles": ["theorist"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        # Agent proposes 3 experiments (enough to trigger per-round circuit breaker)
        multi_code_agent = MagicMock(spec=Agent)
        multi_code_agent.agent_id = "experimentalist-0"
        multi_code_agent.skill_profile = "experimentalist"
        multi_code_agent.generate = AsyncMock(
            return_value=AgentResponse(
                content=(
                    "Design plan:\n"
                    "```python\n# EXPERIMENT: exp_a\nprint('a')\n```\n"
                    "```python\n# EXPERIMENT: exp_b\nprint('b')\n```\n"
                    "```python\n# EXPERIMENT: exp_c\nprint('c')\n```\n"
                ),
                usage=TokenUsage(input_tokens=50, output_tokens=80, total_tokens=130),
                model="test",
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

        theorist = make_mock_agent("theorist-0", "theorist")

        factory = MagicMock()
        factory.create_team = MagicMock(
            side_effect=lambda roles, skill_mode="default": [
                multi_code_agent if r == "experimentalist" else theorist for r in roles
            ]
        )

        failure_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.FAILURE,
            stderr="Error: something broke",
            error_message="Process exited with code 1",
        )

        with patch("paradigm.orchestrator.experimentation.CodeExecutor") as mock_code_executor:
            mock_executor_instance = AsyncMock()
            mock_executor_instance.execute = AsyncMock(return_value=failure_result)
            mock_executor_instance.cleanup = AsyncMock()
            mock_code_executor.return_value = mock_executor_instance

            engine = OrchestrationEngine(
                config=config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            engine.state.agents = {a.agent_id: a for a in [multi_code_agent, theorist]}
            engine.state.thread_id = "test-thread"
            tmp_db.create_thread(
                thread_id="test-thread", title="Test", mode="experimental", participants=[]
            )
            engine.state.seed_prompt = "Test circuit breaker in sprints"
            engine.state.messages = []
            engine.state.checkpoint = None
            engine.state.resolved_resources = []
            engine.state.code_context = ""
            engine.state.data_context = ""

            await engine._experimentation.run_experimentation_phase()

            # Circuit breaker should fire in sprint 1 (3 experiments, all fail)
            # and prevent sprints 2 and 3 from running.
            # Sprint 1: 3 experiments × 3 attempts = 9 calls
            total_calls = mock_executor_instance.execute.call_count
            assert total_calls == 9  # Only sprint 1's round ran


# --- Unit tests: _peek_json_schema (Fix 1) ---


class TestPeekJsonSchema:
    def test_dict_schema(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"alpha": 1, "beta": [1, 2], "gamma": "x"}')
        result = _peek_json_schema(f)
        assert "dict with keys:" in result
        assert "alpha" in result

    def test_list_of_dicts_schema(self, tmp_path):
        f = tmp_path / "rows.json"
        f.write_text('[{"col1": 1, "col2": 2}, {"col1": 3, "col2": 4}]')
        result = _peek_json_schema(f)
        assert "list[dict]" in result
        assert "len=2" in result
        assert "col1" in result

    def test_list_of_scalars(self, tmp_path):
        f = tmp_path / "nums.json"
        f.write_text("[1, 2, 3, 4]")
        result = _peek_json_schema(f)
        assert "list[int]" in result
        assert "len=4" in result

    def test_empty_list(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("[]")
        result = _peek_json_schema(f)
        assert result == "empty list"

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json at all")
        result = _peek_json_schema(f)
        assert result == ""

    def test_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent.json"
        result = _peek_json_schema(f)
        assert result == ""

    def test_max_keys_truncation(self, tmp_path):
        import json

        data = {f"key_{i}": i for i in range(20)}
        f = tmp_path / "many_keys.json"
        f.write_text(json.dumps(data))
        result = _peek_json_schema(f, max_keys=5)
        assert "+15 more" in result


# --- Unit tests: STOP AND PIVOT (Fix 2) ---


class TestStopAndPivot:
    @pytest.mark.asyncio
    async def test_checkpoint_detects_pivot_majority(
        self, tmp_path, tmp_db, tmp_logger, mock_corpus
    ):
        """Majority saying STOP AND PIVOT triggers pivot stop."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 6,
                "enable_execution_sprints": True,
                "sprint_review_roles": ["theorist", "analyst", "skeptic"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        theorist = make_mock_agent("theorist-0", "theorist")
        analyst = make_mock_agent("analyst-0", "analyst")
        skeptic = make_mock_agent("skeptic-0", "skeptic")

        # 2 out of 3 say STOP AND PIVOT
        theorist.generate = AsyncMock(
            return_value=AgentResponse(
                content="Approach is fundamentally broken. STOP AND PIVOT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )
        analyst.generate = AsyncMock(
            return_value=AgentResponse(
                content="Data structure errors are systemic. STOP AND PIVOT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )
        skeptic.generate = AsyncMock(
            return_value=AgentResponse(
                content="I think we should continue. EXPERIMENTS INSUFFICIENT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )

        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[theorist, analyst, skeptic])

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine.state.agents = {a.agent_id: a for a in [theorist, analyst, skeptic]}
        engine.state.thread_id = "test-thread"
        tmp_db.create_thread(
            thread_id="test-thread", title="Test", mode="experimental", participants=[]
        )
        engine.state.seed_prompt = "Test"
        engine.state.messages = []
        engine.state.checkpoint = None
        engine.state.resolved_resources = []
        engine.state.code_context = ""
        engine.state.data_context = ""

        stop_reason = await engine._experimentation._run_sprint_results_checkpoint(
            sprint_num=1, num_sprints=3, checkpoint_context="", sprint_results="Failed results"
        )
        assert stop_reason == SprintStopReason.PIVOT

    @pytest.mark.asyncio
    async def test_checkpoint_no_majority_returns_none(
        self, tmp_path, tmp_db, tmp_logger, mock_corpus
    ):
        """Mixed signals (no majority) returns None."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 6,
                "enable_execution_sprints": True,
                "sprint_review_roles": ["theorist", "analyst", "skeptic"],
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        theorist = make_mock_agent("theorist-0", "theorist")
        analyst = make_mock_agent("analyst-0", "analyst")
        skeptic = make_mock_agent("skeptic-0", "skeptic")

        # 1 sufficient, 1 pivot, 1 insufficient — no majority
        theorist.generate = AsyncMock(
            return_value=AgentResponse(
                content="EXPERIMENTS SUFFICIENT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )
        analyst.generate = AsyncMock(
            return_value=AgentResponse(
                content="STOP AND PIVOT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )
        skeptic.generate = AsyncMock(
            return_value=AgentResponse(
                content="EXPERIMENTS INSUFFICIENT",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                model="test",
            )
        )

        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[theorist, analyst, skeptic])

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine.state.agents = {a.agent_id: a for a in [theorist, analyst, skeptic]}
        engine.state.thread_id = "test-thread"
        tmp_db.create_thread(
            thread_id="test-thread", title="Test", mode="experimental", participants=[]
        )
        engine.state.seed_prompt = "Test"
        engine.state.messages = []
        engine.state.checkpoint = None
        engine.state.resolved_resources = []
        engine.state.code_context = ""
        engine.state.data_context = ""

        stop_reason = await engine._experimentation._run_sprint_results_checkpoint(
            sprint_num=1, num_sprints=3, checkpoint_context="", sprint_results="Some results"
        )
        assert stop_reason is None


# --- Unit tests: advisory context (Fix 4) ---


class TestAdvisoryContext:
    @pytest.mark.asyncio
    async def test_advisory_includes_seed_prompt(self, tmp_path, tmp_db, tmp_logger, mock_corpus):
        """Advisory prompt includes the research topic (seed_prompt)."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "enable_checkpointing": False,
                "enable_writing": False,
                "enable_experimentation": True,
                "max_experiment_rounds": 2,
            },
            sandbox={"enabled": True},
        )
        patch_config_provider(config)

        experimentalist = make_mock_agent("experimentalist-0", "experimentalist")
        theorist = make_mock_agent("theorist-0", "theorist")

        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[experimentalist, theorist])

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine.state.agents = {a.agent_id: a for a in [experimentalist, theorist]}
        engine.state.thread_id = "test-thread"
        tmp_db.create_thread(
            thread_id="test-thread", title="Test", mode="experimental", participants=[]
        )
        engine.state.seed_prompt = "Red noise in massive stars"
        engine.state.messages = []
        engine.state.checkpoint = None
        engine.state.resolved_resources = []
        engine.state.code_context = ""
        engine.state.data_context = ""

        # Set up experimentation handler state
        engine._experimentation._consecutive_failures = 3
        engine._experimentation._sprint_results = [
            "Experiment failed: TypeError dict vs list",
            "Experiment failed: KeyError 'frequency'",
        ]

        await engine._experimentation._request_advisory("experimentalist-0")

        # Theorist should have been called with a prompt containing the seed
        assert theorist.generate.call_count == 1
        call_args = str(theorist.generate.call_args)
        assert "Red noise in massive stars" in call_args
        assert "3 consecutive" in call_args


# --- Unit tests: CSV schema peeking (Fix 1 from paper-cdddc9232c19) ---


class TestPeekCsvSchema:
    def test_basic_csv(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age,score\nAlice,30,95\nBob,25,88\n")
        result = _peek_csv_schema(csv_file)
        assert "CSV columns" in result
        assert "2 rows" in result
        assert "name" in result
        assert "age" in result
        assert "score" in result

    def test_empty_csv(self, tmp_path):
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")
        result = _peek_csv_schema(csv_file)
        assert result == ""

    def test_header_only_csv(self, tmp_path):
        csv_file = tmp_path / "header.csv"
        csv_file.write_text("col_a,col_b\n")
        result = _peek_csv_schema(csv_file)
        assert "0 rows" in result
        assert "col_a" in result

    def test_many_columns_truncated(self, tmp_path):
        csv_file = tmp_path / "wide.csv"
        cols = [f"col_{i}" for i in range(20)]
        csv_file.write_text(",".join(cols) + "\n" + ",".join(["1"] * 20) + "\n")
        result = _peek_csv_schema(csv_file, max_cols=5)
        assert "+15 more" in result

    def test_nonexistent_file(self, tmp_path):
        result = _peek_csv_schema(tmp_path / "no_such.csv")
        assert result == ""

    def test_binary_file(self, tmp_path):
        binary_file = tmp_path / "data.csv"
        binary_file.write_bytes(b"\x00\x01\x02\xff" * 100)
        result = _peek_csv_schema(binary_file)
        # Should not crash — returns empty or a parsed line
        assert isinstance(result, str)
