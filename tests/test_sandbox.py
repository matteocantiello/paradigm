"""Tests for the computational sandbox module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from paradigm.config import SandboxConfig
from paradigm.logging.events import EventLogger
from paradigm.sandbox.docker import ContainerManager
from paradigm.sandbox.executor import CodeExecutor
from paradigm.sandbox.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    SafetyVerdict,
)
from paradigm.sandbox.safety import SafetyConfig, SafetyScanner

# ============================================================
# Safety Scanner Tests
# ============================================================


class TestSafetyScanner:
    """Tests for AST-based safety scanner."""

    def setup_method(self) -> None:
        self.scanner = SafetyScanner()

    def test_safe_numpy_code(self) -> None:
        code = "import numpy as np\nx = np.array([1, 2, 3])\nprint(x.mean())"
        verdict = self.scanner.scan(code)
        assert verdict.safe is True
        assert verdict.violations == []

    def test_safe_matplotlib_code(self) -> None:
        code = "import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.savefig('plot.png')\n"
        verdict = self.scanner.scan(code)
        assert verdict.safe is True

    def test_safe_scipy_code(self) -> None:
        code = "from scipy import optimize\nresult = optimize.minimize(lambda x: x**2, 0)"
        verdict = self.scanner.scan(code)
        assert verdict.safe is True

    def test_safe_astropy_code(self) -> None:
        code = "from astropy import units as u\ndist = 10 * u.pc"
        verdict = self.scanner.scan(code)
        assert verdict.safe is True

    def test_denied_import_os(self) -> None:
        code = "import os\nos.system('rm -rf /')"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False
        assert any("os" in v for v in verdict.violations)

    def test_denied_import_subprocess(self) -> None:
        code = "import subprocess\nsubprocess.run(['ls'])"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False
        assert any("subprocess" in v for v in verdict.violations)

    def test_denied_from_import(self) -> None:
        code = "from os.path import join"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False
        assert any("os" in v for v in verdict.violations)

    def test_denied_socket(self) -> None:
        code = "import socket\ns = socket.socket()"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False

    def test_denied_builtin_exec(self) -> None:
        code = "exec('print(1)')"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False
        assert any("exec" in v for v in verdict.violations)

    def test_denied_builtin_eval(self) -> None:
        code = "x = eval('1 + 2')"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False
        assert any("eval" in v for v in verdict.violations)

    def test_denied_open(self) -> None:
        code = "f = open('/etc/passwd')"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False
        assert any("open" in v for v in verdict.violations)

    def test_denied_dunder_import(self) -> None:
        code = "__import__('os')"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False

    def test_syntax_error(self) -> None:
        code = "def foo(\n"
        verdict = self.scanner.scan(code)
        assert verdict.safe is False
        assert any("Syntax error" in v for v in verdict.violations)

    def test_code_too_long(self) -> None:
        code = "x = 1\n" * 20_000
        verdict = self.scanner.scan(code)
        assert verdict.safe is False
        assert any("maximum length" in v for v in verdict.violations)

    def test_custom_config(self) -> None:
        """Custom safety config can allow normally-denied modules."""
        config = SafetyConfig(denied_modules=frozenset({"numpy"}), denied_builtins=frozenset())
        scanner = SafetyScanner(config)
        verdict = scanner.scan("import numpy")
        assert verdict.safe is False

        verdict2 = scanner.scan("import os")
        assert verdict2.safe is True

    def test_verdict_summary(self) -> None:
        verdict = SafetyVerdict(safe=True)
        assert "passed" in verdict.summary

        verdict2 = SafetyVerdict(safe=False, violations=["bad import"])
        assert "bad import" in verdict2.summary


# ============================================================
# Container Manager Tests (mocked Docker)
# ============================================================


class TestContainerManager:
    """Tests for Docker container manager with mocked Docker SDK."""

    def setup_method(self) -> None:
        self.config = SandboxConfig(enabled=True, execution_timeout=10)

    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path: Path) -> None:
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.side_effect = [b"hello world\n", b""]

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container

        manager = ContainerManager(self.config)
        manager._client = mock_client

        request = ExecutionRequest(
            code="print('hello world')",
            agent_id="test-agent",
            thread_id="test-thread",
        )
        results_dir = tmp_path / "results"

        result = await manager.execute(request, results_dir)

        assert result.status == ExecutionStatus.SUCCESS
        assert result.exit_code == 0
        assert "hello world" in result.stdout
        mock_container.start.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_execute_failure(self, tmp_path: Path) -> None:
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 1}
        mock_container.logs.side_effect = [b"", b"Traceback...\n"]

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container

        manager = ContainerManager(self.config)
        manager._client = mock_client

        request = ExecutionRequest(
            code="raise ValueError('bad')",
            agent_id="test-agent",
            thread_id="test-thread",
        )
        result = await manager.execute(request, tmp_path / "results")

        assert result.status == ExecutionStatus.FAILURE
        assert result.exit_code == 1
        assert "Traceback" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_timeout(self, tmp_path: Path) -> None:
        mock_container = MagicMock()
        mock_container.wait.side_effect = Exception("timeout")
        mock_container.kill.return_value = None

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container

        manager = ContainerManager(self.config)
        manager._client = mock_client

        request = ExecutionRequest(
            code="import time; time.sleep(999)",
            agent_id="test-agent",
            thread_id="test-thread",
            timeout=1,
        )
        result = await manager.execute(request, tmp_path / "results")

        assert result.status == ExecutionStatus.TIMEOUT
        assert "timed out" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_image_not_found(self, tmp_path: Path) -> None:
        from docker.errors import ImageNotFound

        mock_client = MagicMock()
        mock_client.containers.create.side_effect = ImageNotFound("not found")

        manager = ContainerManager(self.config)
        manager._client = mock_client

        request = ExecutionRequest(
            code="print(1)",
            agent_id="test-agent",
            thread_id="test-thread",
        )
        result = await manager.execute(request, tmp_path / "results")

        assert result.status == ExecutionStatus.ERROR
        assert "not found" in result.error_message

    @pytest.mark.asyncio
    async def test_cleanup_removes_container(self, tmp_path: Path) -> None:
        """Container is always removed, even on success."""
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.side_effect = [b"ok", b""]

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container

        manager = ContainerManager(self.config)
        manager._client = mock_client

        request = ExecutionRequest(code="print('ok')", agent_id="a", thread_id="t")
        await manager.execute(request, tmp_path / "results")

        mock_container.remove.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_ensure_image_exists(self) -> None:
        mock_client = MagicMock()
        mock_client.images.get.return_value = MagicMock()

        manager = ContainerManager(self.config)
        manager._client = mock_client

        assert await manager.ensure_image() is True

    @pytest.mark.asyncio
    async def test_ensure_image_missing(self) -> None:
        from docker.errors import ImageNotFound

        mock_client = MagicMock()
        mock_client.images.get.side_effect = ImageNotFound("nope")

        manager = ContainerManager(self.config)
        manager._client = mock_client

        assert await manager.ensure_image() is False


# ============================================================
# Executor Tests (integration with mocked Docker)
# ============================================================


class TestCodeExecutor:
    """Tests for the high-level code execution pipeline."""

    def setup_method(self) -> None:
        self.config = SandboxConfig(enabled=True, execution_timeout=10)

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, tmp_path: Path) -> None:
        logger = EventLogger(tmp_path / "events.jsonl")
        executor = CodeExecutor(self.config, logger, tmp_path / "data")

        # Mock the container manager
        mock_result = ExecutionResult(
            request=ExecutionRequest(
                code="import numpy as np\nprint(np.pi)",
                agent_id="agent-1",
                thread_id="thread-1",
            ),
            status=ExecutionStatus.SUCCESS,
            stdout="3.141592653589793\n",
            exit_code=0,
            duration_seconds=1.5,
        )

        with patch.object(executor.container_manager, "execute", return_value=mock_result):
            request = ExecutionRequest(
                code="import numpy as np\nprint(np.pi)",
                agent_id="agent-1",
                thread_id="thread-1",
            )
            result = await executor.execute(request)

        assert result.status == ExecutionStatus.SUCCESS
        assert result.safety_verdict is not None
        assert result.safety_verdict.safe is True

    @pytest.mark.asyncio
    async def test_rejection_never_touches_docker(self, tmp_path: Path) -> None:
        logger = EventLogger(tmp_path / "events.jsonl")
        executor = CodeExecutor(self.config, logger, tmp_path / "data")

        with patch.object(executor.container_manager, "execute") as mock_exec:
            request = ExecutionRequest(
                code="import os\nos.system('rm -rf /')",
                agent_id="agent-1",
                thread_id="thread-1",
            )
            result = await executor.execute(request)

        assert result.status == ExecutionStatus.REJECTED
        assert result.safety_verdict is not None
        assert result.safety_verdict.safe is False
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_sandbox(self, tmp_path: Path) -> None:
        config = SandboxConfig(enabled=False)
        logger = EventLogger(tmp_path / "events.jsonl")
        executor = CodeExecutor(config, logger, tmp_path / "data")

        request = ExecutionRequest(
            code="print('hello')",
            agent_id="agent-1",
            thread_id="thread-1",
        )
        result = await executor.execute(request)

        assert result.status == ExecutionStatus.ERROR
        assert "disabled" in result.error_message

    @pytest.mark.asyncio
    async def test_execution_logs_events(self, tmp_path: Path) -> None:
        logger = EventLogger(tmp_path / "events.jsonl")
        executor = CodeExecutor(self.config, logger, tmp_path / "data")

        mock_result = ExecutionResult(
            request=ExecutionRequest(code="print(42)", agent_id="a", thread_id="t"),
            status=ExecutionStatus.SUCCESS,
            stdout="42\n",
            exit_code=0,
            duration_seconds=0.5,
        )

        with patch.object(executor.container_manager, "execute", return_value=mock_result):
            await executor.execute(ExecutionRequest(code="print(42)", agent_id="a", thread_id="t"))

        from paradigm.logging.events import EventType

        events = logger.read_events(event_type=EventType.CODE_EXECUTION)
        # Should have at least 2 events: pre-execution log + result log
        assert len(events) >= 2
