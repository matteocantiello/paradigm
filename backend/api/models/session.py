"""Session state schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    """Status of a running session."""

    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class SessionCreate(BaseModel):
    """Request body for starting a new session."""

    config_overrides: dict[str, object] | None = None


class SessionState(BaseModel):
    """Full snapshot of a session's current state."""

    session_id: str
    cycle_id: str
    status: SessionStatus
    current_phase: str | None = None
    round_num: int = 0
    max_rounds: int = 0
    thread_id: str | None = None
    active_agents: dict[str, str] = Field(default_factory=dict)
    total_tokens: int = 0
    total_searches: int = 0
    papers_found: int = 0
    elapsed_seconds: float = 0.0
    completed_phases: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class SessionResponse(BaseModel):
    """Response body for a session."""

    session_id: str
    cycle_id: str
    status: SessionStatus
    thread_id: str | None = None
    current_phase: str | None = None
    created_at: datetime


class SessionList(BaseModel):
    """List of sessions for a cycle."""

    items: list[SessionResponse]
    total: int


class SessionHistory(BaseModel):
    """Full interaction history for a session."""

    session_id: str
    events: list[dict[str, object]]
    total: int


class CheckpointResponse(BaseModel):
    """Response body for a checkpoint."""

    checkpoint_id: str
    session_id: str
    phase: str
    round_number: int
    hypothesis: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    created_at: datetime


class CheckpointList(BaseModel):
    """List of checkpoints for a session."""

    items: list[CheckpointResponse]
    total: int
