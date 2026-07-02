"""High-level code execution pipeline."""

import ast
import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from paradigm.config import SandboxConfig
from paradigm.logging.events import EventLogger
from paradigm.sandbox.docker import ContainerManager
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from paradigm.sandbox.safety import SafetyConfig, SafetyScanner

_logger = logging.getLogger(__name__)

# Max characters of stdout/stderr to include in event logs
_LOG_OUTPUT_LIMIT: int = 2048


def prune_execution_dirs(executions_dir: Path, retention_days: int, keep_last: int) -> int:
    """Prune old per-execution results dirs under ``data/executions/``.

    Bounded sweep: a dir survives only if it is within the newest ``keep_last``
    AND younger than ``retention_days``. A bound <= 0 disables that bound.
    Per-paper experiment code is archived separately by the engine, so pruning
    loses nothing load-bearing.

    Never raises — unreadable entries and failed deletes are logged and skipped.

    Returns:
        The number of directories removed.
    """
    if retention_days <= 0 and keep_last <= 0:
        return 0
    if not executions_dir.is_dir():
        return 0

    entries: list[tuple[float, Path]] = []
    try:
        for path in executions_dir.iterdir():
            try:
                if path.is_dir():
                    entries.append((path.stat().st_mtime, path))
            except OSError as e:
                _logger.warning("Skipping unreadable executions entry %s: %s", path, e)
    except OSError as e:
        _logger.warning("Could not scan %s for pruning: %s", executions_dir, e)
        return 0

    entries.sort(key=lambda item: item[0], reverse=True)  # newest first
    cutoff = time.time() - retention_days * 86400 if retention_days > 0 else None

    removed = 0
    for index, (mtime, path) in enumerate(entries):
        beyond_count = keep_last > 0 and index >= keep_last
        too_old = cutoff is not None and mtime < cutoff
        if not (beyond_count or too_old):
            continue
        try:
            shutil.rmtree(path)
            removed += 1
        except Exception as e:
            _logger.warning("Could not prune execution results dir %s: %s", path, e)
    if removed:
        _logger.info("Pruned %d old execution results dir(s) from %s", removed, executions_dir)
    return removed


def _make_sandbox_writable(path: Path) -> None:
    """Make a host dir writable by the container's non-root ``sandbox`` user.

    /data/workspace and /data/results are bind-mounted from host dirs created
    by the backend. On a deployed VM the backend runs as root, so those dirs
    are root-owned and the in-container ``sandbox`` user gets PermissionError
    when it writes intermediate files/figures. Relaxing the mode (the dirs are
    ephemeral per-thread scratch under the data dir) lets the sandbox write.
    """
    try:
        path.chmod(0o777)
    except OSError as e:
        _logger.warning("Could not relax permissions on %s for the sandbox: %s", path, e)


# Auto-import preamble prepended to all experiment code.
# Agents frequently use standard aliases (np, pd, plt) without explicit imports;
# this prevents NameError crashes for the most common scientific libraries.
#
# It ALSO applies a publication-quality matplotlib style to EVERY generated figure
# (experiment + conceptual) — both paths run through CodeExecutor.execute, so this
# is the single styling chokepoint. Without it, figures used raw matplotlib
# defaults: tiny fonts, clashing colors, thin spines, and the notorious
# "1e-13+7.04e-2" axis offset text. The style is best-effort (try/except) so a
# matplotlib version that rejects a key can never break an experiment. Agent code
# can still override any of these afterwards.
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
try:
    from cycler import cycler as _cycler
    plt.rcParams.update({
        'figure.figsize': (7.0, 4.5),
        'figure.dpi': 150,
        'figure.facecolor': 'white',
        'savefig.dpi': 200,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.05,
        'savefig.facecolor': 'white',
        'font.family': 'serif',
        'font.serif': ['DejaVu Serif'],
        'font.size': 12,
        'mathtext.fontset': 'cm',
        'axes.titlesize': 13,
        'axes.titleweight': 'bold',
        'axes.labelsize': 12,
        'axes.linewidth': 0.8,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.grid': True,
        'axes.axisbelow': True,
        'grid.alpha': 0.3,
        'grid.linewidth': 0.6,
        'axes.formatter.useoffset': False,
        'axes.formatter.use_mathtext': True,
        'legend.fontsize': 10,
        'legend.frameon': False,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'xtick.direction': 'out',
        'ytick.direction': 'out',
        'lines.linewidth': 1.8,
        'lines.markersize': 5,
        'image.cmap': 'viridis',
        'axes.prop_cycle': _cycler(color=[
            '#0072B2', '#D55E00', '#009E73', '#CC79A7',
            '#E69F00', '#56B4E9', '#999999', '#000000',
        ]),
    })
except Exception:
    pass
try:
    import astropy.units as u
    import astropy.constants as const
except ImportError:
    pass
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
        # Bounded retention sweep at startup — executions/ otherwise grows one
        # results dir per execution, forever (1,000+ dirs observed locally).
        prune_execution_dirs(
            self.data_dir / "executions",
            config.executions_retention_days,
            config.executions_keep_last,
        )

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
            _make_sandbox_writable(workspace_dir)

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
        _make_sandbox_writable(results_dir)
        return results_dir

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.container_manager.cleanup()
        prune_execution_dirs(
            self.data_dir / "executions",
            self.config.executions_retention_days,
            self.config.executions_keep_last,
        )
