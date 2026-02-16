"""Color theme, agent styles, and phase icons for the Paradigm display system."""

from paradigm.orchestrator.phases import ResearchPhase

# ---------------------------------------------------------------------------
# Agent role → visual style
# ---------------------------------------------------------------------------

AGENT_STYLES: dict[str, dict[str, str]] = {
    "theorist": {"color": "blue", "icon": "\U0001f52d"},  # 🔭
    "analyst": {"color": "orange3", "icon": "\U0001f4ca"},  # 📊
    "experimentalist": {"color": "green", "icon": "\U0001f9ea"},  # 🧪
    "synthesizer": {"color": "magenta", "icon": "\U0001f517"},  # 🔗
    "skeptic": {"color": "red", "icon": "\U0001f50d"},  # 🔍
    "writer": {"color": "cyan", "icon": "\u270d\ufe0f"},  # ✍️
    "editor": {"color": "yellow", "icon": "\U0001f4dd"},  # 📝
    "reviewer": {"color": "bright_white", "icon": "\U0001f4cb"},  # 📋
}

# ---------------------------------------------------------------------------
# Phase → icon mapping
# ---------------------------------------------------------------------------

PHASE_ICONS: dict[ResearchPhase, str] = {
    ResearchPhase.SEEDING: "\U0001f331",  # 🌱
    ResearchPhase.IDEATION: "\U0001f4a1",  # 💡
    ResearchPhase.PLANNING: "\U0001f4d0",  # 📐
    ResearchPhase.LITERATURE: "\U0001f4da",  # 📚
    ResearchPhase.EXECUTION: "\u2699\ufe0f",  # ⚙️
    ResearchPhase.WRITING: "\U0001f4dd",  # 📝
    ResearchPhase.INTERNAL_REVIEW: "\U0001f50e",  # 🔎
    ResearchPhase.SUBMITTED: "\U0001f4e8",  # 📨
    ResearchPhase.PEER_REVIEW: "\U0001f9d1\u200d\u2696\ufe0f",  # 🧑‍⚖️
    ResearchPhase.REVISION: "\U0001f504",  # 🔄
    ResearchPhase.PUBLISHED: "\u2705",  # ✅
    ResearchPhase.REJECTED: "\u274c",  # ❌
}

# ---------------------------------------------------------------------------
# Phase display order (for progress bar rendering)
# ---------------------------------------------------------------------------

PHASE_DISPLAY_ORDER: list[ResearchPhase] = [
    ResearchPhase.SEEDING,
    ResearchPhase.IDEATION,
    ResearchPhase.PLANNING,
    ResearchPhase.EXECUTION,
    ResearchPhase.WRITING,
    ResearchPhase.INTERNAL_REVIEW,
    ResearchPhase.SUBMITTED,
    ResearchPhase.PEER_REVIEW,
    ResearchPhase.PUBLISHED,
]

# ---------------------------------------------------------------------------
# Status indicators
# ---------------------------------------------------------------------------

STATUS_ICONS: dict[str, str] = {
    "success": "\u2713",  # ✓
    "failure": "\u2717",  # ✗
    "running": "\u27f3",  # ⟳
    "pending": "\u25fb",  # ◻
    "active": "\u25ba",  # ►
    "warning": "\u26a0\ufe0f",  # ⚠️
    "skip": "[dim]skip[/dim]",
}

# ---------------------------------------------------------------------------
# Color constants for non-agent elements
# ---------------------------------------------------------------------------

PHASE_BANNER_STYLE = "bold bright_white on blue"
STATS_STYLE = "dim"
WARNING_STYLE = "yellow"
ERROR_STYLE = "bold red"
SUCCESS_STYLE = "bold green"
DIM_STYLE = "dim"
DEBATE_BORDER_STYLE = "gold1"
