"""Pydantic models for evaluation scores and reports."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Outcome → score (0..1). Domain-agnostic: keyed on the orchestrator's end-state
# statuses, not on any scientific content. Published is the goal; the failure
# statuses are ordered by how far the cycle got before stopping.
OUTCOME_SCORES: dict[str, float] = {
    "published": 1.0,
    "reviewed": 0.85,  # passed internal review, awaiting/!peer review
    "revised": 0.5,
    "revision_exhausted": 0.30,
    "review_rejected": 0.20,
    "rejected": 0.20,  # peer-review rejection
    "writing_incomplete": 0.10,
    "execution_failed": 0.10,
    "writing_failed": 0.10,  # legacy/historical threads
    "aborted": 0.0,
}


class DeterministicMetrics(BaseModel):
    """Objective, reproducible signals computed without any LLM call."""

    outcome: str
    outcome_score: float = 0.0  # 0..1, from OUTCOME_SCORES
    body_chars: int = 0
    num_sections: int = 0  # count of markdown headings (#, ##)
    has_references: bool = False
    figures_referenced: int = 0
    figures_present: int = 0
    figure_validity: float = 1.0  # present / referenced (1.0 when none referenced)
    total_references: int = 0
    bare_url_references: int = 0
    citation_quality: float = 1.0  # 1 - bare/total (1.0 when no references)
    citation_count: int = 0
    total_tokens: int | None = None  # None when the thread can't be mapped

    @property
    def structure_score(self) -> float:
        """Soft 0..1 structure signal: enough sections + a references section."""
        section_component = min(self.num_sections / 6.0, 1.0)
        ref_component = 1.0 if self.has_references else 0.0
        return 0.7 * section_component + 0.3 * ref_component

    @property
    def grounding_score(self) -> float:
        """0..1 grounding signal: figures exist and citations aren't bare URLs."""
        return 0.5 * self.figure_validity + 0.5 * self.citation_quality

    @property
    def deterministic_score(self) -> float:
        """Blended 0..1 deterministic quality (outcome-weighted)."""
        return 0.5 * self.outcome_score + 0.25 * self.structure_score + 0.25 * self.grounding_score


class JudgeScores(BaseModel):
    """LLM taste-judge scores on a 1..10 rubric."""

    novelty: int = Field(ge=0, le=10)
    rigor: int = Field(ge=0, le=10)
    clarity: int = Field(ge=0, le=10)
    significance: int = Field(ge=0, le=10)
    honesty: int = Field(ge=0, le=10)
    justification: str = ""

    @property
    def mean(self) -> float:
        """Mean of the five dimensions, normalized to 0..1."""
        return (
            self.novelty + self.rigor + self.clarity + self.significance + self.honesty
        ) / 50.0


class PaperScore(BaseModel):
    """Full score for a single paper."""

    paper_id: str
    title: str
    deterministic: DeterministicMetrics
    judge: JudgeScores | None = None
    quality_score: float = 0.0  # blended 0..100

    @staticmethod
    def blend(det: DeterministicMetrics, judge: JudgeScores | None) -> float:
        """Blend deterministic + judge into a 0..100 quality score.

        When the judge is unavailable, fall back to deterministic-only so offline
        runs without an API key still produce a meaningful number.
        """
        if judge is None:
            return round(100.0 * det.deterministic_score, 1)
        return round(100.0 * (0.5 * det.deterministic_score + 0.5 * judge.mean), 1)


class EvalReport(BaseModel):
    """Aggregate report over a set of scored papers."""

    scores: list[PaperScore] = Field(default_factory=list)
    judged: bool = False

    @property
    def count(self) -> int:
        return len(self.scores)

    @property
    def mean_quality(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(s.quality_score for s in self.scores) / len(self.scores), 1)

    def outcome_breakdown(self) -> dict[str, int]:
        """Count of papers per outcome status."""
        out: dict[str, int] = {}
        for s in self.scores:
            out[s.deterministic.outcome] = out.get(s.deterministic.outcome, 0) + 1
        return out
