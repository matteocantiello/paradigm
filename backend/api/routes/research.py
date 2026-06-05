"""REST endpoints for research cycle CRUD."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.middleware.auth import verify_api_key
from backend.api.models.research import (
    CycleStatus,
    ResearchCycleCreate,
    ResearchCycleList,
    ResearchCycleResponse,
    ResumeRequest,
)

router = APIRouter(prefix="/api/v1/research", tags=["research"])

# In-memory store for research cycles (demo / core-unavailable fallback; the
# CycleStore shares this dict when there's no DB).
_cycles: dict[str, ResearchCycleResponse] = {}


def _json_list(raw: Any) -> list[str]:
    """Coerce a thread's JSON-encoded list field (or a real list) to list[str]."""
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            v = json.loads(raw)
            return [str(x) for x in v] if isinstance(v, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _build_continuation_note(
    database: Any, prior: ResearchCycleResponse, comment: str
) -> str:
    """Assemble the continuation context delivered to the resumed run as guidance.

    Built from the prior thread's checkpoint (hypothesis / findings / open
    questions / next steps / summary) plus the operator's steering comment, so
    the team picks up the established direction rather than starting cold.
    """
    phase = (prior.current_phase or "an earlier phase").replace("_", " ")
    parts = [
        f"You are CONTINUING prior research that stopped during the {phase} phase. "
        "Build on the established work below — do not restart from scratch."
    ]
    if database is not None and prior.thread_id:
        thread = database.get_thread(prior.thread_id)
        if thread:
            if thread.get("hypothesis"):
                parts.append(f"Established hypothesis: {thread['hypothesis']}")
            for label, key in (
                ("Key findings so far", "key_findings"),
                ("Open questions", "open_questions"),
                ("Planned next steps", "next_steps"),
            ):
                vals = _json_list(thread.get(key))
                if vals:
                    parts.append(f"{label}:\n" + "\n".join(f"- {v}" for v in vals[:8]))
            if thread.get("checkpoint_summary"):
                parts.append(f"Progress summary: {thread['checkpoint_summary']}")
    if comment.strip():
        parts.append(f"Operator steering for this continuation: {comment.strip()}")
    parts.append("Continue from here toward a complete, well-supported paper.")
    return "\n\n".join(parts)


def _enrich_cycle(cycle: ResearchCycleResponse, request: Request) -> ResearchCycleResponse:
    """Backfill live status / thread_id / paper_id onto an in-memory cycle.

    The cycle row is only written at creation/start, so without this it shows
    ``running`` forever and never learns its paper. We pull the real terminal
    status from the (retained) session state and the produced paper from the
    thread, so the research tab and the end-of-run "View Paper" action are
    correct. Best-effort: never let enrichment break the listing.
    """
    try:
        mgr = getattr(request.app.state, "session_manager", None)
        if mgr is not None and cycle.session_id:
            state = mgr.get_state(cycle.session_id)
            if state is not None:
                try:
                    cycle.status = CycleStatus(state.status.value)
                except ValueError:
                    pass  # e.g. "starting" has no CycleStatus — keep prior
                cycle.thread_id = state.thread_id or cycle.thread_id
                cycle.current_phase = state.current_phase or cycle.current_phase
        db = getattr(request.app.state, "database", None)
        if db is not None and cycle.thread_id:
            thread = db.get_thread(cycle.thread_id)
            if thread:
                if thread.get("current_draft_id"):
                    cycle.paper_id = thread["current_draft_id"]
                if not cycle.current_phase and thread.get("current_phase"):
                    cycle.current_phase = thread["current_phase"]
    except Exception:  # noqa: BLE001 — enrichment must never break the API
        pass
    return cycle


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
    request.app.state.cycle_store.create(cycle)
    return cycle


@router.post(
    "/{cycle_id}/resume",
    response_model=ResearchCycleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def resume_research_cycle(
    cycle_id: str,
    request: Request,
    body: ResumeRequest | None = None,
) -> ResearchCycleResponse:
    """Continue a cycle from its last checkpoint as a new run, with optional steering.

    Resume is *checkpoint-granularity*: the prior cycle's checkpoint plus the
    operator's comment are delivered to a fresh continuation run as first-round
    guidance (reusing the steering inbox), so the team builds on the established
    direction. A new cycle is created (linked via ``resumed_from``); the original
    is left untouched. Works for interrupted/failed/aborted *and* completed
    cycles (the latter = "extend this further").
    """
    store = request.app.state.cycle_store
    prior = store.get(cycle_id)
    if prior is None:
        raise HTTPException(status_code=404, detail="Research cycle not found")

    manager = request.app.state.session_manager
    database = getattr(request.app.state, "database", None)
    comment = (body.comment if body else None) or ""
    note = _build_continuation_note(database, prior, comment)

    new_id = f"cycle-{secrets.token_hex(16)}"
    new_cycle = ResearchCycleResponse(
        cycle_id=new_id,
        seed_prompt=prior.seed_prompt,
        mode=prior.mode,
        status=CycleStatus.PENDING,
        team_roles=prior.team_roles,
        resumed_from=cycle_id,
        created_at=datetime.now(timezone.utc),
    )
    store.create(new_cycle)

    state = await manager.create_session(
        cycle_id=new_id,
        seed_prompt=prior.seed_prompt,
        mode=prior.mode,
        team_roles=prior.team_roles,
    )
    # Queue the continuation context + steering BEFORE the engine starts, so it's
    # drained into the first agent round.
    await manager.queue_user_guidance(state.session_id, note)
    await manager.start_session(state.session_id)
    store.update(new_id, status=CycleStatus.RUNNING, session_id=state.session_id)

    return _enrich_cycle(store.get(new_id), request)


@router.get(
    "",
    response_model=ResearchCycleList,
    dependencies=[Depends(verify_api_key)],
)
async def list_research_cycles(
    request: Request,
    offset: int = 0,
    limit: int = 20,
) -> ResearchCycleList:
    """List research cycles with pagination."""
    all_cycles = request.app.state.cycle_store.list()
    page = [_enrich_cycle(c, request) for c in all_cycles[offset : offset + limit]]
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
async def get_research_cycle(cycle_id: str, request: Request) -> ResearchCycleResponse:
    """Get research cycle details."""
    cycle = request.app.state.cycle_store.get(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Research cycle not found")
    return _enrich_cycle(cycle, request)


@router.delete(
    "/{cycle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_api_key)],
)
async def delete_research_cycle(cycle_id: str, request: Request) -> None:
    """Cancel and delete a research cycle."""
    store = request.app.state.cycle_store
    if store.get(cycle_id) is None:
        raise HTTPException(status_code=404, detail="Research cycle not found")

    # Abort any running sessions for this cycle, then free their resources
    # (network clients, buffers, vector collection) — deletion means gone.
    manager = request.app.state.session_manager
    for session in manager.list_sessions(cycle_id=cycle_id):
        if session.status in ("starting", "running"):
            await manager.abort_session(session.session_id)
        await manager.cleanup_session(session.session_id)

    store.delete(cycle_id)
