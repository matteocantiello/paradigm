"""High-level code execution pipeline."""

from datetime import UTC, datetime
from pathlib import Path

from paradigm.config import SandboxConfig
from paradigm.logging.events import EventLogger
from paradigm.sandbox.docker import ContainerManager
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from paradigm.sandbox.safety import SafetyScanner

# Max characters of stdout/stderr to include in event logs
_LOG_OUTPUT_LIMIT: int = 2048


class CodeExecutor:
    """Orchestrates the code execution pipeline.

    Pipeline: safety scan → log → Docker execute → log result → return.
    """

    def __init__(
        self,
        config: SandboxConfig,
        logger: EventLogger,
        data_dir: Path,
    ) -> None:
        self.config = config
        self.logger = logger
        self.data_dir = data_dir
        self.scanner = SafetyScanner()
        self.container_manager = ContainerManager(config)

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code through the full safety + Docker pipeline.

        Args:
            request: The code execution request.

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

        # Step 2: Log code before execution
        self.logger.log_code_execution(
            agent_id=request.agent_id,
            thread_id=request.thread_id,
            code=request.code[:_LOG_OUTPUT_LIMIT],
            success=True,
            output="Execution started",
        )

        # Step 3: Execute in Docker
        results_dir = self._make_results_dir(request)
        shared_dir = self.data_dir / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)

        result = await self.container_manager.execute(
            request=request,
            results_dir=results_dir,
            shared_dir=shared_dir,
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
