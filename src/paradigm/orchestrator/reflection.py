"""PI reflection — the strongest model steps back and judges the work (R1-R3).

Humans writing papers stop, read the draft, and decide whether something
obvious is missing before submitting. This handler gives the cycle that
faculty: a "principal investigator" (config role ``pi`` — the strongest model
in the active tier) reads the draft plus the evidence inventory and rules:

- ``proceed``   — ready for review (the default).
- ``loop_back`` — a specific, fixable gap would sink the paper: send the team
                  back to EXECUTION (more experiments) or PLANNING (rethink),
                  with concrete directives and MEASURABLE success criteria.
- ``call_it``   — more work won't help; finish honestly with what stands.

Convergence is guaranteed mechanically, not by trust: loop-backs are budgeted
(``orchestrator.max_loop_backs``), a second loop-back must show the first one's
success criteria were met, and when the budget is spent only proceed/call_it
parse. The same PI triages peer reviews (R2): demands that need NEW ANALYSIS
(not rewording) can trigger one deep revision loop before resubmission.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from paradigm.knowledge.json_utils import first_json_object

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine

_PI_SYSTEM = (
    "You are the principal investigator of a research team. You are decisive, "
    "skeptical of sunk costs, and you never spend resources on work that will "
    "not change the paper's fate. Return ONLY a JSON object."
)

_REFLECTION_PROMPT = """Step back and judge whether this draft is ready for internal review.

## Research brief
{seed_prompt}

## Current draft (may be truncated)
{draft}

## Evidence inventory
{inventory}

## Execution caveats
{caveats}

## Loop-back budget
{budget_line}
{history_block}

Decide ONE of:
- "proceed" — the draft is coherent and the evidence supports its claims; go to review.
- "loop_back" — ONLY if a specific, fixable gap would sink the paper in review
  (e.g. a central claim resting on too little data, a missing control, an
  obvious analysis never run). Give concrete directives and a MEASURABLE
  success criterion. target "execution" = run more/better experiments with the
  current plan; target "planning" = the plan itself is wrong, rethink first.
- "call_it" — the paper will not materially improve with more work; finish
  honestly with what stands.

RULES:
- If a previous loop-back's success criteria were NOT clearly met by the new
  work, you MUST NOT loop back again — choose proceed or call_it.
- With 0 loop-backs remaining, only proceed or call_it are valid.
- A loop-back for cosmetic or wording issues is FORBIDDEN (review handles those).

Return ONLY JSON:
{{"verdict": "proceed" | "loop_back" | "call_it",
  "target": "execution" | "planning" | null,
  "directives": ["specific instruction", ...],
  "success_criteria": "measurable outcome the new work must achieve",
  "reason": "one or two sentences"}}"""

_TRIAGE_PROMPT = """You are the PI triaging peer reviews of your team's paper.

## Peer review feedback
{reviews}

## Evidence inventory
{inventory}

## Loop-back budget
{budget_line}

Classify the reviewers' substantive demands: which are TEXTUAL (rewording,
clarity, presentation — the writer can fix them) and which require NEW ANALYSIS
(experiments/computations that do not exist yet)?

Trigger a deep revision ("deep_loop": true) ONLY if (a) at least one demand
genuinely requires new analysis, (b) that analysis is feasible with the data
and tools the team already has or can fetch, and (c) it plausibly changes the
review outcome. Otherwise the writer revises text only.

Return ONLY JSON:
{{"deep_loop": true | false,
  "directives": ["specific new analysis to run", ...],
  "reason": "one or two sentences"}}"""

_DRAFT_CHARS = 24_000
_VALID_VERDICTS = ("proceed", "loop_back", "call_it")


class ReflectionHandler:
    """PI reflection + peer-review triage (see module docstring)."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------ utils

    def _budget_remaining(self) -> int:
        cfg = self._engine._config.orchestrator
        return max(0, cfg.max_loop_backs - self._engine.state.loop_backs_used)

    def _inventory(self) -> str:
        """Compact per-experiment ledger the PI can reason over."""
        rows = []
        for m in self._engine.state.experiment_metadata[-40:]:
            rows.append(
                f"- {m.get('name')}: {m.get('status')}"
                f" [{m.get('data_provenance', '?')}] {str(m.get('stdout_preview', ''))[:120]}"
            )
        return "\n".join(rows) or "(no experiments were run)"

    async def _pi_complete(self, prompt: str, agent_label: str) -> str:
        """One PI call via the config role 'pi' (same pattern as the refiner)."""
        provider, model, extra_body = self._engine._config.get_provider_and_model_for_role("pi")
        text, input_tokens, output_tokens = await asyncio.to_thread(
            provider.complete,
            model=model,
            system=_PI_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.2,
            extra_body=extra_body,
        )
        self._engine._db.record_token_usage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            agent_id=agent_label,
            thread_id=self._engine.state.thread_id,
        )
        return text or ""

    # ------------------------------------------------------------- reflection

    async def run_reflection(self, draft_body: str) -> dict[str, Any]:
        """PI verdict on the current draft. Never raises; defaults to proceed."""
        state = self._engine.state
        remaining = self._budget_remaining()
        budget_line = f"Loop-backs remaining: {remaining}"
        history = ""
        if state.reflection_log:
            lines = []
            for v in state.reflection_log:
                lines.append(
                    f"- loop_back to {v.get('target')}: directives={v.get('directives')}; "
                    f"success_criteria: {v.get('success_criteria')}"
                )
            history = "\n## Previous loop-backs (verify their success criteria!)\n" + "\n".join(
                lines
            )
        prompt = _REFLECTION_PROMPT.format(
            seed_prompt=state.seed_prompt[:3000],
            draft=(draft_body or "")[:_DRAFT_CHARS],
            inventory=self._inventory(),
            caveats="\n".join(f"- {c}" for c in state.execution_caveats) or "(none)",
            budget_line=budget_line,
            history_block=history,
        )
        try:
            raw = await self._pi_complete(prompt, "pi_reflection")
            verdict = first_json_object(raw) or {}
        except Exception as e:  # noqa: BLE001 — reflection must never kill a cycle
            self._engine._logger.log_error(e, thread_id=state.thread_id)
            verdict = {}

        v = str(verdict.get("verdict", "")).strip().lower()
        if v not in _VALID_VERDICTS:
            return {"verdict": "proceed", "reason": "unparseable reflection — defaulting"}
        # Mechanical convergence guards (never trust the model to enforce them):
        if v == "loop_back":
            if remaining <= 0:
                return {"verdict": "proceed", "reason": "loop-back budget exhausted"}
            target = str(verdict.get("target", "execution")).strip().lower()
            if target not in ("execution", "planning"):
                target = "execution"
            if any(prior.get("target") == target for prior in state.reflection_log):
                # A target can never be looped back to twice (R3).
                return {
                    "verdict": "call_it",
                    "reason": (
                        "second loop-back to the same target requested — the first "
                        "did not resolve it; calling it to avoid a non-converging loop"
                    ),
                }
            directives = [str(d) for d in (verdict.get("directives") or []) if str(d).strip()]
            if not directives:
                return {"verdict": "proceed", "reason": "loop_back with no directives"}
            verdict["target"] = target
            verdict["directives"] = directives[:5]
            verdict["success_criteria"] = str(verdict.get("success_criteria") or "")[:500]
        return verdict

    # ----------------------------------------------------------- peer triage

    async def triage_peer_reviews(self, review_feedback: str) -> dict[str, Any]:
        """PI triage of peer reviews: deep revision (new analysis) vs text-only."""
        if self._budget_remaining() <= 0:
            return {"deep_loop": False, "reason": "loop-back budget exhausted"}
        prompt = _TRIAGE_PROMPT.format(
            reviews=review_feedback[:16_000],
            inventory=self._inventory(),
            budget_line=f"Loop-backs remaining: {self._budget_remaining()}",
        )
        try:
            raw = await self._pi_complete(prompt, "pi_triage")
            verdict = first_json_object(raw) or {}
        except Exception as e:  # noqa: BLE001
            self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
            return {"deep_loop": False, "reason": "triage failed — text-only revision"}
        directives = [str(d) for d in (verdict.get("directives") or []) if str(d).strip()]
        return {
            "deep_loop": bool(verdict.get("deep_loop")) and bool(directives),
            "directives": directives[:5],
            "reason": str(verdict.get("reason") or "")[:400],
        }
