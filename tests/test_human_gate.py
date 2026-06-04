"""Tests for Phase 1E — hybrid human-gate + provenance."""

from __future__ import annotations

from paradigm.knowledge.models import PredictionRule, VerificationRecord
from paradigm.orchestrator.human_gate import build_provenance, decide_human_gate

_POINTS = ["problem_selection", "pre_registration", "final_verification"]


# ---------------------------------------------------------------------------
# decide_human_gate
# ---------------------------------------------------------------------------


class TestDecideHumanGate:
    def test_off_always_continues(self):
        called = []

        def hook(t, f, to):
            called.append((f, to))
            return "abort"

        decision, _ = decide_human_gate("off", _POINTS, "problem_selection", hook, "t1")
        assert decision == "continue"
        assert called == []  # hook never consulted when off

    def test_point_not_enabled_continues(self):
        decision, _ = decide_human_gate("blocking", ["pre_registration"], "problem_selection", None, "t1")
        assert decision == "continue"

    def test_advisory_never_blocks(self):
        def hook(t, f, to):
            return "abort"

        decision, reason = decide_human_gate("advisory", _POINTS, "pre_registration", hook, "t1")
        assert decision == "continue"
        assert "advisory" in reason

    def test_blocking_defers_to_hook(self):
        def hook(t, f, to):
            return "abort"

        decision, _ = decide_human_gate("blocking", _POINTS, "final_verification", hook, "t1")
        assert decision == "abort"

    def test_blocking_pause(self):
        decision, _ = decide_human_gate(
            "blocking", _POINTS, "final_verification", lambda t, f, to: "pause", "t1"
        )
        assert decision == "pause"

    def test_blocking_no_hook_deadlock_guard(self):
        decision, reason = decide_human_gate("blocking", _POINTS, "problem_selection", None, "t1")
        assert decision == "continue"
        assert "deadlock guard" in reason

    def test_blocking_invalid_hook_result_falls_back(self):
        decision, _ = decide_human_gate(
            "blocking", _POINTS, "problem_selection", lambda t, f, to: "garbage", "t1"
        )
        assert decision == "continue"


# ---------------------------------------------------------------------------
# build_provenance
# ---------------------------------------------------------------------------


class TestBuildProvenance:
    def test_autonomous_defaults(self):
        rec = build_provenance(
            paper_id="p1",
            thread_id="t1",
            mode="off",
            gate_decisions={},
            registered_rules=[],
            verification_records=[],
        )
        assert rec.framed_by == "agents"
        assert rec.registered_by == "none"
        assert rec.verified_by == "none"
        assert rec.human_gate_mode == "off"

    def test_human_framed_when_blocking_problem_selection(self):
        rec = build_provenance(
            paper_id="p1",
            thread_id="t1",
            mode="blocking",
            gate_decisions={"problem_selection": "continue"},
            registered_rules=[],
            verification_records=[],
        )
        assert rec.framed_by == "human"

    def test_advisory_is_not_human_framed(self):
        rec = build_provenance(
            paper_id="p1",
            thread_id="t1",
            mode="advisory",
            gate_decisions={"problem_selection": "continue"},
            registered_rules=[],
            verification_records=[],
        )
        assert rec.framed_by == "agents"

    def test_registered_and_verified(self):
        rules = [PredictionRule(id="r1"), PredictionRule(id="r2")]
        records = [
            VerificationRecord(experiment_name="a", status="accepted"),
            VerificationRecord(experiment_name="b", status="nondeterministic"),
        ]
        rec = build_provenance(
            paper_id="p1",
            thread_id="t1",
            mode="blocking",
            gate_decisions={"final_verification": "continue"},
            registered_rules=rules,
            verification_records=records,
        )
        assert rec.registered_by == "agents"
        assert rec.prereg_rule_ids == ["r1", "r2"]
        assert rec.verified_by == "kernel+human"
        assert rec.verification_summary == {"accepted": "1", "total": "2"}

    def test_kernel_only_without_human_gate(self):
        records = [VerificationRecord(experiment_name="a", status="accepted")]
        rec = build_provenance(
            paper_id="p1",
            thread_id="t1",
            mode="off",
            gate_decisions={},
            registered_rules=[],
            verification_records=records,
        )
        assert rec.verified_by == "kernel"
