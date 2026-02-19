"""High-level code execution pipeline."""

import ast
from datetime import UTC, datetime
from pathlib import Path

from paradigm.config import SandboxConfig
from paradigm.logging.events import EventLogger
from paradigm.sandbox.docker import ContainerManager
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from paradigm.sandbox.safety import SafetyConfig, SafetyScanner

# Max characters of stdout/stderr to include in event logs
_LOG_OUTPUT_LIMIT: int = 2048

# Auto-import preamble prepended to all experiment code.
# Agents frequently use standard aliases (np, pd, plt) without explicit imports;
# this prevents NameError crashes for the most common scientific libraries.
_SCIENCE_PREAMBLE = """\
import re
import numpy as np
import scipy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
workspace = Path('/data/workspace')
workspace.mkdir(parents=True, exist_ok=True)
"""


class CodeExecutor:
    """Orchestrates the code execution pipeline.

    Pipeline: safety scan → log → Docker execute → log result → return.
    """

    def __init__(
        self,
        config: SandboxConfig,
        logger: EventLogger,
        data_dir: Path,
        workspace_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.data_dir = data_dir
        self.workspace_dir = workspace_dir
        self.scanner = SafetyScanner(SafetyConfig(network_enabled=config.network_mode != "none"))
        self.container_manager = ContainerManager(config)

    async def execute(
        self,
        request: ExecutionRequest,
        repo_paths: list[str] | None = None,
    ) -> ExecutionResult:
        """Execute code through the full safety + Docker pipeline.

        Args:
            request: The code execution request.
            repo_paths: Optional list of sandbox paths to include in PYTHONPATH,
                allowing sandbox code to import from cloned repositories.

        Returns:
            ExecutionResult with the outcome.
        """
        # Step 0: Check if sandbox is enabled
        if not self.config.enabled:
            return ExecutionResult(
                request=request,
                status=ExecutionStatus.ERROR,
                error_message="Sandbox is disabled in configuration.",
            )

        # Step 0b: Quick syntax check — catches SyntaxError before Docker overhead
        try:
            ast.parse(request.code)
        except SyntaxError as e:
            self.logger.log_code_execution(
                agent_id=request.agent_id,
                thread_id=request.thread_id,
                code=request.code[:_LOG_OUTPUT_LIMIT],
                success=False,
                error=f"Syntax error (pre-flight): {e}",
            )
            return ExecutionResult(
                request=request,
                status=ExecutionStatus.FAILURE,
                error_message=f"SyntaxError on line {e.lineno}: {e.msg}",
                stderr=f'  File "script.py", line {e.lineno}\n    {e.text or ""}\n    SyntaxError: {e.msg}',
            )

        # Step 1: Safety scan
        verdict = self.scanner.scan(request.code)

        if not verdict.safe:
            # Log rejection
            self.logger.log_code_execution(
                agent_id=request.agent_id,
                thread_id=request.thread_id,
                code=request.code[:_LOG_OUTPUT_LIMIT],
                success=False,
                error=f"Safety scan failed: {verdict.summary}",
            )
            return ExecutionResult(
                request=request,
                status=ExecutionStatus.REJECTED,
                safety_verdict=verdict,
                error_message=verdict.summary,
            )

        # Step 2: Prepend standard scientific imports so agents don't crash
        # on common aliases (np, pd, plt) they forget to import explicitly.
        request = request.model_copy(update={"code": _SCIENCE_PREAMBLE + request.code})

        # Step 3: Log code before execution
        self.logger.log_code_execution(
            agent_id=request.agent_id,
            thread_id=request.thread_id,
            code=request.code[:_LOG_OUTPUT_LIMIT],
            success=True,
            output="Execution started",
        )

        # Step 4: Execute in Docker
        results_dir = self._make_results_dir(request)
        shared_dir = self.data_dir / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)

        # Build environment for PYTHONPATH injection (cloned repos)
        environment: dict[str, str] = {}
        if repo_paths:
            environment["PYTHONPATH"] = ":".join(repo_paths)

        # Workspace dir persists across executions within a thread
        workspace_dir = self.workspace_dir
        if workspace_dir:
            workspace_dir.mkdir(parents=True, exist_ok=True)

        # Offline pip cache for agent-driven package installs
        packages_dir = self.data_dir / "packages"
        if not packages_dir.is_dir():
            packages_dir = None

        result = await self.container_manager.execute(
            request=request,
            results_dir=results_dir,
            shared_dir=shared_dir,
            workspace_dir=workspace_dir,
            packages_dir=packages_dir,
            environment=environment,
        )
        result.safety_verdict = verdict

        # Step 4: Log result
        self.logger.log_code_execution(
            agent_id=request.agent_id,
            thread_id=request.thread_id,
            code=request.code[:_LOG_OUTPUT_LIMIT],
            success=result.status == ExecutionStatus.SUCCESS,
            output=result.stdout[:_LOG_OUTPUT_LIMIT] if result.stdout else None,
            error=result.stderr[:_LOG_OUTPUT_LIMIT] if result.stderr else None,
            status=result.status.value,
            exit_code=result.exit_code,
            duration_seconds=result.duration_seconds,
        )

        return result

    def _make_results_dir(self, request: ExecutionRequest) -> Path:
        """Create a unique results directory for this execution."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        dir_name = f"{request.agent_id}-{timestamp}"
        results_dir = self.data_dir / "executions" / dir_name
        results_dir.mkdir(parents=True, exist_ok=True)
        return results_dir

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.container_manager.cleanup()
