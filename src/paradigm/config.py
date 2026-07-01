"""Configuration management for Paradigm."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

# Load .env file so ANTHROPIC_API_KEY is available via os.getenv
load_dotenv()


class AgentOverrideConfig(BaseModel):
    """Per-role provider and model override."""

    provider: str | None = None  # name from providers registry
    model: str | None = None
    max_tokens: int | None = None
    token_budget_per_agent: int | None = None
    extra_body: dict[str, Any] | None = None  # provider-specific extra params


class AgentConfig(BaseModel):
    """Configuration for agent behavior."""

    default_model: str = "claude-sonnet-4-5-20250929"
    opus_model: str = "claude-opus-4-6-20250514"
    max_tokens: int = 8192
    temperature: float = 1.0
    token_budget_per_thread: int = 1_000_000
    token_budget_per_agent: int = 100_000
    default_provider: str = "anthropic"
    overrides: dict[str, AgentOverrideConfig] = Field(default_factory=dict)


class SandboxConfig(BaseModel):
    """Configuration for code execution sandbox."""

    enabled: bool = True
    image_name: str = "paradigm-sandbox:latest"
    network_mode: str = "none"
    cpu_limit: float = 2.0  # CPU cores
    memory_limit: str = "2g"
    execution_timeout: int = 300  # seconds
    max_output_size: int = 10_485_760  # 10 MB
    # Extra isolation for shared/web deployments (safe defaults; the workspace
    # bind-mount stays writable even with read_only_rootfs).
    pids_limit: int = 256  # cap process count — fork-bomb guard
    drop_capabilities: bool = True  # cap_drop=ALL in the sandbox container
    no_new_privileges: bool = True  # block setuid privilege escalation
    read_only_rootfs: bool = False  # rootfs read-only (workspace stays rw)


class MCPLiteratureConfig(BaseModel):
    """Optional MCP literature provider (e.g. alphaXiv).

    Off by default and strictly *additive* — the platform stays offline-runnable
    on the in-house providers without it. When enabled, the orchestrator connects
    to a remote MCP server (streamable HTTP), discovers its tools, and exposes
    them behind the SourceProvider abstraction. alphaXiv's get_paper_content
    returns an LLM-optimized report (cheap to inject) instead of raw PDF text.
    alphaXiv is OAuth-gated (Clerk) — run ``paradigm mcp-login`` once; there is
    no static API key.
    """

    enabled: bool = False
    name: str = "alphaxiv"
    server_url: str = "https://api.alphaxiv.org/mcp/v1"
    transport: str = "http"  # streamable HTTP (sse/stdio reserved for later)
    # alphaXiv is OAuth-gated (Clerk) — no static API key. Run `paradigm mcp-login`
    # once; the token is cached + auto-refreshed for headless runs. Set "bearer"
    # (with auth_token_env) only for servers that issue a static token, "none" for
    # open servers (e.g. a local paper-search-mcp).
    auth_mode: str = "oauth"  # oauth | bearer | none
    # offline_access is required for a refresh token (headless auto-refresh);
    # without it the cached token expires and you'd have to re-run mcp-login.
    oauth_scope: str = "openid profile email offline_access"
    auth_token_env: str = "ALPHAXIV_API_KEY"  # used only when auth_mode == "bearer"
    search_tool: str | None = None  # override; otherwise auto-discovered
    content_tool: str | None = None
    # Effort for servers with a "difficulty"-style search arg (e.g. alphaXiv's
    # discover_papers, 1-10): higher = more retrieval rounds but slower.
    search_difficulty: int = 3
    timeout: float = 30.0
    max_results: int = 10
    source_type: str = "alphaxiv"


class LiteratureConfig(BaseModel):
    """Configuration for literature search and retrieval."""

    arxiv_rate_limit: float = 3.0  # seconds between requests
    max_results_per_search: int = 50
    enable_pdf_fetch: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    follow_budget_per_round: int = 3
    cited_by_budget_per_round: int = 2
    read_budget_per_round: int = 5
    chain_budget_per_round: int = 1  # multi-hop [CHAIN:] is expensive (depth x fan-out)
    max_read_chars: int = 8000
    max_citation_results: int = 10
    max_reference_results: int = 20
    # Semantic relevance filter on aggregated search results. Each result's
    # title+summary is scored (cosine) against the query; results below the
    # threshold are dropped so broad providers don't inject off-topic papers.
    # 0.0 disables filtering (pure re-rank). ~0.25 is a conservative cut.
    relevance_threshold: float = 0.25
    relevance_min_keep: int = 3  # never drop below this many (avoid starving)
    pubmed_rate_limit: float = 0.34  # ~3 req/sec (NCBI default without API key)
    biorxiv_rate_limit: float = 1.0  # 1 req/sec
    ads_rate_limit: float = 1.0  # 1 req/sec (~5000 req/day)
    mcp: MCPLiteratureConfig = Field(default_factory=MCPLiteratureConfig)


class StorageConfig(BaseModel):
    """Configuration for data storage."""

    data_dir: Path = Field(default_factory=lambda: Path("./data"))
    db_path: Path | None = None
    vector_db_path: Path | None = None
    papers_dir: Path | None = None
    log_path: Path | None = None
    threads_dir: Path | None = None

    @field_validator("data_dir", mode="before")
    @classmethod
    def resolve_data_dir(cls, v: Any) -> Path:
        """Resolve data directory path."""
        if isinstance(v, str):
            v = Path(v)
        return v.expanduser().resolve()

    def __init__(self, **data: Any) -> None:
        """Initialize storage config with derived paths."""
        super().__init__(**data)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.db_path is None:
            self.db_path = self.data_dir / "paradigm.db"
        if self.vector_db_path is None:
            self.vector_db_path = self.data_dir / "vector_db"
        if self.papers_dir is None:
            self.papers_dir = self.data_dir / "papers"
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        if self.log_path is None:
            self.log_path = self.data_dir / "events.jsonl"
        if self.threads_dir is None:
            # Per-thread research record (dashboard event streams). NOT the
            # sandbox-mounted workspaces dir — the sandbox must not see this.
            self.threads_dir = self.data_dir / "threads"


class OrchestratorConfig(BaseModel):
    """Configuration for orchestrator behavior."""

    max_rounds_per_phase: int = Field(default=10, gt=0)
    # Ping each agent's model before a run; swap any that don't respond to a healthy
    # fallback (so a dead/over-capacity provider can't cripple a role).
    model_preflight: bool = True
    enable_checkpointing: bool = True
    checkpoint_interval: int = Field(default=5, gt=0)  # rounds (must be >0: used in modulo)
    enable_writing: bool = True
    max_review_iterations: int = 5
    # Internal review may run this many iterations PAST max_review_iterations while
    # the editor's required-change count is STRICTLY falling (a converging paper),
    # bounded by max_review_iterations + this. Diverging/stalled papers stop early.
    review_convergence_extra: int = 3
    enable_peer_review: bool = True
    num_reviewers: int = 2
    max_revision_rounds: int = 4
    enable_experimentation: bool = True
    # When experiments were attempted but none produced usable output, abort the
    # cycle before WRITING instead of writing a paper the editor will reject.
    abort_on_execution_failure: bool = True
    enable_post_execution_discussion: bool = True
    max_experiment_rounds: int | None = None  # Default: 2 × max_rounds_per_phase
    max_searches_per_round: int = 3
    enable_debates: bool = True
    max_debate_exchanges: int = 3
    max_debates_per_phase: int = 2
    enable_convergence_detection: bool = True
    convergence_confidence_threshold: float = 0.70
    search_relevance_threshold: float = 0.15
    max_strategy_retries: int = 3
    enable_execution_advisory: bool = True
    execution_advisory_threshold: int = 3
    cross_round_failure_threshold: float = 0.6
    cross_round_min_experiments: int = 5
    enable_pre_execution_review: bool = False  # Opt-in (adds ~1K tokens/experiment)
    pre_execution_review_role: str = "analyst"  # Which role reviews code
    enable_conceptual_figures: bool = (
        True  # Generate matplotlib schematics when EXECUTION was skipped
    )
    max_conceptual_figures: int = 3  # Cap on figures per paper
    enable_execution_sprints: bool = False  # Off by default for backward compat
    num_execution_sprints: int = 3
    # Tree-search / step-restart (Phase 1C). All off by default.
    enable_step_restart: bool = False  # inject "resume from prior artifacts" retry guidance
    enable_best_first_nodes: bool = False  # prefer non-buggy experiments in within-round order
    debug_buggy_node_prob: float = 0.3  # chance a ready buggy node is promoted to be retried
    max_step_restarts_per_experiment: int = 2  # reserved for per-step resume budget
    # Verification kernel (Phase 1B): re-execution as ground truth. All off by default.
    enable_verification: bool = False
    verification_tolerance: float = 1e-6  # relative tolerance for reproducing RESULT[...] tokens
    verification_seed: int = 12345  # deterministic seed injected before re-execution
    verification_reexec_budget: int = 20  # cap on re-runs per cycle (cost control)
    abort_on_verification_failure: bool = True  # abort before WRITING if nothing reproduces
    # Figure-aware multimodal review (Phase 2 P2-VLM). Off by default.
    enable_multimodal_review: bool = False  # show the editor the actual figure images
    multimodal_review_role: str = "editor"  # role whose provider/model does the figure review
    max_review_figures: int = 6  # cap images sent to the vision model
    # Hybrid human-gate (Phase 1E). Autonomous by default; gates are opt-in.
    human_gate_mode: str = "off"  # off | advisory | blocking
    human_gate_points: list[str] = Field(
        default_factory=lambda: ["problem_selection", "pre_registration", "final_verification"]
    )
    sprint_review_roles: list[str] = Field(
        default_factory=lambda: ["theorist", "analyst", "skeptic"]
    )


class SkillsConfig(BaseModel):
    """Configuration for scientific skills integration."""

    skills_dir: Path = Field(
        default_factory=lambda: Path("vendor/claude-scientific-skills/scientific-skills")
    )
    default_mode: str = "default"  # "default", "all", "none"
    max_skill_chars: int | None = None  # Per-skill truncation limit


class MemoryConfig(BaseModel):
    """Configuration for agent episodic memory."""

    enabled: bool = True
    max_memories_per_prompt: int = 5
    recency_half_life_days: float = 30.0
    reflection_model: str = "claude-sonnet-4-5-20250929"
    collection_name: str = "agent_memories"
    max_memory_chars: int = 2000


class CitationConfig(BaseModel):
    """Configuration for citation grounding and novelty checking."""

    enable_citation_grounding: bool = False
    drop_unresolved_citations: bool = False  # drop refs that don't resolve (vs bare-URL)
    # Corpus-grounded citations (the OpenDraft-style invariant): inject the cycle's
    # discovered-paper set into the writer as a numbered [N] allow-list, tell it to cite
    # ONLY those [N] markers (never free-text "(Author, Year)" or its own References
    # section), and build the bibliography deterministically from that same set. Makes an
    # ungrounded inline citation structurally impossible. Off by default (opt-in / A/B);
    # when ON it OWNS citations and the Perplexity grounding path is skipped.
    corpus_grounded_citations: bool = False
    max_allowlist_papers: int = 40  # cap on the injected allow-list size (matches 15-40 refs)
    # Always-on safety net (independent of the flag above): strip fabricated inline
    # identifiers (arXiv ids / DOIs not in the cycle's corpus) from the assembled paper and
    # log unverifiable "(Author, Year)" cites. Pure robustness — leave ON; kill-switch only.
    strip_ungrounded_citations: bool = True
    perplexity_api_key_env: str = "PERPLEXITY_API_KEY"
    # Ground the whole body, not just intro+methods — results/discussion/conclusion
    # make substantive claims that need citing too (a big completeness win). Grounding
    # is concurrent under a wall-clock budget, so more sections cost little latency.
    citation_sections: list[str] = Field(
        default_factory=lambda: [
            "introduction",
            "methods",
            "results",
            "discussion",
            "conclusion",
        ]
    )
    max_retries_per_paragraph: int = 3
    perplexity_timeout: float = 120.0
    enable_novelty_check: bool = False
    novelty_mode: str = "semantic_scholar"  # or "futurehouse"
    futurehouse_api_key_env: str = "FUTURE_HOUSE_API_KEY"
    novelty_max_iterations: int = 5
    enable_seed_discovery: bool = False
    seed_discovery_max_papers: int = 10


class KnowledgeConfig(BaseModel):
    """Configuration for the knowledge architecture (world model, evidence graph, tournaments)."""

    enable_world_model: bool = True
    world_model_max_context_chars: int = 3000
    enable_evidence_graph: bool = False
    enable_hypothesis_tournament: bool = False
    tournament_population_size: int = 8
    tournament_winners: int = 2
    tournament_k_factor: float = 32.0
    # World-model ↔ tournament unification (C2). When True, the tournament ranks the
    # canonical world-model hypotheses (the [HYPOTHESIS:] tag set) by reference instead
    # of re-extracting a fresh ≤N set from the discussion, so Elo/status mutate the same
    # objects the rest of the world model references. Off by default (opt-in / A/B).
    unified_hypotheses: bool = False
    # Evidence-driven belief revision (C2 step 4, active only under unified_hypotheses):
    # a hypothesis flips status once its accumulated evidence crosses these thresholds.
    belief_support_min: int = 3  # min supporting evidence to mark SUPPORTED
    belief_contradict_min: int = 2  # min contradicting evidence to mark CONTRADICTED
    # Hypothesis de-dup matcher (active only under unified_hypotheses). "normalized"
    # = exact restatements only (cheap, default); "embedding" = cosine over sentence
    # embeddings to also fold paraphrases (the real ~53→~30 collapse).
    hypothesis_dedup: str = "normalized"  # "normalized" | "embedding"
    hypothesis_dedup_threshold: float = 0.85  # cosine threshold for "embedding"
    # Pre-registration / falsifiability (Phase 1A). Off by default.
    enable_preregistration: bool = False
    prereg_require_refutation: bool = True  # reject hypotheses lacking a refutation condition
    prereg_on_empty: str = "advisory"  # "advisory" (warn + continue) or "blocking" (abort)


class JournalConfig(BaseModel):
    """Configuration for paper output formats (Phase 2)."""

    # Toggle journal-ready LaTeX output (writes papers/<id>/<id>.tex). Off by default.
    enable_latex_output: bool = False
    latex_journal: str = "none"  # preset: none | arxiv | neurips
    compile_pdf: bool = False  # also build a PDF (requires a LaTeX engine on PATH)
    # Plain-language "Digest": a ~200-word layman summary generated from the finished
    # paper and written to papers/<id>/<id>-digest.md. On by default (one short call).
    enable_digest: bool = True


class NarrationConfig(BaseModel):
    """Plain-language event narration (Phase B)."""

    enabled: bool = True
    mode: str = "templated"  # "templated" (free) | "llm" (cheap model, opt-in)
    llm_model: str = "claude-haiku-4-5"  # used only when mode == "llm"
    llm_max_tokens: int = 60


class DisplayConfig(BaseModel):
    """Live-display / responsiveness options (Phase A+). Off by default."""

    # Stream agent tokens live to the GUI (token-by-token bubbles). The CLI/Rich
    # path is unaffected. Off by default; enable in the interactive profile.
    stream_tokens: bool = False
    # Optional coalescing: only flush a chunk once it has at least this many
    # characters buffered (0 = forward every provider delta). Tames chatty
    # providers / WebSocket back-pressure.
    stream_chunk_min_chars: int = 0
    # Pedagogical "why is this happening" narration on activity-timeline events.
    narration: NarrationConfig = Field(default_factory=NarrationConfig)


class ProviderConfigEntry(BaseModel):
    """Configuration for a single LLM provider in the registry."""

    type: str  # "anthropic" or "openai_compatible"
    api_key_env: str  # env var name, NOT the key itself
    base_url: str | None = None  # required for openai_compatible
    default_model: str | None = None


class Config(BaseModel):
    """Main configuration for Paradigm."""

    agent: AgentConfig = Field(default_factory=AgentConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    literature: LiteratureConfig = Field(default_factory=LiteratureConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    citation: CitationConfig = Field(default_factory=CitationConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    journal: JournalConfig = Field(default_factory=JournalConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    domain: str = "science"
    providers: dict[str, ProviderConfigEntry] = Field(default_factory=dict)
    testing_overrides: dict[str, AgentOverrideConfig] = Field(default_factory=dict)
    api_key: str | None = Field(default=None, validate_default=True)

    # Runtime state (not serialised by Pydantic)
    _testing_mode: bool = False
    _production_overrides: dict[str, AgentOverrideConfig] | None = None

    @field_validator("api_key", mode="before")
    @classmethod
    def get_api_key(cls, v: str | None) -> str:
        """Get API key from environment if not provided."""
        if v is None:
            v = os.getenv("ANTHROPIC_API_KEY")
        if not v:
            raise ValueError("ANTHROPIC_API_KEY must be set in environment or config file")
        return v

    @model_validator(mode="after")
    def _ensure_providers(self) -> Config:
        """Auto-create default anthropic provider if providers is empty."""
        if not self.providers:
            self.providers["anthropic"] = ProviderConfigEntry(
                type="anthropic",
                api_key_env="ANTHROPIC_API_KEY",
            )

        # Validate default_provider exists
        if self.agent.default_provider not in self.providers:
            raise ValueError(
                f"agent.default_provider '{self.agent.default_provider}' "
                f"not found in providers: {list(self.providers.keys())}"
            )

        # Validate override provider names exist
        for role, override in self.agent.overrides.items():
            if override.provider and override.provider not in self.providers:
                raise ValueError(
                    f"Override for role '{role}' references provider '{override.provider}' "
                    f"not found in providers: {list(self.providers.keys())}"
                )

        # Validate testing_overrides provider names exist
        for role, override in self.testing_overrides.items():
            if override.provider and override.provider not in self.providers:
                raise ValueError(
                    f"Testing override for role '{role}' references provider "
                    f"'{override.provider}' not found in providers: "
                    f"{list(self.providers.keys())}"
                )

        return self

    @property
    def is_testing_mode(self) -> bool:
        """Whether the config is currently using testing overrides."""
        return self._testing_mode

    def apply_testing_overrides(self) -> None:
        """Merge testing_overrides into agent.overrides for testing mode."""
        if self._testing_mode:
            return  # Already in testing mode
        # Backup current production overrides before replacing
        self._production_overrides = {
            role: override.model_copy() for role, override in self.agent.overrides.items()
        }
        for role, override in self.testing_overrides.items():
            self.agent.overrides[role] = override
        self._testing_mode = True

    def restore_production_overrides(self) -> None:
        """Restore original agent overrides, exiting testing mode."""
        if not self._testing_mode:
            return  # Already in production mode
        if self._production_overrides is not None:
            self.agent.overrides = self._production_overrides
            self._production_overrides = None
        else:
            # No backup — clear testing overrides by removing their keys
            for role in self.testing_overrides:
                self.agent.overrides.pop(role, None)
        self._testing_mode = False

    def get_domain_profile(self) -> Any:
        """Load and return the domain profile for this config's ``domain`` key.

        Returns:
            DomainProfile instance.

        Raises:
            ValueError: If the domain cannot be loaded.
        """
        from paradigm.domains.registry import get_domain

        return get_domain(self.domain)

    def get_provider(self, name: str | None = None) -> Any:
        """Get an instantiated LLMProvider by name.

        Args:
            name: Provider name from the registry. If None, uses agent.default_provider.

        Returns:
            LLMProvider instance.
        """
        from paradigm.agents.providers import ProviderConfig, create_provider

        if name is None:
            name = self.agent.default_provider

        entry = self.providers.get(name)
        if entry is None:
            raise ValueError(
                f"Provider '{name}' not found in providers: {list(self.providers.keys())}"
            )

        return create_provider(
            ProviderConfig(
                type=entry.type,
                api_key_env=entry.api_key_env,
                base_url=entry.base_url,
                default_model=entry.default_model,
            )
        )

    def get_provider_and_model_for_role(self, role: str) -> tuple[Any, str, dict[str, Any] | None]:
        """Resolve provider + model + extra_body for a given agent role.

        Override chain: role override → agent defaults → provider defaults.

        Args:
            role: Agent role name (e.g. "theorist", "skeptic").

        Returns:
            (LLMProvider, model_name, extra_body) tuple.
        """
        override = self.agent.overrides.get(role)

        # Determine provider name
        provider_name = self.agent.default_provider
        if override and override.provider:
            provider_name = override.provider

        provider = self.get_provider(provider_name)

        # Determine model: role override → provider default → agent default
        if override and override.model:
            model = override.model
        elif hasattr(provider, "default_model") and provider.default_model:
            model = provider.default_model
        else:
            model = self.agent.default_model

        # Determine extra_body from override
        extra_body = override.extra_body if override else None

        return provider, model, extra_body


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file with environment variable overrides.

    Args:
        config_path: Path to config YAML file. If None, uses PARADIGM_CONFIG env var
                    or defaults to configs/default.yaml

    Returns:
        Config object with loaded and validated configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    # Determine config file path
    if config_path is None:
        config_path = os.getenv("PARADIGM_CONFIG", "configs/default.yaml")

    config_path = Path(config_path)
    if not config_path.exists():
        # Try to create default config
        if config_path.name == "default.yaml":
            return Config()
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Load YAML
    config_dir = config_path.resolve().parent
    with open(config_path) as f:
        config_dict = yaml.safe_load(f) or {}

    # Resolve relative data_dir against the project root (config file's parent's parent)
    # e.g. configs/default.yaml -> project root is configs/..
    project_root = config_dir.parent
    storage = config_dict.get("storage", {})
    if "data_dir" in storage:
        data_path = Path(storage["data_dir"])
        if not data_path.is_absolute():
            storage["data_dir"] = str(project_root / data_path)
            config_dict["storage"] = storage

    # Also resolve skills_dir relative to project root
    skills = config_dict.get("skills", {})
    if "skills_dir" in skills:
        skills_path = Path(skills["skills_dir"])
        if not skills_path.is_absolute():
            skills["skills_dir"] = str(project_root / skills_path)
            config_dict["skills"] = skills

    # Override with environment variables
    if data_dir := os.getenv("PARADIGM_DATA_DIR"):
        config_dict.setdefault("storage", {})["data_dir"] = data_dir

    if log_level := os.getenv("PARADIGM_LOG_LEVEL"):
        config_dict["log_level"] = log_level

    return Config(**config_dict)
