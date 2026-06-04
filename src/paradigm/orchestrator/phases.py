"""Research phase state machine."""

from enum import StrEnum


class ResearchPhase(StrEnum):
    """Phases of the research lifecycle."""

    SEEDING = "seeding"
    IDEATION = "ideation"
    PLANNING = "planning"
    LITERATURE = "literature"
    PRE_REGISTRATION = "pre_registration"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    POST_EXECUTION = "post_execution"
    WRITING = "writing"
    INTERNAL_REVIEW = "internal"
    SUBMITTED = "submitted"
    PEER_REVIEW = "peer_review"
    REVISION = "revision"
    PUBLISHED = "published"
    REJECTED = "rejected"


# Valid phase transitions
_TRANSITIONS: dict[ResearchPhase, list[ResearchPhase]] = {
    ResearchPhase.SEEDING: [ResearchPhase.IDEATION],
    ResearchPhase.IDEATION: [ResearchPhase.PLANNING],
    ResearchPhase.PLANNING: [
        ResearchPhase.LITERATURE,
        ResearchPhase.PRE_REGISTRATION,
        ResearchPhase.EXECUTION,
        ResearchPhase.WRITING,
    ],
    ResearchPhase.LITERATURE: [
        ResearchPhase.PRE_REGISTRATION,
        ResearchPhase.EXECUTION,
        ResearchPhase.PLANNING,
    ],
    ResearchPhase.PRE_REGISTRATION: [ResearchPhase.EXECUTION, ResearchPhase.PLANNING],
    ResearchPhase.EXECUTION: [
        ResearchPhase.VERIFICATION,
        ResearchPhase.POST_EXECUTION,
        ResearchPhase.WRITING,
        ResearchPhase.PLANNING,
    ],
    ResearchPhase.VERIFICATION: [
        ResearchPhase.POST_EXECUTION,
        ResearchPhase.WRITING,
        ResearchPhase.PLANNING,
    ],
    ResearchPhase.POST_EXECUTION: [ResearchPhase.WRITING, ResearchPhase.PLANNING],
    ResearchPhase.WRITING: [ResearchPhase.INTERNAL_REVIEW],
    ResearchPhase.INTERNAL_REVIEW: [ResearchPhase.SUBMITTED, ResearchPhase.WRITING],
    ResearchPhase.SUBMITTED: [ResearchPhase.PEER_REVIEW, ResearchPhase.REJECTED],
    ResearchPhase.PEER_REVIEW: [
        ResearchPhase.PUBLISHED,
        ResearchPhase.REVISION,
        ResearchPhase.REJECTED,
    ],
    ResearchPhase.REVISION: [ResearchPhase.SUBMITTED],
    ResearchPhase.PUBLISHED: [],
    ResearchPhase.REJECTED: [],
}

_DESCRIPTIONS: dict[ResearchPhase, str] = {
    ResearchPhase.SEEDING: "Initialize research thread with seed prompt and optional literature context.",
    ResearchPhase.IDEATION: "Agents propose and debate hypotheses through structured discussion rounds.",
    ResearchPhase.PLANNING: "Develop a concrete research plan: experiments, data needs, success criteria.",
    ResearchPhase.LITERATURE: "Deep literature review to inform execution.",
    ResearchPhase.PRE_REGISTRATION: "Freeze falsifiable predictions and decision rules before execution.",
    ResearchPhase.EXECUTION: "Run computational experiments in sandboxed environment.",
    ResearchPhase.VERIFICATION: "Re-execute experiments in a fresh sandbox to verify results reproduce.",
    ResearchPhase.POST_EXECUTION: "Team discusses experimental results: interprets findings, flags limitations, agrees on conclusions.",
    ResearchPhase.WRITING: "Draft the research paper in markdown format.",
    ResearchPhase.INTERNAL_REVIEW: "Internal quality review before submission.",
    ResearchPhase.SUBMITTED: "Paper submitted to journal for peer review.",
    ResearchPhase.PEER_REVIEW: "External peer review evaluation.",
    ResearchPhase.REVISION: "Revise paper based on reviewer feedback.",
    ResearchPhase.PUBLISHED: "Paper accepted and published.",
    ResearchPhase.REJECTED: "Paper rejected after review.",
}


class PhaseManager:
    """Manages phase transitions with validation."""

    def __init__(self, initial_phase: ResearchPhase = ResearchPhase.SEEDING) -> None:
        """Initialize phase manager.

        Args:
            initial_phase: Starting phase.
        """
        self._current_phase = initial_phase

    @property
    def current_phase(self) -> ResearchPhase:
        """Get current phase."""
        return self._current_phase

    def can_transition_to(self, target: ResearchPhase) -> bool:
        """Check if a transition to target phase is valid.

        Args:
            target: Target phase to transition to.

        Returns:
            True if the transition is allowed.
        """
        return target in _TRANSITIONS.get(self._current_phase, [])

    def transition_to(self, target: ResearchPhase) -> None:
        """Transition to target phase.

        Args:
            target: Target phase.

        Raises:
            ValueError: If the transition is invalid.
        """
        if not self.can_transition_to(target):
            allowed = _TRANSITIONS.get(self._current_phase, [])
            allowed_str = ", ".join(str(p) for p in allowed) if allowed else "none"
            raise ValueError(
                f"Invalid transition: {self._current_phase} -> {target}. "
                f"Allowed transitions from {self._current_phase}: {allowed_str}"
            )
        self._current_phase = target

    @staticmethod
    def get_phase_description(phase: ResearchPhase) -> str:
        """Get a human-readable description of a phase.

        Args:
            phase: The phase to describe.

        Returns:
            Description string.
        """
        return _DESCRIPTIONS.get(phase, f"No description for phase: {phase}")
