"""Tests for Phase 1B — the verification kernel (re-execution as ground truth)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.verification import (
    VerificationKernel,
    _extract_result_tokens,
    _relative_error,
)
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestResultTokens:
    def test_extract_basic(self):
        out = _extract_result_tokens("RESULT[rmse]=0.123\nRESULT[r2]=0.95")
        assert out == {"rmse": 0.123, "r2": 0.95}

    def test_last_value_wins(self):
        assert _extract_result_tokens("RESULT[x]=1\nRESULT[x]=2") == {"x": 2.0}

    def test_scientific_and_spaces(self):
        assert _extract_result_tokens("RESULT[ p ] = 1.2e-3") == {"p": 0.0012}

    def test_ignores_non_tokens(self):
        assert _extract_result_tokens("no tokens here") == {}


class TestRelativeError:
    def test_zero_for_equal(self):
        assert _relative_error(1.0, 1.0) == 0.0

    def test_symmetric(self):
        assert _relative_error(1.0, 2.0) == _relative_error(2.0, 1.0)


# ---------------------------------------------------------------------------
# Fake executor + engine
# ---------------------------------------------------------------------------


class FakeExecutor:
    """Async executor stub: maps re-run code -> (status, stdout) via a responder."""

    def __init__(self, responder):
        self._responder = responder
        self.calls = 0

    async def execute(self, request: ExecutionRequest, repo_paths=None) -> ExecutionResult:
        self.calls += 1
        status, stdout = self._responder(request.code)
        return ExecutionResult(request=request, status=status, stdout=stdout)


def _make_engine(successful_code, metadata, *, tolerance=1e-6, budget=20):
    state = SimpleNamespace(
        thread_id="t1",
        successful_code=list(successful_code),
        experiment_metadata=[dict(m) for m in metadata],
        verification_records=[],
    )
    orch = SimpleNamespace(
        verification_seed=12345,
        verification_reexec_budget=budget,
        verification_tolerance=tolerance,
        abort_on_verification_failure=True,
    )
    config = SimpleNamespace(orchestrator=orch)
    return SimpleNamespace(
        _config=config,
        _logger=MagicMock(),
        _display=MagicMock(),
        state=state,
    )


# ---------------------------------------------------------------------------
# verify_experiments
# ---------------------------------------------------------------------------


class TestVerifyExperiments:
    async def test_reproduced_accepted(self):
        engine = _make_engine(
            [("exp1", "code")],
            [{"name": "exp1", "status": "success", "stdout_full": "RESULT[rmse]=0.100"}],
        )
        executor = FakeExecutor(lambda code: (ExecutionStatus.SUCCESS, "RESULT[rmse]=0.100"))
        records = await VerificationKernel(engine).verify_experiments(executor)
        assert len(records) == 1
        assert records[0].status == "accepted"
        assert records[0].reproduced is True
        assert engine.state.verification_records == records

    async def test_nondeterministic_rejected(self):
        engine = _make_engine(
            [("exp1", "code")],
            [{"name": "exp1", "status": "success", "stdout_full": "RESULT[rmse]=0.100"}],
        )
        executor = FakeExecutor(lambda code: (ExecutionStatus.SUCCESS, "RESULT[rmse]=0.500"))
        records = await VerificationKernel(engine).verify_experiments(executor)
        assert records[0].status == "nondeterministic"
        assert records[0].reproduced is False
        assert records[0].max_rel_error is not None and records[0].max_rel_error > 0

    async def test_rerun_failure_rejected(self):
        engine = _make_engine(
            [("exp1", "code")],
            [{"name": "exp1", "status": "success", "stdout_full": "RESULT[rmse]=0.100"}],
        )
        executor = FakeExecutor(lambda code: (ExecutionStatus.FAILURE, ""))
        records = await VerificationKernel(engine).verify_experiments(executor)
        assert records[0].status == "rejected"
        assert records[0].reproduced is False

    async def test_no_tokens_accepted(self):
        engine = _make_engine(
            [("exp1", "code")],
            [{"name": "exp1", "status": "success", "stdout_full": "did some stuff"}],
        )
        executor = FakeExecutor(lambda code: (ExecutionStatus.SUCCESS, "did some stuff"))
        records = await VerificationKernel(engine).verify_experiments(executor)
        assert records[0].status == "accepted"
        assert records[0].reproduced is True

    async def test_seed_preamble_injected(self):
        engine = _make_engine(
            [("exp1", "print(1)")],
            [{"name": "exp1", "status": "success", "stdout_full": ""}],
        )
        seen = {}

        def responder(code):
            seen["code"] = code
            return (ExecutionStatus.SUCCESS, "")

        await VerificationKernel(engine).verify_experiments(FakeExecutor(responder))
        assert "seed(12345)" in seen["code"]
        assert seen["code"].endswith("print(1)")

    async def test_budget_caps_reruns(self):
        codes = [(f"exp{i}", "code") for i in range(5)]
        meta = [{"name": f"exp{i}", "status": "success", "stdout_full": ""} for i in range(5)]
        engine = _make_engine(codes, meta, budget=2)
        executor = FakeExecutor(lambda code: (ExecutionStatus.SUCCESS, ""))
        records = await VerificationKernel(engine).verify_experiments(executor)
        assert len(records) == 2
        assert executor.calls == 2

    async def test_no_successful_code_returns_empty(self):
        engine = _make_engine([], [])
        records = await VerificationKernel(engine).verify_experiments(FakeExecutor(lambda c: None))
        assert records == []


# ---------------------------------------------------------------------------
# apply_gate
# ---------------------------------------------------------------------------


class TestApplyGate:
    def test_demotes_unverified(self):
        from paradigm.knowledge.models import VerificationRecord

        engine = _make_engine(
            [("good", "c1"), ("bad", "c2")],
            [
                {"name": "good", "status": "success", "stdout_full": ""},
                {"name": "bad", "status": "success", "stdout_full": ""},
            ],
        )
        records = [
            VerificationRecord(experiment_name="good", status="accepted", reproduced=True),
            VerificationRecord(
                experiment_name="bad", status="nondeterministic", detail="drifted"
            ),
        ]
        demoted = VerificationKernel.apply_gate(engine, records)
        assert demoted == 1
        assert [n for n, _ in engine.state.successful_code] == ["good"]
        bad_meta = next(m for m in engine.state.experiment_metadata if m["name"] == "bad")
        assert bad_meta["status"] == "failure"
        assert "Failed verification" in bad_meta["failure_reason"]

    def test_no_demotion_when_all_accepted(self):
        from paradigm.knowledge.models import VerificationRecord

        engine = _make_engine(
            [("good", "c1")], [{"name": "good", "status": "success", "stdout_full": ""}]
        )
        records = [VerificationRecord(experiment_name="good", status="accepted", reproduced=True)]
        assert VerificationKernel.apply_gate(engine, records) == 0
        assert [n for n, _ in engine.state.successful_code] == ["good"]


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------


class TestVerificationPhase:
    def test_execution_to_verification(self):
        pm = PhaseManager(ResearchPhase.EXECUTION)
        assert pm.can_transition_to(ResearchPhase.VERIFICATION)

    def test_verification_to_writing(self):
        pm = PhaseManager(ResearchPhase.VERIFICATION)
        assert pm.can_transition_to(ResearchPhase.WRITING)

    def test_verification_to_post_execution(self):
        pm = PhaseManager(ResearchPhase.VERIFICATION)
        assert pm.can_transition_to(ResearchPhase.POST_EXECUTION)

    def test_legacy_execution_to_post_execution_still_valid(self):
        pm = PhaseManager(ResearchPhase.EXECUTION)
        assert pm.can_transition_to(ResearchPhase.POST_EXECUTION)
