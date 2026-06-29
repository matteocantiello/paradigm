"""Handler for hypothesis tournament within the orchestration engine."""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING

from paradigm.knowledge.hypothesis_tournament import (
    HypothesisPopulation,
    MatchupResult,
)
from paradigm.knowledge.models import Hypothesis, HypothesisStatus

if TYPE_CHECKING:
    from typing import Any

    from paradigm.orchestrator.engine import OrchestrationEngine

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)
# Tolerant field extractors — survive TRUNCATED JSON (the judge response getting
# cut off mid-"reasoning" at max_tokens left no closing brace, so full JSON parse
# failed and every matchup scored None → all Elos stuck at 1500).
_WINNER_RE = re.compile(
    r'"?winner"?\s*(?:is\s+|[:=]\s*)"?\s*(hypothesis\s*)?([ABab12])', re.IGNORECASE
)
_MARGIN_RE = re.compile(r'"?margin"?\s*[:=]\s*"?\s*(\d*\.?\d+)', re.IGNORECASE)


def _first_json_object(text: str) -> dict | None:
    """Pull the first JSON object out of a model response.

    Robust to code fences AND chatty preamble ("Here is my verdict: {...}") — the
    brittle 'must start with a fence' parsing silently returned None for every
    matchup, leaving the whole tournament stuck at the 1500 starting Elo.
    """
    m = _JSON_OBJ_RE.search(text or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_judge_verdict(text: str) -> dict | None:
    """Parse a judge response into {winner, margin, reasoning}, tolerant of
    truncation. Tries full JSON first; falls back to regex-extracting just the
    ``winner`` (the only field the tournament needs) so a verbose model whose
    JSON gets cut off still produces a usable verdict instead of a dead matchup.
    Returns None only when no winner can be found at all.
    """
    obj = _first_json_object(text)
    if obj is not None and "winner" in obj:
        return obj
    if not text:
        return None
    wm = _WINNER_RE.search(text)
    if wm is None:
        return None
    winner = wm.group(2).upper().replace("1", "A").replace("2", "B")
    mm = _MARGIN_RE.search(text)
    margin = 0.5
    if mm is not None:
        try:
            margin = float(mm.group(1))
        except ValueError:
            margin = 0.5
    return {"winner": winner, "margin": margin, "reasoning": ""}


class TournamentHandler:
    """Manages hypothesis tournaments within the IDEATION phase.

    The tournament runs as internal steps (not sub-phases):
    1. Extract candidate hypotheses from discussion
    2. Create population with Elo ratings
    3. Generate matchups and judge each one
    4. Select winners by Elo ranking
    5. Update world model

    Graceful degradation: <2 hypotheses → skip tournament, return as-is.
    """

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine
        self._last_population: HypothesisPopulation | None = None
        self._last_matchup_results: list[MatchupResult] = []

    async def run_tournament(self) -> list[Hypothesis]:
        """Run a full hypothesis tournament.

        Returns:
            List of winning hypotheses, or empty list if tournament
            was skipped (too few hypotheses).
        """
        config = self._engine._config.knowledge
        display = self._engine._display

        # Step 1: Extract hypotheses from discussion
        hypotheses = await self._extract_hypotheses_from_discussion()
        for h in hypotheses:
            self._engine.emit_event(
                "hypothesis.created",
                {"hypothesis_id": h.id, "statement": h.statement, "rationale": h.rationale[:2000]},
            )
        if len(hypotheses) < 2:
            return hypotheses  # Can't tournament with < 2

        # Limit population size
        hypotheses = hypotheses[: config.tournament_population_size]

        display.info(
            f"Hypothesis tournament: {len(hypotheses)} candidates, "
            f"selecting top {config.tournament_winners}"
        )

        # Step 2: Create population
        population = HypothesisPopulation(
            hypotheses=hypotheses,
            k_factor=config.tournament_k_factor,
        )

        # Step 3: Generate matchups and judge
        matchups = population.generate_matchups()
        matchup_results: list[MatchupResult] = []
        for hyp_a_id, hyp_b_id in matchups:
            result = await self._judge_matchup(
                population.hypotheses[hyp_a_id],
                population.hypotheses[hyp_b_id],
            )
            if result is not None:
                population.record_result(result)
                matchup_results.append(result)

        # Store for external access
        self._last_population = population
        self._last_matchup_results = matchup_results

        self._engine.emit_event(
            "tournament.round",
            {
                "matchups": [
                    [r.hypothesis_a_id, r.hypothesis_b_id, r.winner_id] for r in matchup_results
                ],
                "rationales": [r.judge_reasoning[:300] for r in matchup_results],
            },
        )

        # Surface judging failures — otherwise an all-failed tournament looks
        # "complete" with every hypothesis stuck at the 1500 starting Elo and an
        # arbitrary tie-break "winner".
        if len(matchup_results) < len(matchups):
            note = f"tournament: only {len(matchup_results)}/{len(matchups)} matchups were judged"
            if not matchup_results:
                note += " — Elo rankings are NOT meaningful (every judge call failed; check the judge model)"
            self._engine._logger.log_error(
                RuntimeError(note),
                thread_id=self._engine.state.thread_id,
                metadata_key="tournament",
            )
            display.info(note)

        # Step 4: Select winners
        winners = population.select_winners(n=config.tournament_winners)

        # Step 5: Update world model — route every belief change through the single
        # revise_hypothesis choke point (C2 step 1) so each update is auditable
        # (reason/source) and goes through the canonical WorldModel.update_hypothesis.
        wm = self._engine.state.world_model
        if wm is not None:
            wmh = self._engine._world_model
            for h in hypotheses:
                wm.add_hypothesis(h)
                wmh.revise_hypothesis(
                    h.id,
                    status=HypothesisStatus.UNDER_INVESTIGATION,
                    elo=h.elo_rating,
                    reason="entered tournament",
                    source="tournament",
                )
            for w in winners:
                wmh.revise_hypothesis(
                    w.id,
                    status=HypothesisStatus.SUPPORTED,
                    reason="tournament winner",
                    source="tournament",
                    extra={"selected": True},
                )

        display.info(
            "Tournament complete. Winners: "
            + ", ".join(f'"{w.statement[:50]}" (Elo: {w.elo_rating:.0f})' for w in winners)
        )

        return winners

    def get_tournament_data(self) -> dict[str, Any] | None:
        """Return serializable tournament data, or None if no tournament has run."""
        if self._last_population is None:
            return None
        rankings = [
            {
                "hypothesis_id": h.id,
                "statement": h.statement,
                "elo_rating": round(h.elo_rating, 1),
                "status": h.status.value if hasattr(h.status, "value") else str(h.status),
            }
            for h in self._last_population.ranked
        ]
        matchups = [r.model_dump() for r in self._last_matchup_results]
        summary = self._last_population.get_tournament_summary()
        return {
            "rankings": rankings,
            "matchup_results": matchups,
            "summary": summary,
        }

    async def _extract_hypotheses_from_discussion(self) -> list[Hypothesis]:
        """Use an LLM call to extract hypotheses from IDEATION messages."""
        messages = self._engine.state.messages
        if not messages:
            return []

        # Build discussion text from recent messages
        discussion_parts = []
        for m in messages[-15:]:
            agent = m.get("from", "unknown")
            content = m.get("content", "")[:500]
            discussion_parts.append(f"**{agent}**: {content}")
        discussion = "\n\n".join(discussion_parts)

        from paradigm.orchestrator.constants import _HYPOTHESIS_EXTRACTION_PROMPT

        config = self._engine._config.knowledge
        prompt = _HYPOTHESIS_EXTRACTION_PROMPT.format(
            seed_prompt=self._engine.state.seed_prompt,
            discussion=discussion,
            max_hypotheses=config.tournament_population_size,
        )

        try:
            provider, model, extra_body = self._engine._config.get_provider_and_model_for_role(
                "synthesizer"
            )
            response_text, input_tokens, output_tokens = await asyncio.to_thread(
                provider.complete,
                model=model,
                system="You extract hypotheses from research discussions.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                extra_body=extra_body,
            )

            self._engine._db.record_token_usage(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thread_id=self._engine.state.thread_id,
            )

            # Parse JSON response
            # Strip markdown fences if present
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
            hypotheses = []
            for item in data:
                if isinstance(item, dict) and "statement" in item:
                    h = Hypothesis(
                        statement=item["statement"],
                        rationale=item.get("rationale", ""),
                    )
                    hypotheses.append(h)
            return hypotheses

        except Exception as e:
            self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
            # Fallback: extract from world model if available
            wm = self._engine.state.world_model
            if wm is not None and wm.hypotheses:
                return list(wm.hypotheses.values())
            return []

    async def _judge_matchup(
        self,
        hypothesis_a: Hypothesis,
        hypothesis_b: Hypothesis,
    ) -> MatchupResult | None:
        """Judge a single matchup between two hypotheses."""
        from paradigm.orchestrator.constants import _TOURNAMENT_JUDGE_PROMPT

        prompt = _TOURNAMENT_JUDGE_PROMPT.format(
            seed_prompt=self._engine.state.seed_prompt,
            hypothesis_a=f"{hypothesis_a.statement}\nRationale: {hypothesis_a.rationale}",
            hypothesis_b=f"{hypothesis_b.statement}\nRationale: {hypothesis_b.rationale}",
        )

        try:
            provider, model, extra_body = self._engine._config.get_provider_and_model_for_role(
                "debate_judge"
            )
            response_text, input_tokens, output_tokens = await asyncio.to_thread(
                provider.complete,
                model=model,
                system="You are an impartial hypothesis judge.",
                messages=[{"role": "user", "content": prompt}],
                # Headroom so the JSON verdict isn't truncated mid-"reasoning"
                # (truncation left no closing brace → every matchup scored None
                # → all Elos stuck at 1500). The tolerant parser is the backstop.
                max_tokens=1500,
                extra_body=extra_body,
            )

            self._engine._db.record_token_usage(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thread_id=self._engine.state.thread_id,
            )

            # Parse JSON response (robust to fences, preamble, AND truncation).
            data = parse_judge_verdict(response_text)
            if data is None:
                self._engine._logger.log_error(
                    ValueError(f"tournament judge: unparseable response: {response_text[:160]!r}"),
                    thread_id=self._engine.state.thread_id,
                    metadata_key="tournament",
                )
                return None
            # Lenient winner parse: "A" / "a" / "Hypothesis A" all map to A.
            winner_label = str(data.get("winner", "A")).strip().upper()
            winner_id = hypothesis_a.id if winner_label.startswith("A") else hypothesis_b.id
            try:
                margin = float(data.get("margin", 0.5))
            except (TypeError, ValueError):
                margin = 0.5
            return MatchupResult(
                hypothesis_a_id=hypothesis_a.id,
                hypothesis_b_id=hypothesis_b.id,
                winner_id=winner_id,
                judge_reasoning=str(data.get("reasoning", "")),
                margin=margin,
            )

        except Exception as e:
            self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
            return None
