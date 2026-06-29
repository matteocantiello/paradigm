"""Hypothesis tournament with Elo-based ranking."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from paradigm.knowledge.models import Hypothesis


def swiss_num_rounds(n: int) -> int:
    """Number of Swiss rounds to rank ``n`` competitors (~⌈log2 n⌉, ≥1 for n≥2).

    Round-robin is O(n²) judge calls; Swiss converges a ranking in ⌈log2 n⌉
    rounds of ~n/2 matches each — e.g. n=8 → 3 rounds × 4 = 12 vs round-robin's 28.
    """
    if n < 2:
        return 0
    return max(1, math.ceil(math.log2(n)))


class MatchupResult(BaseModel):
    """Result of a head-to-head hypothesis comparison."""

    hypothesis_a_id: str
    hypothesis_b_id: str
    winner_id: str
    judge_reasoning: str = ""
    margin: float = 0.5  # 0-1, how decisive the win was


class TournamentState(BaseModel):
    """Snapshot of tournament progress."""

    population_ids: list[str] = Field(default_factory=list)
    matchup_results: list[MatchupResult] = Field(default_factory=list)
    round_number: int = 0
    status: str = "pending"  # pending, in_progress, complete


class HypothesisPopulation:
    """Manages a population of hypotheses with Elo ratings.

    Provides matchup generation, Elo updates, and winner selection.
    Standard Elo formula with configurable K-factor.
    """

    def __init__(
        self,
        hypotheses: list[Hypothesis],
        k_factor: float = 32.0,
    ) -> None:
        self._hypotheses = {h.id: h for h in hypotheses}
        self._k_factor = k_factor

    @property
    def ranked(self) -> list[Hypothesis]:
        """Return hypotheses sorted by Elo descending."""
        return sorted(
            self._hypotheses.values(),
            key=lambda h: h.elo_rating,
            reverse=True,
        )

    @property
    def hypotheses(self) -> dict[str, Hypothesis]:
        return self._hypotheses

    def generate_matchups(self, mode: str = "round_robin") -> list[tuple[str, str]]:
        """Generate pairs for head-to-head comparisons.

        Args:
            mode: "round_robin" generates all unique pairs.

        Returns:
            List of (hypothesis_a_id, hypothesis_b_id) tuples.
        """
        ids = list(self._hypotheses.keys())
        matchups: list[tuple[str, str]] = []
        if mode == "round_robin":
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    matchups.append((ids[i], ids[j]))
        return matchups

    def generate_swiss_round(self, played: set[frozenset[str]]) -> list[tuple[str, str]]:
        """Pair competitors for ONE Swiss round by current Elo, avoiding rematches.

        Adjacent pairing on the current ranking (so closely-rated hypotheses meet);
        if the natural opponent was already played, the next available unplayed
        opponent is used, and a rematch is allowed only when every remaining
        opponent has been played. An odd competitor out gets a bye (no match this
        round). Deterministic (ranking order, no RNG).

        Args:
            played: Set of ``frozenset({a_id, b_id})`` pairs already judged.

        Returns:
            List of ``(a_id, b_id)`` pairings for this round.
        """
        ranked_ids = [h.id for h in self.ranked]
        pairs: list[tuple[str, str]] = []
        used: set[str] = set()
        for i, a in enumerate(ranked_ids):
            if a in used:
                continue
            opponent: str | None = None
            fallback: str | None = None  # an unused opponent already played (rematch)
            for b in ranked_ids[i + 1 :]:
                if b in used:
                    continue
                if frozenset((a, b)) in played:
                    fallback = fallback or b
                    continue
                opponent = b
                break
            chosen = opponent or fallback
            if chosen is None:
                continue  # `a` gets a bye this round
            used.add(a)
            used.add(chosen)
            pairs.append((a, chosen))
        return pairs

    def record_result(self, result: MatchupResult) -> None:
        """Update Elo ratings based on a matchup result.

        Uses standard Elo formula:
        E_A = 1 / (1 + 10^((R_B - R_A) / 400))
        New R_A = R_A + K * (S_A - E_A)

        where S_A = 1 if A wins, 0 if A loses.
        """
        hyp_a = self._hypotheses.get(result.hypothesis_a_id)
        hyp_b = self._hypotheses.get(result.hypothesis_b_id)
        if hyp_a is None or hyp_b is None:
            return

        # Expected scores
        exp_a = 1.0 / (1.0 + math.pow(10, (hyp_b.elo_rating - hyp_a.elo_rating) / 400.0))
        exp_b = 1.0 - exp_a

        # Actual scores
        if result.winner_id == result.hypothesis_a_id:
            score_a, score_b = 1.0, 0.0
        else:
            score_a, score_b = 0.0, 1.0

        # Update ratings
        hyp_a.elo_rating += self._k_factor * (score_a - exp_a)
        hyp_b.elo_rating += self._k_factor * (score_b - exp_b)

    def select_winners(self, n: int = 2) -> list[Hypothesis]:
        """Select the top-n hypotheses by Elo rating."""
        return self.ranked[:n]

    def get_tournament_summary(self) -> str:
        """Produce a markdown summary of the tournament standings."""
        parts = ["### Hypothesis Tournament Rankings"]
        for i, h in enumerate(self.ranked, 1):
            parts.append(f"{i}. **{h.statement}** (Elo: {h.elo_rating:.0f}, status: {h.status})")
        return "\n".join(parts)
