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
