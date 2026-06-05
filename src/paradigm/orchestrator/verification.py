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
                )
                records.append(record)
                engine._display.info(f"Verification [{record.status}]: {name} — {record.detail}")

            engine.state.verification_records = records
            return records
        finally:
            if built_here:
                await executor.cleanup()

    def _build_executor(self) -> CodeExecutor:
        """Build an executor with a fresh, isolated verification workspace."""
        engine = self._engine
        workspace = (
            engine._config.storage.data_dir / "verify" / (engine.state.thread_id or "thread")
        )
        workspace.mkdir(parents=True, exist_ok=True)
        return CodeExecutor(
            config=engine._config.sandbox,
            logger=engine._logger,
            data_dir=engine._config.storage.data_dir,
            workspace_dir=workspace,
        )

    async def _verify_one(
        self,
        executor: CodeExecutor,
        name: str,
        code: str,
        original_stdout: str,
        seed: int,
        tolerance: float,
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
                )
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

        orig = _extract_result_tokens(original_stdout)
        rerun = _extract_result_tokens(result.stdout)
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
