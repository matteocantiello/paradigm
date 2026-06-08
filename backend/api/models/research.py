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
    # Broad arXiv-style field tags (cross-pollination → multiple), classified by an
    # agent from the prompt and refreshed from the finished paper.
    topics: list[str] | None = None
    # Set when this cycle continues an earlier one (resume).
    resumed_from: str | None = None
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
