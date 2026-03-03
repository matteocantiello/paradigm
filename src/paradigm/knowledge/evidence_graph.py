"""Evidence graph: conflict tracking, assumption management, provenance chains."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from paradigm.knowledge.models import HypothesisStatus
from paradigm.knowledge.world_model import WorldModel

# ---------------------------------------------------------------------------
# Evidence graph models
# ---------------------------------------------------------------------------


class ConflictType(StrEnum):
    """Types of evidence conflicts."""

    DIRECT_CONTRADICTION = "direct_contradiction"
    METHODOLOGICAL = "methodological"
    SCOPE_MISMATCH = "scope_mismatch"
    QUANTITATIVE_DISAGREEMENT = "quantitative_disagreement"


class ConflictResolution(StrEnum):
    """Resolution status for conflicts."""

    UNRESOLVED = "unresolved"
    RESOLVED_A = "resolved_a"
    RESOLVED_B = "resolved_b"
    RESOLVED_SYNTHESIS = "resolved_synthesis"
    ACKNOWLEDGED = "acknowledged"


class AssumptionStatus(StrEnum):
    """Status of an assumption."""

    ACTIVE = "active"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"


class ConflictEdge(BaseModel):
    """An edge representing a conflict between two pieces of evidence."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    evidence_a_id: str
    evidence_b_id: str
    conflict_type: ConflictType
    description: str = ""
    resolution_status: ConflictResolution = ConflictResolution.UNRESOLVED
    resolution_notes: str = ""


class Assumption(BaseModel):
    """An assumption underlying one or more hypotheses."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    statement: str
    basis: str = ""
    dependent_hypothesis_ids: list[str] = Field(default_factory=list)
    status: AssumptionStatus = AssumptionStatus.ACTIVE
    invalidated_by_evidence_id: str | None = None


class ProvenanceStep(BaseModel):
    """A single step in a provenance chain."""

    evidence_id: str
    description: str = ""


class ProvenanceChain(BaseModel):
    """A chain of reasoning from evidence to conclusion."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    conclusion_id: str  # hypothesis ID
    steps: list[ProvenanceStep] = Field(default_factory=list)
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# Evidence Graph
# ---------------------------------------------------------------------------


class EvidenceGraph:
    """Wraps a WorldModel with conflict tracking, assumptions, and provenance.

    Provides epistemic structure on top of the flat world model:
    conflict edges between evidence, assumption tracking with cascade
    invalidation, and provenance chains.
    """

    def __init__(self, world_model: WorldModel) -> None:
        self.world_model = world_model
        self.conflicts: dict[str, ConflictEdge] = {}
        self.assumptions: dict[str, Assumption] = {}
        self.provenance_chains: dict[str, ProvenanceChain] = {}

    # ------------------------------------------------------------------
    # Conflicts
    # ------------------------------------------------------------------

    def add_conflict(self, conflict: ConflictEdge) -> str:
        self.conflicts[conflict.id] = conflict
        return conflict.id

    def get_conflict(self, conflict_id: str) -> ConflictEdge | None:
        return self.conflicts.get(conflict_id)

    def get_unresolved_conflicts(self) -> list[ConflictEdge]:
        return [
            c
            for c in self.conflicts.values()
            if c.resolution_status == ConflictResolution.UNRESOLVED
        ]

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution: ConflictResolution,
        notes: str = "",
    ) -> bool:
        conflict = self.conflicts.get(conflict_id)
        if conflict is None:
            return False
        conflict.resolution_status = resolution
        conflict.resolution_notes = notes
        return True

    # ------------------------------------------------------------------
    # Assumptions
    # ------------------------------------------------------------------

    def add_assumption(self, assumption: Assumption) -> str:
        self.assumptions[assumption.id] = assumption
        return assumption.id

    def get_assumption(self, assumption_id: str) -> Assumption | None:
        return self.assumptions.get(assumption_id)

    def invalidate_assumption(
        self,
        assumption_id: str,
        evidence_id: str,
    ) -> list[str]:
        """Invalidate an assumption and cascade to dependent hypotheses.

        Returns:
            List of hypothesis IDs whose confidence was downgraded.
        """
        assumption = self.assumptions.get(assumption_id)
        if assumption is None:
            return []

        assumption.status = AssumptionStatus.INVALIDATED
        assumption.invalidated_by_evidence_id = evidence_id

        affected: list[str] = []
        for hyp_id in assumption.dependent_hypothesis_ids:
            hyp = self.world_model.get_hypothesis(hyp_id)
            if hyp is not None and hyp.status not in (
                HypothesisStatus.ABANDONED,
                HypothesisStatus.CONTRADICTED,
            ):
                hyp.status = HypothesisStatus.CONTRADICTED
                affected.append(hyp_id)

        return affected

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    def add_provenance(self, chain: ProvenanceChain) -> str:
        self.provenance_chains[chain.id] = chain
        return chain.id

    def get_provenance(self, chain_id: str) -> ProvenanceChain | None:
        return self.provenance_chains.get(chain_id)

    def get_provenance_for_hypothesis(self, hypothesis_id: str) -> list[ProvenanceChain]:
        return [c for c in self.provenance_chains.values() if c.conclusion_id == hypothesis_id]

    # ------------------------------------------------------------------
    # Hypothesis strength assessment
    # ------------------------------------------------------------------

    def assess_hypothesis_strength(self, hypothesis_id: str) -> dict[str, Any]:
        """Assess the epistemic strength of a hypothesis.

        Returns:
            Dict with support_count, contradict_count, active_assumptions,
            invalidated_assumptions, unresolved_conflicts, strength_score.
        """
        hyp = self.world_model.get_hypothesis(hypothesis_id)
        if hyp is None:
            return {"error": "hypothesis not found"}

        support_count = len(hyp.supporting_evidence_ids)
        contradict_count = len(hyp.contradicting_evidence_ids)

        # Count assumptions
        active_assumptions = 0
        invalidated_assumptions = 0
        for a in self.assumptions.values():
            if hypothesis_id in a.dependent_hypothesis_ids:
                if a.status == AssumptionStatus.ACTIVE:
                    active_assumptions += 1
                elif a.status == AssumptionStatus.INVALIDATED:
                    invalidated_assumptions += 1

        # Count unresolved conflicts involving this hypothesis's evidence
        all_evidence_ids = set(hyp.supporting_evidence_ids + hyp.contradicting_evidence_ids)
        unresolved = 0
        for c in self.conflicts.values():
            if c.resolution_status == ConflictResolution.UNRESOLVED:
                if c.evidence_a_id in all_evidence_ids or c.evidence_b_id in all_evidence_ids:
                    unresolved += 1

        # Simple strength score
        score = support_count - contradict_count - invalidated_assumptions - unresolved
        return {
            "support_count": support_count,
            "contradict_count": contradict_count,
            "active_assumptions": active_assumptions,
            "invalidated_assumptions": invalidated_assumptions,
            "unresolved_conflicts": unresolved,
            "strength_score": score,
        }

    # ------------------------------------------------------------------
    # Summary for prompt injection
    # ------------------------------------------------------------------

    def summarize_evidence_landscape(self, max_chars: int = 2000) -> str:
        """Produce a markdown summary of the evidence landscape."""
        parts: list[str] = []

        # Unresolved conflicts
        unresolved = self.get_unresolved_conflicts()
        if unresolved:
            parts.append("### Unresolved Conflicts")
            for c in unresolved[:5]:
                ev_a = self.world_model.get_evidence(c.evidence_a_id)
                ev_b = self.world_model.get_evidence(c.evidence_b_id)
                a_desc = ev_a.content[:60] if ev_a else c.evidence_a_id
                b_desc = ev_b.content[:60] if ev_b else c.evidence_b_id
                parts.append(f"- **{c.conflict_type}**: {a_desc} vs {b_desc}")

        # Active assumptions
        active = [a for a in self.assumptions.values() if a.status == AssumptionStatus.ACTIVE]
        if active:
            parts.append("### Active Assumptions")
            for a in active[:5]:
                dep_count = len(a.dependent_hypothesis_ids)
                parts.append(f"- {a.statement} (affects {dep_count} hypotheses)")

        # Invalidated assumptions
        invalidated = [
            a for a in self.assumptions.values() if a.status == AssumptionStatus.INVALIDATED
        ]
        if invalidated:
            parts.append("### Invalidated Assumptions")
            for a in invalidated[:3]:
                parts.append(f"- ~~{a.statement}~~ (invalidated)")

        # Hypothesis strength ranking
        if self.world_model.hypotheses:
            parts.append("### Hypothesis Strength")
            for hyp in sorted(
                self.world_model.hypotheses.values(),
                key=lambda h: h.elo_rating,
                reverse=True,
            )[:5]:
                strength = self.assess_hypothesis_strength(hyp.id)
                parts.append(
                    f"- {hyp.statement}: score={strength['strength_score']}, "
                    f"+{strength['support_count']}/-{strength['contradict_count']}"
                )

        summary = "\n".join(parts)
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "\n... (truncated)"
        return summary

    # ------------------------------------------------------------------
    # Snapshot serialization
    # ------------------------------------------------------------------

    def to_snapshot(self) -> dict[str, Any]:
        """Serialize including the world model and graph-specific data."""
        return {
            "world_model": self.world_model.to_snapshot(),
            "conflicts": {k: v.model_dump() for k, v in self.conflicts.items()},
            "assumptions": {k: v.model_dump() for k, v in self.assumptions.items()},
            "provenance_chains": {k: v.model_dump() for k, v in self.provenance_chains.items()},
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> EvidenceGraph:
        """Restore from a snapshot dict."""
        wm = WorldModel.from_snapshot(data.get("world_model", {}))
        eg = cls(wm)
        for k, v in data.get("conflicts", {}).items():
            eg.conflicts[k] = ConflictEdge.model_validate(v)
        for k, v in data.get("assumptions", {}).items():
            eg.assumptions[k] = Assumption.model_validate(v)
        for k, v in data.get("provenance_chains", {}).items():
            eg.provenance_chains[k] = ProvenanceChain.model_validate(v)
        return eg
