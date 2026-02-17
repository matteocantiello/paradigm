"""Structured event logging system."""

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Types of events that can be logged."""

    AGENT_MESSAGE = "agent_message"
    API_CALL = "api_call"
    CODE_EXECUTION = "code_execution"
    STATE_CHANGE = "state_change"
    ERROR = "error"
    PHASE_TRANSITION = "phase_transition"
    LITERATURE_SEARCH = "literature_search"
    CHECKPOINT_CREATED = "checkpoint_created"
    PAPER_SUBMITTED = "paper_submitted"
    REVIEW_COMPLETED = "review_completed"
    PUBLICATION = "publication"
    MEMORY_GENERATED = "memory_generated"
    DEBATE_TRIGGERED = "debate_triggered"
    LITERATURE_FOLLOW = "literature_follow"
    LITERATURE_CITED_BY = "literature_cited_by"
    LITERATURE_READ = "literature_read"
    CITATION_GROUNDING = "citation_grounding"
    NOVELTY_CHECK = "novelty_check"
    SEED_DISCOVERY = "seed_discovery"


class Event(BaseModel):
    """Structured event for logging."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: EventType
    agent_id: str | None = None
    thread_id: str | None = None
    phase: str | None = None
    content: str | dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        return self.model_dump_json(exclude_none=True)


class EventLogger:
    """JSON-lines event logger for structured logging."""

    def __init__(self, log_path: Path) -> None:
        """Initialize event logger.

        Args:
            log_path: Path to the JSONL log file
        """
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create file if it doesn't exist
        if not self.log_path.exists():
            self.log_path.touch()

    def log(
        self,
        event_type: EventType,
        content: str | dict[str, Any] | None = None,
        agent_id: str | None = None,
        thread_id: str | None = None,
        phase: str | None = None,
        **metadata: Any,
    ) -> None:
        """Log an event.

        Args:
            event_type: Type of event
            content: Event content (string or dict)
            agent_id: ID of agent involved (if applicable)
            thread_id: ID of research thread (if applicable)
            phase: Current research phase (if applicable)
            **metadata: Additional metadata to include
        """
        event = Event(
            event_type=event_type,
            agent_id=agent_id,
            thread_id=thread_id,
            phase=phase,
            content=content,
            metadata=metadata,
        )
        self._write_event(event)

    def log_agent_message(
        self,
        agent_id: str,
        thread_id: str,
        phase: str,
        message: dict[str, Any],
    ) -> None:
        """Log an agent message.

        Args:
            agent_id: ID of the agent
            thread_id: ID of the research thread
            phase: Current research phase
            message: The message dict (from, to, type, content, etc.)
        """
        self.log(
            EventType.AGENT_MESSAGE,
            content=message,
            agent_id=agent_id,
            thread_id=thread_id,
            phase=phase,
        )

    def log_api_call(
        self,
        agent_id: str | None,
        model: str,
        input_tokens: int,
        output_tokens: int,
        **metadata: Any,
    ) -> None:
        """Log a Claude API call.

        Args:
            agent_id: ID of the agent making the call
            model: Model used
            input_tokens: Input token count
            output_tokens: Output token count
            **metadata: Additional metadata
        """
        self.log(
            EventType.API_CALL,
            content={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
            agent_id=agent_id,
            **metadata,
        )

    def log_code_execution(
        self,
        agent_id: str,
        thread_id: str,
        code: str,
        success: bool,
        output: str | None = None,
        error: str | None = None,
        **metadata: Any,
    ) -> None:
        """Log a code execution event.

        Args:
            agent_id: ID of the agent
            thread_id: ID of the research thread
            code: The code that was executed
            success: Whether execution succeeded
            output: stdout/stderr output
            error: Error message if failed
            **metadata: Additional metadata
        """
        self.log(
            EventType.CODE_EXECUTION,
            content={
                "code": code,
                "success": success,
                "output": output,
                "error": error,
            },
            agent_id=agent_id,
            thread_id=thread_id,
            **metadata,
        )

    def log_error(
        self,
        error: str | Exception,
        agent_id: str | None = None,
        thread_id: str | None = None,
        **metadata: Any,
    ) -> None:
        """Log an error.

        Args:
            error: Error message or exception
            agent_id: ID of the agent (if applicable)
            thread_id: ID of the research thread (if applicable)
            **metadata: Additional metadata
        """
        error_str = str(error)
        if isinstance(error, Exception):
            metadata["exception_type"] = type(error).__name__

        self.log(
            EventType.ERROR,
            content=error_str,
            agent_id=agent_id,
            thread_id=thread_id,
            **metadata,
        )

    def log_state_change(
        self,
        thread_id: str,
        old_state: str,
        new_state: str,
        **metadata: Any,
    ) -> None:
        """Log a state/phase change.

        Args:
            thread_id: ID of the research thread
            old_state: Previous state
            new_state: New state
            **metadata: Additional metadata
        """
        self.log(
            EventType.STATE_CHANGE,
            content={"old_state": old_state, "new_state": new_state},
            thread_id=thread_id,
            **metadata,
        )

    def _write_event(self, event: Event) -> None:
        """Write event to log file.

        Args:
            event: Event to write
        """
        with open(self.log_path, "a") as f:
            f.write(event.to_json() + "\n")

    def read_events(
        self,
        event_type: EventType | None = None,
        agent_id: str | None = None,
        thread_id: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """Read events from log file with optional filtering.

        Args:
            event_type: Filter by event type
            agent_id: Filter by agent ID
            thread_id: Filter by thread ID
            limit: Maximum number of events to return (most recent)

        Returns:
            List of events matching filters
        """
        if not self.log_path.exists():
            return []

        events = []
        with open(self.log_path) as f:
            for line in f:
                try:
                    event_dict = json.loads(line)
                    event = Event(**event_dict)

                    # Apply filters
                    if event_type and event.event_type != event_type:
                        continue
                    if agent_id and event.agent_id != agent_id:
                        continue
                    if thread_id and event.thread_id != thread_id:
                        continue

                    events.append(event)
                except (json.JSONDecodeError, ValueError):
                    # Skip malformed lines
                    continue

        # Return most recent events if limit specified
        if limit:
            events = events[-limit:]

        return events
