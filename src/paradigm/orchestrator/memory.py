"""Memory generation handler — extracted from OrchestrationEngine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from paradigm.logging.events import EventType

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine

# Post-cycle reflection makes one LLM call per agent. It is best-effort and runs
# as the LAST step of a cycle, so a stuck call must NOT block the cycle from
# finalizing (otherwise the run never reaches its terminal state and the UI
# stalls forever). Bound it so completion is guaranteed.
_REFLECTION_TIMEOUT_S = 120.0


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
            thread_id=self._engine.state.thread_id,
        )
        return [e.content for e in events if isinstance(e.content, dict)]

    def _build_outcome_summary(self, outcome: str) -> str:
        """Cycle facts for reflection memories (cross-cycle lessons, T3c).

        Memories that NAME the repository datasets fetched, the data-provenance
        mix, and the judge score let future cycles on similar topics start from
        validated sources and methods instead of relearning them.
        """
        engine = self._engine
        parts = [f"Research cycle ended with status: {outcome}."]
        try:
            fetched = sorted(getattr(engine._literature, "fetched_dataset_ids", set()) or [])
            if fetched:
                parts.append(
                    "Repository datasets fetched and used: " + ", ".join(fetched[:8]) + "."
                )
            meta = engine.state.experiment_metadata
            if meta:
                from collections import Counter

                prov = Counter(str(m.get("data_provenance", "?")) for m in meta)
                parts.append(
                    "Experiment data provenance: "
                    + ", ".join(f"{v} {k}" for k, v in prov.most_common())
                    + "."
                )
            if getattr(engine.state, "loop_backs_used", 0):
                parts.append(f"PI loop-backs used: {engine.state.loop_backs_used}.")
            thread = engine._db.get_thread(engine.state.thread_id)
            paper_id = thread.get("current_draft_id") if thread else None
            if paper_id:
                import json as _json

                raw = (engine._db.get_paper(paper_id) or {}).get("judge_scores")
                js = _json.loads(raw) if isinstance(raw, str) and raw else raw
                if isinstance(js, dict) and "composite" in js:
                    parts.append(f"Quality-judge composite: {js['composite']}/10.")
        except Exception:  # facts are garnish — never block memory generation
            pass
        return " ".join(parts)

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
            thread = engine._db.get_thread(engine.state.thread_id)
            outcome = thread.get("status", "completed") if thread else "completed"
            _reflection_provider = engine._config.get_provider()
            reflections = await asyncio.wait_for(
                generate_reflections(
                    agents=engine.state.agents,
                    messages=all_messages,
                    seed_prompt=engine.state.seed_prompt,
                    thread_id=engine.state.thread_id,
                    outcome_summary=self._build_outcome_summary(outcome),
                    provider=_reflection_provider,
                    model=_reflection_provider.default_model,
                    database=engine._db,
                ),
                timeout=_REFLECTION_TIMEOUT_S,
            )
            total = sum(len(r.memories) for r in reflections)
            for r in reflections:
                engine._memory_store.add_memories(r.memories)
            engine._display.memory_stored(total, len(reflections))
            engine._logger.log(
                EventType.MEMORY_GENERATED,
                content={
                    "thread_id": engine.state.thread_id,
                    "total_memories": total,
                    "agents": [r.agent_id for r in reflections],
                },
                thread_id=engine.state.thread_id,
            )
        except Exception as e:
            engine._display.memory_error(e)
