"""Configuration management for Paradigm."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Load .env file so ANTHROPIC_API_KEY is available via os.getenv
load_dotenv()


class AgentConfig(BaseModel):
    """Configuration for agent behavior."""

    default_model: str = "claude-sonnet-4-5-20250929"
    opus_model: str = "claude-opus-4-6-20250514"
    max_tokens: int = 4096
    temperature: float = 1.0
    token_budget_per_thread: int = 1_000_000
    token_budget_per_agent: int = 100_000


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
    max_results_per_search: int = 20
    enable_pdf_fetch: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


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
    max_review_iterations: int = 1
    enable_peer_review: bool = True
    num_reviewers: int = 2
    max_revision_rounds: int = 2
    enable_experimentation: bool = True
    max_experiment_rounds: int = 3


class SkillsConfig(BaseModel):
    """Configuration for scientific skills integration."""

    skills_dir: Path = Field(
        default_factory=lambda: Path("vendor/claude-scientific-skills/scientific-skills")
    )
    default_mode: str = "default"  # "default", "all", "none"
    max_skill_chars: int | None = None  # Per-skill truncation limit


class Config(BaseModel):
    """Main configuration for Paradigm."""

    agent: AgentConfig = Field(default_factory=AgentConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    literature: LiteratureConfig = Field(default_factory=LiteratureConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
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
