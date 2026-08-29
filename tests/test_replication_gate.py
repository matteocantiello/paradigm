"""Layer 1 — independent adversarial replication gate: an independent re-derivation
of the paper's headline + a sign-stability verdict that gates review."""

from __future__ import annotations

from unittest.mock import MagicMock

from paradigm.config import Config
from paradigm.orchestrator.replication import (
    FRAGILE,
    NOT_REPRODUCED,
    REPRODUCED,
    SKIPPED,
    ReplicationHandler,
    ReplicationReport,
)


def _handler(*, stability=0.8, enabled=True):
    eng = MagicMock()
    eng._config.orchestrator.replication_sign_stability = stability
    eng._config.orchestrator.enable_replication_gate = enabled
    return ReplicationHandler(eng)


class TestAssessVerdict:
    def test_reproduced_and_sign_stable(self):
        h = _handler()
        out = (
            "RESULT[headline_recomputed]=-0.049\nRESULT[headline_reproduced]=1\n"
            "RESULT[n_specs]=5\nRESULT[n_same_sign]=5\n"
        )
        r = h._assess(out)
        assert r.verdict == REPRODUCED and r.reproduced and r.sign_stability == 1.0

    def test_reproduced_but_fragile(self):
        h = _handler()
        out = (
            "RESULT[headline_recomputed]=-0.010\nRESULT[headline_reproduced]=1\n"
            "RESULT[n_specs]=5\nRESULT[n_same_sign]=2\n"  # sign flips in 3/5 → 0.4 < 0.8
        )
        r = h._assess(out)
        assert r.verdict == FRAGILE and r.reproduced and r.sign_stability == 0.4

    def test_not_reproduced(self):
        h = _handler()
        out = "RESULT[headline_recomputed]=0.02\nRESULT[headline_reproduced]=0\nRESULT[n_specs]=5\nRESULT[n_same_sign]=5\n"
        r = h._assess(out)
        assert r.verdict == NOT_REPRODUCED and not r.reproduced

    def test_falls_back_to_per_spec_signs(self):
        # No n_specs/n_same_sign summary → derive stability from per-spec sign tokens.
        h = _handler()
        out = (
            "RESULT[headline_recomputed]=-0.05\nRESULT[headline_reproduced]=1\n"
            "RESULT[spec_a_sign]=-1\nRESULT[spec_b_sign]=1\nRESULT[spec_c_sign]=-1\n"
        )
        r = h._assess(out)
        assert r.n_specs == 3 and r.n_same_sign == 2  # 2 of 3 negative, matching headline
        assert r.verdict == FRAGILE  # 0.667 < 0.8


class TestReport:
    def test_blocking_and_block_text(self):
        frag = ReplicationReport(
            ran=True, verdict=FRAGILE, n_specs=5, n_same_sign=2, sign_stability=0.4
        )
        assert frag.is_blocking
        blk = frag.as_review_block()
        assert "Independent Replication Report" in blk and "FRAGILE" in blk and "2/5" in blk

    def test_reproduced_not_blocking(self):
        rep = ReplicationReport(
            ran=True, verdict=REPRODUCED, n_specs=5, n_same_sign=5, sign_stability=1.0
        )
        assert not rep.is_blocking

    def test_skipped_and_error_have_no_block(self):
        assert ReplicationReport(ran=False, verdict=SKIPPED).as_review_block() == ""
        assert ReplicationReport(ran=True, verdict="error").as_review_block() == ""


class TestGateWiring:
    async def test_skips_when_disabled(self):
        h = _handler(enabled=False)
        r = await h.run_replication(MagicMock())
        assert r.verdict == SKIPPED and not r.ran

    async def test_skips_when_no_draft(self):
        h = _handler(enabled=True)
        r = await h.run_replication(None)
        assert r.verdict == SKIPPED

    def test_finalize_emits_event_on_error(self):
        """A failed gate must emit an event + surface — never vanish silently
        (the bug: 0 replication events across two production runs)."""
        from paradigm.orchestrator.replication import ERROR, ReplicationReport

        h = _handler(enabled=True)
        h._engine.emit_event = MagicMock()
        out = h._finalize(ReplicationReport(ran=True, verdict=ERROR, detail="produced no code"))
        assert out.verdict == ERROR
        h._engine.emit_event.assert_called_once()
        assert h._engine.emit_event.call_args.args[0] == "replication.completed"

    def test_finalize_skipped_stays_silent(self):
        h = _handler(enabled=True)
        h._engine.emit_event = MagicMock()
        h._finalize(ReplicationReport(ran=False, verdict=SKIPPED))
        h._engine.emit_event.assert_not_called()

    def test_replicator_uses_reasoning_headroom(self):
        import inspect

        from paradigm.orchestrator import replication

        src = inspect.getsource(replication.ReplicationHandler.run_replication)
        assert "max_tokens=16384" in src  # not the starved 8192


def test_config_defaults_and_default_yaml(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert Config().orchestrator.enable_replication_gate is False  # back-compat off
    from paradigm.config import load_config

    cfg = load_config("configs/default.yaml").orchestrator
    assert cfg.enable_replication_gate is True
    assert cfg.replication_max_specs == 5


def test_replicator_prompt_is_adversarial_and_structured():
    from paradigm.orchestrator.constants import _REPLICATOR_PROMPT, _REPLICATOR_SYSTEM

    assert "BREAK" in _REPLICATOR_PROMPT and "RE-DERIVE" in _REPLICATOR_PROMPT
    assert "headline_recomputed" in _REPLICATOR_PROMPT
    assert "n_same_sign" in _REPLICATOR_PROMPT and "headline_reproduced" in _REPLICATOR_PROMPT
    assert "adversarial" in _REPLICATOR_SYSTEM.lower()


def test_editor_review_has_replication_check():
    from paradigm.orchestrator.constants import _PHASE_INSTRUCTIONS
    from paradigm.orchestrator.phases import ResearchPhase

    editor = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["editor_review"]
    assert "Independent replication" in editor
    assert "FRAGILE" in editor and "reframed" in editor
