"""FastAPI server for the research dashboard (replay + live).

Serves the built React app from ``dashboard/dist`` and exposes the per-thread
event streams written by the orchestrator (``data/threads/<id>/events.jsonl``).

The thread list and metadata are derived purely from the event files — no
database coupling — so any finished (or copied-in) thread folder replays.

Launched via:
    paradigm dashboard [thread-id-or-path]      # replay mode
    paradigm run ... --dashboard                # live mode alongside a run
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
except ImportError as e:  # pragma: no cover - import guard
    raise ImportError(
        "The dashboard requires FastAPI and uvicorn. Install with: pip install 'paradigm[dashboard]'"
    ) from e

# Polling interval for the live SSE tail (no inotify dependency)
_STREAM_POLL_SECONDS = 0.5

# Artifact roots (relative to data_dir) the artifacts endpoint may serve from.
# Experiment outputs land in executions/ and workspaces/<thread>/; final paper
# figures in papers/<paper-id>/figures/.
_ARTIFACT_ROOTS = ("executions", "workspaces", "papers", "threads")


def _read_first_last(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """First and last parseable events of a stream (cheap thread metadata)."""
    first: dict[str, Any] | None = None
    last: dict[str, Any] | None = None
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if first is None:
                    first = event
                last = event
    except OSError:
        return None, None
    return first, last


def _thread_summary(thread_dir: Path) -> dict[str, Any] | None:
    events_file = thread_dir / "events.jsonl"
    if not events_file.is_file():
        return None
    first, last = _read_first_last(events_file)
    if first is None:
        return None
    prompt = ""
    if first.get("type") == "run.started":
        prompt = str(first.get("payload", {}).get("prompt", ""))
    status = "running"
    if last is not None and last.get("type") == "run.completed":
        status = str(last.get("payload", {}).get("status", "completed"))
    return {
        "id": thread_dir.name,
        "title": prompt.split("\n")[0][:160] or thread_dir.name,
        "status": status,
        "date": first.get("ts"),
        "n_events": (last or first).get("seq", 0),
    }


def _find_dist_dir() -> Path | None:
    """Locate the built frontend (dashboard/dist) relative to the repo or cwd."""
    candidates = [
        Path(__file__).resolve().parents[3] / "dashboard" / "dist",
        Path.cwd() / "dashboard" / "dist",
    ]
    for c in candidates:
        if (c / "index.html").is_file():
            return c
    return None


def create_app(data_dir: Path, threads_dir: Path | None = None) -> FastAPI:
    """Build the dashboard app rooted at a paradigm data directory."""
    data_dir = data_dir.resolve()
    threads_root = (threads_dir or data_dir / "threads").resolve()
    dist_dir = _find_dist_dir()

    app = FastAPI(title="Paradigm Dashboard", docs_url=None, redoc_url=None)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    @app.get("/api/threads")
    def list_threads() -> JSONResponse:
        threads = []
        if threads_root.is_dir():
            for child in sorted(threads_root.iterdir()):
                if child.is_dir():
                    summary = _thread_summary(child)
                    if summary:
                        threads.append(summary)
        threads.sort(key=lambda t: t.get("date") or "", reverse=True)
        return JSONResponse(threads)

    def _events_file(thread_id: str) -> Path:
        # Thread ids are flat folder names; reject anything path-like
        if "/" in thread_id or "\\" in thread_id or thread_id in (".", ".."):
            raise HTTPException(status_code=404, detail="Unknown thread")
        path = threads_root / thread_id / "events.jsonl"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Unknown thread")
        return path

    @app.get("/api/threads/{thread_id}/events")
    def get_events(thread_id: str) -> JSONResponse:
        path = _events_file(thread_id)
        events = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return JSONResponse(events)

    @app.get("/api/threads/{thread_id}/stream")
    async def stream_events(thread_id: str, request: Request) -> StreamingResponse:
        """SSE: send all existing events, then tail the file for new lines."""
        path = _events_file(thread_id)

        async def event_source():
            sent_done = False
            with path.open(encoding="utf-8") as f:
                while True:
                    if await request.is_disconnected():
                        return
                    line = f.readline()
                    if line:
                        line = line.strip()
                        if not line:
                            continue
                        yield f"data: {line}\n\n"
                        # A run.completed event ends the stream politely
                        if '"run.completed"' in line:
                            sent_done = True
                    else:
                        if sent_done:
                            yield "event: end\ndata: {}\n\n"
                            return
                        yield ": keepalive\n\n"
                        await asyncio.sleep(_STREAM_POLL_SECONDS)

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/threads/{thread_id}/artifacts/{artifact_path:path}")
    def get_artifact(thread_id: str, artifact_path: str) -> FileResponse:
        _events_file(thread_id)  # 404 unless the thread exists
        # Artifact paths are recorded relative to data_dir by the orchestrator.
        target = (data_dir / artifact_path).resolve()
        # Confinement: must stay inside data_dir AND under a known artifact root
        if not target.is_relative_to(data_dir):
            raise HTTPException(status_code=404, detail="Not found")
        rel_root = target.relative_to(data_dir).parts
        if not rel_root or rel_root[0] not in _ARTIFACT_ROOTS:
            raise HTTPException(status_code=404, detail="Not found")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return FileResponse(target, media_type=media_type)

    # ------------------------------------------------------------------
    # Static frontend
    # ------------------------------------------------------------------

    if dist_dir is not None:

        @app.get("/{spa_path:path}")
        def serve_app(spa_path: str) -> FileResponse:
            candidate = (dist_dir / spa_path).resolve() if spa_path else dist_dir / "index.html"
            if spa_path and candidate.is_relative_to(dist_dir) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist_dir / "index.html")
    else:

        @app.get("/")
        def no_frontend() -> JSONResponse:
            return JSONResponse(
                {
                    "error": "dashboard frontend not built",
                    "hint": "run: cd dashboard && npm install && npm run build",
                    "api": ["/api/threads", "/api/threads/{id}/events"],
                },
                status_code=503,
            )

    return app


def run_server(
    data_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8060,
    threads_dir: Path | None = None,
) -> None:
    """Blocking uvicorn server (CLI replay mode)."""
    import uvicorn

    app = create_app(data_dir, threads_dir=threads_dir)
    uvicorn.run(app, host=host, port=port, log_level="warning")


def start_server_in_background(
    data_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8060,
) -> Any:
    """Start uvicorn in a daemon thread (live mode alongside `paradigm run`).

    Returns the uvicorn Server object (callers may ignore it; the thread dies
    with the process).
    """
    import threading

    import uvicorn

    app = create_app(data_dir)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="paradigm-dashboard", daemon=True)
    thread.start()
    return server
