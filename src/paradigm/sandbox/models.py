"""Data models for the computational sandbox."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ExecutionStatus(StrEnum):
    """Status of a code execution."""

    PENDING = "pending"
    SCANNING = "scanning"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"


class OutputFile(BaseModel):
    """A file produced by code execution."""

    filename: str
    path: str
    size_bytes: int


class SafetyVerdict(BaseModel):
    """Result of safety scanning code."""

    safe: bool
    violations: list[str] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def summary(self) -> str:
        """Human-readable summary of the verdict."""
        if self.safe:
            return "Code passed safety scan."
        return f"Code rejected: {'; '.join(self.violations)}"


class ExecutionRequest(BaseModel):
    """Request to execute code in the sandbox."""

    code: str
    agent_id: str
    thread_id: str
    language: str = "python"
    timeout: int | None = None  # Override default timeout


class ExecutionResult(BaseModel):
    """Result of a code execution."""

    request: ExecutionRequest
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_seconds: float | None = None
    output_files: list[OutputFile] = Field(default_factory=list)
    safety_verdict: SafetyVerdict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
