"""Per-cycle mutable research state for the orchestration engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from paradigm.agents.base import Agent
    from paradigm.knowledge.evidence_graph import EvidenceGraph
    from paradigm.knowledge.models import Hypothesis, PredictionRule
    from paradigm.knowledge.world_model import WorldModel
    from paradigm.literature.resources import ResolvedResource
    from paradigm.orchestrator.phases import PhaseManager
    from paradigm.storage.checkpoints import Checkpoint


@dataclass
class ResearchState:
    """Holds all per-cycle mutable state for a research cycle.

    Created fresh at the start of each ``run_research_cycle`` call.
    Infrastructure (config, db, display, handlers) stays on the engine.
    """

    # Identity / lifecycle
    thread_id: str = ""
    seed_prompt: str = ""
    mode: str = "directed"
    start_time: float = field(default_factory=time.monotonic)

    # Agent team
    agents: dict[str, Agent] = field(default_factory=dict)

    # Phase management
    phase_manager: PhaseManager | None = None
    checkpoint: Checkpoint | None = None

    # Conversation
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Execution results
    execution_context: str = ""
    execution_caveats: list[str] = field(default_factory=list)
    execution_figures: list[tuple[str, Path]] = field(default_factory=list)
    successful_code: list[tuple[str, str]] = field(default_factory=list)
    experiment_metadata: list[dict[str, str | bool]] = field(default_factory=list)

    # Phase synthesis
    post_execution_summary: str = ""
    consensus_summary: str = ""
    phase_synthesis: dict[str, str] = field(default_factory=dict)
    planning_action_items: str = ""

    # Resource contexts (seeding)
    code_context: str = ""
    data_context: str = ""
    reference_context: str = ""
    resolved_resources: list[ResolvedResource] = field(default_factory=list)
    graveyard_context: str = ""

    # Knowledge architecture
    world_model: WorldModel | None = None
    evidence_graph: EvidenceGraph | None = None

    # Pre-registration (1A): hypotheses carried into execution, their frozen
    # prediction rules, and the post-execution verdicts computed against them.
    selected_hypotheses: list[Hypothesis] = field(default_factory=list)
    registered_rules: list[PredictionRule] = field(default_factory=list)
    prereg_verdicts: list[dict[str, str]] = field(default_factory=list)

    # Writing
    forbidden_claims_violations: list[str] = field(default_factory=list)
