"""Pure Pydantic models for the knowledge architecture."""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EntityType(StrEnum):
    """Types of entities in the world model."""

    CONCEPT = "concept"
    OBJECT = "object"
    PROCESS = "process"
    QUANTITY = "quantity"
    METHOD = "method"
    DATASET = "dataset"
    RESULT = "result"


class RelationshipType(StrEnum):
    """Types of relationships between entities."""

    CAUSES = "causes"
    CORRELATES_WITH = "correlates_with"
    PART_OF = "part_of"
    INSTANCE_OF = "instance_of"
    DEPENDS_ON = "depends_on"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    MEASURED_BY = "measured_by"
    PRODUCES = "produces"


class EvidenceSource(StrEnum):
    """Sources of evidence."""

    LITERATURE = "literature"
    EXPERIMENT = "experiment"
    THEORETICAL = "theoretical"
    AGENT_REASONING = "agent_reasoning"
    EXTERNAL_DATA = "external_data"


class HypothesisStatus(StrEnum):
    """Status of a hypothesis."""

    PROPOSED = "proposed"
    UNDER_INVESTIGATION = "under_investigation"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    REFINED = "refined"
    ABANDONED = "abandoned"


class ConfidenceLevel(StrEnum):
    """Qualitative confidence levels."""

    SPECULATIVE = "speculative"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    ESTABLISHED = "established"


class PredictionDirection(StrEnum):
    """How a metric value relates to the bound(s) for a claim to hold."""

    INSIDE = "inside"  # claim holds iff low <= metric <= high
    OUTSIDE = "outside"  # claim holds iff metric < low or metric > high
    GREATER = "greater"  # claim holds iff metric > low
    LESS = "less"  # claim holds iff metric < high


class PredictionVerdict(StrEnum):
    """Outcome of evaluating a pre-registered prediction against captured results."""

    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------


class Entity(BaseModel):
    """A named entity in the world model (concept, object, process, etc.)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    entity_type: EntityType
    description: str = ""
    properties: dict[str, str] = Field(default_factory=dict)
    created_by: str = ""  # agent_id that created this


class Relationship(BaseModel):
    """A directed relationship between two entities."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    confidence: ConfidenceLevel = ConfidenceLevel.MODERATE
    evidence_ids: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """A piece of evidence supporting or contradicting hypotheses."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str
    source: EvidenceSource
    source_ref: str = ""  # paper ID, experiment name, etc.
    confidence: ConfidenceLevel = ConfidenceLevel.MODERATE
    supports_hypothesis_ids: list[str] = Field(default_factory=list)
    contradicts_hypothesis_ids: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    """A testable hypothesis with evidence tracking and Elo rating."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    statement: str
    rationale: str = ""
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    confidence: ConfidenceLevel = ConfidenceLevel.SPECULATIVE
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    elo_rating: float = 1500.0
    # Pre-registration (1A): link to a frozen prediction rule + its evaluated verdict.
    prediction_rule_id: str | None = None
    verdict: PredictionVerdict = PredictionVerdict.UNREGISTERED


class PredictionRule(BaseModel):
    """A machine-readable, falsifiable prediction frozen before EXECUTION.

    The post-execution verdict is computed *only* against this frozen rule
    (never re-read from agent text), which blocks post-hoc redefinition.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    hypothesis_id: str = ""
    metric_name: str = ""  # human-readable metric name, e.g. "pearson_r"
    metric_stdout_key: str = ""  # exact token the experimentalist must print, e.g. "pearson_r"
    direction: PredictionDirection = PredictionDirection.INSIDE
    low: float | None = None
    high: float | None = None
    significance_max_p: float | None = None  # if set, p-value must be <= this
    refutation_condition: str = ""  # REQUIRED non-empty: what would prove the claim wrong
    registered_at: str = ""  # ISO timestamp, set at the freeze gate
    frozen: bool = False  # True once frozen; immutable thereafter

    def is_well_formed(self) -> bool:
        """A rule is admissible only if it has a refutation condition and a usable bound."""
        if not self.refutation_condition.strip():
            return False
        if not self.metric_stdout_key.strip():
            return False
        if self.direction in (PredictionDirection.INSIDE, PredictionDirection.OUTSIDE):
            return self.low is not None and self.high is not None
        if self.direction == PredictionDirection.GREATER:
            return self.low is not None
        if self.direction == PredictionDirection.LESS:
            return self.high is not None
        return False

    def holds(self, value: float) -> bool:
        """Whether a measured value satisfies the claim (the hypothesis is confirmed)."""
        if self.direction == PredictionDirection.INSIDE:
            return self.low is not None and self.high is not None and self.low <= value <= self.high
        if self.direction == PredictionDirection.OUTSIDE:
            return (
                self.low is not None
                and self.high is not None
                and (value < self.low or value > self.high)
            )
        if self.direction == PredictionDirection.GREATER:
            return self.low is not None and value > self.low
        if self.direction == PredictionDirection.LESS:
            return self.high is not None and value < self.high
        return False


class VerificationRecord(BaseModel):
    """Result of re-executing an experiment to verify its reported numbers (1B).

    A reported result is "accepted" only if its committed code re-runs in a fresh
    sandbox with a fixed seed and reproduces its ``RESULT[...]`` tokens within
    tolerance. This is Paradigm's empirical analog of a proof checker.
    """

    experiment_name: str
    seed: int = 0
    reproduced: bool = False
    tolerance: float = 1e-6
    original_values: dict[str, float] = Field(default_factory=dict)
    rerun_values: dict[str, float] = Field(default_factory=dict)
    max_rel_error: float | None = None
    checks: dict[str, str] = Field(default_factory=dict)
    status: str = "unverified"  # unverified | accepted | rejected | nondeterministic
    detail: str = ""


class ProvenanceRecord(BaseModel):
    """Who framed / registered / verified a paper (Phase 1E).

    Makes the human-vs-agent chain of accountability a legible, first-class
    artifact. Fields are written by the engine (never by agents) so they can't
    be confabulated.
    """

    paper_id: str = ""
    thread_id: str = ""
    framed_by: str = "agents"  # "human" or "agents"
    registered_by: str = "none"  # who authored the pre-registration rules
    verified_by: str = "none"  # e.g. "kernel", "kernel+human"
    human_gate_mode: str = "off"
    gate_decisions: dict[str, str] = Field(default_factory=dict)
    prereg_rule_ids: list[str] = Field(default_factory=list)
    verification_summary: dict[str, str] = Field(default_factory=dict)


class OpenQuestion(BaseModel):
    """An unresolved question identified during research."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    question: str
    context: str = ""
    priority: ConfidenceLevel = ConfidenceLevel.MODERATE
    related_hypothesis_ids: list[str] = Field(default_factory=list)


class ResearchGoal(BaseModel):
    """A high-level research goal guiding the investigation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    success_criteria: str = ""
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    related_hypothesis_ids: list[str] = Field(default_factory=list)
