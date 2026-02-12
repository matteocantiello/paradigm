"""Agent turn-taking scheduler."""

import random
from collections import deque
from typing import Protocol, runtime_checkable

from paradigm.orchestrator.phases import ResearchPhase


@runtime_checkable
class HasAgentId(Protocol):
    """Protocol for objects with an agent_id attribute."""

    agent_id: str


# Priority orderings per phase: which roles speak first
_PHASE_PRIORITIES: dict[ResearchPhase, list[str]] = {
    ResearchPhase.IDEATION: [
        "theorist",
        "synthesizer",
        "analyst",
        "experimentalist",
        "writer",
        "skeptic",
    ],
    ResearchPhase.PLANNING: [
        "experimentalist",
        "analyst",
        "theorist",
        "synthesizer",
        "skeptic",
        "writer",
    ],
}


def _extract_role(agent_id: str) -> str:
    """Extract role name from agent_id like 'theorist-0'."""
    parts = agent_id.rsplit("-", 1)
    return parts[0] if len(parts) > 1 and parts[1].isdigit() else agent_id


class Scheduler:
    """Manages agent speaking order within rounds."""

    def __init__(
        self,
        agents: list[HasAgentId],
        mode: str = "phase_appropriate",
        seed: int | None = None,
    ) -> None:
        """Initialize scheduler.

        Args:
            agents: List of agents (anything with agent_id attribute).
            mode: Scheduling mode - "round_robin", "phase_appropriate", or "random".
            seed: Random seed for reproducibility (used in random mode).
        """
        self._agents = list(agents)
        self._mode = mode
        self._seed = seed
        self._rng = random.Random(seed)
        self._order: deque[str] = deque(a.agent_id for a in self._agents)
        self._round = 0

    def get_speaker_order(self, phase: ResearchPhase) -> list[str]:
        """Get the speaking order for the current round in a given phase.

        Args:
            phase: Current research phase.

        Returns:
            List of agent_ids in speaking order.
        """
        if self._mode == "round_robin":
            return list(self._order)

        if self._mode == "random":
            ids = list(self._order)
            self._rng.shuffle(ids)
            return ids

        # phase_appropriate: sort by role priority for this phase
        priorities = _PHASE_PRIORITIES.get(phase)
        if priorities is None:
            return list(self._order)

        def _sort_key(agent_id: str) -> int:
            role = _extract_role(agent_id)
            try:
                return priorities.index(role)
            except ValueError:
                return len(priorities)

        return sorted(self._order, key=_sort_key)

    def advance_round(self) -> None:
        """Advance to the next round, rotating agent order for round_robin."""
        self._round += 1
        self._order.rotate(-1)

    def reset(self) -> None:
        """Reset to initial state."""
        self._round = 0
        self._order = deque(a.agent_id for a in self._agents)
        self._rng = random.Random(self._seed)
