"""REST endpoints for research cycle CRUD."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.middleware.auth import verify_api_key
from backend.api.models.research import (
    CycleStatus,
    ResearchCycleCreate,
    ResearchCycleList,
    ResearchCycleResponse,
)

router = APIRouter(prefix="/api/v1/research", tags=["research"])

# In-memory store for research cycles (replaced by DB in production)
_cycles: dict[str, ResearchCycleResponse] = {}


@router.post(
    "",
    response_model=ResearchCycleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def create_research_cycle(
    body: ResearchCycleCreate,
    request: Request,
) -> ResearchCycleResponse:
    """Create a new research cycle."""
    cycle_id = f"cycle-{secrets.token_hex(16)}"
    now = datetime.now(timezone.utc)

    cycle = ResearchCycleResponse(
        cycle_id=cycle_id,
        seed_prompt=body.seed_prompt,
        mode=body.mode,
        status=CycleStatus.PENDING,
        team_roles=body.team_roles,
        created_at=now,
    )
    _cycles[cycle_id] = cycle
    return cycle


@router.get(
    "",
    response_model=ResearchCycleList,
    dependencies=[Depends(verify_api_key)],
)
async def list_research_cycles(
    offset: int = 0,
    limit: int = 20,
) -> ResearchCycleList:
    """List research cycles with pagination."""
    all_cycles = sorted(_cycles.values(), key=lambda c: c.created_at, reverse=True)
    page = all_cycles[offset : offset + limit]
    return ResearchCycleList(
        items=page,
        total=len(all_cycles),
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{cycle_id}",
    response_model=ResearchCycleResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_research_cycle(cycle_id: str) -> ResearchCycleResponse:
    """Get research cycle details."""
    cycle = _cycles.get(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Research cycle not found")
    return cycle


@router.delete(
    "/{cycle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_api_key)],
)
async def delete_research_cycle(cycle_id: str, request: Request) -> None:
    """Cancel and delete a research cycle."""
    cycle = _cycles.get(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Research cycle not found")

    # Abort any running sessions for this cycle, then free their resources
    # (network clients, buffers, vector collection) — deletion means gone.
    manager = request.app.state.session_manager
    for session in manager.list_sessions(cycle_id=cycle_id):
        if session.status in ("starting", "running"):
            await manager.abort_session(session.session_id)
        await manager.cleanup_session(session.session_id)

    del _cycles[cycle_id]
