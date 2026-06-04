"""Pre-registration handler (Phase 1A): freeze falsifiable predictions before EXECUTION.

Before any experiment runs, each candidate hypothesis is assigned a machine-readable
``PredictionRule`` (metric, bounds, refutation condition). Rules are *frozen* — the
post-execution verdict is computed only against the frozen rule, never re-read from
agent text, which blocks post-hoc redefinition. Hypotheses without a well-formed,
falsifiable rule are rejected (dropped) when ``prereg_require_refutation`` is set.

Plain-Python handler, mirroring ``TournamentHandler``. Default-off via
``config.knowledge.enable_preregistration``.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from paradigm.knowledge.models import (
    Hypothesis,
    PredictionDirection,
    PredictionRule,
    PredictionVerdict,
)

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences from an LLM JSON response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


class PreRegistrationHandler:
    """Freezes prediction rules before EXECUTION and evaluates them afterward."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Freeze (called between PLANNING and EXECUTION)
    # ------------------------------------------------------------------

    async def run_freeze(self) -> list[PredictionRule]:
        """Author and freeze one prediction rule per candidate hypothesis.

        Reads candidate hypotheses from ``state.selected_hypotheses`` (tournament
        winners) or, as a fallback, the world model. Ill-formed / non-falsifiable
        rules are rejected; surviving hypotheses are dropped from
        ``state.selected_hypotheses`` when ``prereg_require_refutation`` is set.

        Returns:
            The list of frozen ``PredictionRule`` objects (also stored on state).
        """
        engine = self._engine
        config = engine._config.knowledge
        display = engine._display

        hypotheses = self._candidate_hypotheses()
        if not hypotheses:
            display.info("Pre-registration: no candidate hypotheses; skipping freeze.")
            return []

        rules_by_index = await self._author_rules(hypotheses)

        frozen: list[PredictionRule] = []
        kept_hypotheses: list[Hypothesis] = []
        now = datetime.now(UTC).isoformat()

        for idx, hyp in enumerate(hypotheses):
            rule = rules_by_index.get(idx)
            well_formed = rule is not None and rule.is_well_formed()
            if not well_formed:
                if config.prereg_require_refutation:
                    display.info(
                        f"Pre-registration: dropped non-falsifiable hypothesis "
                        f'"{hyp.statement[:60]}" (no admissible refutation rule).'
                    )
                    continue
                # Not requiring refutation: keep the hypothesis without a frozen rule.
                kept_hypotheses.append(hyp)
                continue

            assert rule is not None  # narrowed by well_formed
            rule.hypothesis_id = hyp.id
            rule.frozen = True
            rule.registered_at = now
            hyp.prediction_rule_id = rule.id
            hyp.verdict = PredictionVerdict.REGISTERED
            frozen.append(rule)
            kept_hypotheses.append(hyp)

        # Only prune the carried-forward set when we actually require refutation.
        if config.prereg_require_refutation:
            engine.state.selected_hypotheses = kept_hypotheses
        engine.state.registered_rules = frozen

        if frozen:
            display.info(
                f"Pre-registration: froze {len(frozen)} falsifiable prediction(s) "
                f"before execution."
            )
        else:
            display.info("Pre-registration: no admissible prediction rules were frozen.")
        return frozen

    def _candidate_hypotheses(self) -> list[Hypothesis]:
        """Candidate hypotheses to pre-register: tournament winners, else world model."""
        state = self._engine.state
        if state.selected_hypotheses:
            return list(state.selected_hypotheses)
        wm = state.world_model
        if wm is not None and getattr(wm, "hypotheses", None):
            return list(wm.hypotheses.values())
        return []

    async def _author_rules(self, hypotheses: list[Hypothesis]) -> dict[int, PredictionRule]:
        """Use the theorist's model to author one prediction rule per hypothesis."""
        from paradigm.orchestrator.constants import _PREREGISTRATION_PROMPT

        engine = self._engine
        hyp_block = "\n".join(
            f"{i}. {h.statement}" + (f" — {h.rationale}" if h.rationale else "")
            for i, h in enumerate(hypotheses)
        )
        prompt = _PREREGISTRATION_PROMPT.format(
            seed_prompt=engine.state.seed_prompt,
            hypotheses=hyp_block,
            planning_actions=engine.state.planning_action_items or "(not specified)",
        )

        try:
            provider, model, extra_body = engine._config.get_provider_and_model_for_role(
                "theorist"
            )
            response_text, input_tokens, output_tokens = provider.complete(
                model=model,
                system="You pre-register falsifiable predictions for scientific hypotheses.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                extra_body=extra_body,
            )
            engine._db.record_token_usage(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thread_id=engine.state.thread_id,
            )
            data = json.loads(_strip_json_fences(response_text))
        except Exception as e:  # noqa: BLE001 — non-fatal; freeze degrades gracefully
            engine._logger.log_error(e, thread_id=engine.state.thread_id)
            return {}

        return self._parse_rules(data, len(hypotheses))

    @staticmethod
    def _parse_rules(data: object, n_hypotheses: int) -> dict[int, PredictionRule]:
        """Parse the LLM JSON array into PredictionRule objects keyed by hypothesis index."""
        rules: dict[int, PredictionRule] = {}
        if not isinstance(data, list):
            return rules
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("hypothesis_index", -1))
            except (TypeError, ValueError):
                continue
            if not (0 <= idx < n_hypotheses):
                continue
            direction_raw = str(item.get("direction", "inside")).lower()
            try:
                direction = PredictionDirection(direction_raw)
            except ValueError:
                direction = PredictionDirection.INSIDE
            rules[idx] = PredictionRule(
                metric_name=str(item.get("metric_name", "")),
                metric_stdout_key=str(item.get("metric_stdout_key", "")).strip(),
                direction=direction,
                low=_as_float(item.get("low")),
                high=_as_float(item.get("high")),
                significance_max_p=_as_float(item.get("significance_max_p")),
                refutation_condition=str(item.get("refutation_condition", "")).strip(),
            )
        return rules

    # ------------------------------------------------------------------
    # Evaluate (called after EXECUTION)
    # ------------------------------------------------------------------

    def evaluate(self, experiment_metadata: list[dict[str, object]]) -> list[dict[str, str]]:
        """Compute confirmed/refuted/inconclusive verdicts against the frozen rules.

        The verdict is derived ONLY from the frozen rule and the captured stdout
        of successful experiments — never from agent prose — which blocks post-hoc
        redefinition.

        Returns:
            A list of verdict dicts (also stored on ``state.prereg_verdicts``).
        """
        engine = self._engine
        rules = engine.state.registered_rules
        if not rules:
            return []

        stdout_blob = "\n".join(
            str(m.get("stdout_full", ""))
            for m in experiment_metadata
            if str(m.get("status", "")).lower() not in ("failure", "failed", "error")
        )

        # Map hypothesis_id -> Hypothesis so we can write the verdict back.
        by_id = {h.id: h for h in engine.state.selected_hypotheses}

        verdicts: list[dict[str, str]] = []
        for rule in rules:
            value = _extract_metric(stdout_blob, rule.metric_stdout_key)
            if value is None:
                verdict = PredictionVerdict.INCONCLUSIVE
                detail = f"metric '{rule.metric_stdout_key}' not found in experiment output"
            elif not rule.holds(value):
                verdict = PredictionVerdict.REFUTED
                detail = f"{rule.metric_stdout_key}={value:g} fails the prediction"
            else:
                # Value satisfies the bound; check significance if required.
                if rule.significance_max_p is not None:
                    p_value = _extract_metric(stdout_blob, f"{rule.metric_stdout_key}_p")
                    if p_value is None:
                        verdict = PredictionVerdict.INCONCLUSIVE
                        detail = (
                            f"{rule.metric_stdout_key}={value:g} holds but required p-value "
                            f"'{rule.metric_stdout_key}_p' was not reported"
                        )
                    elif p_value <= rule.significance_max_p:
                        verdict = PredictionVerdict.CONFIRMED
                        detail = f"{rule.metric_stdout_key}={value:g}, p={p_value:g} (significant)"
                    else:
                        verdict = PredictionVerdict.REFUTED
                        detail = (
                            f"{rule.metric_stdout_key}={value:g} holds but p={p_value:g} "
                            f"exceeds {rule.significance_max_p:g}"
                        )
                else:
                    verdict = PredictionVerdict.CONFIRMED
                    detail = f"{rule.metric_stdout_key}={value:g} satisfies the prediction"

            hyp = by_id.get(rule.hypothesis_id)
            if hyp is not None:
                hyp.verdict = verdict
            verdicts.append(
                {
                    "hypothesis_id": rule.hypothesis_id,
                    "metric": rule.metric_stdout_key,
                    "verdict": verdict.value,
                    "detail": detail,
                    "refutation_condition": rule.refutation_condition,
                }
            )

        engine.state.prereg_verdicts = verdicts
        return verdicts


def _as_float(value: object) -> float | None:
    """Best-effort float coercion; returns None for null/non-numeric input."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _extract_metric(stdout: str, key: str) -> float | None:
    """Find the last ``key=<number>`` (or ``key: <number>``) occurrence in stdout."""
    if not key:
        return None
    pattern = re.compile(
        rf"{re.escape(key)}\s*[=:]\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    )
    matches = pattern.findall(stdout)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None
