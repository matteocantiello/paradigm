"""Rich renderable builders for the Paradigm display system.

All functions return Rich renderables (Panel, Table, Text, Rule, etc.)
that can be printed directly or composed into a Live layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from paradigm.display.theme import (
    AGENT_STYLES,
    DEBATE_BORDER_STYLE,
    DIM_STYLE,
    ERROR_STYLE,
    PHASE_DISPLAY_ORDER,
    PHASE_ICONS,
    SUCCESS_STYLE,
    WARNING_STYLE,
)

if TYPE_CHECKING:
    from paradigm.display.manager import DisplayState


# ---------------------------------------------------------------------------
# Phase bar — horizontal phase indicator with ✓/●/○
# ---------------------------------------------------------------------------


def build_phase_bar(state: DisplayState) -> Text:
    """Build a horizontal phase progress indicator.

    Completed phases show ✓, current shows ●, future shows ○.
    """
    parts = Text()
    completed = set(state.completed_phases)

    for i, phase in enumerate(PHASE_DISPLAY_ORDER):
        icon = PHASE_ICONS.get(phase, "")
        name = phase.value.upper()

        if phase in completed:
            parts.append(f" \u2713 {name} ", style="green")
        elif phase == state.current_phase:
            parts.append(f" \u25cf {icon} {name} ", style="bold bright_white")
        else:
            parts.append(f" \u25cb {name} ", style="dim")

        if i < len(PHASE_DISPLAY_ORDER) - 1:
            parts.append("\u2192", style="dim")

    return parts


# ---------------------------------------------------------------------------
# Stats bar — round, papers, searches, tokens, elapsed
# ---------------------------------------------------------------------------


def build_stats_bar(state: DisplayState) -> Text:
    """Build a compact stats summary line."""
    elapsed = state.elapsed_seconds
    minutes, seconds = divmod(int(elapsed), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        time_str = f"{hours}h{minutes:02d}m"
    elif minutes:
        time_str = f"{minutes}m{seconds:02d}s"
    else:
        time_str = f"{seconds}s"

    tokens_k = state.total_tokens / 1000

    parts = Text()
    if state.max_rounds > 0:
        parts.append(f"Round {state.round_num}/{state.max_rounds}", style="bold")
        parts.append("  \u2502  ", style="dim")
    parts.append(f"\U0001f4c4 {state.papers_count} papers", style="cyan")
    parts.append("  \u2502  ", style="dim")
    parts.append(f"\U0001f50d {state.total_searches} searches", style="yellow")
    parts.append("  \u2502  ", style="dim")
    parts.append(f"\U0001f4b0 {tokens_k:.1f}K tokens", style="magenta")
    parts.append("  \u2502  ", style="dim")
    parts.append(f"\u23f1 {time_str}", style="dim")

    return parts


# ---------------------------------------------------------------------------
# Phase banner — prominent display on phase transitions
# ---------------------------------------------------------------------------


def build_phase_banner(phase_name: str, state: DisplayState) -> Panel:
    """Build a prominent phase transition banner."""
    from paradigm.orchestrator.phases import ResearchPhase

    try:
        phase = ResearchPhase(phase_name.lower())
        icon = PHASE_ICONS.get(phase, "")
    except ValueError:
        icon = ""

    title_text = Text(f" {icon} {phase_name.upper()} ", style="bold bright_white")

    # Include phase bar underneath
    content = Text()
    content.append_text(build_phase_bar(state))
    content.append("\n")
    content.append_text(build_stats_bar(state))

    return Panel(
        content,
        title=title_text,
        border_style="blue",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Resource table — compact table of ingested resources at startup
# ---------------------------------------------------------------------------


def build_resource_table(resources: list[dict[str, str]]) -> Table:
    """Build a compact table of ingested resources."""
    table = Table(title="Resources", show_header=True, border_style="dim")
    table.add_column("Type", style="cyan", width=12)
    table.add_column("Name", style="white")
    table.add_column("Status", style="green", width=10)

    for r in resources:
        table.add_row(r.get("type", ""), r.get("name", ""), r.get("status", "OK"))

    return table


# ---------------------------------------------------------------------------
# Debate panel
# ---------------------------------------------------------------------------


def build_debate_panel(challenger_id: str, defender_id: str, topic: str) -> Panel:
    """Build a prominent debate announcement panel."""
    challenger_style = _agent_style(challenger_id)
    defender_style = _agent_style(defender_id)

    content = Text()
    content.append(f"{_agent_icon(challenger_id)} ", style=challenger_style)
    content.append(challenger_id, style=f"bold {challenger_style}")
    content.append("  vs  ", style="bold")
    content.append(f"{_agent_icon(defender_id)} ", style=defender_style)
    content.append(defender_id, style=f"bold {defender_style}")
    content.append(f"\n{topic[:80]}", style="italic")

    return Panel(
        content,
        title="Debate",
        border_style=DEBATE_BORDER_STYLE,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Execution table — experiment status with indicators
# ---------------------------------------------------------------------------


def build_execution_table(experiments: list[dict[str, str]]) -> Table:
    """Build a table of experiment execution results."""
    table = Table(title="Experiments", show_header=True, border_style="dim")
    table.add_column("Experiment", style="white")
    table.add_column("Status", width=8, justify="center")
    table.add_column("Details", style="dim")

    status_map = {
        "success": ("[green]\u2713[/green]", "green"),
        "failure": ("[red]\u2717[/red]", "red"),
        "timeout": ("[yellow]\u23f1[/yellow]", "yellow"),
        "rejected": ("[red]\u2717[/red]", "red"),
        "running": ("[cyan]\u27f3[/cyan]", "cyan"),
    }

    for exp in experiments:
        status = exp.get("status", "").lower()
        indicator, _ = status_map.get(status, ("\u25fb", "dim"))
        table.add_row(exp.get("name", ""), indicator, exp.get("details", ""))

    return table


# ---------------------------------------------------------------------------
# Review scorecard — iteration table with recommendations
# ---------------------------------------------------------------------------


def build_review_scorecard(
    iterations: list[dict[str, str]],
) -> Table:
    """Build a review iteration scorecard."""
    table = Table(title="Internal Review", show_header=True, border_style="dim")
    table.add_column("#", width=3, justify="center")
    table.add_column("Recommendation", style="bold")
    table.add_column("Changes", width=8, justify="center")

    for it in iterations:
        rec = it.get("recommendation", "?")
        style = "green" if rec == "accept" else "yellow"
        table.add_row(
            it.get("iteration", ""),
            Text(rec, style=style),
            it.get("changes", ""),
        )

    return table


# ---------------------------------------------------------------------------
# Peer review scorecard — reviewer scores table
# ---------------------------------------------------------------------------


def build_peer_review_scorecard(
    reviews: list[dict[str, object]],
) -> Table:
    """Build a peer review scores table."""
    table = Table(title="Peer Review", show_header=True, border_style="dim")
    table.add_column("Reviewer", style="bold")
    table.add_column("Recommendation")
    table.add_column("Avg Score", justify="center")

    for r in reviews:
        rec = str(r.get("recommendation", "?"))
        rec_style = {
            "accept": "bold green",
            "minor_revision": "yellow",
            "major_revision": "orange3",
            "reject": "bold red",
        }.get(rec, "white")

        table.add_row(
            str(r.get("reviewer_id", "")),
            Text(rec, style=rec_style),
            str(r.get("avg_score", "")),
        )

    return table


# ---------------------------------------------------------------------------
# Final summary panel
# ---------------------------------------------------------------------------


def build_final_summary(
    *,
    total_k: float,
    input_k: float,
    output_k: float,
    time_str: str,
    state: DisplayState,
) -> Panel:
    """Build a comprehensive end-of-cycle summary panel."""
    content = Text()
    content.append_text(build_phase_bar(state))
    content.append("\n\n")

    # Token usage
    content.append("Token usage: ", style="bold")
    content.append(f"{total_k:.1f}K total", style="magenta")
    content.append(f" ({input_k:.1f}K input, {output_k:.1f}K output)\n", style="dim")

    # Elapsed time
    content.append("Elapsed: ", style="bold")
    content.append(f"{time_str}\n", style="dim")

    # Stats
    content.append("Papers found: ", style="bold")
    content.append(f"{state.papers_count}\n", style="cyan")
    content.append("Searches: ", style="bold")
    content.append(f"{state.total_searches}\n", style="yellow")

    return Panel(
        content,
        title="Research Cycle Complete",
        border_style="green",
        padding=(1, 2),
    )


# ---------------------------------------------------------------------------
# Status messages (colored one-liners)
# ---------------------------------------------------------------------------


def build_status_message(message: str, level: str = "info") -> Text:
    """Build a styled status message."""
    style_map = {
        "info": "bold bright_white",
        "success": SUCCESS_STYLE,
        "warning": WARNING_STYLE,
        "error": ERROR_STYLE,
    }
    return Text(message, style=style_map.get(level, ""))


# ---------------------------------------------------------------------------
# Agent panel for live layout
# ---------------------------------------------------------------------------


def build_agents_panel(state: DisplayState) -> Panel:
    """Build a panel showing active agents and their current activity."""
    if not state.active_agents:
        content = Text("No agent activity yet", style=DIM_STYLE)
    else:
        content = Text()
        for agent_id, activity in list(state.active_agents.items())[-8:]:
            icon = _agent_icon(agent_id)
            style = _agent_style(agent_id)
            content.append(f"{icon} ", style=style)
            content.append(agent_id, style=f"bold {style}")
            content.append(f"  {activity}\n", style=DIM_STYLE)

    return Panel(content, title="Agents", border_style="blue", padding=(0, 1))


# ---------------------------------------------------------------------------
# Events panel for live layout
# ---------------------------------------------------------------------------


def build_events_panel(state: DisplayState) -> Panel:
    """Build a panel showing recent events."""
    if not state.recent_events:
        content = Text("Waiting for events...", style=DIM_STYLE)
    else:
        content = Text()
        for event in state.recent_events[-12:]:
            time_str = event.get("time", "")
            event_type = event.get("type", "")
            message = event.get("message", "")

            type_style = {
                "phase": "bold blue",
                "agent": "cyan",
                "search": "yellow",
                "debate": "gold1",
                "experiment": "green",
                "writing": "cyan",
                "review": "magenta",
                "error": "red",
                "warning": "yellow",
                "skip": "dim",
                "info": "white",
            }.get(event_type, "white")

            content.append(f"[{time_str}] ", style=DIM_STYLE)
            content.append(f"{message}\n", style=type_style)

    return Panel(content, title="Events", border_style="dim", padding=(0, 1))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_style(agent_id: str) -> str:
    """Get the Rich color style for an agent based on its role prefix."""
    role = agent_id.rsplit("-", 1)[0] if "-" in agent_id else agent_id
    return AGENT_STYLES.get(role, {}).get("color", "white")


def _agent_icon(agent_id: str) -> str:
    """Get the icon for an agent based on its role prefix."""
    role = agent_id.rsplit("-", 1)[0] if "-" in agent_id else agent_id
    return AGENT_STYLES.get(role, {}).get("icon", "\u2022")
