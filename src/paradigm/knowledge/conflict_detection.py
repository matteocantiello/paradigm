"""Deterministic conflict detection for new evidence."""

from __future__ import annotations

from paradigm.knowledge.evidence_graph import ConflictEdge, ConflictType, EvidenceGraph
from paradigm.knowledge.models import Evidence


class ConflictDetector:
    """Detects conflicts when new evidence is added to the graph.

    Detection is deterministic (no LLM needed): if new evidence contradicts
    a hypothesis that existing evidence supports, a conflict is flagged.
    """

    def __init__(self, evidence_graph: EvidenceGraph) -> None:
        self._graph = evidence_graph

    def check_new_evidence(self, evidence: Evidence) -> list[ConflictEdge]:
        """Check a new piece of evidence for conflicts with existing evidence.

        Conflict detection logic:
        - If the new evidence contradicts hypothesis H, find all existing evidence
          that supports H — each is a potential conflict.
        - If the new evidence supports hypothesis H, find all existing evidence
          that contradicts H — each is a potential conflict.

        Returns:
            List of new ConflictEdge objects (not yet added to the graph).
        """
        wm = self._graph.world_model
        conflicts: list[ConflictEdge] = []

        # Check hypotheses the new evidence contradicts
        for hyp_id in evidence.contradicts_hypothesis_ids:
            hyp = wm.get_hypothesis(hyp_id)
            if hyp is None:
                continue
            # Find existing evidence that supports this hypothesis
            for sup_ev_id in hyp.supporting_evidence_ids:
                if sup_ev_id == evidence.id:
                    continue
                existing = wm.get_evidence(sup_ev_id)
                if existing is None:
                    continue
                conflict = ConflictEdge(
                    evidence_a_id=evidence.id,
                    evidence_b_id=sup_ev_id,
                    conflict_type=ConflictType.DIRECT_CONTRADICTION,
                    description=(
                        f"New evidence contradicts hypothesis '{hyp.statement[:60]}' "
                        f"while existing evidence supports it."
                    ),
                )
                conflicts.append(conflict)

        # Check hypotheses the new evidence supports
        for hyp_id in evidence.supports_hypothesis_ids:
            hyp = wm.get_hypothesis(hyp_id)
            if hyp is None:
                continue
            # Find existing evidence that contradicts this hypothesis
            for con_ev_id in hyp.contradicting_evidence_ids:
                if con_ev_id == evidence.id:
                    continue
                existing = wm.get_evidence(con_ev_id)
                if existing is None:
                    continue
                conflict = ConflictEdge(
                    evidence_a_id=evidence.id,
                    evidence_b_id=con_ev_id,
                    conflict_type=ConflictType.DIRECT_CONTRADICTION,
                    description=(
                        f"New evidence supports hypothesis '{hyp.statement[:60]}' "
                        f"while existing evidence contradicts it."
                    ),
                )
                conflicts.append(conflict)

        return conflicts
