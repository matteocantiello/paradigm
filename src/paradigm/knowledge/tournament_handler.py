"""Handler for hypothesis tournament within the orchestration engine."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from paradigm.knowledge.hypothesis_tournament import (
    HypothesisPopulation,
    MatchupResult,
)
from paradigm.knowledge.models import Hypothesis, HypothesisStatus

if TYPE_CHECKING:
    from typing import Any

    from paradigm.orchestrator.engine import OrchestrationEngine


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

        # Step 4: Select winners
        winners = population.select_winners(n=config.tournament_winners)

        # Step 5: Update world model
        wm = self._engine.state.world_model
        if wm is not None:
            for h in hypotheses:
                h.status = HypothesisStatus.UNDER_INVESTIGATION
                wm.add_hypothesis(h)
            for w in winners:
                w.status = HypothesisStatus.SUPPORTED

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
            response_text, input_tokens, output_tokens = provider.complete(
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
            response_text, input_tokens, output_tokens = provider.complete(
                model=model,
                system="You are an impartial hypothesis judge.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                extra_body=extra_body,
            )

            self._engine._db.record_token_usage(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thread_id=self._engine.state.thread_id,
            )

            # Parse JSON response
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
            winner_label = data.get("winner", "A")
            winner_id = hypothesis_a.id if winner_label == "A" else hypothesis_b.id
            return MatchupResult(
                hypothesis_a_id=hypothesis_a.id,
                hypothesis_b_id=hypothesis_b.id,
                winner_id=winner_id,
                judge_reasoning=data.get("reasoning", ""),
                margin=float(data.get("margin", 0.5)),
            )

        except Exception as e:
            self._engine._logger.log_error(e, thread_id=self._engine.state.thread_id)
            return None
