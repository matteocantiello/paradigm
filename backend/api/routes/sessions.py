"""REST endpoints for session management."""

from __future__ import annotations

import json
import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

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
    store = request.app.state.cycle_store
    cycle = store.get(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Research cycle not found")

    manager = request.app.state.session_manager
    if manager.at_capacity():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"At capacity ({manager.max_concurrent_sessions} concurrent runs). Try again shortly.",
        )

    # Create and start the session
    state = await manager.create_session(
        cycle_id=cycle_id,
        seed_prompt=cycle.seed_prompt,
        mode=cycle.mode,
        team_roles=cycle.team_roles,
        datasets=cycle.datasets,
        interactive=cycle.interactive,
        model_tier=cycle.model_tier,
    )
    await manager.start_session(state.session_id)

    # Update cycle status and link session (persisted so it survives a restart).
    store.update(cycle_id, status=CycleStatus.RUNNING, session_id=state.session_id)

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
    if request.app.state.cycle_store.get(cycle_id) is None:
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
    "/api/v1/sessions/{session_id}/event-stream",
    dependencies=[Depends(verify_api_key)],
)
async def get_session_event_stream(session_id: str, request: Request) -> dict:
    """Return the per-thread, seq-ordered dashboard event stream for this session.

    This is the durable record the orchestrator writes to
    ``data/threads/<thread_id>/events.jsonl`` — the source for the epistemic
    graphs (literature constellation, evidence, replay). Works for live sessions
    (thread id from the in-memory state) and finished ones (resolved via the
    cycle store, since the session may have been evicted).
    """
    manager = request.app.state.session_manager
    # Resolve through the manager so it works DURING a live run (the engine knows
    # its thread from seeding; SessionState.thread_id is only set on completion).
    thread_id = manager.resolve_thread_id(session_id)
    if not thread_id:
        return {"thread_id": None, "events": []}

    config = request.app.state.config
    path = config.storage.threads_dir / thread_id / "events.jsonl"
    events: list[dict] = []
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {"thread_id": thread_id, "events": events}


# Roots under data_dir that hold servable run artifacts (experiment figures live
# in executions/ and workspaces/<thread>/; final paper figures in papers/).
_ARTIFACT_ROOTS = ("executions", "workspaces", "papers", "threads")


@router.get(
    "/api/v1/sessions/{session_id}/artifacts/{artifact_path:path}",
    dependencies=[Depends(verify_api_key)],
)
async def get_session_artifact(
    session_id: str, artifact_path: str, request: Request
) -> FileResponse:
    """Serve a run artifact (e.g. an experiment figure) by its data-dir-relative path.

    The orchestrator records artifact paths relative to the data dir; this serves
    them so the dashboard can show real figures. Path is resolved and confined to
    data_dir AND a known artifact root, so it can't escape into arbitrary files.
    """
    data_dir = request.app.state.config.storage.data_dir.resolve()
    target = (data_dir / artifact_path).resolve()
    if not target.is_relative_to(data_dir):
        raise HTTPException(status_code=404, detail="Not found")
    parts = target.relative_to(data_dir).parts
    if not parts or parts[0] not in _ARTIFACT_ROOTS:
        raise HTTPException(status_code=404, detail="Not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)


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
