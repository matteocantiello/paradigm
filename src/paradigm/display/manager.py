"""DisplayManager — central display coordinator for the Paradigm UI.

Maintains a DisplayState and delegates rendering to either Rich components
(when stdout is a TTY and verbose is off) or PlainTextFallback.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from paradigm.display.fallback import PlainTextFallback
from paradigm.orchestrator.phases import ResearchPhase


@dataclass
class DisplayState:
    """Mutable state tracked by the DisplayManager for live rendering."""

    current_phase: ResearchPhase | None = None
    completed_phases: list[ResearchPhase] = field(default_factory=list)
    round_num: int = 0
    max_rounds: int = 0
    active_agents: dict[str, str] = field(default_factory=dict)  # agent_id -> activity
    recent_events: list[dict[str, str]] = field(default_factory=list)  # capped at 50
    total_tokens: int = 0
    total_searches: int = 0
    papers_count: int = 0
    start_time: float = field(default_factory=time.monotonic)
    agent_messages: list[dict[str, str]] = field(default_factory=list)  # capped at 8
    # End-of-cycle info for the final summary
    thread_id: str = ""
    paper_id: str = ""
    paper_path: str = ""
    outcome: str = ""  # published, rejected, reviewed, etc.

    def add_agent_message(self, agent_id: str, role: str, model: str, content: str) -> None:
        """Add an agent message preview (capped at 8)."""
        self.agent_messages.append(
            {
                "agent_id": agent_id,
                "role": role,
                "model": model,
                "content": content[:500],
            }
        )
        if len(self.agent_messages) > 8:
            self.agent_messages = self.agent_messages[-8:]

    def add_event(self, event_type: str, message: str) -> None:
        """Add an event to the recent events list (capped at 50)."""
        self.recent_events.append(
            {
                "type": event_type,
                "message": message,
                "time": datetime.now(UTC).strftime("%H:%M:%S"),
            }
        )
        if len(self.recent_events) > 50:
            self.recent_events = self.recent_events[-50:]

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time


class DisplayManager:
    """Central display coordinator.

    When Rich mode is active, renders live-updating panels and styled output.
    When in plain-text mode (verbose=True or non-TTY), delegates to
    PlainTextFallback for behavioral parity with the original click.echo calls.
    """

    def __init__(self, *, verbose: bool = False) -> None:
        self._use_rich = not verbose and sys.stdout.isatty()
        self._state = DisplayState()
        self._fallback = PlainTextFallback()

        # Rich components (lazy-initialized in start())
        self._console: object | None = None
        self._live: object | None = None
        # Saved token summary for the final static panel printed in stop()
        self._token_summary: dict[str, object] = {}

    @property
    def state(self) -> DisplayState:
        return self._state

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the display system."""
        if self._use_rich:
            try:
                from rich.console import Console

                from paradigm.display.layout import create_live_display

                self._console = Console()
                self._live = create_live_display(self._console)
                self._live.start()  # type: ignore[union-attr]
            except Exception:
                # Fallback if Rich initialization fails
                self._use_rich = False
        self._fallback.start()

    def stop(self) -> None:
        """Stop the display system and print a static final summary."""
        if self._live is not None:
            try:
                self._live.stop()  # type: ignore[union-attr]
            except Exception:
                pass
            self._live = None
        self._fallback.stop()

        # Print a static final summary that persists after the live display ends
        if self._use_rich and self._console is not None and self._token_summary:
            try:
                from paradigm.display.components import build_final_summary

                panel = build_final_summary(
                    state=self._state,
                    **self._token_summary,
                )
                self._console.print(panel)  # type: ignore[union-attr]
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Refresh the Live display if active."""
        if self._live is not None:
            try:
                from paradigm.display.layout import build_live_layout

                self._live.update(build_live_layout(self._state))  # type: ignore[union-attr]
            except Exception:
                pass

    def _print_rich(self, renderable: object) -> None:
        """Print a Rich renderable, temporarily pausing Live if needed."""
        if self._console is None:
            return
        if self._live is not None:
            try:
                self._live.stop()  # type: ignore[union-attr]
                self._console.print(renderable)  # type: ignore[union-attr]
                self._live.start()  # type: ignore[union-attr]
            except Exception:
                pass
        else:
            try:
                self._console.print(renderable)  # type: ignore[union-attr]
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Phase transitions
    # ------------------------------------------------------------------

    def phase_transition(
        self,
        phase_name: str | ResearchPhase,
        *,
        max_rounds: int | None = None,
        active_agents: int | None = None,
        total_agents: int | None = None,
    ) -> None:
        # Update state
        if self._state.current_phase is not None:
            self._state.completed_phases.append(self._state.current_phase)

        # Resolve phase: accept ResearchPhase enum, enum value, or enum member name
        if isinstance(phase_name, ResearchPhase):
            self._state.current_phase = phase_name
        else:
            resolved = None
            clean = phase_name.strip().lower()
            # Try as enum value first (e.g. "seeding", "internal", "peer_review")
            for member in ResearchPhase:
                if member.value == clean:
                    resolved = member
                    break
            # Fallback: try as enum member name (e.g. "INTERNAL_REVIEW" -> "internal")
            if resolved is None:
                try:
                    resolved = ResearchPhase[clean.upper()]
                except KeyError:
                    pass
            if resolved is not None:
                self._state.current_phase = resolved
        if max_rounds is not None:
            self._state.max_rounds = max_rounds
        self._state.round_num = 0
        display_name = phase_name if isinstance(phase_name, str) else phase_name.value.upper()
        self._state.add_event("phase", f"Phase: {display_name}")

        if self._use_rich:
            from paradigm.display.components import build_phase_banner

            banner = build_phase_banner(display_name, self._state)
            self._print_rich(banner)
            self._refresh()
        else:
            self._fallback.phase_transition(
                display_name,
                max_rounds=max_rounds,
                active_agents=active_agents,
                total_agents=total_agents,
            )

    def phase_aborted(self) -> None:
        self._state.outcome = "aborted"
        self._state.add_event("phase", "Research cycle aborted")
        if self._use_rich:
            from paradigm.display.components import build_status_message

            self._print_rich(
                build_status_message("Research cycle aborted by intervention hook.", "error")
            )
        else:
            self._fallback.phase_aborted()

    def phase_paused(self) -> None:
        self._state.add_event("phase", "Research cycle paused")
        if self._use_rich:
            from paradigm.display.components import build_status_message

            self._print_rich(
                build_status_message("Research cycle paused by intervention hook.", "warning")
            )
        else:
            self._fallback.phase_paused()

    # ------------------------------------------------------------------
    # Rounds
    # ------------------------------------------------------------------

    def round_start(self, round_num: int, max_rounds: int) -> None:
        self._state.round_num = round_num
        self._state.max_rounds = max_rounds
        self._state.add_event("round", f"Round {round_num}/{max_rounds}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.round_start(round_num, max_rounds)

    # ------------------------------------------------------------------
    # Convergence detection
    # ------------------------------------------------------------------

    def convergence_detected(self, phase: str, round_num: int, max_rounds: int) -> None:
        rounds_skipped = max_rounds - round_num
        self._state.add_event(
            "convergence",
            f"Agents converged in {phase} after round {round_num}, "
            f"skipping {rounds_skipped} round(s)",
        )
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.convergence_detected(phase, round_num, max_rounds)

    # ------------------------------------------------------------------
    # Agent activity
    # ------------------------------------------------------------------

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
        self._state.total_tokens += total_tokens
        self._state.active_agents[agent_id] = f"{total_tokens} tokens"
        self._state.add_event("agent", f"{agent_id}: {total_tokens} tokens")
        if content:
            self._state.add_agent_message(agent_id, role, model, content)
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.agent_response(agent_id, total_tokens)

    def agent_stream_start(
        self, agent_id: str, stream_id: str, *, role: str = "", phase: str = ""
    ) -> None:
        """Live-streaming start hook. No-op for the Rich/CLI display."""

    def agent_stream_chunk(
        self, agent_id: str, stream_id: str, chunk: str, *, role: str = "", phase: str = ""
    ) -> None:
        """Live-streaming chunk hook. No-op for the Rich/CLI display."""

    def agent_error(self, agent_id: str, error: str | Exception) -> None:
        self._state.add_event("error", f"{agent_id} failed: {error}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.agent_error(agent_id, error)

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
        self._state.total_searches += 1
        self._state.papers_count += new_results
        self._state.add_event("search", f"{agent_id}: '{query[:40]}' \u2192 {new_results} new")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.search_result(agent_id, query, total_results, new_results)

    def search_skipped(self, query: str, *, reason: str = "similar") -> None:
        self._state.add_event("skip", f"Skipped {reason} query")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.search_skipped(query, reason=reason)

    def search_budget_exhausted(self, budget: int, query: str) -> None:
        self._state.add_event("warning", "Search budget exhausted")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.search_budget_exhausted(budget, query)

    def search_agent_cap(self, agent_id: str, cap: int, query: str) -> None:
        self._state.add_event("warning", f"{agent_id}: per-agent cap reached")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.search_agent_cap(agent_id, cap, query)

    def search_error(self, query: str, error: str | Exception) -> None:
        self._state.add_event("error", f"Search failed: {query[:40]}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.search_error(query, error)

    def search_stale(self, agent_id: str, count: int = 2) -> None:
        self._state.add_event("warning", f"{agent_id}: stale searches")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.search_stale(agent_id, count)

    def follow_result(self, agent_id: str, arxiv_id: str, count: int) -> None:
        self._state.papers_count += count
        self._state.add_event("search", f"{agent_id} followed {arxiv_id} \u2192 {count}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.follow_result(agent_id, arxiv_id, count)

    def follow_budget_exhausted(self, arxiv_id: str) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.follow_budget_exhausted(arxiv_id)

    def follow_skipped(self, arxiv_id: str) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.follow_skipped(arxiv_id)

    def follow_error(self, arxiv_id: str, error: str | Exception) -> None:
        self._state.add_event("error", f"Follow failed: {arxiv_id}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.follow_error(arxiv_id, error)

    def cited_by_result(self, agent_id: str, arxiv_id: str, count: int) -> None:
        self._state.papers_count += count
        self._state.add_event("search", f"{agent_id} cited-by {arxiv_id} \u2192 {count}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.cited_by_result(agent_id, arxiv_id, count)

    def cited_by_budget_exhausted(self, arxiv_id: str) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.cited_by_budget_exhausted(arxiv_id)

    def cited_by_skipped(self, arxiv_id: str) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.cited_by_skipped(arxiv_id)

    def cited_by_error(self, arxiv_id: str, error: str | Exception) -> None:
        self._state.add_event("error", f"Cited-by failed: {arxiv_id}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.cited_by_error(arxiv_id, error)

    def read_result(self, agent_id: str, arxiv_id: str, title: str, chars: int) -> None:
        self._state.add_event("search", f"{agent_id} read {arxiv_id}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.read_result(agent_id, arxiv_id, title, chars)

    def read_budget_exhausted(self, arxiv_id: str) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.read_budget_exhausted(arxiv_id)

    def read_skipped(self, arxiv_id: str) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.read_skipped(arxiv_id)

    def read_error(self, arxiv_id: str, error: str | Exception) -> None:
        self._state.add_event("error", f"Read failed: {arxiv_id}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.read_error(arxiv_id, error)

    def read_not_found(self, arxiv_id: str) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.read_not_found(arxiv_id)

    # ------------------------------------------------------------------
    # Data staging
    # ------------------------------------------------------------------

    def data_staged(self, filename: str, size_bytes: int, url: str) -> None:
        self._state.add_event("data", f"Staged: {filename}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.data_staged(filename, size_bytes, url)

    def data_stage_error(self, url: str, error: str | Exception) -> None:
        self._state.add_event("error", f"Data staging failed: {url[:40]}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.data_stage_error(url, error)

    def data_stage_skipped(self, url: str, reason: str) -> None:
        self._state.add_event("skip", f"Data skipped: {reason}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.data_stage_skipped(url, reason)

    def network_access_warning(self) -> None:
        self._state.add_event("warning", "Network access enabled for sandbox")
        if self._use_rich:
            from paradigm.display.components import build_status_message

            self._print_rich(
                build_status_message(
                    "WARNING: --network-access enabled. Sandbox containers have internet access.",
                    "warning",
                )
            )
        else:
            self._fallback.network_access_warning()

    # ------------------------------------------------------------------
    # Resources (seeding phase)
    # ------------------------------------------------------------------

    def resource_detected(self, url: str, resource_type: str) -> None:
        self._state.add_event("resource", f"{resource_type}: {url[:50]}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.resource_detected(url, resource_type)

    def resource_ingested(self, title: str) -> None:
        self._state.add_event("resource", f"Ingested: {title[:50]}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.resource_ingested(title)

    def resource_resolved(self, name: str, resource_type: str) -> None:
        self._state.add_event("resource", f"Resolved: {name}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.resource_resolved(name, resource_type)

    def resource_error(self, message: str) -> None:
        self._state.add_event("error", message)
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.resource_error(message)

    def resource_fetch_error(self, url: str, error: str | Exception) -> None:
        self._state.add_event("error", f"Fetch failed: {url[:40]}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.resource_fetch_error(url, error)

    def resource_extract_error(self, url: str) -> None:
        self._state.add_event("error", f"Extract failed: {url[:40]}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.resource_extract_error(url)

    def pdf_saved(self, name: str) -> None:
        self._state.add_event("resource", f"PDF saved: {name}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.pdf_saved(name)

    def pdf_save_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "PDF save failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.pdf_save_error(error)

    def graveyard_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Graveyard search failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.graveyard_error(error)

    # ------------------------------------------------------------------
    # Debates
    # ------------------------------------------------------------------

    def debate_start(self, challenger_id: str, defender_id: str, topic: str) -> None:
        self._state.add_event("debate", f"{challenger_id} vs {defender_id}")
        if self._use_rich:
            from paradigm.display.components import build_debate_panel

            panel = build_debate_panel(challenger_id, defender_id, topic)
            self._print_rich(panel)
            self._refresh()
        else:
            self._fallback.debate_start(challenger_id, defender_id, topic)

    def debate_turn(self, agent_id: str, event: str) -> None:
        self._state.add_event("debate", event)
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.debate_turn(agent_id, event)

    def debate_resolved(self, agent_id: str) -> None:
        self._state.add_event("debate", f"Resolved by {agent_id}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.debate_resolved(agent_id)

    def debate_concede(self, agent_id: str) -> None:
        self._state.add_event("debate", f"{agent_id} concedes")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.debate_concede(agent_id)

    def debate_error(self, agent_id: str, error: str | Exception) -> None:
        self._state.add_event("error", f"Debate error: {agent_id}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.debate_error(agent_id, error)

    def debate_complete(self, resolution_type: str, num_turns: int) -> None:
        self._state.add_event("debate", f"Complete: {resolution_type}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.debate_complete(resolution_type, num_turns)

    def debate_skipped(self, target_id: str, reason: str) -> None:
        self._state.add_event("skip", f"Debate skipped: {reason}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.debate_skipped(target_id, reason)

    def debate_budget_exhausted(self, max_debates: int, phase: str) -> None:
        self._state.add_event("warning", "Debate budget exhausted")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.debate_budget_exhausted(max_debates, phase)

    def synthesis_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Synthesis failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.synthesis_error(error)

    # ------------------------------------------------------------------
    # Execution / experiments
    # ------------------------------------------------------------------

    def experiment_round(self, round_num: int, max_rounds: int) -> None:
        self._state.round_num = round_num
        self._state.add_event("experiment", f"Experiment round {round_num}/{max_rounds}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_round(round_num, max_rounds)

    def experiment_no_agent(self) -> None:
        self._state.add_event("warning", "No experimentalist found")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_no_agent()

    def experiment_declared_sufficient(self) -> None:
        self._state.add_event("experiment", "Experiments sufficient")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_declared_sufficient()

    def experiment_no_code(self) -> None:
        self._state.add_event("skip", "No code blocks proposed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_no_code()

    def experiment_running(self, exp_name: str) -> None:
        self._state.add_event("experiment", f"Running: {exp_name}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_running(exp_name)

    def experiment_result(self, exp_name: str, status: str) -> None:
        self._state.add_event("experiment", f"{exp_name}: {status}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_result(exp_name, status)

    def experiment_retry(self, attempt: int, max_retries: int) -> None:
        self._state.add_event("experiment", f"Retry {attempt}/{max_retries}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_retry(attempt, max_retries)

    def experiment_high_failure_rate(self, failures: int, total: int) -> None:
        self._state.add_event("warning", f"High failure rate ({failures}/{total})")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_high_failure_rate(failures, total)

    def experiment_strategy_redirect(self, category: str, count: int) -> None:
        self._state.add_event("warning", f"Strategy redirect: {category} ({count}x)")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_strategy_redirect(category, count)

    def experiment_advisory_requested(self) -> None:
        self._state.add_event("experiment", "Requesting team advisory")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_advisory_requested()

    def experiment_cross_round_breaker(self, failures: int, total: int) -> None:
        self._state.add_event("warning", f"Cross-round breaker ({failures}/{total})")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_cross_round_breaker(failures, total)

    def experiment_budget_exhausted(self, total: int) -> None:
        self._state.add_event("warning", f"Experiment budget exhausted ({total} total)")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_budget_exhausted(total)

    def experiment_skipped(self, exp_name: str, failed_deps: list[str]) -> None:
        self._state.add_event("skip", f"Skipped {exp_name} (deps: {', '.join(failed_deps)})")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_skipped(exp_name, failed_deps)

    def experiment_review_requested(self, exp_name: str, reviewer_role: str) -> None:
        self._state.add_event("experiment", f"Review: {exp_name} by {reviewer_role}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_review_requested(exp_name, reviewer_role)

    def experiment_review_passed(self, exp_name: str) -> None:
        self._state.add_event("experiment", f"Review passed: {exp_name}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_review_passed(exp_name)

    def experiment_review_issues(self, exp_name: str) -> None:
        self._state.add_event("experiment", f"Review issues: {exp_name}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.experiment_review_issues(exp_name)

    def sprint_start(self, sprint_num: int, num_sprints: int) -> None:
        self._state.add_event("sprint", f"Sprint {sprint_num}/{num_sprints}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.sprint_start(sprint_num, num_sprints)

    def sprint_design_proposed(self, sprint_num: int) -> None:
        self._state.add_event("sprint", f"Sprint {sprint_num}: design proposed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.sprint_design_proposed(sprint_num)

    def sprint_design_review(self, sprint_num: int, reviewer_role: str) -> None:
        self._state.add_event("sprint", f"Sprint {sprint_num}: {reviewer_role} reviewing")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.sprint_design_review(sprint_num, reviewer_role)

    def sprint_checkpoint(self, sprint_num: int, agent_role: str) -> None:
        self._state.add_event("sprint", f"Sprint {sprint_num}: {agent_role} checkpoint")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.sprint_checkpoint(sprint_num, agent_role)

    def sprint_early_stop(self, sprint_num: int) -> None:
        self._state.add_event("sprint", "Team declares experiments sufficient")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.sprint_early_stop(sprint_num)

    def sprint_pivot_stop(self, sprint_num: int) -> None:
        self._state.add_event("sprint", "Team recommends STOP AND PIVOT")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.sprint_pivot_stop(sprint_num)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def writing_round(self, round_name: str) -> None:
        self._state.add_event("writing", f"Round {round_name}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.writing_round(round_name)

    def writing_section_drafting(self) -> None:
        self._state.add_event("writing", "Section drafting")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.writing_section_drafting()

    def writing_assembly(self) -> None:
        self._state.add_event("writing", "Assembly")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.writing_assembly()

    def writing_no_writer(self) -> None:
        self._state.add_event("warning", "No writer agent found")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.writing_no_writer()

    def writing_assembly_retry(self, attempt: int, error: Exception) -> None:
        self._state.add_event("writing", f"Assembly API error, retry {attempt}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.writing_assembly_retry(attempt, error)

    def writing_assembly_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Assembly failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.writing_assembly_error(error)

    def paper_saved(self, paper_id: str, *, paper_path: str = "") -> None:
        self._state.paper_id = paper_id
        if paper_path:
            self._state.paper_path = paper_path
        self._state.add_event("writing", f"Paper saved: {paper_id}")
        if self._use_rich:
            from paradigm.display.components import build_status_message

            self._print_rich(build_status_message(f"Paper saved: {paper_id}", "success"))
            self._refresh()
        else:
            self._fallback.paper_saved(paper_id)

    def paper_too_short(self, length: int, minimum: int) -> None:
        self._state.add_event("error", f"Paper too short ({length}/{minimum})")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.paper_too_short(length, minimum)

    def figure_copied(self, filename: str) -> None:
        self._state.add_event("writing", f"Figure: {filename}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.figure_copied(filename)

    def conceptual_figures_start(self, count: int) -> None:
        self._state.add_event("writing", f"Generating {count} conceptual figure(s)")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figures_start(count)

    def conceptual_figure_generating(self, fig_num: int) -> None:
        self._state.add_event("writing", f"Generating Figure {fig_num}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figure_generating(fig_num)

    def conceptual_figure_success(self, fig_num: int) -> None:
        self._state.add_event("writing", f"Figure {fig_num} generated")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figure_success(fig_num)

    def conceptual_figure_error(self, fig_num: int, error: str | Exception) -> None:
        self._state.add_event("error", f"Figure {fig_num} error: {error}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figure_error(fig_num, error)

    def conceptual_figure_failed(self, fig_num: int, reason: str) -> None:
        self._state.add_event("error", f"Figure {fig_num} failed: {reason}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figure_failed(fig_num, reason)

    def conceptual_figure_no_code(self, fig_num: int) -> None:
        self._state.add_event("warning", f"Figure {fig_num}: no code block")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figure_no_code(fig_num)

    def conceptual_figure_no_output(self, fig_num: int) -> None:
        self._state.add_event("warning", f"Figure {fig_num}: no PNG output")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figure_no_output(fig_num)

    def conceptual_figures_complete(self, count: int) -> None:
        self._state.add_event("writing", f"Conceptual figures: {count} generated")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figures_complete(count)

    def code_saved(self, count: int) -> None:
        self._state.add_event("writing", f"Saved {count} code file(s) to code/")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.code_saved(count)

    def conceptual_figures_none(self) -> None:
        self._state.add_event("warning", "All conceptual figure attempts failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.conceptual_figures_none()

    def execution_failed_abort(self, caveats: list[str] | None = None) -> None:
        self._state.outcome = "execution_failed"
        self._state.add_event(
            "error", "Experiments produced no usable output — aborting before writing"
        )
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.execution_failed_abort(caveats or [])

    def writing_failed_skip_review(self) -> None:
        self._state.outcome = "writing_incomplete"
        self._state.add_event("error", "Writing produced too little content, skipping review")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.writing_failed_skip_review()

    def writing_failed_review_exhausted(self, status: str = "revision_exhausted") -> None:
        self._state.outcome = status
        msg = (
            "Internal review rejected the paper"
            if status == "review_rejected"
            else "Internal review never accepted the paper after revisions"
        )
        self._state.add_event("error", msg)
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.writing_failed_review_exhausted(status)

    # ------------------------------------------------------------------
    # Review
    # ------------------------------------------------------------------

    def review_iteration(self, iteration: int, max_iterations: int) -> None:
        self._state.add_event("review", f"Review iteration {iteration}/{max_iterations}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_iteration(iteration, max_iterations)

    def review_no_editor(self) -> None:
        self._state.add_event("warning", "No editor agent found")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_no_editor()

    def review_editor_retry(self, attempt: int, error: Exception) -> None:
        self._state.add_event("review", f"Editor API error, retry {attempt}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_editor_retry(attempt, error)

    def review_editor_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Editor review failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_editor_error(error)

    def review_recommendation(self, recommendation: str, num_changes: int) -> None:
        self._state.add_event("review", f"Editor: {recommendation} ({num_changes} changes)")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_recommendation(recommendation, num_changes)

    def review_rejected(self) -> None:
        self._state.add_event("review", "Editor REJECTED paper")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_rejected()

    def review_revising(self) -> None:
        self._state.add_event("review", "Revising...")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_revising()

    def review_max_iterations(self) -> None:
        self._state.add_event("warning", "Max review iterations reached")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_max_iterations()

    def review_too_short(self, length: int) -> None:
        self._state.add_event("warning", f"Paper too short for review ({length})")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.review_too_short(length)

    def revision_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Revision failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.revision_error(error)

    # ------------------------------------------------------------------
    # Submission / desk review
    # ------------------------------------------------------------------

    def desk_review_result(self, passed: bool) -> None:
        label = "passed" if passed else "REJECTED"
        self._state.add_event("review", f"Desk review: {label}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.desk_review_result(passed)

    def desk_review_no_editor(self) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.desk_review_no_editor()

    def desk_review_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Desk review failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.desk_review_error(error)

    # ------------------------------------------------------------------
    # Peer review
    # ------------------------------------------------------------------

    def peer_review_start(self, num_reviewers: int) -> None:
        self._state.add_event("review", f"Peer review: {num_reviewers} reviewers")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.peer_review_start(num_reviewers)

    def peer_review_result(self, reviewer_id: str, recommendation: str, avg_score: float) -> None:
        self._state.add_event("review", f"{reviewer_id}: {recommendation} ({avg_score:.1f})")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.peer_review_result(reviewer_id, recommendation, avg_score)

    def peer_review_error(self, reviewer_id: str, error: str | Exception) -> None:
        self._state.add_event("error", f"{reviewer_id} review failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.peer_review_error(reviewer_id, error)

    def peer_review_decision(self, decision: str) -> None:
        self._state.add_event("review", f"Decision: {decision}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.peer_review_decision(decision)

    # ------------------------------------------------------------------
    # Revision (peer review)
    # ------------------------------------------------------------------

    def revision_start(self) -> None:
        self._state.add_event("revision", "Revision started")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.revision_start()

    def revision_no_writer(self) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.revision_no_writer()

    def revision_complete(self) -> None:
        self._state.add_event("revision", "Revision complete")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.revision_complete()

    def revision_phase_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Revision failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.revision_phase_error(error)

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------

    def paper_published(self) -> None:
        # Move current phase to completed and set PUBLISHED as current
        if self._state.current_phase is not None:
            self._state.completed_phases.append(self._state.current_phase)
        self._state.current_phase = ResearchPhase.PUBLISHED
        self._state.completed_phases.append(ResearchPhase.PUBLISHED)
        self._state.outcome = "published"
        self._state.add_event("publication", "Paper PUBLISHED")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.paper_published()

    def paper_rejected(self) -> None:
        # Move current phase to completed and set REJECTED as current
        if self._state.current_phase is not None:
            self._state.completed_phases.append(self._state.current_phase)
        self._state.current_phase = ResearchPhase.REJECTED
        self._state.outcome = "rejected"
        self._state.add_event("publication", "Paper REJECTED")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.paper_rejected()

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def checkpoint_saved(self, label: str) -> None:
        self._state.add_event("checkpoint", f"Saved: {label}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.checkpoint_saved(label)

    def checkpoint_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Checkpoint failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.checkpoint_error(error)

    # ------------------------------------------------------------------
    # Token usage / summary
    # ------------------------------------------------------------------

    def token_summary(self, total_k: float, input_k: float, output_k: float, time_str: str) -> None:
        # Save for the static final summary printed in stop()
        self._token_summary = {
            "total_k": total_k,
            "input_k": input_k,
            "output_k": output_k,
            "time_str": time_str,
        }
        if self._use_rich:
            # Don't print now — the final summary is printed in stop() after
            # the Live display is torn down so it persists on screen.
            self._refresh()
        else:
            self._fallback.token_summary(total_k, input_k, output_k, time_str)

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def memory_generating(self) -> None:
        self._state.add_event("memory", "Generating reflections")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.memory_generating()

    def memory_stored(self, total: int, agent_count: int) -> None:
        self._state.add_event("memory", f"Stored {total} memories")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.memory_stored(total, agent_count)

    def memory_error(self, error: str | Exception) -> None:
        self._state.add_event("error", "Memory reflection failed")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.memory_error(error)

    # ------------------------------------------------------------------
    # General info / warning / error
    # ------------------------------------------------------------------

    def info(self, message: str) -> None:
        self._state.add_event("info", message)
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.info(message)

    def warning(self, message: str) -> None:
        self._state.add_event("warning", message)
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.warning(message)

    def error(self, message: str, *, err: bool = False) -> None:
        self._state.add_event("error", message)
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.error(message, err=err)

    # ------------------------------------------------------------------
    # Main.py specific
    # ------------------------------------------------------------------

    def testing_mode(self) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.testing_mode()

    def cycle_complete(self, thread_id: str) -> None:
        self._state.thread_id = thread_id
        if not self._state.outcome:
            self._state.outcome = "completed"
        self._state.add_event("complete", f"Thread: {thread_id}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.cycle_complete(thread_id)

    def cycle_interrupted(self) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.cycle_interrupted()

    def cycle_error(self, error: str | Exception) -> None:
        self._state.add_event("error", str(error))
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.cycle_error(error)

    def prompt_loaded(self, path: str, length: int) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.prompt_loaded(path, length)

    def fresh_corpus(self, path: object) -> None:
        self._state.add_event("info", "Fresh corpus: isolated vector DB")
        if self._use_rich:
            from paradigm.display.components import build_status_message

            self._print_rich(
                build_status_message("Fresh corpus: starting with empty internal corpus", "info")
            )
        else:
            self._fallback.fresh_corpus(path)

    def starting_cycle(self, mode: str) -> None:
        self._state.add_event("info", f"Starting {mode} research cycle")
        if self._use_rich:
            from paradigm.display.components import build_status_message

            self._print_rich(build_status_message(f"Starting {mode} research cycle...", "info"))
        else:
            self._fallback.starting_cycle(mode)

    def rounds_override(self, rounds: int) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.rounds_override(rounds)

    def interactive_mode(self) -> None:
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.interactive_mode()

    # ------------------------------------------------------------------
    # Seed discovery
    # ------------------------------------------------------------------

    def seed_discovery_start(self) -> None:
        self._state.add_event("seed_discovery", "Querying Perplexity for initial literature")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.seed_discovery_start()

    def seed_discovery_complete(self, num_papers: int) -> None:
        self._state.papers_count += num_papers
        self._state.add_event("seed_discovery", f"{num_papers} papers found")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.seed_discovery_complete(num_papers)

    def seed_discovery_error(self, error: str | Exception) -> None:
        self._state.add_event("error", f"Seed discovery failed: {error}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.seed_discovery_error(error)

    # ------------------------------------------------------------------
    # Citation grounding
    # ------------------------------------------------------------------

    def citation_grounding_start(self) -> None:
        self._state.add_event("citation", "Citation grounding started")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.citation_grounding_start()

    def citation_grounding_complete(self, num_citations: int) -> None:
        self._state.add_event("citation", f"{num_citations} citations added")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.citation_grounding_complete(num_citations)

    def citation_grounding_error(self, error: str | Exception) -> None:
        self._state.add_event("error", f"Citation grounding failed: {error}")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.citation_grounding_error(error)

    # ------------------------------------------------------------------
    # Novelty checking
    # ------------------------------------------------------------------

    def novelty_check_start(self, mode: str) -> None:
        self._state.add_event("novelty", f"Novelty check ({mode})")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.novelty_check_start(mode)

    def novelty_warning(self, result: object) -> None:
        self._state.add_event("warning", "Idea may not be novel")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.novelty_warning(result)

    def novelty_confirmed(self) -> None:
        self._state.add_event("novelty", "Idea appears novel")
        if self._use_rich:
            self._refresh()
        else:
            self._fallback.novelty_confirmed()

    # ------------------------------------------------------------------
    # Knowledge architecture (no-op for CLI — data is in Rich panels)
    # ------------------------------------------------------------------

    def knowledge_updated(self, **kwargs) -> None:  # noqa: ARG002
        """No-op for terminal display; knowledge is shown in Rich panels."""
