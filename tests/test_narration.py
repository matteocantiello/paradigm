"""Tests for the templated event narrator (Phase B)."""

from __future__ import annotations

import pytest

from paradigm.display.narration import PHASE_PURPOSE, narrate, narrate_llm

KNOWN_CATEGORIES = [
    "phase_transition",
    "round_start",
    "search_result",
    "debate_start",
    "debate_complete",
    "experiment_running",
    "experiment_result",
    "convergence_detected",
    "peer_review_decision",
    "paper_saved",
    "citation_grounding",
    "novelty_check",
    "seed_discovery",
    "agent_step",
]


@pytest.mark.parametrize("category", KNOWN_CATEGORIES)
def test_known_categories_return_string(category):
    out = narrate(category, phase="ideation", agent_id="theorist-1", title="t")
    assert isinstance(out, str)


def test_phase_transition_uses_purpose():
    out = narrate("phase_transition", to_phase="execution")
    assert "execution" in out.lower()
    assert PHASE_PURPOSE["execution"].split()[0] in out  # purpose woven in


def test_debate_uses_roles():
    out = narrate("debate_start", challenger_id="skeptic-2", defender_id="theorist-1")
    assert "skeptic" in out and "theorist" in out


def test_experiment_result_status_variants():
    ok = narrate("experiment_result", name="exp_a", status="success")
    fail = narrate("experiment_result", name="exp_a", status="failure")
    assert "exp_a" in ok and "success" in ok.lower()
    assert "exp_a" in fail and "failure" in fail.lower()


def test_unknown_category_falls_back_to_title():
    assert narrate("totally_unknown", title="fallback text") == "fallback text"
    assert narrate("totally_unknown") == ""


def test_never_raises_on_bad_context():
    # Missing/None context must not raise.
    assert isinstance(narrate("round_start"), str)
    assert isinstance(narrate("search_result", query=None, count=None), str)


def test_narrate_llm_falls_back_to_templated_without_calling_provider():
    class _Boom:
        def complete(self, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("provider should not be called in stub mode")

    out = narrate_llm(_Boom(), "model", "phase_transition", to_phase="writing")
    assert "writing" in out.lower()
