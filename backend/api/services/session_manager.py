"""Core service managing running research sessions."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from backend.api.models.messages import (
    AgentOutputStreamMsg,
    ApprovalRequestMsg,
    ErrorMsg,
    KnowledgeUpdateMsg,
    NotificationMsg,
    SessionStateMsg,
)
from backend.api.models.session import SessionState, SessionStatus

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


def _summarize_failure(exc: BaseException, phase: str | None) -> str:
    """A short, user-facing reason for a failed cycle.

    The full traceback is logged separately; this is the one-line gist the
    research tab shows so an aborted run isn't a dead end. Keeps the exception
    type + its first line (bounded), prefixed with the phase it died in.
    """
    detail = str(exc).strip().splitlines()
    first = detail[0] if detail else exc.__class__.__name__
    msg = f"{exc.__class__.__name__}: {first}" if first else exc.__class__.__name__
    if len(msg) > 280:
        msg = msg[:277] + "…"
    where = f" during the {phase} phase" if phase else ""
    return f"The run hit an error{where} — {msg}"


class SessionManager:
    """Manages all running research sessions.

    Each session wraps an OrchestrationEngine.run_research_cycle() call
    running as an asyncio background task. The manager tracks state,
    routes interventions, and broadcasts WebSocket messages.
    """

    def __init__(
        self,
        config: Any | None = None,
        database: Any | None = None,
        event_logger: Any | None = None,
    ) -> None:
        self._config = config
        self._db = database
        self._event_logger = event_logger

        # In-memory state
        self._sessions: dict[str, SessionState] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._intervention_events: dict[str, asyncio.Event] = {}
        self._intervention_responses: dict[str, str] = {}
        self._ws_connections: dict[str, set[WebSocket]] = {}

        # Cycle metadata (seed_prompt, mode, team_roles)
        self._cycle_metadata: dict[str, dict[str, Any]] = {}
        self._session_start_times: dict[str, float] = {}

        # Knowledge snapshot cache (latest per session, for reconnect)
        self._knowledge_snapshots: dict[str, KnowledgeUpdateMsg] = {}

        # Message replay buffer: last N messages per session for reconnect catch-up
        self._message_buffers: dict[str, deque[str]] = {}
        # Per-session resume gate: set = running, cleared = paused. The engine
        # awaits this at round boundaries, making pause/resume actually pause.
        self._resume_events: dict[str, asyncio.Event] = {}
        # Per-session guidance inbox: free-text steering typed into the GUI,
        # drained by the engine at the next round boundary. Each entry is a
        # ready-to-inject line (target prefix already applied).
        self._guidance: dict[str, list[str]] = {}
        # Durable cycle store, injected at app startup (None in unit tests / when
        # core is unavailable). Used to persist the terminal cycle status.
        self.cycle_store: Any | None = None
        # Cap on simultaneously-running cycles — each run + its sandbox competes
        # for CPU/RAM and spends tokens, so a shared/web deployment must bound it.
        # Overridable via PARADIGM_MAX_CONCURRENT_SESSIONS at startup.
        self.max_concurrent_sessions: int = 4
        self._message_buffer_size = 200

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def create_session(
        self,
        cycle_id: str,
        seed_prompt: str,
        mode: str = "directed",
        team_roles: list[str] | None = None,
    ) -> SessionState:
        """Create a new session for a research cycle."""
        session_id = f"session-{secrets.token_hex(16)}"
        now = datetime.now(timezone.utc)

        state = SessionState(
            session_id=session_id,
            cycle_id=cycle_id,
            status=SessionStatus.STARTING,
            created_at=now,
        )
        self._sessions[session_id] = state
        self._ws_connections[session_id] = set()
        self._session_start_times[session_id] = time.monotonic()
        self._message_buffers[session_id] = deque(maxlen=self._message_buffer_size)

        # Store cycle metadata for starting the engine later
        self._cycle_metadata[session_id] = {
            "seed_prompt": seed_prompt,
            "mode": mode,
            "team_roles": team_roles,
        }

        return state

    def active_session_count(self) -> int:
        """Number of sessions currently starting or running."""
        return sum(
            1
            for s in self._sessions.values()
            if s.status in (SessionStatus.STARTING, SessionStatus.RUNNING)
        )

    def at_capacity(self) -> bool:
        """True when no more concurrent runs should be started right now."""
        return self.active_session_count() >= self.max_concurrent_sessions

    async def start_session(self, session_id: str) -> None:
        """Launch the research cycle as a background task."""
        state = self._sessions.get(session_id)
        if state is None:
            raise ValueError(f"Session not found: {session_id}")

        meta = self._cycle_metadata.get(session_id)
        if meta is None:
            raise ValueError(f"No cycle metadata for session: {session_id}")

        state.status = SessionStatus.RUNNING
        state.updated_at = datetime.now(timezone.utc)

        task = asyncio.create_task(
            self._run_cycle(session_id, meta),
            name=f"paradigm-session-{session_id}",
        )
        self._tasks[session_id] = task

    async def _run_cycle(self, session_id: str, meta: dict[str, Any]) -> None:
        """Run OrchestrationEngine.run_research_cycle() in a background task.

        Falls back to demo mode when the Paradigm core is not available.
        """
        state = self._sessions[session_id]

        # Check if Paradigm core is available
        if self._config is None or self._db is None or self._event_logger is None:
            logger.warning(
                "Paradigm core not initialized — running session %s in demo mode",
                session_id,
            )
            from backend.api.services.demo_runner import run_demo_cycle

            await run_demo_cycle(session_id, self)
            return

        corpus = None
        engine = None  # bound here so the finally can read engine.state.thread_id
        try:
            # Import here to avoid startup dependency
            # Create the WebSocket display adapter
            from backend.api.services.ws_display import WebSocketDisplayAdapter
            from paradigm.agents.factory import AgentFactory
            from paradigm.literature.corpus import Corpus
            from paradigm.literature.provider_factory import create_source_providers
            from paradigm.orchestrator.engine import OrchestrationEngine

            display = WebSocketDisplayAdapter(session_id, self)

            # Create the intervention hook that bridges to WebSocket
            # Only wire the blocking phase-transition approval gate for
            # interactive sessions (human_gate_mode == "blocking"). Otherwise an
            # unattended run would stall up to 5 min per transition waiting for
            # an approval that never comes.
            intervention_hook = (
                self._make_intervention_hook(session_id)
                if self._config.orchestrator.human_gate_mode == "blocking"
                else None
            )

            # Load the domain profile first — it declares which SourceProviders
            # to build (arXiv, semantic_scholar, alphaXiv MCP, …).
            domain_profile = self._config.get_domain_profile()

            # Build the corpus with a session-specific ChromaDB collection to
            # isolate literature embeddings across research cycles. Wire the
            # configured SourceProviders (same as the CLI) so the GUI uses the
            # domain-aware routing path — including the alphaXiv MCP provider and
            # the circuit-breaker-protected arXiv provider — instead of the
            # legacy direct-arXiv fallback (which ignores every provider and
            # hammers the rate-limited arXiv API).
            collection_name = f"paradigm_papers_{session_id}"
            source_providers = create_source_providers(
                provider_configs=domain_profile.source_providers,
                literature_config=self._config.literature,
                storage_config=self._config.storage,
                database=self._db,
                logger=self._event_logger,
                collection_name=collection_name,
            )
            corpus = Corpus(
                database=self._db,
                literature_config=self._config.literature,
                storage_config=self._config.storage,
                logger=self._event_logger,
                source_providers=source_providers or None,
                topic=meta["seed_prompt"],
                collection_name=collection_name,
            )

            # Build the agent factory with domain-specific prompts
            agent_factory = AgentFactory(
                self._config,
                prompts_dir=domain_profile.prompts_dir,
            )

            # Real pause gate: an Event the engine awaits at round boundaries.
            # Set = running; pause_session() clears it so the engine blocks.
            resume_event = asyncio.Event()
            resume_event.set()
            self._resume_events[session_id] = resume_event

            # Create engine with our WS-backed display and intervention hook
            engine = OrchestrationEngine(
                config=self._config,
                database=self._db,
                corpus=corpus,
                logger=self._event_logger,
                agent_factory=agent_factory,
                intervention_hook=intervention_hook,
                display=display,
                domain_profile=domain_profile,
                pause_gate=resume_event.wait,
                # Predicate the engine uses to checkpoint at the pause point (so a
                # paused cycle can be resumed later). `resume_event` is set while
                # running, cleared while paused.
                is_paused=lambda ev=resume_event: not ev.is_set(),
                guidance_provider=self._make_guidance_provider(session_id),
            )

            # Run the cycle
            thread_id = await engine.run_research_cycle(
                seed_prompt=meta["seed_prompt"],
                mode=meta["mode"],
                team_roles=meta.get("team_roles"),
            )

            state.thread_id = thread_id
            state.status = SessionStatus.COMPLETED
            state.updated_at = datetime.now(timezone.utc)

            # Notify connected clients
            await self._broadcast(
                session_id,
                NotificationMsg(
                    level="success",
                    category="lifecycle",
                    message=f"Research cycle completed. Thread: {thread_id}",
                ),
            )

        except asyncio.CancelledError:
            state.status = SessionStatus.ABORTED
            state.status_detail = (
                "Stopped before completion — usually because the run was stopped "
                "manually or the server restarted (e.g. a deploy). Your work up to "
                "the last checkpoint is saved; you can resume or retry."
            )
            state.updated_at = datetime.now(timezone.utc)
            logger.info("Session %s cancelled", session_id)

        except Exception as exc:
            state.status = SessionStatus.FAILED
            state.status_detail = _summarize_failure(exc, state.current_phase)
            state.updated_at = datetime.now(timezone.utc)
            logger.exception("Session %s failed", session_id)
            await self._broadcast(
                session_id,
                ErrorMsg(
                    code="session_failed",
                    # Surface the concrete reason so the UI isn't a dead end.
                    message=f"Session failed: {state.status_detail}",
                    recoverable=False,
                ),
            )

        finally:
            # Push the TERMINAL status (completed / aborted / failed) so the live
            # UI flips off "running" — otherwise a finished cycle looks stuck on
            # its last message (StatusPill: running -> stalled). This is a
            # structural message, so it's buffered and reconnecting clients see
            # the terminal state too. Without it, completion was silent.
            try:
                await self._broadcast_status(session_id)
            except Exception:
                logger.exception("Failed to broadcast terminal status for %s", session_id)
            # Persist the terminal status + thread + produced paper onto the
            # durable cycle row, so the research tab is correct after a restart
            # and the run stays resumable. thread_id is read from the engine's
            # own state (set during seeding), so it survives even a mid-run
            # failure such as a dropped connection — not just clean completion.
            store = getattr(self, "cycle_store", None)
            if store is not None:
                try:
                    thread_id = state.thread_id or getattr(
                        getattr(engine, "state", None), "thread_id", None
                    )
                    fields: dict[str, Any] = {"status": state.status.value}
                    if state.status_detail:
                        fields["status_detail"] = state.status_detail
                    if thread_id:
                        fields["thread_id"] = thread_id
                        if self._db is not None:
                            thread = self._db.get_thread(thread_id)
                            if thread and thread.get("current_draft_id"):
                                fields["paper_id"] = thread["current_draft_id"]
                    if state.current_phase:
                        fields["current_phase"] = state.current_phase
                    store.update(state.cycle_id, **fields)
                except Exception:
                    logger.exception("Failed to persist terminal cycle for %s", session_id)
            # Always release the cycle's network clients (httpx pools, wrapped
            # API clients) — otherwise each cycle leaks a connection pool.
            if corpus is not None:
                try:
                    await corpus.close()
                except Exception:
                    logger.exception("Failed to close corpus for session %s", session_id)
            # Drop the per-cycle metadata (only read once at cycle start). The
            # SessionState, start time, and knowledge snapshot are kept for
            # post-run status queries / reconnecting viewers.
            self._cycle_metadata.pop(session_id, None)
            self._resume_events.pop(session_id, None)
            self._guidance.pop(session_id, None)

    def _make_intervention_hook(self, session_id: str):
        """Create a synchronous intervention hook that bridges to async WS approval.

        The engine calls this hook off the event loop (via ``to_thread``, to avoid
        deadlock), so we capture the running loop HERE at creation time — calling
        ``get_running_loop()`` inside the hook would fail in the worker thread and
        silently skip the gate. The hook schedules the approval coroutine onto the
        captured loop and blocks the worker thread on the result.
        """
        loop = asyncio.get_running_loop()

        def hook(thread_id: str, from_phase: str, to_phase: str) -> str:
            future = asyncio.run_coroutine_threadsafe(
                self._request_approval(session_id, thread_id, from_phase, to_phase),
                loop,
            )
            try:
                return future.result(timeout=300)  # 5 min timeout
            except Exception:
                return "continue"

        return hook

    async def _request_approval(
        self,
        session_id: str,
        thread_id: str,
        from_phase: str,
        to_phase: str,
    ) -> str:
        """Send approval request via WebSocket and wait for response."""
        request_id = f"approval-{secrets.token_hex(8)}"
        event = asyncio.Event()
        self._intervention_events[request_id] = event

        # Enrich the prompt with live context (surviving hypotheses) so the
        # reviewer can make an informed call rather than a blind approve.
        description = f"The team finished {from_phase} and wants to move to {to_phase}."
        snapshot = self.get_knowledge_snapshot(session_id)
        if snapshot is not None and snapshot.hypotheses:
            alive = [h for h in snapshot.hypotheses if h.get("status") != "rejected"]
            if alive:
                top = max(alive, key=lambda h: h.get("elo_rating") or 0)
                stmt = str(top.get("statement", "")).strip()
                lead = f" Leading: “{stmt[:120]}”." if stmt else ""
                description += f" {len(alive)} hypotheses still in play.{lead}"

        # Broadcast approval request
        await self._broadcast(
            session_id,
            ApprovalRequestMsg(
                request_id=request_id,
                title=f"Approve transition: {from_phase} → {to_phase}",
                description=description,
                from_phase=from_phase,
                to_phase=to_phase,
            ),
        )

        # Wait for response (timeout after 5 minutes, default to continue)
        try:
            await asyncio.wait_for(event.wait(), timeout=300)
        except TimeoutError:
            self._intervention_responses[request_id] = "continue"

        response = self._intervention_responses.pop(request_id, "continue")
        self._intervention_events.pop(request_id, None)
        return response

    async def respond_to_approval(self, request_id: str, decision: str) -> None:
        """Process a frontend approval response."""
        if decision not in ("continue", "pause", "abort"):
            decision = "continue"
        self._intervention_responses[request_id] = decision
        event = self._intervention_events.get(request_id)
        if event is not None:
            event.set()

    async def _broadcast_status(self, session_id: str) -> None:
        """Push a fresh SessionStateMsg so the UI badge reflects a status change
        (pause/resume) even while the engine is blocked and emitting nothing."""
        state = self.get_state(session_id)
        if state is None:
            return
        await self._broadcast(
            session_id,
            SessionStateMsg(
                session_id=session_id,
                status=state.status.value,
                current_phase=state.current_phase,
                completed_phases=state.completed_phases,
                topics=state.topics,
                round_num=state.round_num,
                max_rounds=state.max_rounds,
                thread_id=state.thread_id,
                active_agents=state.active_agents,
                total_tokens=state.total_tokens,
                total_searches=state.total_searches,
                papers_found=state.papers_found,
                elapsed_seconds=state.elapsed_seconds,
            ),
        )

    async def pause_session(self, session_id: str) -> None:
        """Pause a running session — the engine blocks at the next round boundary."""
        state = self._sessions.get(session_id)
        if state is None:
            raise ValueError(f"Session not found: {session_id}")
        state.status = SessionStatus.PAUSED
        state.updated_at = datetime.now(timezone.utc)
        # Clear the gate so the engine awaits before its next round.
        event = self._resume_events.get(session_id)
        if event is not None:
            event.clear()
        await self._broadcast(
            session_id,
            NotificationMsg(
                level="warning",
                category="lifecycle",
                message="Paused — research will halt at the next round boundary.",
            ),
        )
        await self._broadcast_status(session_id)

    async def resume_session(self, session_id: str) -> None:
        """Resume a paused session — release the engine's round-boundary gate."""
        state = self._sessions.get(session_id)
        if state is None:
            raise ValueError(f"Session not found: {session_id}")
        state.status = SessionStatus.RUNNING
        state.updated_at = datetime.now(timezone.utc)
        event = self._resume_events.get(session_id)
        if event is not None:
            event.set()
        await self._broadcast(
            session_id,
            NotificationMsg(level="success", category="lifecycle", message="Resumed."),
        )
        await self._broadcast_status(session_id)

    async def queue_user_guidance(
        self, session_id: str, content: str, target_agent: str | None = None
    ) -> None:
        """Queue free-text human guidance for the running cycle.

        The engine drains this at the next round boundary and injects it into the
        agents' prompts, so typed steering actually reaches the research — unlike
        before, where ``user_message`` was dropped on the floor. We acknowledge
        receipt immediately so the operator knows it landed.
        """
        text = (content or "").strip()
        if not text:
            return
        line = f"(to {target_agent}) {text}" if target_agent else text
        self._guidance.setdefault(session_id, []).append(line)
        await self._broadcast(
            session_id,
            NotificationMsg(
                level="info",
                category="intervention",
                message="Guidance received — the agents will see it at the next round.",
            ),
        )

    def _make_guidance_provider(self, session_id: str):
        """Return an async callable the engine drains for queued guidance."""

        async def _provider() -> list[str]:
            pending = self._guidance.get(session_id)
            if not pending:
                return []
            self._guidance[session_id] = []
            return pending

        return _provider

    async def abort_session(self, session_id: str) -> None:
        """Cancel a running session."""
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()

        state = self._sessions.get(session_id)
        if state is not None:
            state.status = SessionStatus.ABORTED
            state.updated_at = datetime.now(timezone.utc)

    async def cleanup_session(self, session_id: str) -> None:
        """Fully evict a session's state and drop its per-cycle vector collection.

        Called when a research cycle is explicitly deleted. Frees the
        SessionState, message buffer, knowledge snapshot, timing/metadata, WS
        bookkeeping, and the cycle-isolated ChromaDB collection. Best-effort —
        never raises.
        """
        task = self._tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()

        for store in (
            self._sessions,
            self._message_buffers,
            self._knowledge_snapshots,
            self._session_start_times,
            self._cycle_metadata,
            self._ws_connections,
            self._resume_events,
        ):
            store.pop(session_id, None)

        # Drop the cycle-isolated ChromaDB collection (never reused across cycles).
        if self._config is not None:
            try:
                import chromadb

                client = chromadb.PersistentClient(path=str(self._config.storage.vector_db_path))
                client.delete_collection(f"paradigm_papers_{session_id}")
            except Exception:  # collection may not exist / chroma unavailable
                logger.debug("No vector collection to drop for session %s", session_id)

    async def shutdown(self) -> None:
        """Cancel all running sessions (called during app shutdown)."""
        for session_id in list(self._tasks.keys()):
            await self.abort_session(session_id)

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_state(self, session_id: str) -> SessionState | None:
        """Get current state snapshot for a session."""
        state = self._sessions.get(session_id)
        if state is not None:
            start = self._session_start_times.get(session_id)
            if start is not None:
                state.elapsed_seconds = round(time.monotonic() - start, 1)
        return state

    def list_sessions(self, cycle_id: str | None = None) -> list[SessionState]:
        """List all sessions, optionally filtered by cycle_id."""
        sessions = list(self._sessions.values())
        if cycle_id is not None:
            sessions = [s for s in sessions if s.cycle_id == cycle_id]
        return sessions

    # ------------------------------------------------------------------
    # Knowledge snapshot cache
    # ------------------------------------------------------------------

    def store_knowledge_snapshot(self, session_id: str, snapshot: KnowledgeUpdateMsg) -> None:
        """Cache the latest knowledge snapshot for reconnect."""
        self._knowledge_snapshots[session_id] = snapshot

    def get_knowledge_snapshot(self, session_id: str) -> KnowledgeUpdateMsg | None:
        """Return the cached knowledge snapshot, if any."""
        return self._knowledge_snapshots.get(session_id)

    # ------------------------------------------------------------------
    # WebSocket connection management
    # ------------------------------------------------------------------

    async def connect_ws(self, session_id: str, ws: WebSocket) -> None:
        """Register a WebSocket connection for a session."""
        if session_id not in self._ws_connections:
            self._ws_connections[session_id] = set()
        self._ws_connections[session_id].add(ws)

        # Send current state immediately
        state = self.get_state(session_id)
        if state is not None:
            await self._send_ws(
                ws,
                SessionStateMsg(
                    session_id=session_id,
                    status=state.status.value,
                    current_phase=state.current_phase,
                    round_num=state.round_num,
                    max_rounds=state.max_rounds,
                    thread_id=state.thread_id,
                    active_agents=state.active_agents,
                    total_tokens=state.total_tokens,
                    total_searches=state.total_searches,
                    papers_found=state.papers_found,
                    elapsed_seconds=state.elapsed_seconds,
                    completed_phases=state.completed_phases,
                ),
            )

        # Send cached knowledge snapshot (reconnect support)
        knowledge = self._knowledge_snapshots.get(session_id)
        if knowledge is not None:
            await self._send_ws(ws, knowledge)

        # Replay buffered messages so reconnecting clients catch up
        buf = self._message_buffers.get(session_id)
        if buf:
            for data in buf:
                try:
                    await ws.send_text(data)
                except Exception:
                    break

    async def disconnect_ws(self, session_id: str, ws: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        conns = self._ws_connections.get(session_id)
        if conns is not None:
            conns.discard(ws)

    async def _broadcast(self, session_id: str, msg: Any) -> None:
        """Broadcast a message to all connected WebSocket clients for a session."""
        conns = self._ws_connections.get(session_id, set())
        dead: list[WebSocket] = []
        data = msg.model_dump_json()

        # Buffer for replay on reconnect — but NOT mid-stream token chunks, which
        # would flood the bounded deque (evicting phase/knowledge history) and
        # replay a half-typed bubble. Only the final (full-content) stream
        # message is buffered; live chunks stay ephemeral.
        is_stream_chunk = isinstance(msg, AgentOutputStreamMsg) and not msg.is_final
        buf = self._message_buffers.get(session_id)
        if buf is not None and not is_stream_chunk:
            buf.append(data)

        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.discard(ws)

    async def _send_ws(self, ws: WebSocket, msg: Any) -> None:
        """Send a message to a single WebSocket client."""
        try:
            await ws.send_text(msg.model_dump_json())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Display adapter helpers (called by WebSocketDisplayAdapter)
    # ------------------------------------------------------------------

    def update_session_state(self, session_id: str, **kwargs: Any) -> None:
        """Update session state fields (called by the display adapter)."""
        state = self._sessions.get(session_id)
        if state is None:
            return
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        state.updated_at = datetime.now(timezone.utc)

    async def broadcast_message(self, session_id: str, msg: Any) -> None:
        """Public broadcast method for the display adapter."""
        await self._broadcast(session_id, msg)
