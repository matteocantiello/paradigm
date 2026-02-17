"""Live layout assembly and update logic for the Paradigm Rich UI.

Provides the persistent, auto-refreshing Live display that shows
phase progress, active agents, and an event feed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.layout import Layout
from rich.live import Live

from paradigm.display.components import (
    build_agent_messages_panel,
    build_agents_panel,
    build_events_panel,
    build_phase_bar,
    build_stats_bar,
)

if TYPE_CHECKING:
    from paradigm.display.manager import DisplayState

from rich.panel import Panel
from rich.text import Text


def create_live_display(console: Console) -> Live:
    """Create a Live display instance.

    Args:
        console: Rich Console to render to.

    Returns:
        Configured Live instance (not yet started).
    """
    # Start with a minimal placeholder — actual content comes from updates
    placeholder = Text("Initializing...", style="dim")
    return Live(
        placeholder,
        console=console,
        refresh_per_second=4,
        transient=True,
    )


def build_live_layout(state: DisplayState) -> Layout:
    """Build the full live layout from current state.

    Layout structure:
        ┌──────────────────────────────┐
        │       Phase Bar + Stats      │  (header)
        ├────────┬──────────┬──────────┤
        │ Agents │ Messages │  Events  │  (body)
        └────────┴──────────┴──────────┘

    Args:
        state: Current display state.

    Returns:
        Rich Layout renderable.
    """
    layout = Layout()

    # Header: phase bar + stats
    header_content = Text()
    header_content.append_text(build_phase_bar(state))
    header_content.append("\n")
    header_content.append_text(build_stats_bar(state))

    header = Panel(header_content, border_style="blue", padding=(0, 1))

    # Body: agents + messages + events side by side
    agents_panel = build_agents_panel(state)
    messages_panel = build_agent_messages_panel(state)
    events_panel = build_events_panel(state)

    layout.split_column(
        Layout(header, name="header", size=4),
        Layout(name="body"),
    )
    layout["body"].split_row(
        Layout(agents_panel, name="agents", ratio=1),
        Layout(messages_panel, name="messages", ratio=2),
        Layout(events_panel, name="events", ratio=2),
    )

    return layout
