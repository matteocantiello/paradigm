"""Agent configuration schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    """Information about an agent type."""

    agent_type: str
    description: str = ""
    default_model: str = ""
    default_provider: str = ""


class AgentConfigUpdate(BaseModel):
    """Request body for updating agent configuration."""

    model: str | None = None
    provider: str | None = None
    max_tokens: int | None = None
    token_budget: int | None = None
    extra_body: dict[str, object] | None = None


class AgentList(BaseModel):
    """List of available agent types."""

    items: list[AgentInfo]
    total: int


class AgentOverrideResponse(BaseModel):
    """Current override configuration for an agent type."""

    agent_type: str
    provider: str | None = None
    model: str | None = None
    max_tokens: int | None = None
    token_budget: int | None = None
    extra_body: dict[str, object] | None = None
    active: bool = Field(default=False, description="Whether this override is currently active")


class ModelOption(BaseModel):
    """One selectable model in the catalog."""

    id: str
    label: str


class ProviderModels(BaseModel):
    """Available models for one configured provider."""

    name: str  # config provider name (the value stored in an override's `provider`)
    family: str  # anthropic | gemini | together | openai
    label: str  # display name (e.g. "TogetherAI")
    available: bool  # whether the provider's API key is set
    models: list[ModelOption] = Field(default_factory=list)
    source: str = "curated"  # "curated" | "live"
    error: str = ""  # set when a live refresh failed and we fell back to curated


class ModelCatalogResponse(BaseModel):
    """The model picker's options, grouped by provider."""

    providers: list[ProviderModels] = Field(default_factory=list)
