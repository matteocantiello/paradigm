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


class LiteratureConfig(BaseModel):
    """Configuration for literature search and retrieval."""

    arxiv_rate_limit: float = 3.0  # seconds between requests
    max_results_per_search: int = 50
    enable_pdf_fetch: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    follow_budget_per_round: int = 3
    cited_by_budget_per_round: int = 2
    read_budget_per_round: int = 5
    max_read_chars: int = 8000
    max_citation_results: int = 10
    max_reference_results: int = 20


class StorageConfig(BaseModel):
    """Configuration for data storage."""

    data_dir: Path = Field(default_factory=lambda: Path("./data"))
    db_path: Path | None = None
    vector_db_path: Path | None = None
    papers_dir: Path | None = None
    log_path: Path | None = None

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


class OrchestratorConfig(BaseModel):
    """Configuration for orchestrator behavior."""

    max_rounds_per_phase: int = 10
    enable_checkpointing: bool = True
    checkpoint_interval: int = 5  # rounds
    enable_writing: bool = True
    max_review_iterations: int = 5
    enable_peer_review: bool = True
    num_reviewers: int = 2
    max_revision_rounds: int = 4
    enable_experimentation: bool = True
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
    perplexity_api_key_env: str = "PERPLEXITY_API_KEY"
    citation_sections: list[str] = Field(default_factory=lambda: ["introduction", "methods"])
    max_retries_per_paragraph: int = 2
    perplexity_timeout: float = 120.0
    enable_novelty_check: bool = False
    novelty_mode: str = "semantic_scholar"  # or "futurehouse"
    futurehouse_api_key_env: str = "FUTURE_HOUSE_API_KEY"
    novelty_max_iterations: int = 5
    enable_seed_discovery: bool = False
    seed_discovery_max_papers: int = 10


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
    domain: str = "science"
    providers: dict[str, ProviderConfigEntry] = Field(default_factory=dict)
    testing_overrides: dict[str, AgentOverrideConfig] = Field(default_factory=dict)
    api_key: str | None = Field(default=None, validate_default=True)

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

    def apply_testing_overrides(self) -> None:
        """Merge testing_overrides into agent.overrides for testing mode."""
        for role, override in self.testing_overrides.items():
            self.agent.overrides[role] = override

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
