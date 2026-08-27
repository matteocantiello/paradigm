"""Pydantic models for the Settings API."""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- Read models (full field set, returned by GET) ---


class OrchestratorSettings(BaseModel):
    max_rounds_per_phase: int = 10
    enable_checkpointing: bool = True
    enable_writing: bool = True
    max_review_iterations: int = 5
    enable_peer_review: bool = True
    num_reviewers: int = 2
    enable_experimentation: bool = True
    enable_debates: bool = True
    max_debate_exchanges: int = 3
    enable_convergence_detection: bool = True
    convergence_confidence_threshold: float = 0.70
    enable_execution_sprints: bool = False
    num_execution_sprints: int = 3
    # Correctness kernel (Phase 1) + output quality (Phase 2) toggles
    enable_verification: bool = False
    verification_tolerance: float = 1e-6
    abort_on_verification_failure: bool = True
    enable_robustness_loop: bool = False
    robustness_max_passes: int = 2
    enable_replication_gate: bool = False
    replication_max_specs: int = 5
    enable_best_first_nodes: bool = False
    enable_step_restart: bool = False
    human_gate_mode: str = "off"  # off | advisory | blocking
    enable_multimodal_review: bool = False
    max_review_figures: int = 6


class SandboxSettings(BaseModel):
    enabled: bool = True
    network_mode: str = "none"
    cpu_limit: float = 2.0
    memory_limit: str = "2g"
    execution_timeout: int = 300


class LiteratureSettings(BaseModel):
    max_results_per_search: int = 50
    enable_pdf_fetch: bool = True
    follow_budget_per_round: int = 3
    cited_by_budget_per_round: int = 2
    read_budget_per_round: int = 5
    max_read_chars: int = 8000


class KnowledgeSettings(BaseModel):
    enable_world_model: bool = True
    enable_evidence_graph: bool = False
    enable_hypothesis_tournament: bool = False
    # Pre-registration / falsifiability (Phase 1A)
    enable_preregistration: bool = False
    prereg_require_refutation: bool = True
    prereg_on_empty: str = "advisory"  # advisory | blocking


class JournalSettings(BaseModel):
    # Toggleable journal-ready LaTeX/PDF output (Phase 2 P2-LaTeX)
    enable_latex_output: bool = False
    latex_journal: str = "none"  # none | arxiv | neurips
    compile_pdf: bool = False


class MemorySettings(BaseModel):
    enabled: bool = True
    max_memories_per_prompt: int = 5


class CitationSettings(BaseModel):
    enable_citation_grounding: bool = False
    enable_novelty_check: bool = False
    enable_seed_discovery: bool = False
    drop_unresolved_citations: bool = False  # resolve-or-drop (Phase 2 P2-cite)


# --- Update models (all fields Optional for partial updates) ---


class OrchestratorSettingsUpdate(BaseModel):
    max_rounds_per_phase: int | None = None
    enable_checkpointing: bool | None = None
    enable_writing: bool | None = None
    max_review_iterations: int | None = None
    enable_peer_review: bool | None = None
    num_reviewers: int | None = None
    enable_experimentation: bool | None = None
    enable_debates: bool | None = None
    max_debate_exchanges: int | None = None
    enable_convergence_detection: bool | None = None
    convergence_confidence_threshold: float | None = None
    enable_execution_sprints: bool | None = None
    num_execution_sprints: int | None = None
    enable_verification: bool | None = None
    verification_tolerance: float | None = None
    abort_on_verification_failure: bool | None = None
    enable_robustness_loop: bool | None = None
    robustness_max_passes: int | None = None
    enable_replication_gate: bool | None = None
    replication_max_specs: int | None = None
    enable_best_first_nodes: bool | None = None
    enable_step_restart: bool | None = None
    human_gate_mode: str | None = None
    enable_multimodal_review: bool | None = None
    max_review_figures: int | None = None


class SandboxSettingsUpdate(BaseModel):
    enabled: bool | None = None
    network_mode: str | None = None
    cpu_limit: float | None = None
    memory_limit: str | None = None
    execution_timeout: int | None = None


class LiteratureSettingsUpdate(BaseModel):
    max_results_per_search: int | None = None
    enable_pdf_fetch: bool | None = None
    follow_budget_per_round: int | None = None
    cited_by_budget_per_round: int | None = None
    read_budget_per_round: int | None = None
    max_read_chars: int | None = None


class KnowledgeSettingsUpdate(BaseModel):
    enable_world_model: bool | None = None
    enable_evidence_graph: bool | None = None
    enable_hypothesis_tournament: bool | None = None
    enable_preregistration: bool | None = None
    prereg_require_refutation: bool | None = None
    prereg_on_empty: str | None = None


class JournalSettingsUpdate(BaseModel):
    enable_latex_output: bool | None = None
    latex_journal: str | None = None
    compile_pdf: bool | None = None


class MemorySettingsUpdate(BaseModel):
    enabled: bool | None = None
    max_memories_per_prompt: int | None = None


class CitationSettingsUpdate(BaseModel):
    enable_citation_grounding: bool | None = None
    enable_novelty_check: bool | None = None
    enable_seed_discovery: bool | None = None
    drop_unresolved_citations: bool | None = None


# --- Container ---


class AllSettings(BaseModel):
    orchestrator: OrchestratorSettings = Field(default_factory=OrchestratorSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    literature: LiteratureSettings = Field(default_factory=LiteratureSettings)
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    citation: CitationSettings = Field(default_factory=CitationSettings)
    journal: JournalSettings = Field(default_factory=JournalSettings)
