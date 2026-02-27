"""Routes user interventions to agents via asyncio.Queue."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentRouter:
    """Routes user interventions and messages to specific agents.

    Each session has a queue for pending interventions. The orchestration
    engine can poll this queue to inject user guidance into agent prompts.
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    def get_queue(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Get or create the intervention queue for a session."""
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    async def send_intervention(
        self,
        session_id: str,
        target_agent: str | None,
        action: str,
        content: str,
    ) -> None:
        """Queue an intervention for delivery to an agent."""
        queue = self.get_queue(session_id)
        await queue.put(
            {
                "target_agent": target_agent,
                "action": action,
                "content": content,
            }
        )
        logger.info(
            "Intervention queued for session %s -> %s: %s",
            session_id,
            target_agent or "all",
            action,
        )

    async def get_pending(self, session_id: str, timeout: float = 0.0) -> list[dict[str, Any]]:
        """Get all pending interventions for a session (non-blocking)."""
        queue = self.get_queue(session_id)
        items: list[dict[str, Any]] = []
        try:
            while True:
                item = queue.get_nowait()
                items.append(item)
        except asyncio.QueueEmpty:
            pass
        return items

    def cleanup(self, session_id: str) -> None:
        """Remove the queue for a completed session."""
        self._queues.pop(session_id, None)
