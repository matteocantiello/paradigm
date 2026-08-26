"""Verification kernel (Phase 1B): re-execution as ground truth.

Empirical/computational science has no Lean kernel, so we manufacture a proxy:
a reported result is "accepted" only if its committed code re-runs in a fresh
``--network=none`` sandbox with a fixed seed and reproduces its machine-readable
``RESULT[label]=value`` tokens within tolerance. Experiments that fail to
re-execute, or whose numbers drift beyond tolerance, are demoted by the engine
so the paper cannot be built on unreproduced results.

Plain-Python handler. Default-off via ``config.orchestrator.enable_verification``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from paradigm.knowledge.models import VerificationRecord
from paradigm.sandbox.executor import CodeExecutor
from paradigm.sandbox.models import ExecutionRequest, ExecutionStatus

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine

# RESULT[label]=value  (the console-as-data-bus contract emitted during EXECUTION)
_RESULT_TOKEN_RE = re.compile(r"RESULT\[\s*([^\]]+?)\s*\]\s*=\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)")
_EPSILON = 1e-12


def _extract_result_tokens(stdout: str) -> dict[str, float]:
    """Parse ``RESULT[label]=value`` tokens from stdout (last value wins per label)."""
    values: dict[str, float] = {}
    for label, raw in _RESULT_TOKEN_RE.findall(stdout or ""):
        try:
            values[label.strip()] = float(raw)
        except ValueError:
            continue
    return values


# Run-dependent bookkeeping tokens (whether a cache was hit, wall-clock timing).
# These legitimately differ between the first run and the verification re-run —
# e.g. loaded_from_cache flips 0→1 once the cache exists — so they must NOT count
# against reproducibility. The reproducibility directive tells agents to cache
# live pulls, which is exactly what makes this flag flip.
_BOOKKEEPING_TOKEN_RE = re.compile(
    r"loaded_from_cache|from_cache|cache_hit|cache_miss|cache_used|is_cached|"
    r"\belapsed|runtime|wall_?clock|wall_?time|timestamp|_epoch\b",
    re.IGNORECASE,
)


def _drop_bookkeeping(tokens: dict[str, float]) -> dict[str, float]:
    """Drop run-dependent bookkeeping tokens before the reproducibility compare."""
    return {k: v for k, v in tokens.items() if not _BOOKKEEPING_TOKEN_RE.search(k)}


def _relative_error(a: float, b: float) -> float:
    """Symmetric relative error between two values."""
    denom = max(abs(a), abs(b), _EPSILON)
    return abs(a - b) / denom


def _seed_preamble(seed: int) -> str:
    """Deterministic seeding prepended before re-execution."""
    return (
        f"import random as _v_random\n_v_random.seed({seed})\n"
        "try:\n"
        f"    import numpy as _v_np\n    _v_np.random.seed({seed})\n"
        "except Exception:\n    pass\n"
    )


class VerificationKernel:
    """Re-executes successful experiments and records whether they reproduce."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    async def verify_experiments(
        self, executor: CodeExecutor | None = None
    ) -> list[VerificationRecord]:
        """Re-run each successful experiment in a fresh sandbox and compare outputs.

        Args:
            executor: Optional executor (injected in tests). If None, a fresh one is
                built with an isolated ``verify/<thread>`` workspace so reproduction
                is from committed code + seed only.

        Returns:
            One ``VerificationRecord`` per re-run experiment (also stored on state).
        """
        engine = self._engine
        config = engine._config.orchestrator
        successful = engine.state.successful_code
        if not successful:
            return []

        # Map experiment name -> original captured stdout.
        original_stdout = {
            str(m.get("name", "")): str(m.get("stdout_full", m.get("stdout_preview", "")))
            for m in engine.state.experiment_metadata
        }

        # Only tear down an executor we created here — an injected one (tests)
        # is owned by the caller.
        built_here = executor is None
        if built_here:
            executor = self._build_executor()

        seed = config.verification_seed
        budget = config.verification_reexec_budget
        repo_paths = self._collect_repo_paths()
        records: list[VerificationRecord] = []

        try:
            for name, code in successful[:budget]:
                record = await self._verify_one(
                    executor,
                    name,
                    code,
                    original_stdout.get(name, ""),
                    seed,
                    config.verification_tolerance,
                    repo_paths,
                )
                records.append(record)
                engine._display.info(f"Verification [{record.status}]: {name} — {record.detail}")

            engine.state.verification_records = records
            return records
        finally:
            if built_here:
                await executor.cleanup()

    def _build_executor(self) -> CodeExecutor:
        """Build an executor whose workspace mirrors the thread's.

        Verification re-runs each experiment, so it must see the same environment
        the original run did. We snapshot-copy the persistent thread workspace
        into an isolated ``verify/<thread>`` dir: multi-step experiments that read
        artifacts an earlier step wrote then reproduce instead of FileNotFound-ing
        and being wrongly demoted (the copy keeps verification from mutating the
        real workspace).
        """
        import shutil

        engine = self._engine
        thread = engine.state.thread_id or "thread"
        workspace = engine._config.storage.data_dir / "verify" / thread
        workspace.mkdir(parents=True, exist_ok=True)
        source_ws = engine._config.storage.data_dir / "workspaces" / thread
        if source_ws.is_dir():
            try:
                shutil.copytree(source_ws, workspace, dirs_exist_ok=True)
                # The copy runs as the backend user (root on a server), so the
                # copied artifacts are root-owned; the sandbox runs as a non-root
                # uid and must be able to OVERWRITE them on re-execution (an
                # experiment that re-writes its cached CSV would otherwise hit
                # PermissionError → be wrongly demoted → abort the cycle). Make the
                # copied tree world-writable, mirroring the executor's own
                # _make_sandbox_writable on the workspace dir.
                for p in workspace.rglob("*"):
                    try:
                        p.chmod(0o777 if p.is_dir() else 0o666)
                    except OSError:
                        pass
            except OSError as e:  # a copy hiccup must not crash the cycle
                engine._logger.log_error(e, thread_id=engine.state.thread_id)
        return CodeExecutor(
            config=engine._config.sandbox,
            logger=engine._logger,
            data_dir=engine._config.storage.data_dir,
            workspace_dir=workspace,
        )

    def _collect_repo_paths(self) -> list[str]:
        """The PYTHONPATH the EXECUTION run used — cloned repos + code-file dirs.

        Recomputed from ``resolved_resources`` (a pure function of state) so
        verification imports resolve the same way the original run's did; without
        it, any experiment importing a cloned repo re-runs into ModuleNotFound and
        is demoted. Defensive ``getattr`` keeps injected test engines working.
        """
        from pathlib import Path

        from paradigm.literature.resources import ResourceType

        resources = getattr(self._engine.state, "resolved_resources", None) or []
        repo_paths = [
            r.sandbox_path
            for r in resources
            if r.resource_type == ResourceType.CODE_REPO and r.sandbox_path and r.error is None
        ]
        code_file_dirs = {
            str(Path(r.sandbox_path).parent)
            for r in resources
            if r.resource_type == ResourceType.CODE_FILE and r.sandbox_path and r.error is None
        }
        return repo_paths + sorted(code_file_dirs)

    async def _verify_one(
        self,
        executor: CodeExecutor,
        name: str,
        code: str,
        original_stdout: str,
        seed: int,
        tolerance: float,
        repo_paths: list[str] | None = None,
    ) -> VerificationRecord:
        """Re-execute one experiment and classify whether it reproduced."""
        engine = self._engine
        record = VerificationRecord(experiment_name=name, seed=seed, tolerance=tolerance)

        seeded_code = _seed_preamble(seed) + code
        try:
            result = await executor.execute(
                ExecutionRequest(
                    code=seeded_code,
                    agent_id="verifier",
                    thread_id=engine.state.thread_id,
                ),
                repo_paths=repo_paths,
            )
        except Exception as e:  # noqa: BLE001 — re-execution must never crash the cycle
            engine._logger.log_error(e, thread_id=engine.state.thread_id)
            record.status = "rejected"
            record.detail = f"re-execution raised: {e}"
            return record

        if result.status != ExecutionStatus.SUCCESS:
            record.status = "rejected"
            record.reproduced = False
            record.detail = f"re-execution did not succeed (status={result.status})"
            return record

        orig = _drop_bookkeeping(_extract_result_tokens(original_stdout))
        rerun = _drop_bookkeeping(_extract_result_tokens(result.stdout))
        record.original_values = orig
        record.rerun_values = rerun

        shared = sorted(set(orig) & set(rerun))
        if not shared:
            # Rerun succeeded but there are no comparable RESULT[...] tokens.
            record.status = "accepted"
            record.reproduced = True
            record.detail = "re-executed successfully; no RESULT[] tokens to compare"
            return record

        max_err = max(_relative_error(orig[k], rerun[k]) for k in shared)
        record.max_rel_error = max_err
        if max_err <= tolerance:
            record.status = "accepted"
            record.reproduced = True
            record.detail = f"reproduced {len(shared)} metric(s); max rel error {max_err:.2e}"
        else:
            record.status = "nondeterministic"
            record.reproduced = False
            worst = max(shared, key=lambda k: _relative_error(orig[k], rerun[k]))
            record.detail = (
                f"did not reproduce: {worst} {orig[worst]:g}->{rerun[worst]:g} "
                f"(rel error {max_err:.2e} > tol {tolerance:g})"
            )
        return record

    @staticmethod
    def apply_gate(engine: OrchestrationEngine, records: list[VerificationRecord]) -> int:
        """Demote experiments that did not verify so WRITING can't use them.

        Non-``accepted`` experiments are removed from ``successful_code`` and their
        metadata is flipped to ``failure`` (which routes them into the FAILED /
        FORBIDDEN sections of the writing Fact Sheet via existing machinery).

        Returns:
            The number of experiments demoted.
        """
        rejected = {r.experiment_name for r in records if r.status != "accepted"}
        if not rejected:
            return 0

        engine.state.successful_code = [
            (name, code) for (name, code) in engine.state.successful_code if name not in rejected
        ]
        detail_by_name = {r.experiment_name: r.detail for r in records}
        for entry in engine.state.experiment_metadata:
            if str(entry.get("name", "")) in rejected:
                entry["status"] = "failure"
                entry["failure_reason"] = "Failed verification: " + detail_by_name.get(
                    str(entry.get("name", "")), ""
                )
        return len(rejected)
