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


class MemorySettings(BaseModel):
    enabled: bool = True
    max_memories_per_prompt: int = 5


class CitationSettings(BaseModel):
    enable_citation_grounding: bool = False
    enable_novelty_check: bool = False
    enable_seed_discovery: bool = False


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


class MemorySettingsUpdate(BaseModel):
    enabled: bool | None = None
    max_memories_per_prompt: int | None = None


class CitationSettingsUpdate(BaseModel):
    enable_citation_grounding: bool | None = None
    enable_novelty_check: bool | None = None
    enable_seed_discovery: bool | None = None


# --- Container ---


class AllSettings(BaseModel):
    orchestrator: OrchestratorSettings = Field(default_factory=OrchestratorSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    literature: LiteratureSettings = Field(default_factory=LiteratureSettings)
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    citation: CitationSettings = Field(default_factory=CitationSettings)
