"""Research cycle schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CycleStatus(str, Enum):
    """Status of a research cycle."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"
    # Cut off mid-run (process restart / crash / dropped connection). Persisted
    # so the research tab can show it as resumable.
    INTERRUPTED = "interrupted"


class ResearchCycleCreate(BaseModel):
    """Request body for creating a new research cycle."""

    seed_prompt: str = Field(..., min_length=1, max_length=10000)
    mode: str = Field(default="directed", pattern=r"^(directed|explore|test)$")
    team_roles: list[str] | None = None
    # Interactive supervision: the user approves key decisions during the run
    # (hypothesis selection, experiment plan, phase transitions).
    interactive: bool = False
    # Model tier for this cycle: "premium" (top closed models) or "open"
    # (open weights). None = whatever the active config runs.
    model_tier: str | None = Field(default=None, pattern=r"^(premium|open)$")
    config_overrides: dict[str, object] | None = None


class ResumeRequest(BaseModel):
    """Request body for resuming/continuing a cycle (optional steering note)."""

    comment: str | None = Field(default=None, max_length=10000)


class ResearchCycleResponse(BaseModel):
    """Response body for a research cycle."""

    cycle_id: str
    seed_prompt: str
    mode: str
    status: CycleStatus
    team_roles: list[str] | None = None
    session_id: str | None = None
    thread_id: str | None = None
    paper_id: str | None = None
    current_phase: str | None = None
    # Short human-readable reason for a terminal failed/aborted cycle (e.g. the
    # error summary, or "stopped before completion"), shown in the research tab.
    status_detail: str | None = None
    # Broad arXiv-style field tags (cross-pollination → multiple), classified by an
    # agent from the prompt and refreshed from the finished paper.
    topics: list[str] | None = None
    # Set when this cycle continues an earlier one (resume).
    resumed_from: str | None = None
    # Host paths of datasets uploaded for this cycle (staged into the sandbox
    # shared data dir when the session starts).
    datasets: list[str] | None = None
    # Interactive supervision: the user approves key decisions during the run.
    interactive: bool = False
    # Model tier this cycle runs on ("premium" | "open"; None = active config).
    model_tier: str | None = None
    # End-of-run stats, backfilled from the thread for the terminal summary
    # (None when unknown — e.g. before the cycle has a thread).
    total_tokens: int | None = None
    elapsed_seconds: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ResearchCycleList(BaseModel):
    """Paginated list of research cycles."""

    items: list[ResearchCycleResponse]
    total: int
    offset: int
    limit: int


class ResearchStats(BaseModel):
    """Headline counts for the dashboard overview."""

    total_cycles: int = 0
    papers_published: int = 0
    total_tokens: int = 0
