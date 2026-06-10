"""Handler for world model operations within the orchestration engine."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from paradigm.knowledge.conflict_detection import ConflictDetector
from paradigm.knowledge.evidence_graph import ConflictEdge, EvidenceGraph
from paradigm.knowledge.models import (
    ConfidenceLevel,
    Entity,
    EntityType,
    Evidence,
    EvidenceSource,
    Hypothesis,
    ResearchGoal,
)
from paradigm.knowledge.world_model import WorldModel

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine

# ---------------------------------------------------------------------------
# Tag-parsing regexes (same style as [SEARCH:] in prompt_utils)
# ---------------------------------------------------------------------------

_ENTITY_TAG_RE = re.compile(
    r"\[ENTITY:\s*([^\]]+?)\]",
    re.IGNORECASE,
)
_HYPOTHESIS_TAG_RE = re.compile(
    r"\[HYPOTHESIS:\s*([^\]]+?)\]",
    re.IGNORECASE,
)
_EVIDENCE_TAG_RE = re.compile(
    r"\[EVIDENCE:\s*([^\]]+?)\]",
    re.IGNORECASE,
)


class WorldModelHandler:
    """Manages the world model lifecycle within a research cycle.

    Follows the handler pattern used by LiteratureHandler, DebateHandler, etc.:
    stores a reference to the engine and accesses state/config through it.
    """

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize_world_model(self) -> WorldModel:
        """Create a fresh world model and seed it with the research goal."""
        wm = WorldModel()
        seed = self._engine.state.seed_prompt
        goal = ResearchGoal(
            description=seed[:500],
            success_criteria="Complete a research cycle producing a publishable paper.",
        )
        wm.add_research_goal(goal)
        return wm

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def build_world_model_context(self, max_chars: int = 3000) -> str:
        """Build a markdown context block from the world model for prompt injection."""
        wm = self._engine.state.world_model
        if wm is None:
            return ""
        summary = wm.summarize_state(max_chars=max_chars)
        if not summary.strip():
            return ""
        return "## World Model\n" + summary

    # ------------------------------------------------------------------
    # Agent response parsing
    # ------------------------------------------------------------------

    def update_from_agent_response(
        self,
        agent_id: str,
        content: str,
        phase: str,
    ) -> None:
        """Parse structured tags from an agent response and update the world model.

        Recognized tags:
        - [ENTITY: name | type | description]
        - [HYPOTHESIS: statement]
        - [EVIDENCE: content | source]
        """
        wm = self._engine.state.world_model
        if wm is None:
            return

        # Parse entities
        for match in _ENTITY_TAG_RE.finditer(content):
            raw = match.group(1).strip()
            parts = [p.strip() for p in raw.split("|")]
            name = parts[0]
            etype = EntityType.CONCEPT
            desc = ""
            if len(parts) >= 2:
                try:
                    etype = EntityType(parts[1].lower())
                except ValueError:
                    desc = parts[1]
            if len(parts) >= 3:
                desc = parts[2]
            entity = Entity(
                name=name,
                entity_type=etype,
                description=desc,
                created_by=agent_id,
            )
            wm.add_entity(entity)

        # Parse hypotheses
        for match in _HYPOTHESIS_TAG_RE.finditer(content):
            statement = match.group(1).strip()
            hyp = Hypothesis(statement=statement)
            wm.add_hypothesis(hyp)
            self._engine.emit_event(
                "hypothesis.created",
                {"hypothesis_id": hyp.id, "statement": statement},
                agent=agent_id,
            )

        # Parse evidence
        for match in _EVIDENCE_TAG_RE.finditer(content):
            raw = match.group(1).strip()
            parts = [p.strip() for p in raw.split("|")]
            ev_content = parts[0]
            source = EvidenceSource.AGENT_REASONING
            if len(parts) >= 2:
                try:
                    source = EvidenceSource(parts[1].lower())
                except ValueError:
                    pass
            ev = Evidence(
                content=ev_content,
                source=source,
                confidence=ConfidenceLevel.MODERATE,
            )
            wm.add_evidence(ev)
            self._engine.emit_event(
                "claim.extracted",
                {"claim_id": ev.id, "statement": ev_content[:2000], "source": source.value},
                agent=agent_id,
            )
            # TODO(evidence.linked): nothing in the orchestrator calls
            # WorldModel.link_evidence_to_hypothesis yet, so claim→hypothesis
            # links never form; emit evidence.linked here when linking lands.

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def persist_snapshot(self) -> None:
        """Save the current world model snapshot to the database."""
        wm = self._engine.state.world_model
        if wm is None:
            return
        thread_id = self._engine.state.thread_id
        json_str = wm.to_json()
        self._engine._db.save_world_model_snapshot(thread_id, json_str)

    def load_snapshot(self, thread_id: str) -> WorldModel | None:
        """Load a world model snapshot from the database."""
        json_str = self._engine._db.load_world_model_snapshot(thread_id)
        if json_str is None:
            return None
        return WorldModel.from_json(json_str)

    def save_to_thread(self, paper_id: str) -> None:
        """Write the world model JSON to the paper directory."""
        wm = self._engine.state.world_model
        if wm is None:
            return
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return
        paper_dir = papers_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / "knowledge" / "world_model.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wm.to_json())

    # ------------------------------------------------------------------
    # Evidence graph (Stage 2)
    # ------------------------------------------------------------------

    def initialize_evidence_graph(self) -> EvidenceGraph:
        """Create an evidence graph wrapping the current world model."""
        wm = self._engine.state.world_model
        if wm is None:
            wm = self.initialize_world_model()
            self._engine.state.world_model = wm
        return EvidenceGraph(wm)

    def build_evidence_landscape_context(self, max_chars: int = 2000) -> str:
        """Build a markdown context block from the evidence landscape."""
        eg = self._engine.state.evidence_graph
        if eg is None:
            return ""
        summary = eg.summarize_evidence_landscape(max_chars=max_chars)
        if not summary.strip():
            return ""
        return "## Evidence Landscape\n" + summary

    def detect_and_register_conflicts(self, evidence: Evidence) -> list[ConflictEdge]:
        """Detect conflicts for new evidence and register them in the graph.

        Returns:
            List of newly created ConflictEdge objects.
        """
        eg = self._engine.state.evidence_graph
        if eg is None:
            return []
        detector = ConflictDetector(eg)
        conflicts = detector.check_new_evidence(evidence)
        for conflict in conflicts:
            eg.add_conflict(conflict)
        return conflicts
