"""Lightweight config loader for the backend API.

Reads the YAML config directly without importing from ``paradigm`` (which
requires Python 3.11+).  Only the subset of config fields actually used by
the backend routes is modelled here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class AgentOverrideConfig(BaseModel):
    """Per-role provider and model override (mirrors paradigm.config.AgentOverrideConfig)."""

    provider: str | None = None
    model: str | None = None
    max_tokens: int | None = None
    token_budget_per_agent: int | None = None
    extra_body: dict[str, Any] | None = None


class AgentConfig(BaseModel):
    """Agent defaults used by the backend routes."""

    default_model: str = "claude-sonnet-4-5-20250929"
    default_provider: str = "anthropic"
    overrides: dict[str, AgentOverrideConfig] = Field(default_factory=dict)


class StorageConfig(BaseModel):
    """Storage paths derived from ``data_dir``."""

    data_dir: Path = Field(default_factory=lambda: Path("./data"))
    db_path: Path | None = None
    log_path: Path | None = None

    @field_validator("data_dir", mode="before")
    @classmethod
    def resolve_data_dir(cls, v: Any) -> Path:
        if isinstance(v, str):
            v = Path(v)
        return v.expanduser().resolve()

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.db_path is None:
            self.db_path = self.data_dir / "paradigm.db"
        if self.log_path is None:
            self.log_path = self.data_dir / "events.jsonl"


class BackendConfig(BaseModel):
    """Minimal config consumed by the backend API routes."""

    agent: AgentConfig = Field(default_factory=AgentConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    testing_overrides: dict[str, AgentOverrideConfig] = Field(default_factory=dict)

    # ---- runtime state (not serialised) ----
    _testing_mode: bool = False
    _production_overrides: dict[str, AgentOverrideConfig] | None = None

    @property
    def is_testing_mode(self) -> bool:
        return self._testing_mode

    def apply_testing_overrides(self) -> None:
        if self._testing_mode:
            return
        self._production_overrides = {
            role: override.model_copy() for role, override in self.agent.overrides.items()
        }
        for role, override in self.testing_overrides.items():
            self.agent.overrides[role] = override
        self._testing_mode = True

    def restore_production_overrides(self) -> None:
        if not self._testing_mode:
            return
        if self._production_overrides is not None:
            self.agent.overrides = self._production_overrides
            self._production_overrides = None
        else:
            for role in self.testing_overrides:
                self.agent.overrides.pop(role, None)
        self._testing_mode = False


def load_backend_config(config_path: str | Path | None = None) -> BackendConfig:
    """Load a :class:`BackendConfig` from the project YAML file.

    Resolution order for *config_path*:
    1. Explicit argument
    2. ``PARADIGM_CONFIG`` env var
    3. ``configs/default.yaml``
    """
    if config_path is None:
        config_path = os.getenv("PARADIGM_CONFIG", "configs/default.yaml")

    config_path = Path(config_path)
    if not config_path.exists():
        if config_path.name == "default.yaml":
            return BackendConfig()
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config_dir = config_path.resolve().parent
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    # Resolve relative data_dir against project root
    project_root = config_dir.parent
    storage = raw.get("storage", {})
    if "data_dir" in storage:
        data_path = Path(storage["data_dir"])
        if not data_path.is_absolute():
            storage["data_dir"] = str(project_root / data_path)
            raw["storage"] = storage

    # Env-var override
    if data_dir := os.getenv("PARADIGM_DATA_DIR"):
        raw.setdefault("storage", {})["data_dir"] = data_dir

    # Build with only the fields BackendConfig cares about
    return BackendConfig(
        agent=AgentConfig(**raw.get("agent", {})),
        storage=StorageConfig(**raw.get("storage", {})),
        testing_overrides={
            role: AgentOverrideConfig(**v) for role, v in raw.get("testing_overrides", {}).items()
        },
    )
