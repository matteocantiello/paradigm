"""REST endpoints for agent configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.middleware.auth import verify_api_key
from backend.api.models.agents import (
    AgentConfigUpdate,
    AgentInfo,
    AgentList,
    AgentOverrideResponse,
)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# Default agent types available in Paradigm
_DEFAULT_AGENT_TYPES = [
    AgentInfo(
        agent_type="theorist",
        description="Develops theoretical frameworks and hypotheses",
    ),
    AgentInfo(
        agent_type="experimentalist",
        description="Designs and runs computational experiments",
    ),
    AgentInfo(
        agent_type="analyst",
        description="Analyzes data and interprets results",
    ),
    AgentInfo(
        agent_type="skeptic",
        description="Challenges assumptions and identifies weaknesses",
    ),
    AgentInfo(
        agent_type="synthesizer",
        description="Integrates ideas and builds consensus",
    ),
    AgentInfo(
        agent_type="writer",
        description="Drafts and revises the research paper",
    ),
    AgentInfo(
        agent_type="editor",
        description="Reviews and provides editorial feedback",
    ),
]


@router.get(
    "",
    response_model=AgentList,
    dependencies=[Depends(verify_api_key)],
)
async def list_agents(request: Request) -> AgentList:
    """List available agent types and their configurations."""
    config = request.app.state.config
    agents = list(_DEFAULT_AGENT_TYPES)

    # Populate model/provider info from config if available
    if config is not None:
        for agent in agents:
            override = config.agent.overrides.get(agent.agent_type)
            if override and override.model:
                agent.default_model = override.model
            else:
                agent.default_model = config.agent.default_model
            if override and override.provider:
                agent.default_provider = override.provider
            else:
                agent.default_provider = config.agent.default_provider

    return AgentList(items=agents, total=len(agents))


@router.get(
    "/{agent_type}",
    response_model=AgentOverrideResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_agent_config(agent_type: str, request: Request) -> AgentOverrideResponse:
    """Get current configuration for an agent type."""
    config = request.app.state.config
    if config is None:
        return AgentOverrideResponse(agent_type=agent_type)

    override = config.agent.overrides.get(agent_type)
    if override is None:
        return AgentOverrideResponse(agent_type=agent_type)

    return AgentOverrideResponse(
        agent_type=agent_type,
        provider=override.provider,
        model=override.model,
        max_tokens=override.max_tokens,
        token_budget=override.token_budget_per_agent,
        active=True,
    )


@router.put(
    "/{agent_type}",
    response_model=AgentOverrideResponse,
    dependencies=[Depends(verify_api_key)],
)
async def update_agent_config(
    agent_type: str,
    body: AgentConfigUpdate,
    request: Request,
) -> AgentOverrideResponse:
    """Update agent configuration (runtime override)."""
    config = request.app.state.config
    if config is None:
        raise HTTPException(status_code=503, detail="Configuration not available")

    # Validate agent_type exists
    known = {a.agent_type for a in _DEFAULT_AGENT_TYPES}
    if agent_type not in known:
        raise HTTPException(status_code=404, detail=f"Unknown agent type: {agent_type}")

    # Validate the provider is one the config actually knows about (the picker only
    # offers valid providers, but guard against a stale/typo'd selection).
    registry = getattr(config, "providers", None) or {}
    if body.provider and registry and body.provider not in registry:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{body.provider}'. Known: {', '.join(sorted(registry))}",
        )

    # Apply override
    from backend.api.config import AgentOverrideConfig

    current = config.agent.overrides.get(agent_type, AgentOverrideConfig())
    if body.model is not None:
        current.model = body.model
    if body.provider is not None:
        current.provider = body.provider
    if body.max_tokens is not None:
        current.max_tokens = body.max_tokens
    if body.token_budget is not None:
        current.token_budget_per_agent = body.token_budget
    config.agent.overrides[agent_type] = current

    return AgentOverrideResponse(
        agent_type=agent_type,
        provider=current.provider,
        model=current.model,
        max_tokens=current.max_tokens,
        token_budget=current.token_budget_per_agent,
        active=True,
    )
