"""Session checkpointing and forking logic."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.api.models.session import CheckpointResponse

logger = logging.getLogger(__name__)


class CheckpointService:
    """Manages session checkpoints and forking.

    Wraps the existing Paradigm CheckpointManager and adds
    session-level operations (list, fork).
    """

    def __init__(self, database: Any | None = None) -> None:
        self._db = database
        self._checkpoints: dict[str, list[CheckpointResponse]] = {}

    def list_checkpoints(self, session_id: str) -> list[CheckpointResponse]:
        """List all checkpoints for a session."""
        return self._checkpoints.get(session_id, [])

    def add_checkpoint(
        self,
        session_id: str,
        phase: str,
        round_number: int,
        hypothesis: str | None = None,
        key_findings: list[str] | None = None,
    ) -> CheckpointResponse:
        """Record a checkpoint."""
        checkpoint = CheckpointResponse(
            checkpoint_id=f"ckpt-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            phase=phase,
            round_number=round_number,
            hypothesis=hypothesis,
            key_findings=key_findings or [],
            created_at=datetime.now(timezone.utc),
        )
        if session_id not in self._checkpoints:
            self._checkpoints[session_id] = []
        self._checkpoints[session_id].append(checkpoint)
        return checkpoint

    async def fork_from_checkpoint(self, checkpoint_id: str) -> str:
        """Fork a new session from a checkpoint.

        Returns:
            New session ID.

        Note:
            Full implementation requires deep-copying engine state,
            which is deferred to a future iteration. For now, returns
            a placeholder session ID.
        """
        new_session_id = f"session-{uuid.uuid4().hex[:12]}"
        logger.info(
            "Fork requested from checkpoint %s -> %s (stub)",
            checkpoint_id,
            new_session_id,
        )
        return new_session_id
