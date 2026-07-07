"""REST endpoints for research cycle CRUD."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.middleware.auth import verify_api_key
from backend.api.models.research import (
    CycleStatus,
    ResearchCycleCreate,
    ResearchCycleList,
    ResearchCycleResponse,
    ResearchStats,
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


def _build_continuation_note(database: Any, prior: ResearchCycleResponse, comment: str) -> str:
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


def _thread_elapsed_seconds(thread: dict[str, Any]) -> int | None:
    """Wall-clock seconds from thread creation to its last update (≈ completion)."""
    created, updated = thread.get("created_at"), thread.get("updated_at")
    if not created or not updated:
        return None
    try:
        delta = datetime.fromisoformat(str(updated)) - datetime.fromisoformat(str(created))
    except ValueError:
        return None
    secs = int(delta.total_seconds())
    return secs if secs > 0 else None


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
                cycle.status_detail = getattr(state, "status_detail", None) or cycle.status_detail
        db = getattr(request.app.state, "database", None)
        if db is not None and cycle.thread_id:
            thread = db.get_thread(cycle.thread_id)
            if thread:
                if thread.get("current_draft_id"):
                    cycle.paper_id = thread["current_draft_id"]
                if not cycle.current_phase and thread.get("current_phase"):
                    cycle.current_phase = thread["current_phase"]
                raw_topics = thread.get("topics")
                if raw_topics:
                    cycle.topics = (
                        json.loads(raw_topics) if isinstance(raw_topics, str) else raw_topics
                    )
                cycle.elapsed_seconds = _thread_elapsed_seconds(thread)
            # Per-thread token total for the end-of-run summary (own try so a stats
            # hiccup doesn't drop the paper_id/topics enrichment above).
            try:
                usage = db.get_token_usage(thread_id=cycle.thread_id)
                cycle.total_tokens = usage.get("total_tokens") or None
            except Exception:  # noqa: BLE001
                pass
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
        interactive=body.interactive,
        created_at=now,
    )
    request.app.state.cycle_store.create(cycle)
    return cycle


# Dataset uploads: raw request body (no multipart dependency); the frontend
# sends fetch(url, {method: "POST", body: file}). Files land in a per-cycle
# holding dir and are STAGED into the sandbox shared data dir (with data-card
# schema previews) by the engine when the session starts.
_DATASET_ALLOWED_EXTS = frozenset(
    {".csv", ".tsv", ".txt", ".json", ".dat", ".fits", ".parquet", ".npy", ".npz", ".h5", ".hdf5"}
)
_DATASET_MAX_BYTES = 100 * 1024 * 1024
_DATASET_NAME_RE = re.compile(r"[^\w.\-]+")


@router.post(
    "/{cycle_id}/datasets",
    response_model=ResearchCycleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
async def upload_cycle_dataset(
    cycle_id: str,
    filename: str,
    request: Request,
) -> ResearchCycleResponse:
    """Attach a dataset file to a PENDING cycle (raw body upload).

    The file is held under data/uploads/<cycle_id>/ and staged into the
    sandbox-visible shared data dir when the session starts.
    """
    store = request.app.state.cycle_store
    cycle = store.get(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Research cycle not found")
    if cycle.status != CycleStatus.PENDING:
        raise HTTPException(
            status_code=409, detail="Datasets can only be attached before the session starts"
        )

    safe = _DATASET_NAME_RE.sub("_", Path(filename).name).strip("._")
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = Path(safe).suffix.lower()
    if ext not in _DATASET_ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported dataset type '{ext}'. Allowed: "
            + ", ".join(sorted(_DATASET_ALLOWED_EXTS)),
        )

    config = getattr(request.app.state, "config", None)
    data_dir = Path(getattr(getattr(config, "storage", None), "data_dir", "./data"))
    dest_dir = data_dir / "uploads" / cycle_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{Path(safe).stem}-{counter}{ext}"
        counter += 1

    # Stream to disk with a hard size cap (no full-file buffering in memory).
    written = 0
    try:
        with open(dest, "wb") as f:
            async for chunk in request.stream():
                written += len(chunk)
                if written > _DATASET_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Dataset too large (max {_DATASET_MAX_BYTES // (1024 * 1024)} MB)",
                    )
                f.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001 — surface as an HTTP error
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}") from e
    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Empty upload body")

    datasets = list(cycle.datasets or []) + [str(dest)]
    store.update(cycle_id, datasets=datasets)
    updated = store.get(cycle_id)
    assert updated is not None
    return updated


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
    if manager.at_capacity():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"At capacity ({manager.max_concurrent_sessions} concurrent runs). Try again shortly.",
        )
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
        interactive=prior.interactive,
        resumed_from=cycle_id,
        created_at=datetime.now(timezone.utc),
    )
    store.create(new_cycle)

    state = await manager.create_session(
        cycle_id=new_id,
        seed_prompt=prior.seed_prompt,
        mode=prior.mode,
        team_roles=prior.team_roles,
        datasets=prior.datasets,
        interactive=prior.interactive,
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
    "/stats",
    response_model=ResearchStats,
    dependencies=[Depends(verify_api_key)],
)
async def research_stats(request: Request) -> ResearchStats:
    """Headline counts for the dashboard overview (cycles run, papers, tokens).

    Declared BEFORE ``/{cycle_id}`` so "stats" isn't matched as a cycle id.
    """
    total_cycles = len(request.app.state.cycle_store.list())
    papers_published = 0
    total_tokens = 0
    db = getattr(request.app.state, "database", None)
    if db is not None:
        try:
            papers_published = len(db.list_papers(status="published", limit=100000))
        except Exception:  # noqa: BLE001 — stats must never 500 the dashboard
            pass
        try:
            total_tokens = db.get_token_usage().get("total_tokens", 0)
        except Exception:  # noqa: BLE001
            pass
    return ResearchStats(
        total_cycles=total_cycles,
        papers_published=papers_published,
        total_tokens=total_tokens,
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
