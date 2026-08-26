"""Phase 2: scientific-validity gate (review + experiment directives).

Evidence: a live cycle tested a theory on a sample outside the regime where it
applies and reported an artefactual 'measurement' — honest and traceable, yet it
did not answer its own question, and the editor accepted it anyway.
"""

from __future__ import annotations

from paradigm.orchestrator.constants import _SCIENTIFIC_VALIDITY_DIRECTIVE
from paradigm.orchestrator.phases import ResearchPhase


def test_validity_directive_covers_regime_sanity_and_competition():
    d = _SCIENTIFIC_VALIDITY_DIRECTIVE
    assert "REGIME RELEVANCE" in d
    assert "SANITY ORACLES" in d
    assert "COMPETE ALTERNATIVES" in d
    # Domain-agnostic — no field specifics baked into the platform.
    for word in ("tidal", "Zahn", "binary", "stellar", "Gaia"):
        assert word.lower() not in d.lower()


def test_validity_directive_injected_into_experiment_prompts():
    import inspect

    from paradigm.orchestrator import experimentation

    src = inspect.getsource(experimentation)
    assert "prompt += _SCIENTIFIC_VALIDITY_DIRECTIVE" in src


def test_editor_review_has_scientific_validity_check():
    from paradigm.orchestrator.constants import _PHASE_INSTRUCTIONS

    editor = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["editor_review"]
    # A paper can be honest+traceable yet fail to answer its own question.
    assert "Scientific validity" in editor
    assert "regime" in editor.lower()
    assert "REFRAME" in editor
    # An honest, correctly-scoped null/pilot must remain acceptable.
    assert "pilot result is acceptable" in editor
