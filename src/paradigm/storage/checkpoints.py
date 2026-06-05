"""Checkpoint compression for research threads."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from paradigm.logging.events import EventLogger, EventType
from paradigm.storage.database import Database

if TYPE_CHECKING:
    from paradigm.agents.providers import LLMProvider

logger = logging.getLogger(__name__)

_COMPRESSION_PROMPT = """\
You are summarizing a research discussion for checkpoint compression.
Given the conversation below, extract a structured JSON summary.

{previous_context}

## New Messages

{messages_text}

---

Respond with ONLY a JSON object (no markdown fences) with these fields:
- "hypothesis": The current working hypothesis (string or null if none yet)
- "key_findings": List of key findings or insights so far (list of strings)
- "open_questions": Unresolved questions (list of strings)
- "next_steps": Proposed next steps (list of strings)
- "conversation_summary": A concise narrative summary of the discussion (string)
"""


class Checkpoint(BaseModel):
    """Compressed research thread checkpoint."""

    thread_id: str
    phase: str
    round_number: int
    hypothesis: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    conversation_summary: str = ""

    def to_context_string(self) -> str:
        """Format as markdown for agent context windows.

        Returns:
            Markdown-formatted checkpoint summary.
        """
        parts = [
            f"## Research Checkpoint (Phase: {self.phase}, Round: {self.round_number})",
        ]

        if self.hypothesis:
            parts.append(f"\n### Hypothesis\n{self.hypothesis}")

        if self.key_findings:
            parts.append("\n### Key Findings")
            for finding in self.key_findings:
                parts.append(f"- {finding}")

        if self.open_questions:
            parts.append("\n### Open Questions")
            for question in self.open_questions:
                parts.append(f"- {question}")

        if self.next_steps:
            parts.append("\n### Next Steps")
            for step in self.next_steps:
                parts.append(f"- {step}")

        if self.conversation_summary:
            parts.append(f"\n### Discussion Summary\n{self.conversation_summary}")

        return "\n".join(parts)


class CheckpointManager:
    """Creates and manages checkpoints for research threads."""

    def __init__(
        self,
        database: Database,
        provider: LLMProvider,
        event_logger: EventLogger | None = None,
        compression_model: str = "claude-sonnet-4-5-20250929",
    ) -> None:
        """Initialize checkpoint manager.

        Args:
            database: Database for persistence.
            provider: LLM provider for compression calls.
            event_logger: Optional event logger.
            compression_model: Model to use for compression.
        """
        self._db = database
        self._provider = provider
        self._logger = event_logger
        self._model = compression_model

    async def create_checkpoint(
        self,
        thread_id: str,
        phase: str,
        round_number: int,
        messages: list[dict[str, str]],
        previous_checkpoint: Checkpoint | None = None,
    ) -> Checkpoint:
        """Compress conversation into a checkpoint via LLM.

        Args:
            thread_id: Research thread ID.
            phase: Current phase.
            round_number: Current round number.
            messages: Recent messages as list of {from, content} dicts.
            previous_checkpoint: Previous checkpoint to build on.

        Returns:
            New Checkpoint with compressed summary.
        """
        # Format messages for compression
        messages_text = "\n\n".join(
            f"**{m.get('from', 'unknown')}**: {m.get('content', '')}" for m in messages
        )

        previous_context = ""
        if previous_checkpoint:
            previous_context = (
                "## Previous Checkpoint\n\n" + previous_checkpoint.to_context_string()
            )

        prompt = _COMPRESSION_PROMPT.format(
            previous_context=previous_context,
            messages_text=messages_text,
        )

        # Call LLM for compression
        raw, input_tokens, output_tokens = await asyncio.to_thread(
            self._provider.complete,
            model=self._model,
            max_tokens=2048,
            temperature=0.3,
            system="",
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse JSON response
        summary = self._parse_summary(raw)

        checkpoint = Checkpoint(
            thread_id=thread_id,
            phase=phase,
            round_number=round_number,
            hypothesis=summary.get("hypothesis"),
            key_findings=summary.get("key_findings", []),
            open_questions=summary.get("open_questions", []),
            next_steps=summary.get("next_steps", []),
            conversation_summary=summary.get("conversation_summary", ""),
        )

        # Persist to database
        self._db.update_thread(
            thread_id,
            current_phase=phase,
            hypothesis=checkpoint.hypothesis,
            key_findings=checkpoint.key_findings,
            open_questions=checkpoint.open_questions,
            next_steps=checkpoint.next_steps,
            checkpoint_summary=checkpoint.conversation_summary,
        )

        if self._logger:
            self._logger.log(
                EventType.CHECKPOINT_CREATED,
                content={
                    "round_number": round_number,
                    "phase": phase,
                    "hypothesis": checkpoint.hypothesis,
                    "findings_count": len(checkpoint.key_findings),
                },
                thread_id=thread_id,
                phase=phase,
            )

        # Track token usage for compression call
        self._db.record_token_usage(
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            agent_id="checkpoint_compressor",
            thread_id=thread_id,
        )

        return checkpoint

    def load_checkpoint(self, thread_id: str) -> Checkpoint | None:
        """Load the latest checkpoint from the database.

        Args:
            thread_id: Thread ID.

        Returns:
            Checkpoint if thread exists and has data, None otherwise.
        """
        thread = self._db.get_thread(thread_id)
        if thread is None:
            return None

        # Only return if there's actual checkpoint data
        summary = thread.get("checkpoint_summary")
        if not summary:
            return None

        # Deserialize JSON fields
        def _load_json(val: str | list | None) -> list[str]:
            if val is None:
                return []
            if isinstance(val, list):
                return val
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []

        return Checkpoint(
            thread_id=thread_id,
            phase=thread.get("current_phase", ""),
            round_number=0,  # DB doesn't track round number directly
            hypothesis=thread.get("hypothesis"),
            key_findings=_load_json(thread.get("key_findings")),
            open_questions=_load_json(thread.get("open_questions")),
            next_steps=_load_json(thread.get("next_steps")),
            conversation_summary=summary,
        )

    @staticmethod
    def _parse_summary(raw: str) -> dict:
        """Parse Claude's JSON response with fallback handling.

        Args:
            raw: Raw text response from Claude.

        Returns:
            Parsed dict with summary fields.
        """
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse checkpoint JSON, using fallback")
            return {
                "hypothesis": None,
                "key_findings": [],
                "open_questions": [],
                "next_steps": [],
                "conversation_summary": raw[:500],
            }
