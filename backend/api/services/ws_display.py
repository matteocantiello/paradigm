"""WebSocket display adapter — bridges DisplayManager interface to WebSocket clients.

Implements the same interface as paradigm.display.DisplayManager so the
OrchestrationEngine doesn't know the difference. Each method call is
serialized into a WebSocket message and broadcast to connected clients.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from backend.api.models.messages import (
    ActivityEventMsg,
    AgentOutputStreamMsg,
    AgentStepCompleteMsg,
    DraftUpdateMsg,
    ExperimentUpdateMsg,
    KnowledgeUpdateMsg,
    LiteraturePaperMsg,
    LiteratureSearchMsg,
    LiteratureUpdateMsg,
    NotificationMsg,
    PhaseTransitionMsg,
    RoundUpdateMsg,
    SessionStateMsg,
    TopicsUpdateMsg,
)

if TYPE_CHECKING:
    from backend.api.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

# Strong references to in-flight broadcast tasks so they aren't garbage-collected
# mid-send (per the asyncio.create_task docs); discarded when each task finishes.
_pending_tasks: set[asyncio.Task[Any]] = set()


def _on_broadcast_done(task: asyncio.Task[Any]) -> None:
    _pending_tasks.discard(task)
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            # Routine during client disconnects — retrieve it so it isn't an
            # "exception was never retrieved" warning, and record at debug.
            logger.debug("WS broadcast task failed: %s", exc)


def _fire_and_forget(coro):
    """Schedule a coroutine from sync context without awaiting it.

    Tracks the task (so it isn't GC'd in flight) and logs any failure instead of
    leaving it unretrieved. If no event loop runs in the current thread, the
    coroutine is closed cleanly to avoid a "never awaited" warning.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        return
    task = loop.create_task(coro)
    _pending_tasks.add(task)
    task.add_done_callback(_on_broadcast_done)


class WebSocketDisplayAdapter:
    """DisplayManager-compatible adapter that broadcasts to WebSocket clients.

    Every method mirrors the DisplayManager interface, serializes the event
    into a WS message, and broadcasts it via the SessionManager.
    """

    def __init__(self, session_id: str, manager: SessionManager) -> None:
        self._session_id = session_id
        self._manager = manager
        # Live literature accumulator
        self._search_log: list[LiteratureSearchMsg] = []
        self._unique_papers: dict[str, LiteraturePaperMsg] = {}  # keyed by arxiv_id
        # Capture the running loop so token-stream chunks (which arrive from a
        # worker thread via asyncio.to_thread) can be scheduled back safely.
        try:
            self._loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        # Activity timeline (Phase B): monotonically increasing event ids + a
        # registry of start times so paired events can report a duration.
        self._activity_seq = 0
        self._timers: dict[str, float] = {}
        # Pacing: rolling per-turn durations + when the current phase started.
        self._turn_starts: dict[str, float] = {}
        self._step_durations: deque[float] = deque(maxlen=20)
        self._phase_started_at: float | None = None

    def _activity(
        self,
        category: str,
        title: str,
        *,
        phase: str = "",
        agent_id: str = "",
        severity: str = "info",
        detail: str = "",
        duration_ms: int | None = None,
        **ctx: Any,
    ) -> None:
        """Emit a structured, persistent timeline event (with narration)."""
        self._activity_seq += 1
        narration = self._narration_for(
            category, phase=phase, agent_id=agent_id, title=title, **ctx
        )
        self._schedule(
            self._manager.broadcast_message(
                self._session_id,
                ActivityEventMsg(
                    event_id=f"act-{self._session_id[:8]}-{self._activity_seq}",
                    category=category,
                    phase=phase,
                    agent_id=agent_id,
                    severity=severity,
                    title=title,
                    detail=detail,
                    narration=narration,
                    duration_ms=duration_ms,
                ),
            )
        )

    def _narration_for(self, category: str, **ctx: Any) -> str:
        """Templated (or, later, LLM) narration honoring the config flags."""
        cfg = getattr(getattr(self._manager, "_config", None), "display", None)
        ncfg = getattr(cfg, "narration", None)
        if ncfg is not None and not ncfg.enabled:
            return ""
        from paradigm.display.narration import narrate

        return narrate(category, **ctx)

    def _elapsed_ms(self, key: str) -> int | None:
        """Pop a previously-started timer and return its elapsed ms (or None)."""
        start = self._timers.pop(key, None)
        if start is None:
            return None
        return int((time.monotonic() - start) * 1000)

    def _current_phase(self) -> str:
        state = self._manager.get_state(self._session_id)
        return state.current_phase if state and state.current_phase else ""

    def _schedule(self, coro: Any) -> None:
        """Schedule a broadcast coroutine on the captured loop, thread-safely.

        Works whether called from the loop thread or a worker thread (unlike
        ``_fire_and_forget``, which silently drops when no loop is running in
        the *current* thread).
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            _fire_and_forget(coro)  # best effort if we never captured a loop
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            pass

    def _notify(
        self,
        message: str,
        *,
        level: str = "info",
        category: str = "",
        **metadata: Any,
    ) -> None:
        """Send a notification message."""
        _fire_and_forget(
            self._manager.broadcast_message(
                self._session_id,
                NotificationMsg(
                    level=level,
                    category=category,
                    message=message,
                    metadata=metadata,
                ),
            )
        )

    def _broadcast_state(self) -> None:
        """Broadcast full state sync."""
        state = self._manager.get_state(self._session_id)
        if state is None:
            return
        avg_step_ms = (
            sum(self._step_durations) / len(self._step_durations) * 1000.0
            if self._step_durations
            else 0.0
        )
        phase_elapsed = (
            time.monotonic() - self._phase_started_at if self._phase_started_at is not None else 0.0
        )
        _fire_and_forget(
            self._manager.broadcast_message(
                self._session_id,
                SessionStateMsg(
                    session_id=self._session_id,
                    status=state.status.value,
                    current_phase=state.current_phase,
                    # Must echo completed_phases: the frontend store overwrites its
                    # phase tracker from every state sync, so omitting this wipes the
                    # completed-phase list between transitions in the real engine path.
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
                    avg_step_ms=avg_step_ms,
                    phase_elapsed_seconds=phase_elapsed,
                ),
            )
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """No-op for WS adapter (connection is managed elsewhere)."""

    def stop(self) -> None:
        """No-op for WS adapter."""

    @property
    def state(self):
        """Return a minimal state-like object for compatibility."""
        return self

    # Attributes that engine accesses on display.state
    thread_id: str = ""
    paper_id: str = ""
    paper_path: str = ""
    outcome: str = ""

    # ------------------------------------------------------------------
    # Phase transitions
    # ------------------------------------------------------------------

    def phase_transition(
        self,
        phase_name: str | object,
        *,
        max_rounds: int | None = None,
        active_agents: int | None = None,
        total_agents: int | None = None,
    ) -> None:
        phase_str = str(phase_name) if not isinstance(phase_name, str) else phase_name
        phase_str = phase_str.lower()

        # Track the previous phase for completed_phases
        state = self._manager.get_state(self._session_id)
        from_phase = state.current_phase if state else None

        updates: dict[str, Any] = {"current_phase": phase_str}
        if max_rounds is not None:
            updates["max_rounds"] = max_rounds
        if from_phase and state:
            updates["completed_phases"] = [*state.completed_phases, from_phase]
        self._manager.update_session_state(self._session_id, **updates)

        _fire_and_forget(
            self._manager.broadcast_message(
                self._session_id,
                PhaseTransitionMsg(
                    from_phase=from_phase,
                    to_phase=phase_str,
                    max_rounds=max_rounds,
                    active_agents=active_agents,
                    total_agents=total_agents,
                ),
            )
        )
        # Timeline event, annotated with how long the phase we just left took.
        prev_ms = self._elapsed_ms("phase")
        self._timers["phase"] = time.monotonic()
        self._phase_started_at = time.monotonic()
        self._activity(
            "phase_transition",
            f"Phase: {phase_str.replace('_', ' ')}",
            phase=phase_str,
            duration_ms=prev_ms,
            to_phase=phase_str,
            from_phase=from_phase or "",
        )

    def topics_assigned(
        self, topics: list[str], *, stage: str = "final", agent_id: str = ""
    ) -> None:
        topics = list(topics)
        self._manager.update_session_state(self._session_id, topics=topics)
        _fire_and_forget(
            self._manager.broadcast_message(
                self._session_id,
                TopicsUpdateMsg(topics=topics, stage=stage),
            )
        )
        self._activity(
            "topics_assigned",
            f"Topics: {', '.join(topics)}",
            agent_id=agent_id,
            stage=stage,
            topics=topics,
        )

    def model_preflight(self, checked: int, swaps: list[tuple[str, str, str, str]]) -> None:
        if swaps:
            details = "; ".join(
                (
                    f"{role}: {old} → {new} ({reason})"
                    if new
                    else f"{role}: {old} unreachable, no fallback ({reason})"
                )
                for role, old, new, reason in swaps
            )
            self._notify(
                f"Model check: swapped unreachable model(s) — {details}",
                level="warning",
                category="info",
            )
            self._activity(
                "model_preflight",
                f"Model check: {len(swaps)} model(s) swapped",
                severity="warning",
                detail=details,
            )
        else:
            self._activity(
                "model_preflight",
                f"Model check: {checked} model(s) responsive",
                severity="success",
            )

    def phase_aborted(self) -> None:
        self._notify(
            "Research cycle aborted by intervention hook.", level="error", category="phase"
        )

    def phase_paused(self) -> None:
        self._notify(
            "Research cycle paused by intervention hook.", level="warning", category="phase"
        )

    # ------------------------------------------------------------------
    # Rounds
    # ------------------------------------------------------------------

    def round_start(self, round_num: int, max_rounds: int) -> None:
        self._manager.update_session_state(
            self._session_id, round_num=round_num, max_rounds=max_rounds
        )
        _fire_and_forget(
            self._manager.broadcast_message(
                self._session_id,
                RoundUpdateMsg(round_num=round_num, max_rounds=max_rounds),
            )
        )
        self._broadcast_state()
        self._activity(
            "round_start",
            f"Round {round_num} of {max_rounds}",
            phase=self._current_phase(),
            round_num=round_num,
            max_rounds=max_rounds,
        )

    # ------------------------------------------------------------------
    # Convergence
    # ------------------------------------------------------------------

    def convergence_detected(self, phase: str, round_num: int, max_rounds: int) -> None:
        self._notify(
            f"Agents converged in {phase} after round {round_num}, "
            f"skipping {max_rounds - round_num} round(s)",
            category="convergence",
        )
        self._activity(
            "convergence_detected",
            f"Converged after round {round_num}",
            phase=phase,
            severity="success",
            detail=f"Skipping {max_rounds - round_num} remaining round(s).",
        )

    # ------------------------------------------------------------------
    # Agent activity
    # ------------------------------------------------------------------

    def agent_stream_start(
        self, agent_id: str, stream_id: str, *, role: str = "", phase: str = ""
    ) -> None:
        """A turn began — open an (empty) live bubble so the UI shows 'thinking'."""
        if stream_id:
            self._turn_starts[stream_id] = time.monotonic()
        self._schedule(
            self._manager.broadcast_message(
                self._session_id,
                AgentOutputStreamMsg(
                    agent_id=agent_id,
                    role=role,
                    content="",
                    phase=phase,
                    stream_id=stream_id,
                    is_final=False,
                ),
            )
        )

    def agent_stream_chunk(
        self, agent_id: str, stream_id: str, chunk: str, *, role: str = "", phase: str = ""
    ) -> None:
        """A token delta — append to the live bubble keyed by stream_id."""
        self._schedule(
            self._manager.broadcast_message(
                self._session_id,
                AgentOutputStreamMsg(
                    agent_id=agent_id,
                    role=role,
                    content=chunk,
                    phase=phase,
                    stream_id=stream_id,
                    is_final=False,
                ),
            )
        )

    def agent_response(
        self,
        agent_id: str,
        total_tokens: int,
        *,
        role: str = "",
        model: str = "",
        content: str = "",
        stream_id: str = "",
    ) -> None:
        # Record the turn duration for rolling-average pacing/ETA.
        start = self._turn_starts.pop(stream_id, None) if stream_id else None
        if start is not None:
            self._step_durations.append(time.monotonic() - start)

        state = self._manager.get_state(self._session_id)
        if state is not None:
            new_total = state.total_tokens + total_tokens
            active = dict(state.active_agents)
            active[agent_id] = f"{total_tokens} tokens"
            self._manager.update_session_state(
                self._session_id, total_tokens=new_total, active_agents=active
            )

        # Final message carries the FULL content (no truncation) + stream_id so
        # the client finalizes the accumulated bubble (or reconstructs it on
        # reconnect, since only finals are buffered for replay).
        self._schedule(
            self._manager.broadcast_message(
                self._session_id,
                AgentOutputStreamMsg(
                    agent_id=agent_id,
                    role=role,
                    content=content or "",
                    tokens=total_tokens,
                    model=model,
                    stream_id=stream_id,
                    is_final=True,
                ),
            )
        )
        self._broadcast_state()

    def agent_step_complete(
        self,
        agent_id: str,
        *,
        role: str = "",
        summary: str = "",
        phase: str = "",
        tokens: int = 0,
        next_agent: str | None = None,
    ) -> None:
        """A turn finished — a structured step marker for the activity timeline."""
        self._schedule(
            self._manager.broadcast_message(
                self._session_id,
                AgentStepCompleteMsg(
                    agent_id=agent_id,
                    role=role,
                    summary=summary,
                    phase=phase,
                    tokens=tokens,
                    next_agent=next_agent,
                ),
            )
        )

    def agent_error(self, agent_id: str, error: str | Exception) -> None:
        self._notify(f"{agent_id} failed: {error}", level="error", category="agent")

    # ------------------------------------------------------------------
    # Literature / search
    # ------------------------------------------------------------------

    def search_result(
        self,
        agent_id: str,
        query: str,
        total_results: int,
        new_results: int,
        *,
        papers: list[dict[str, object]] | None = None,
        phase: str = "",
    ) -> None:
        state = self._manager.get_state(self._session_id)
        if state is not None:
            self._manager.update_session_state(
                self._session_id,
                total_searches=state.total_searches + 1,
                papers_found=state.papers_found + new_results,
            )
        self._notify(
            f"{agent_id}: '{query[:40]}' -> {new_results} new papers",
            category="search",
        )
        # Accumulate literature and broadcast live update
        if papers:
            self._accumulate_literature(query, agent_id, phase, papers)
        self._broadcast_state()

    def search_skipped(self, query: str, *, reason: str = "similar") -> None:
        self._notify(f"Skipped {reason} query", category="search", level="info")

    def search_budget_exhausted(self, budget: int, query: str) -> None:
        self._notify("Search budget exhausted", category="search", level="warning")

    def search_agent_cap(self, agent_id: str, cap: int, query: str) -> None:
        self._notify(
            f"{agent_id}: per-agent search cap reached", category="search", level="warning"
        )

    def search_error(self, query: str, error: str | Exception) -> None:
        self._notify(f"Search failed: {query[:40]}", category="search", level="error")

    def source_degraded(self, source: str) -> None:
        """Calm, deduped notice that an external literature source is throttled.

        Sent once per source per cycle instead of a red error per failed
        request — the run proceeds on cached corpus + the other sources.
        """
        self._notify(
            f"{source} rate-limited — using cached corpus + other sources",
            category="search",
            level="warning",
        )

    # ------------------------------------------------------------------
    # Phase C live artifacts — draft + experiments
    # ------------------------------------------------------------------

    def draft_section(
        self, section: str, title: str, content: str, author: str, status: str
    ) -> None:
        """Stream a paper section as it's drafted (draft-as-it-writes)."""
        self._schedule(
            self._manager.broadcast_message(
                self._session_id,
                DraftUpdateMsg(
                    section=section,
                    title=title,
                    content=content,
                    author=author,
                    status=status,
                    char_count=len(content),
                    phase=self._current_phase(),
                ),
            )
        )

    def experiment_update(
        self,
        experiment_id: str,
        name: str,
        agent_id: str,
        status: str,
        *,
        code: str = "",
        stdout: str = "",
        results: dict[str, float] | None = None,
        has_figures: bool = False,
        figures: list[str] | None = None,
    ) -> None:
        """Stream a sandbox experiment's code/stdout/RESULT values live."""
        self._schedule(
            self._manager.broadcast_message(
                self._session_id,
                ExperimentUpdateMsg(
                    experiment_id=experiment_id,
                    name=name,
                    agent_id=agent_id,
                    code=code,
                    stdout=stdout,
                    status=status,
                    results=results or {},
                    has_figures=has_figures,
                    figures=figures or [],
                    phase=self._current_phase(),
                ),
            )
        )

    def search_stale(self, agent_id: str, count: int = 2) -> None:
        self._notify(f"{agent_id}: stale searches", category="search", level="warning")

    def follow_result(self, agent_id: str, arxiv_id: str, count: int) -> None:
        state = self._manager.get_state(self._session_id)
        if state is not None:
            self._manager.update_session_state(
                self._session_id, papers_found=state.papers_found + count
            )
        self._notify(f"{agent_id} followed {arxiv_id} -> {count}", category="search")
        self._broadcast_state()

    def follow_budget_exhausted(self, arxiv_id: str) -> None:
        pass

    def follow_skipped(self, arxiv_id: str) -> None:
        pass

    def follow_error(self, arxiv_id: str, error: str | Exception) -> None:
        self._notify(f"Follow failed: {arxiv_id}", category="search", level="error")

    def cited_by_result(self, agent_id: str, arxiv_id: str, count: int) -> None:
        state = self._manager.get_state(self._session_id)
        if state is not None:
            self._manager.update_session_state(
                self._session_id, papers_found=state.papers_found + count
            )
        self._notify(f"{agent_id} cited-by {arxiv_id} -> {count}", category="search")
        self._broadcast_state()

    def cited_by_budget_exhausted(self, arxiv_id: str) -> None:
        pass

    def cited_by_skipped(self, arxiv_id: str) -> None:
        pass

    def cited_by_error(self, arxiv_id: str, error: str | Exception) -> None:
        self._notify(f"Cited-by failed: {arxiv_id}", category="search", level="error")

    def read_result(self, agent_id: str, arxiv_id: str, title: str, chars: int) -> None:
        self._notify(f"{agent_id} read {arxiv_id}", category="search")

    def read_budget_exhausted(self, arxiv_id: str) -> None:
        pass

    def read_skipped(self, arxiv_id: str) -> None:
        pass

    def read_error(self, arxiv_id: str, error: str | Exception) -> None:
        self._notify(f"Read failed: {arxiv_id}", category="search", level="error")

    def read_not_found(self, arxiv_id: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Live literature helpers
    # ------------------------------------------------------------------

    def _accumulate_literature(
        self,
        query: str,
        agent_id: str,
        phase: str,
        papers: list[dict[str, object]],
    ) -> None:
        """Accumulate search results and broadcast a literature update."""
        paper_msgs = []
        for p in papers:
            aid = str(p.get("arxiv_id", ""))
            paper_msg = LiteraturePaperMsg(
                arxiv_id=aid,
                title=str(p.get("title", "")),
                authors=[str(a) for a in (p.get("authors") or [])],
                year=str(p.get("year", "")),
            )
            paper_msgs.append(paper_msg)
            if aid and aid not in self._unique_papers:
                self._unique_papers[aid] = paper_msg

        self._search_log.append(
            LiteratureSearchMsg(
                query=query,
                agent_id=agent_id,
                phase=phase,
                papers=paper_msgs,
            )
        )
        self._broadcast_literature()

    def _broadcast_literature(self) -> None:
        """Broadcast the accumulated literature state to all WS clients."""
        msg = LiteratureUpdateMsg(
            searches=self._search_log,
            unique_papers=list(self._unique_papers.values()),
            total_searches=len(self._search_log),
        )
        _fire_and_forget(self._manager.broadcast_message(self._session_id, msg))

    # ------------------------------------------------------------------
    # Data staging
    # ------------------------------------------------------------------

    def data_staged(self, filename: str, size_bytes: int, url: str) -> None:
        self._notify(f"Staged: {filename}", category="data")

    def data_stage_error(self, url: str, error: str | Exception) -> None:
        self._notify(f"Data staging failed: {url[:40]}", category="data", level="error")

    def data_stage_skipped(self, url: str, reason: str) -> None:
        self._notify(f"Data skipped: {reason}", category="data")

    def network_access_warning(self) -> None:
        self._notify(
            "WARNING: Network access enabled for sandbox containers.",
            category="sandbox",
            level="warning",
        )

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    def resource_detected(self, url: str, resource_type: str) -> None:
        self._notify(f"{resource_type}: {url[:50]}", category="resource")

    def resource_ingested(self, title: str) -> None:
        self._notify(f"Ingested: {title[:50]}", category="resource")

    def resource_resolved(self, name: str, resource_type: str) -> None:
        self._notify(f"Resolved: {name}", category="resource")

    def resource_error(self, message: str) -> None:
        self._notify(message, category="resource", level="error")

    def resource_fetch_error(self, url: str, error: str | Exception) -> None:
        self._notify(f"Fetch failed: {url[:40]}", category="resource", level="error")

    def resource_extract_error(self, url: str) -> None:
        self._notify(f"Extract failed: {url[:40]}", category="resource", level="error")

    def pdf_saved(self, name: str) -> None:
        self._notify(f"PDF saved: {name}", category="resource")

    def pdf_save_error(self, error: str | Exception) -> None:
        self._notify("PDF save failed", category="resource", level="error")

    def graveyard_error(self, error: str | Exception) -> None:
        self._notify("Graveyard search failed", category="resource", level="error")

    # ------------------------------------------------------------------
    # Debates
    # ------------------------------------------------------------------

    def debate_start(self, challenger_id: str, defender_id: str, topic: str) -> None:
        self._notify(f"{challenger_id} vs {defender_id}: {topic[:60]}", category="debate")
        self._timers["debate"] = time.monotonic()
        self._activity(
            "debate_start",
            f"Debate: {challenger_id} vs {defender_id}",
            phase=self._current_phase(),
            detail=topic[:200],
            challenger_id=challenger_id,
            defender_id=defender_id,
        )

    def debate_turn(self, agent_id: str, event: str) -> None:
        self._notify(event, category="debate")

    def debate_resolved(self, agent_id: str) -> None:
        self._notify(f"Resolved by {agent_id}", category="debate")

    def debate_concede(self, agent_id: str) -> None:
        self._notify(f"{agent_id} concedes", category="debate")

    def debate_error(self, agent_id: str, error: str | Exception) -> None:
        self._notify(f"Debate error: {agent_id}", category="debate", level="error")

    def debate_complete(self, resolution_type: str, num_turns: int) -> None:
        self._notify(f"Complete: {resolution_type} ({num_turns} turns)", category="debate")
        self._activity(
            "debate_complete",
            f"Debate complete: {resolution_type}",
            phase=self._current_phase(),
            severity="success",
            detail=f"{num_turns} turn(s).",
            duration_ms=self._elapsed_ms("debate"),
        )

    def debate_skipped(self, target_id: str, reason: str) -> None:
        self._notify(f"Debate skipped: {reason}", category="debate")

    def debate_budget_exhausted(self, max_debates: int, phase: str) -> None:
        self._notify("Debate budget exhausted", category="debate", level="warning")

    def synthesis_error(self, error: str | Exception) -> None:
        self._notify("Synthesis failed", category="debate", level="error")

    # ------------------------------------------------------------------
    # Execution / experiments
    # ------------------------------------------------------------------

    def experiment_round(self, round_num: int, max_rounds: int) -> None:
        self._notify(f"Experiment round {round_num}/{max_rounds}", category="experiment")

    def experiment_no_agent(self) -> None:
        self._notify("No experimentalist found", category="experiment", level="warning")

    def experiment_declared_sufficient(self) -> None:
        self._notify("Experiments sufficient", category="experiment")

    def experiment_no_code(self) -> None:
        self._notify("No code blocks proposed", category="experiment")

    def experiment_running(self, exp_name: str) -> None:
        self._notify(f"Running: {exp_name}", category="experiment")
        self._timers[f"exp:{exp_name}"] = time.monotonic()
        self._activity(
            "experiment_running",
            f"Running {exp_name}",
            phase=self._current_phase(),
            exp_name=exp_name,
        )

    def experiment_result(self, exp_name: str, status: str) -> None:
        self._notify(f"{exp_name}: {status}", category="experiment")
        sev = "success" if str(status).lower() in ("success", "passed", "ok") else "warning"
        self._activity(
            "experiment_result",
            f"{exp_name}: {status}",
            phase=self._current_phase(),
            severity=sev,
            exp_name=exp_name,
            status=status,
            duration_ms=self._elapsed_ms(f"exp:{exp_name}"),
        )

    def experiment_retry(self, attempt: int, max_retries: int) -> None:
        self._notify(f"Retry {attempt}/{max_retries}", category="experiment")

    def experiment_high_failure_rate(self, failures: int, total: int) -> None:
        self._notify(
            f"High failure rate ({failures}/{total})", category="experiment", level="warning"
        )

    def experiment_strategy_redirect(self, category: str, count: int) -> None:
        self._notify(
            f"Strategy redirect: {category} ({count}x)", category="experiment", level="warning"
        )

    def experiment_advisory_requested(self) -> None:
        self._notify("Requesting team advisory", category="experiment")

    def experiment_cross_round_breaker(self, failures: int, total: int) -> None:
        self._notify(
            f"Cross-round breaker ({failures}/{total})", category="experiment", level="warning"
        )

    def experiment_budget_exhausted(self, total: int) -> None:
        self._notify(
            f"Experiment budget exhausted ({total} total)", category="experiment", level="warning"
        )

    def experiment_skipped(self, exp_name: str, failed_deps: list[str]) -> None:
        self._notify(f"Skipped {exp_name}", category="experiment")

    def experiment_review_requested(self, exp_name: str, reviewer_role: str) -> None:
        self._notify(f"Review: {exp_name} by {reviewer_role}", category="experiment")

    def experiment_review_passed(self, exp_name: str) -> None:
        self._notify(f"Review passed: {exp_name}", category="experiment")

    def experiment_review_issues(self, exp_name: str) -> None:
        self._notify(f"Review issues: {exp_name}", category="experiment")

    def sprint_start(self, sprint_num: int, num_sprints: int) -> None:
        self._notify(f"Sprint {sprint_num}/{num_sprints}", category="sprint")

    def sprint_design_proposed(self, sprint_num: int) -> None:
        self._notify(f"Sprint {sprint_num}: design proposed", category="sprint")

    def sprint_design_review(self, sprint_num: int, reviewer_role: str) -> None:
        self._notify(f"Sprint {sprint_num}: {reviewer_role} reviewing", category="sprint")

    def sprint_checkpoint(self, sprint_num: int, agent_role: str) -> None:
        self._notify(f"Sprint {sprint_num}: {agent_role} checkpoint", category="sprint")

    def sprint_early_stop(self, sprint_num: int) -> None:
        self._notify("Team declares experiments sufficient", category="sprint")

    def sprint_pivot_stop(self, sprint_num: int) -> None:
        self._notify("Team recommends STOP AND PIVOT", category="sprint", level="warning")

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def writing_round(self, round_name: str) -> None:
        self._notify(f"Round {round_name}", category="writing")

    def writing_section_drafting(self) -> None:
        self._notify("Section drafting", category="writing")

    def writing_assembly(self) -> None:
        self._notify("Assembly", category="writing")

    def writing_no_writer(self) -> None:
        self._notify("No writer agent found", category="writing", level="warning")

    def writing_assembly_retry(self, attempt: int, error: Exception) -> None:
        self._notify(f"Assembly API error, retry {attempt}", category="writing")

    def writing_assembly_error(self, error: str | Exception) -> None:
        self._notify("Assembly failed", category="writing", level="error")

    def paper_saved(self, paper_id: str, *, paper_path: str = "") -> None:
        self._notify(f"Paper saved: {paper_id}", category="writing", level="success")
        self._activity(
            "paper_saved",
            "Paper draft saved",
            phase=self._current_phase(),
            severity="success",
            detail=paper_id,
        )

    def paper_too_short(self, length: int, minimum: int) -> None:
        self._notify(f"Paper too short ({length}/{minimum})", category="writing", level="error")

    def figure_copied(self, filename: str) -> None:
        self._notify(f"Figure: {filename}", category="writing")

    def conceptual_figures_start(self, count: int) -> None:
        self._notify(f"Generating {count} conceptual figure(s)", category="writing")

    def conceptual_figure_generating(self, fig_num: int) -> None:
        self._notify(f"Generating Figure {fig_num}", category="writing")

    def conceptual_figure_success(self, fig_num: int) -> None:
        self._notify(f"Figure {fig_num} generated", category="writing")

    def conceptual_figure_error(self, fig_num: int, error: str | Exception) -> None:
        self._notify(f"Figure {fig_num} error: {error}", category="writing", level="error")

    def conceptual_figure_failed(self, fig_num: int, reason: str) -> None:
        self._notify(f"Figure {fig_num} failed: {reason}", category="writing", level="error")

    def conceptual_figure_no_code(self, fig_num: int) -> None:
        self._notify(f"Figure {fig_num}: no code block", category="writing", level="warning")

    def conceptual_figure_no_output(self, fig_num: int) -> None:
        self._notify(f"Figure {fig_num}: no PNG output", category="writing", level="warning")

    def conceptual_figures_complete(self, count: int) -> None:
        self._notify(f"Conceptual figures: {count} generated", category="writing")

    def code_saved(self, count: int) -> None:
        self._notify(f"Saved {count} code file(s) to code/", category="writing")

    def conceptual_figures_none(self) -> None:
        self._notify("All conceptual figure attempts failed", category="writing", level="warning")

    def execution_failed_abort(self, caveats: list[str] | None = None) -> None:
        self._notify(
            "Experiments produced no usable output — aborting before writing",
            category="execution",
            level="error",
        )

    def writing_failed_skip_review(self) -> None:
        self._notify(
            "Writing produced too little content, skipping review",
            category="writing",
            level="error",
        )

    def writing_failed_review_exhausted(self, status: str = "revision_exhausted") -> None:
        msg = (
            "Internal review rejected the paper"
            if status == "review_rejected"
            else "Internal review never accepted the paper after revisions"
        )
        self._notify(msg, category="writing", level="error")

    # ------------------------------------------------------------------
    # Review
    # ------------------------------------------------------------------

    def review_iteration(self, iteration: int, max_iterations: int) -> None:
        self._notify(f"Review iteration {iteration}/{max_iterations}", category="review")

    def review_no_editor(self) -> None:
        self._notify("No editor agent found", category="review", level="warning")

    def review_editor_retry(self, attempt: int, error: Exception) -> None:
        self._notify(f"Editor API error, retry {attempt}", category="review")

    def review_editor_error(self, error: str | Exception) -> None:
        self._notify("Editor review failed", category="review", level="error")

    def review_recommendation(self, recommendation: str, num_changes: int) -> None:
        self._notify(f"Editor: {recommendation} ({num_changes} changes)", category="review")

    def review_rejected(self) -> None:
        self._notify("Editor REJECTED paper", category="review", level="warning")

    def review_revising(self) -> None:
        self._notify("Revising...", category="review")

    def review_max_iterations(self) -> None:
        self._notify("Max review iterations reached", category="review", level="warning")

    def review_too_short(self, length: int) -> None:
        self._notify(f"Paper too short for review ({length})", category="review", level="warning")

    def revision_error(self, error: str | Exception) -> None:
        self._notify("Revision failed", category="review", level="error")

    # ------------------------------------------------------------------
    # Submission / desk review
    # ------------------------------------------------------------------

    def desk_review_result(self, passed: bool) -> None:
        label = "passed" if passed else "REJECTED"
        self._notify(f"Desk review: {label}", category="review")

    def desk_review_no_editor(self) -> None:
        pass

    def desk_review_error(self, error: str | Exception) -> None:
        self._notify("Desk review failed", category="review", level="error")

    # ------------------------------------------------------------------
    # Peer review
    # ------------------------------------------------------------------

    def peer_review_start(self, num_reviewers: int) -> None:
        self._notify(f"Peer review: {num_reviewers} reviewers", category="review")

    def peer_review_result(self, reviewer_id: str, recommendation: str, avg_score: float) -> None:
        self._notify(f"{reviewer_id}: {recommendation} ({avg_score:.1f})", category="review")

    def peer_review_error(self, reviewer_id: str, error: str | Exception) -> None:
        self._notify(f"{reviewer_id} review failed", category="review", level="error")

    def peer_review_decision(self, decision: str) -> None:
        self._notify(f"Decision: {decision}", category="review")
        sev = "success" if "accept" in str(decision).lower() else "warning"
        self._activity(
            "peer_review_decision",
            f"Peer review: {decision}",
            phase=self._current_phase(),
            severity=sev,
            decision=decision,
        )

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    def revision_start(self) -> None:
        self._notify("Revision started", category="revision")

    def revision_no_writer(self) -> None:
        pass

    def revision_complete(self) -> None:
        self._notify("Revision complete", category="revision")

    def revision_phase_error(self, error: str | Exception) -> None:
        self._notify("Revision failed", category="revision", level="error")

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------

    def paper_published(self) -> None:
        self._notify("Paper PUBLISHED", category="publication", level="success")
        self._activity(
            "paper_published",
            "Paper published",
            phase=self._current_phase(),
            severity="success",
        )

    def paper_rejected(self) -> None:
        self._notify("Paper REJECTED", category="publication", level="error")
        self._activity(
            "peer_review_decision",
            "Paper rejected",
            phase=self._current_phase(),
            severity="error",
            decision="rejected",
        )

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def checkpoint_saved(self, label: str) -> None:
        self._notify(f"Checkpoint saved: {label}", category="checkpoint")

    def checkpoint_error(self, error: str | Exception) -> None:
        self._notify("Checkpoint failed", category="checkpoint", level="error")

    # ------------------------------------------------------------------
    # Token usage / summary
    # ------------------------------------------------------------------

    def token_summary(self, total_k: float, input_k: float, output_k: float, time_str: str) -> None:
        self._notify(
            f"Tokens: {total_k:.1f}K total ({input_k:.1f}K in, {output_k:.1f}K out) | {time_str}",
            category="summary",
            level="success",
        )

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def memory_generating(self) -> None:
        self._notify("Generating reflections", category="memory")

    def memory_stored(self, total: int, agent_count: int) -> None:
        self._notify(f"Stored {total} memories", category="memory")

    def memory_error(self, error: str | Exception) -> None:
        self._notify("Memory reflection failed", category="memory", level="error")

    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------

    def info(self, message: str) -> None:
        self._notify(message, level="info")

    # Live-steering feedback — structured categories the frontend keys on.

    def guidance_delivered(self, text: str, phase: str, round_num: int) -> None:
        self._notify(
            text,
            level="success",
            category="guidance_delivered",
            phase=phase,
            round=round_num,
        )

    def run_parked(self, phase: str, round_num: int) -> None:
        self._notify(
            f"Paused ({phase}, round {round_num})",
            level="warning",
            category="run_parked",
            phase=phase,
            round=round_num,
        )

    def run_resumed(self, phase: str, round_num: int) -> None:
        self._notify(
            f"Resumed ({phase}, round {round_num})",
            level="success",
            category="run_resumed",
            phase=phase,
            round=round_num,
        )

    def warning(self, message: str) -> None:
        self._notify(message, level="warning")

    def error(self, message: str, *, err: bool = False) -> None:
        self._notify(message, level="error")

    # ------------------------------------------------------------------
    # Main.py specific (mostly no-ops for WS)
    # ------------------------------------------------------------------

    def testing_mode(self) -> None:
        pass

    def cycle_complete(self, thread_id: str) -> None:
        self._notify(f"Cycle complete: {thread_id}", category="lifecycle", level="success")

    def cycle_interrupted(self) -> None:
        self._notify("Cycle interrupted", category="lifecycle", level="warning")

    def cycle_error(self, error: str | Exception) -> None:
        self._notify(str(error), category="lifecycle", level="error")

    def prompt_loaded(self, path: str, length: int) -> None:
        pass

    def fresh_corpus(self, path: object) -> None:
        self._notify("Fresh corpus: starting with empty internal corpus", category="lifecycle")

    def starting_cycle(self, mode: str) -> None:
        self._notify(f"Starting {mode} research cycle...", category="lifecycle")

    def rounds_override(self, rounds: int) -> None:
        pass

    def interactive_mode(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Seed discovery
    # ------------------------------------------------------------------

    def seed_discovery_start(self) -> None:
        self._notify("Querying Perplexity for initial literature", category="seed_discovery")

    def seed_discovery_complete(self, num_papers: int) -> None:
        self._notify(f"{num_papers} papers found via seed discovery", category="seed_discovery")
        self._activity(
            "seed_discovery",
            f"Seeded {num_papers} foundational paper(s)",
            phase=self._current_phase(),
            count=num_papers,
        )

    def seed_discovery_error(self, error: str | Exception) -> None:
        self._notify(f"Seed discovery failed: {error}", category="seed_discovery", level="error")

    # ------------------------------------------------------------------
    # Citation grounding
    # ------------------------------------------------------------------

    def citation_grounding_start(self) -> None:
        self._notify("Citation grounding started", category="citation")

    def citation_grounding_complete(self, num_citations: int) -> None:
        self._notify(f"{num_citations} citations added", category="citation")
        self._activity(
            "citation_grounding",
            f"Grounded {num_citations} citation(s)",
            phase=self._current_phase(),
            severity="success",
            num_citations=num_citations,
        )

    def citation_grounding_error(self, error: str | Exception) -> None:
        self._notify(f"Citation grounding failed: {error}", category="citation", level="error")

    # ------------------------------------------------------------------
    # Novelty checking
    # ------------------------------------------------------------------

    def novelty_check_start(self, mode: str) -> None:
        self._notify(f"Novelty check ({mode})", category="novelty")

    def novelty_warning(self, result: object) -> None:
        self._notify("Idea may not be novel", category="novelty", level="warning")

    def novelty_confirmed(self) -> None:
        self._notify("Idea appears novel", category="novelty")

    # ------------------------------------------------------------------
    # Knowledge architecture
    # ------------------------------------------------------------------

    def knowledge_updated(self, **kwargs: Any) -> None:
        """Broadcast a knowledge architecture snapshot to connected clients."""
        msg = KnowledgeUpdateMsg(**kwargs)
        self._manager.store_knowledge_snapshot(self._session_id, msg)
        _fire_and_forget(self._manager.broadcast_message(self._session_id, msg))
