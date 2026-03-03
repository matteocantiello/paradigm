"""REST endpoints for session management."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.middleware.auth import verify_api_key
from backend.api.models.research import CycleStatus
from backend.api.models.session import (
    CheckpointList,
    CheckpointResponse,
    SessionCreate,
    SessionList,
    SessionResponse,
    SessionState,
)
from backend.api.routes.research import _cycles

router = APIRouter(tags=["sessions"])


@router.post(
    "/api/v1/research/{cycle_id}/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def start_session(
    cycle_id: str,
    body: SessionCreate | None = None,
    request: Request = None,  # type: ignore[assignment]
) -> SessionResponse:
    """Start a new session for a research cycle."""
    cycle = _cycles.get(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Research cycle not found")

    manager = request.app.state.session_manager

    # Create and start the session
    state = await manager.create_session(
        cycle_id=cycle_id,
        seed_prompt=cycle.seed_prompt,
        mode=cycle.mode,
        team_roles=cycle.team_roles,
    )
    await manager.start_session(state.session_id)

    # Update cycle status and link session
    cycle.status = CycleStatus.RUNNING
    cycle.session_id = state.session_id
    cycle.updated_at = datetime.now(timezone.utc)

    return SessionResponse(
        session_id=state.session_id,
        cycle_id=cycle_id,
        status=state.status,
        thread_id=state.thread_id,
        current_phase=state.current_phase,
        created_at=state.created_at,
    )


@router.get(
    "/api/v1/research/{cycle_id}/sessions",
    response_model=SessionList,
    dependencies=[Depends(verify_api_key)],
)
async def list_sessions(
    cycle_id: str,
    request: Request,
) -> SessionList:
    """List sessions for a research cycle."""
    if cycle_id not in _cycles:
        raise HTTPException(status_code=404, detail="Research cycle not found")

    manager = request.app.state.session_manager
    sessions = manager.list_sessions(cycle_id=cycle_id)

    items = [
        SessionResponse(
            session_id=s.session_id,
            cycle_id=s.cycle_id,
            status=s.status,
            thread_id=s.thread_id,
            current_phase=s.current_phase,
            created_at=s.created_at,
        )
        for s in sessions
    ]
    return SessionList(items=items, total=len(items))


@router.get(
    "/api/v1/sessions/{session_id}",
    response_model=SessionState,
    dependencies=[Depends(verify_api_key)],
)
async def get_session(session_id: str, request: Request) -> SessionState:
    """Get session state snapshot."""
    manager = request.app.state.session_manager
    state = manager.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


@router.get(
    "/api/v1/sessions/{session_id}/history",
    dependencies=[Depends(verify_api_key)],
)
async def get_session_history(
    session_id: str,
    limit: int = 100,
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Get full interaction history for a session."""
    manager = request.app.state.session_manager
    state = manager.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Read events from EventLogger filtered by thread_id
    event_logger = request.app.state.event_logger
    events = []
    if event_logger is not None and state.thread_id:
        raw_events = event_logger.read_events(thread_id=state.thread_id, limit=limit)
        events = [
            {
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "agent_id": e.agent_id,
                "phase": e.phase,
                "content": e.content,
            }
            for e in raw_events
        ]

    return {"session_id": session_id, "events": events, "total": len(events)}


@router.get(
    "/api/v1/sessions/{session_id}/checkpoints",
    response_model=CheckpointList,
    dependencies=[Depends(verify_api_key)],
)
async def list_checkpoints(session_id: str, request: Request) -> CheckpointList:
    """List checkpoints for a session."""
    manager = request.app.state.session_manager
    state = manager.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # For now, return empty (checkpoints are created during execution)
    return CheckpointList(items=[], total=0)


@router.get(
    "/api/v1/sessions/{session_id}/knowledge",
    dependencies=[Depends(verify_api_key)],
)
async def get_knowledge(session_id: str, request: Request) -> dict:
    """Get the latest knowledge architecture snapshot for a session."""
    manager = request.app.state.session_manager
    state = manager.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    snapshot = manager.get_knowledge_snapshot(session_id)
    if snapshot is None:
        return {"session_id": session_id, "knowledge": None}
    return {"session_id": session_id, "knowledge": snapshot.model_dump()}


@router.post(
    "/api/v1/sessions/{session_id}/checkpoints",
    response_model=CheckpointResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def create_checkpoint(session_id: str, request: Request) -> CheckpointResponse:
    """Manually trigger a checkpoint."""
    manager = request.app.state.session_manager
    state = manager.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    from backend.api.services.checkpoint import CheckpointService

    svc = CheckpointService(database=request.app.state.database)
    checkpoint = svc.add_checkpoint(
        session_id=session_id,
        phase=state.current_phase or "unknown",
        round_number=state.round_num,
    )
    return checkpoint


@router.post(
    "/api/v1/checkpoints/{checkpoint_id}/fork",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def fork_from_checkpoint(checkpoint_id: str, request: Request) -> dict:
    """Fork a new session from a checkpoint."""
    from backend.api.services.checkpoint import CheckpointService

    svc = CheckpointService(database=request.app.state.database)
    new_session_id = await svc.fork_from_checkpoint(checkpoint_id)
    return {"session_id": new_session_id, "forked_from": checkpoint_id}
