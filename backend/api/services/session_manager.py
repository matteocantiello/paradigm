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
        try:
            # Import here to avoid startup dependency
            # Create the WebSocket display adapter
            from backend.api.services.ws_display import WebSocketDisplayAdapter
            from paradigm.agents.factory import AgentFactory
            from paradigm.literature.corpus import Corpus
            from paradigm.orchestrator.engine import OrchestrationEngine

            display = WebSocketDisplayAdapter(session_id, self)

            # Create the intervention hook that bridges to WebSocket
            intervention_hook = self._make_intervention_hook(session_id)

            # Build the corpus with a session-specific ChromaDB collection
            # to isolate literature embeddings across research cycles.
            collection_name = f"paradigm_papers_{session_id}"
            corpus = Corpus(
                database=self._db,
                literature_config=self._config.literature,
                storage_config=self._config.storage,
                logger=self._event_logger,
                collection_name=collection_name,
            )

            # Load domain profile (needed for prompts_dir)
            domain_profile = self._config.get_domain_profile()

            # Build the agent factory with domain-specific prompts
            agent_factory = AgentFactory(
                self._config,
                prompts_dir=domain_profile.prompts_dir,
            )

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
            state.updated_at = datetime.now(timezone.utc)
            logger.info("Session %s cancelled", session_id)

        except Exception:
            state.status = SessionStatus.FAILED
            state.updated_at = datetime.now(timezone.utc)
            logger.exception("Session %s failed", session_id)
            await self._broadcast(
                session_id,
                ErrorMsg(
                    code="session_failed",
                    message="Session failed due to an internal error",
                    recoverable=False,
                ),
            )

        finally:
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

    def _make_intervention_hook(self, session_id: str):
        """Create a synchronous intervention hook that bridges to async WS approval.

        The existing engine calls intervention_hook(thread_id, from_phase, to_phase)
        synchronously. We use an asyncio.Event to block until the frontend responds.
        Since the engine runs in an async context, we schedule the approval request
        and wait on the event from the same event loop.
        """

        def hook(thread_id: str, from_phase: str, to_phase: str) -> str:
            # Get the running event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return "continue"

            # Create a future to bridge sync/async
            future = asyncio.run_coroutine_threadsafe(
                self._request_approval(session_id, thread_id, from_phase, to_phase),
                loop,
            )
            # Wait for the response (with timeout)
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

        # Broadcast approval request
        await self._broadcast(
            session_id,
            ApprovalRequestMsg(
                request_id=request_id,
                title=f"Phase transition: {from_phase} -> {to_phase}",
                description=f"Thread {thread_id} wants to transition from {from_phase} to {to_phase}.",
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

    async def pause_session(self, session_id: str) -> None:
        """Pause a running session."""
        state = self._sessions.get(session_id)
        if state is None:
            raise ValueError(f"Session not found: {session_id}")
        state.status = SessionStatus.PAUSED
        state.updated_at = datetime.now(timezone.utc)

    async def resume_session(self, session_id: str) -> None:
        """Resume a paused session."""
        state = self._sessions.get(session_id)
        if state is None:
            raise ValueError(f"Session not found: {session_id}")
        state.status = SessionStatus.RUNNING
        state.updated_at = datetime.now(timezone.utc)

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
        ):
            store.pop(session_id, None)

        # Drop the cycle-isolated ChromaDB collection (never reused across cycles).
        if self._config is not None:
            try:
                import chromadb

                client = chromadb.PersistentClient(
                    path=str(self._config.storage.vector_db_path)
                )
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
