"""Tests for the EXECUTION phase: code extraction, result formatting, and integration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradigm.agents.base import Agent, AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.logging.events import EventLogger
from paradigm.orchestrator.engine import (
    OrchestrationEngine,
    _extract_code_blocks,
    _format_execution_result,
)
from paradigm.sandbox.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    OutputFile,
)
from paradigm.storage.database import Database

# --- Fixtures (shared with test_orchestrator.py patterns) ---


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database."""
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def tmp_logger(tmp_path):
    """Create a temporary event logger."""
    return EventLogger(tmp_path / "events.jsonl")


@pytest.fixture
def mock_config(tmp_path):
    """Create a config with experimentation enabled and small round counts."""
    return Config(
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


@pytest.fixture
def mock_config_no_sandbox(tmp_path):
    """Config with sandbox disabled."""
    return Config(
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


def _make_mock_agent(agent_id: str, role: str) -> Agent:
    """Create a mock agent that returns canned responses."""
    agent = MagicMock(spec=Agent)
    agent.agent_id = agent_id
    agent.skill_profile = role

    response = AgentResponse(
        content=f"Response from {agent_id}: I have ideas about this topic.",
        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
        model="claude-sonnet-4-5-20250929",
    )
    agent.generate = AsyncMock(return_value=response)

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
def mock_factory():
    """Create a mock AgentFactory."""
    factory = MagicMock()

    def _create_team(roles, skill_mode="default"):
        return [_make_mock_agent(f"{role}-0", role) for role in roles]

    factory.create_team = MagicMock(side_effect=_create_team)
    return factory


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
                agents.append(_make_mock_agent(f"{role}-0", role))
        return agents

    factory.create_team = MagicMock(side_effect=_create_team)
    return factory


@pytest.fixture
def mock_corpus():
    """Create a mock Corpus."""
    corpus = MagicMock()
    corpus.build_literature_context = AsyncMock(return_value="## Literature\nNo papers found.")
    return corpus


def _mock_checkpoint_response():
    """Build a mock Anthropic response for checkpoint compression."""
    response = MagicMock()
    response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "hypothesis": "Test hypothesis",
                    "key_findings": ["Finding 1"],
                    "open_questions": ["Question 1"],
                    "next_steps": ["Next step 1"],
                    "conversation_summary": "Agents discussed the topic.",
                }
            )
        )
    ]
    response.usage = MagicMock(input_tokens=200, output_tokens=100)
    return response


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
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

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
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

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

        with (
            patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic,
            patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

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
            stdout="safe output\n",
        )

        with (
            patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic,
            patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

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
            stdout="fixed output\n",
        )

        with (
            patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic,
            patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

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

        mock_exec_result = ExecutionResult(
            request=ExecutionRequest(code="x", agent_id="experimentalist-0", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="Result: 42\n",
            duration_seconds=1.0,
        )

        with (
            patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic,
            patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

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

        with (
            patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic,
            patch("paradigm.orchestrator.engine.CodeExecutor") as mock_code_executor,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

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
