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
