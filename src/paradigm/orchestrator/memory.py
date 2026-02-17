"""Memory generation handler — extracted from OrchestrationEngine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from paradigm.logging.events import EventType

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


class MemoryHandler:
    """Handles post-cycle episodic memory generation via reflection."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    def _collect_all_messages(self) -> list[dict[str, Any]]:
        """Collect all agent messages from the event log for this thread.

        Returns:
            List of message dicts with keys like 'from', 'to', 'type', 'content'.
        """
        events = self._engine._logger.read_events(
            event_type=EventType.AGENT_MESSAGE,
            thread_id=self._engine._thread_id,
        )
        return [e.content for e in events if isinstance(e.content, dict)]

    async def run_memory_generation(self) -> None:
        """Generate agent episodic memories via reflection.

        Short-circuits if memory_store is None or memory is disabled in config.
        """
        engine = self._engine
        if engine._memory_store is None or not engine._config.memory.enabled:
            return

        try:
            from paradigm.agents.memory import generate_reflections

            engine._display.memory_generating()
            all_messages = self._collect_all_messages()
            thread = engine._db.get_thread(engine._thread_id)
            outcome = thread.get("status", "completed") if thread else "completed"
            _reflection_provider = engine._config.get_provider()
            reflections = await generate_reflections(
                agents=engine._agents,
                messages=all_messages,
                seed_prompt=engine._seed_prompt,
                thread_id=engine._thread_id,
                outcome_summary=f"Research cycle ended with status: {outcome}",
                provider=_reflection_provider,
                model=_reflection_provider.default_model,
                database=engine._db,
            )
            total = sum(len(r.memories) for r in reflections)
            for r in reflections:
                engine._memory_store.add_memories(r.memories)
            engine._display.memory_stored(total, len(reflections))
            engine._logger.log(
                EventType.MEMORY_GENERATED,
                content={
                    "thread_id": engine._thread_id,
                    "total_memories": total,
                    "agents": [r.agent_id for r in reflections],
                },
                thread_id=engine._thread_id,
            )
        except Exception as e:
            engine._display.memory_error(e)
