"""In-memory world model with snapshot-based persistence."""

from __future__ import annotations

import json
from typing import Any

from paradigm.knowledge.models import (
    Entity,
    Evidence,
    Hypothesis,
    OpenQuestion,
    Relationship,
    ResearchGoal,
)


class WorldModel:
    """Structured knowledge store for a research cycle.

    Stores entities, relationships, hypotheses, evidence, open questions,
    and research goals in-memory.  Supports JSON snapshot round-trip for
    persistence and a markdown summary for prompt injection.
    """

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.relationships: dict[str, Relationship] = {}
        self.hypotheses: dict[str, Hypothesis] = {}
        self.evidence: dict[str, Evidence] = {}
        self.open_questions: dict[str, OpenQuestion] = {}
        self.research_goals: dict[str, ResearchGoal] = {}

    # ------------------------------------------------------------------
    # CRUD — Entities
    # ------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> str:
        self.entities[entity.id] = entity
        return entity.id

    def get_entity(self, entity_id: str) -> Entity | None:
        return self.entities.get(entity_id)

    def remove_entity(self, entity_id: str) -> bool:
        return self.entities.pop(entity_id, None) is not None

    # ------------------------------------------------------------------
    # CRUD — Relationships
    # ------------------------------------------------------------------

    def add_relationship(self, rel: Relationship) -> str:
        self.relationships[rel.id] = rel
        return rel.id

    def get_relationship(self, rel_id: str) -> Relationship | None:
        return self.relationships.get(rel_id)

    def remove_relationship(self, rel_id: str) -> bool:
        return self.relationships.pop(rel_id, None) is not None

    # ------------------------------------------------------------------
    # CRUD — Hypotheses
    # ------------------------------------------------------------------

    def add_hypothesis(self, hyp: Hypothesis) -> str:
        self.hypotheses[hyp.id] = hyp
        return hyp.id

    def get_hypothesis(self, hyp_id: str) -> Hypothesis | None:
        return self.hypotheses.get(hyp_id)

    def update_hypothesis(self, hyp_id: str, **fields: Any) -> bool:
        hyp = self.hypotheses.get(hyp_id)
        if hyp is None:
            return False
        for key, value in fields.items():
            if hasattr(hyp, key):
                setattr(hyp, key, value)
        return True

    def remove_hypothesis(self, hyp_id: str) -> bool:
        return self.hypotheses.pop(hyp_id, None) is not None

    # ------------------------------------------------------------------
    # CRUD — Evidence
    # ------------------------------------------------------------------

    def add_evidence(self, ev: Evidence) -> str:
        self.evidence[ev.id] = ev
        return ev.id

    def get_evidence(self, ev_id: str) -> Evidence | None:
        return self.evidence.get(ev_id)

    def remove_evidence(self, ev_id: str) -> bool:
        return self.evidence.pop(ev_id, None) is not None

    # ------------------------------------------------------------------
    # CRUD — Open Questions
    # ------------------------------------------------------------------

    def add_open_question(self, oq: OpenQuestion) -> str:
        self.open_questions[oq.id] = oq
        return oq.id

    def get_open_question(self, oq_id: str) -> OpenQuestion | None:
        return self.open_questions.get(oq_id)

    def remove_open_question(self, oq_id: str) -> bool:
        return self.open_questions.pop(oq_id, None) is not None

    # ------------------------------------------------------------------
    # CRUD — Research Goals
    # ------------------------------------------------------------------

    def add_research_goal(self, goal: ResearchGoal) -> str:
        self.research_goals[goal.id] = goal
        return goal.id

    def get_research_goal(self, goal_id: str) -> ResearchGoal | None:
        return self.research_goals.get(goal_id)

    def remove_research_goal(self, goal_id: str) -> bool:
        return self.research_goals.pop(goal_id, None) is not None

    # ------------------------------------------------------------------
    # Evidence ↔ Hypothesis linking
    # ------------------------------------------------------------------

    def link_evidence_to_hypothesis(
        self,
        evidence_id: str,
        hypothesis_id: str,
        *,
        supports: bool,
    ) -> bool:
        """Link evidence to a hypothesis (supporting or contradicting).

        Updates both sides: the evidence's lists and the hypothesis's lists.

        Returns:
            True if both objects exist and were linked.
        """
        ev = self.evidence.get(evidence_id)
        hyp = self.hypotheses.get(hypothesis_id)
        if ev is None or hyp is None:
            return False

        if supports:
            if hypothesis_id not in ev.supports_hypothesis_ids:
                ev.supports_hypothesis_ids.append(hypothesis_id)
            if evidence_id not in hyp.supporting_evidence_ids:
                hyp.supporting_evidence_ids.append(evidence_id)
        else:
            if hypothesis_id not in ev.contradicts_hypothesis_ids:
                ev.contradicts_hypothesis_ids.append(hypothesis_id)
            if evidence_id not in hyp.contradicting_evidence_ids:
                hyp.contradicting_evidence_ids.append(evidence_id)

        return True

    # ------------------------------------------------------------------
    # Summary for prompt injection
    # ------------------------------------------------------------------

    def summarize_state(self, max_chars: int = 3000) -> str:
        """Produce a markdown summary of the current world model state.

        The summary is capped at *max_chars* to fit in prompt budgets.
        Priority order: research goals > hypotheses > key entities > evidence > open questions.
        """
        parts: list[str] = []

        # Research goals
        if self.research_goals:
            parts.append("### Research Goals")
            for g in self.research_goals.values():
                parts.append(f"- **{g.description}** (status: {g.status})")

        # Hypotheses (sorted by Elo descending)
        if self.hypotheses:
            parts.append("### Hypotheses")
            sorted_hyps = sorted(self.hypotheses.values(), key=lambda h: h.elo_rating, reverse=True)
            for h in sorted_hyps:
                sup = len(h.supporting_evidence_ids)
                con = len(h.contradicting_evidence_ids)
                parts.append(
                    f"- [{h.status}] **{h.statement}** "
                    f"(confidence: {h.confidence}, elo: {h.elo_rating:.0f}, "
                    f"+{sup}/-{con} evidence)"
                )

        # Key entities (capped at 15)
        if self.entities:
            parts.append("### Key Entities")
            for ent in list(self.entities.values())[:15]:
                parts.append(f"- {ent.name} ({ent.entity_type}): {ent.description[:80]}")

        # Evidence count summary
        if self.evidence:
            parts.append(f"### Evidence ({len(self.evidence)} items)")
            for ev in list(self.evidence.values())[:10]:
                parts.append(f"- [{ev.source}] {ev.content[:80]}")

        # Open questions
        if self.open_questions:
            parts.append("### Open Questions")
            for oq in self.open_questions.values():
                parts.append(f"- {oq.question}")

        summary = "\n".join(parts)
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "\n... (truncated)"
        return summary

    # ------------------------------------------------------------------
    # Snapshot serialization
    # ------------------------------------------------------------------

    def to_snapshot(self) -> dict[str, Any]:
        """Serialize the world model to a JSON-safe dict."""
        return {
            "entities": {k: v.model_dump() for k, v in self.entities.items()},
            "relationships": {k: v.model_dump() for k, v in self.relationships.items()},
            "hypotheses": {k: v.model_dump() for k, v in self.hypotheses.items()},
            "evidence": {k: v.model_dump() for k, v in self.evidence.items()},
            "open_questions": {k: v.model_dump() for k, v in self.open_questions.items()},
            "research_goals": {k: v.model_dump() for k, v in self.research_goals.items()},
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> WorldModel:
        """Restore a world model from a snapshot dict."""
        wm = cls()
        for k, v in data.get("entities", {}).items():
            wm.entities[k] = Entity.model_validate(v)
        for k, v in data.get("relationships", {}).items():
            wm.relationships[k] = Relationship.model_validate(v)
        for k, v in data.get("hypotheses", {}).items():
            wm.hypotheses[k] = Hypothesis.model_validate(v)
        for k, v in data.get("evidence", {}).items():
            wm.evidence[k] = Evidence.model_validate(v)
        for k, v in data.get("open_questions", {}).items():
            wm.open_questions[k] = OpenQuestion.model_validate(v)
        for k, v in data.get("research_goals", {}).items():
            wm.research_goals[k] = ResearchGoal.model_validate(v)
        return wm

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_snapshot(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> WorldModel:
        """Restore from JSON string."""
        return cls.from_snapshot(json.loads(json_str))
