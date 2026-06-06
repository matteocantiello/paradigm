"""Tests for Phase 1A — falsifiability / pre-registration."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from paradigm.knowledge.models import (
    Hypothesis,
    PredictionDirection,
    PredictionRule,
    PredictionVerdict,
)
from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.preregistration import PreRegistrationHandler, _extract_metric

# ---------------------------------------------------------------------------
# PredictionRule: well-formedness + holds()
# ---------------------------------------------------------------------------


class TestPredictionRuleWellFormed:
    def test_requires_refutation_condition(self):
        r = PredictionRule(metric_stdout_key="r", direction=PredictionDirection.GREATER, low=0.5)
        assert not r.is_well_formed()  # empty refutation_condition

    def test_requires_metric_key(self):
        r = PredictionRule(
            direction=PredictionDirection.GREATER, low=0.5, refutation_condition="r<0.5"
        )
        assert not r.is_well_formed()

    def test_inside_needs_both_bounds(self):
        r = PredictionRule(
            metric_stdout_key="r",
            direction=PredictionDirection.INSIDE,
            low=0.5,
            refutation_condition="outside band",
        )
        assert not r.is_well_formed()  # high missing
        r.high = 0.9
        assert r.is_well_formed()

    def test_greater_needs_low(self):
        r = PredictionRule(
            metric_stdout_key="r",
            direction=PredictionDirection.GREATER,
            low=0.5,
            refutation_condition="r<=0.5",
        )
        assert r.is_well_formed()


class TestPredictionRuleHolds:
    def test_inside(self):
        r = PredictionRule(direction=PredictionDirection.INSIDE, low=0.0, high=1.0)
        assert r.holds(0.5)
        assert not r.holds(1.5)

    def test_outside(self):
        r = PredictionRule(direction=PredictionDirection.OUTSIDE, low=0.0, high=1.0)
        assert r.holds(2.0)
        assert not r.holds(0.5)

    def test_greater(self):
        r = PredictionRule(direction=PredictionDirection.GREATER, low=0.5)
        assert r.holds(0.6)
        assert not r.holds(0.4)

    def test_less(self):
        r = PredictionRule(direction=PredictionDirection.LESS, high=0.5)
        assert r.holds(0.4)
        assert not r.holds(0.6)


# ---------------------------------------------------------------------------
# _extract_metric
# ---------------------------------------------------------------------------


class TestExtractMetric:
    def test_equals_and_colon(self):
        assert _extract_metric("pearson_r=0.83", "pearson_r") == 0.83
        assert _extract_metric("pearson_r: 0.42", "pearson_r") == 0.42

    def test_scientific_notation(self):
        assert _extract_metric("pval=1.2e-3", "pval") == 0.0012

    def test_negative(self):
        assert _extract_metric("slope=-2.5", "slope") == -2.5

    def test_last_occurrence_wins(self):
        assert _extract_metric("r=0.1\nr=0.9", "r") == 0.9

    def test_missing_returns_none(self):
        assert _extract_metric("nothing here", "r") is None

    def test_empty_key_returns_none(self):
        assert _extract_metric("r=0.5", "") is None


# ---------------------------------------------------------------------------
# Handler: _parse_rules (pure)
# ---------------------------------------------------------------------------


class TestParseRules:
    def test_valid_array_maps_by_index(self):
        data = [
            {
                "hypothesis_index": 0,
                "metric_name": "pearson_r",
                "metric_stdout_key": "pearson_r",
                "direction": "greater",
                "low": 0.5,
                "refutation_condition": "r<=0.5",
            }
        ]
        rules = PreRegistrationHandler._parse_rules(data, n_hypotheses=2)
        assert 0 in rules
        assert rules[0].is_well_formed()
        assert rules[0].direction == PredictionDirection.GREATER

    def test_out_of_range_index_dropped(self):
        data = [{"hypothesis_index": 5, "metric_stdout_key": "r", "refutation_condition": "x"}]
        assert PreRegistrationHandler._parse_rules(data, n_hypotheses=2) == {}

    def test_bad_direction_defaults_inside(self):
        data = [{"hypothesis_index": 0, "metric_stdout_key": "r", "direction": "sideways"}]
        rules = PreRegistrationHandler._parse_rules(data, n_hypotheses=1)
        assert rules[0].direction == PredictionDirection.INSIDE

    def test_non_list_returns_empty(self):
        assert PreRegistrationHandler._parse_rules({"x": 1}, n_hypotheses=1) == {}


# ---------------------------------------------------------------------------
# Fake engine for handler integration tests
# ---------------------------------------------------------------------------


def _make_engine(*, provider_response: str | None = None, **knowledge_overrides):
    state = SimpleNamespace(
        thread_id="t1",
        seed_prompt="topic",
        planning_action_items="run experiment X",
        selected_hypotheses=[],
        registered_rules=[],
        prereg_verdicts=[],
        world_model=None,
    )
    knowledge = SimpleNamespace(
        enable_preregistration=True,
        prereg_require_refutation=True,
        prereg_on_empty="advisory",
    )
    for k, v in knowledge_overrides.items():
        setattr(knowledge, k, v)
    provider = MagicMock()
    if provider_response is not None:
        provider.complete = MagicMock(return_value=(provider_response, 1, 1))
    config = SimpleNamespace(
        knowledge=knowledge,
        get_provider_and_model_for_role=MagicMock(return_value=(provider, "model-x", None)),
    )
    return SimpleNamespace(
        _config=config,
        _db=MagicMock(),
        _logger=MagicMock(),
        _display=MagicMock(),
        state=state,
    )


# ---------------------------------------------------------------------------
# run_freeze
# ---------------------------------------------------------------------------


class TestRunFreeze:
    async def test_freezes_well_formed_and_drops_unfalsifiable(self):
        h_good = Hypothesis(id="hg", statement="X correlates with Y")
        h_bad = Hypothesis(id="hb", statement="vague idea")
        response = json.dumps(
            [
                {
                    "hypothesis_index": 0,
                    "metric_name": "pearson_r",
                    "metric_stdout_key": "pearson_r",
                    "direction": "greater",
                    "low": 0.5,
                    "refutation_condition": "pearson_r <= 0.5",
                },
                {  # ill-formed: no refutation condition, no bound
                    "hypothesis_index": 1,
                    "metric_stdout_key": "",
                    "direction": "inside",
                },
            ]
        )
        engine = _make_engine(provider_response=response)
        engine.state.selected_hypotheses = [h_good, h_bad]
        handler = PreRegistrationHandler(engine)

        frozen = await handler.run_freeze()

        assert len(frozen) == 1
        assert frozen[0].frozen is True
        assert frozen[0].registered_at  # timestamp set
        assert frozen[0].hypothesis_id == "hg"
        # non-falsifiable hypothesis dropped from carried-forward set
        kept_ids = {h.id for h in engine.state.selected_hypotheses}
        assert kept_ids == {"hg"}
        assert h_good.prediction_rule_id == frozen[0].id
        assert h_good.verdict == PredictionVerdict.REGISTERED

    async def test_no_hypotheses_returns_empty(self):
        engine = _make_engine(provider_response="[]")
        handler = PreRegistrationHandler(engine)
        assert await handler.run_freeze() == []


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


def _engine_with_rule(rule: PredictionRule, hyp: Hypothesis):
    engine = _make_engine()
    rule.hypothesis_id = hyp.id
    engine.state.registered_rules = [rule]
    engine.state.selected_hypotheses = [hyp]
    return engine


def _meta(stdout: str):
    return [{"name": "exp1", "status": "success", "stdout_full": stdout}]


class TestEvaluate:
    def test_confirmed(self):
        hyp = Hypothesis(id="h1", statement="r is high")
        rule = PredictionRule(
            metric_stdout_key="pearson_r",
            direction=PredictionDirection.GREATER,
            low=0.5,
            refutation_condition="r<=0.5",
        )
        engine = _engine_with_rule(rule, hyp)
        verdicts = PreRegistrationHandler(engine).evaluate(_meta("pearson_r=0.83"))
        assert verdicts[0]["verdict"] == "confirmed"
        assert hyp.verdict == PredictionVerdict.CONFIRMED

    def test_refuted(self):
        hyp = Hypothesis(id="h1", statement="r is high")
        rule = PredictionRule(
            metric_stdout_key="pearson_r",
            direction=PredictionDirection.GREATER,
            low=0.5,
            refutation_condition="r<=0.5",
        )
        engine = _engine_with_rule(rule, hyp)
        verdicts = PreRegistrationHandler(engine).evaluate(_meta("pearson_r=0.12"))
        assert verdicts[0]["verdict"] == "refuted"
        assert hyp.verdict == PredictionVerdict.REFUTED

    def test_inconclusive_when_metric_missing(self):
        hyp = Hypothesis(id="h1", statement="r is high")
        rule = PredictionRule(
            metric_stdout_key="pearson_r",
            direction=PredictionDirection.GREATER,
            low=0.5,
            refutation_condition="r<=0.5",
        )
        engine = _engine_with_rule(rule, hyp)
        verdicts = PreRegistrationHandler(engine).evaluate(_meta("something_else=1.0"))
        assert verdicts[0]["verdict"] == "inconclusive"

    def test_significance_confirmed(self):
        hyp = Hypothesis(id="h1", statement="r is high and significant")
        rule = PredictionRule(
            metric_stdout_key="pearson_r",
            direction=PredictionDirection.GREATER,
            low=0.5,
            significance_max_p=0.05,
            refutation_condition="r<=0.5 or p>0.05",
        )
        engine = _engine_with_rule(rule, hyp)
        verdicts = PreRegistrationHandler(engine).evaluate(
            _meta("pearson_r=0.83\npearson_r_p=0.001")
        )
        assert verdicts[0]["verdict"] == "confirmed"

    def test_significance_refuted_when_p_too_high(self):
        hyp = Hypothesis(id="h1", statement="r high but not significant")
        rule = PredictionRule(
            metric_stdout_key="pearson_r",
            direction=PredictionDirection.GREATER,
            low=0.5,
            significance_max_p=0.05,
            refutation_condition="r<=0.5 or p>0.05",
        )
        engine = _engine_with_rule(rule, hyp)
        verdicts = PreRegistrationHandler(engine).evaluate(
            _meta("pearson_r=0.83\npearson_r_p=0.40")
        )
        assert verdicts[0]["verdict"] == "refuted"

    def test_significance_inconclusive_when_p_missing(self):
        hyp = Hypothesis(id="h1", statement="r high, p unreported")
        rule = PredictionRule(
            metric_stdout_key="pearson_r",
            direction=PredictionDirection.GREATER,
            low=0.5,
            significance_max_p=0.05,
            refutation_condition="r<=0.5 or p>0.05",
        )
        engine = _engine_with_rule(rule, hyp)
        verdicts = PreRegistrationHandler(engine).evaluate(_meta("pearson_r=0.83"))
        assert verdicts[0]["verdict"] == "inconclusive"

    def test_no_rules_returns_empty(self):
        engine = _make_engine()
        assert PreRegistrationHandler(engine).evaluate(_meta("x=1")) == []


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------


class TestPreRegistrationPhase:
    def test_planning_can_transition_to_pre_registration(self):
        pm = PhaseManager(ResearchPhase.PLANNING)
        assert pm.can_transition_to(ResearchPhase.PRE_REGISTRATION)

    def test_pre_registration_to_execution(self):
        pm = PhaseManager(ResearchPhase.PRE_REGISTRATION)
        assert pm.can_transition_to(ResearchPhase.EXECUTION)

    def test_legacy_planning_to_execution_still_valid(self):
        pm = PhaseManager(ResearchPhase.PLANNING)
        assert pm.can_transition_to(ResearchPhase.EXECUTION)
