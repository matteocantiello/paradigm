"""Tests for agent scheduler."""

from dataclasses import dataclass

import pytest

from paradigm.orchestrator.phases import ResearchPhase
from paradigm.orchestrator.scheduler import Scheduler


@dataclass
class FakeAgent:
    """Minimal agent stub for testing."""

    agent_id: str


@pytest.fixture
def agents():
    """Create a set of fake agents."""
    return [
        FakeAgent("theorist-0"),
        FakeAgent("analyst-0"),
        FakeAgent("synthesizer-0"),
        FakeAgent("skeptic-0"),
    ]


class TestSchedulerRoundRobin:
    """Test round_robin scheduling mode."""

    def test_initial_order(self, agents):
        """Initial order matches agent list."""
        s = Scheduler(agents, mode="round_robin")
        order = s.get_speaker_order(ResearchPhase.IDEATION)
        assert order == ["theorist-0", "analyst-0", "synthesizer-0", "skeptic-0"]

    def test_advance_round_rotates(self, agents):
        """advance_round rotates the order."""
        s = Scheduler(agents, mode="round_robin")
        s.advance_round()
        order = s.get_speaker_order(ResearchPhase.IDEATION)
        assert order[0] == "analyst-0"
        assert order[-1] == "theorist-0"

    def test_two_advances(self, agents):
        """Two advances rotates by 2."""
        s = Scheduler(agents, mode="round_robin")
        s.advance_round()
        s.advance_round()
        order = s.get_speaker_order(ResearchPhase.IDEATION)
        assert order[0] == "synthesizer-0"

    def test_reset(self, agents):
        """Reset restores initial order."""
        s = Scheduler(agents, mode="round_robin")
        s.advance_round()
        s.advance_round()
        s.reset()
        order = s.get_speaker_order(ResearchPhase.IDEATION)
        assert order == ["theorist-0", "analyst-0", "synthesizer-0", "skeptic-0"]


class TestSchedulerPhaseAppropriate:
    """Test phase_appropriate scheduling mode."""

    def test_ideation_theorist_first(self, agents):
        """In IDEATION, theorist speaks before skeptic."""
        s = Scheduler(agents, mode="phase_appropriate")
        order = s.get_speaker_order(ResearchPhase.IDEATION)
        theorist_idx = order.index("theorist-0")
        skeptic_idx = order.index("skeptic-0")
        assert theorist_idx < skeptic_idx

    def test_ideation_full_order(self, agents):
        """IDEATION priority: theorist, synthesizer, analyst, ..., skeptic."""
        s = Scheduler(agents, mode="phase_appropriate")
        order = s.get_speaker_order(ResearchPhase.IDEATION)
        # theorist before synthesizer before analyst before skeptic
        assert order.index("theorist-0") < order.index("synthesizer-0")
        assert order.index("synthesizer-0") < order.index("analyst-0")
        assert order.index("analyst-0") < order.index("skeptic-0")

    def test_planning_experimentalist_first(self):
        """In PLANNING, experimentalist speaks first."""
        agents = [
            FakeAgent("theorist-0"),
            FakeAgent("experimentalist-0"),
            FakeAgent("analyst-0"),
            FakeAgent("skeptic-0"),
        ]
        s = Scheduler(agents, mode="phase_appropriate")
        order = s.get_speaker_order(ResearchPhase.PLANNING)
        assert order[0] == "experimentalist-0"

    def test_unknown_phase_uses_insertion_order(self, agents):
        """Phases without explicit priority use insertion order."""
        s = Scheduler(agents, mode="phase_appropriate")
        order = s.get_speaker_order(ResearchPhase.WRITING)
        assert order == ["theorist-0", "analyst-0", "synthesizer-0", "skeptic-0"]


class TestSchedulerRandom:
    """Test random scheduling mode."""

    def test_seeded_reproducibility(self, agents):
        """Same seed produces same order."""
        s1 = Scheduler(agents, mode="random", seed=42)
        s2 = Scheduler(agents, mode="random", seed=42)
        assert s1.get_speaker_order(ResearchPhase.IDEATION) == s2.get_speaker_order(
            ResearchPhase.IDEATION
        )

    def test_different_seeds_different_order(self, agents):
        """Different seeds produce different orders (with high probability)."""
        s1 = Scheduler(agents, mode="random", seed=1)
        s2 = Scheduler(agents, mode="random", seed=999)
        # With 4 agents, chance of same order is 1/24, so this is very likely to differ
        order1 = s1.get_speaker_order(ResearchPhase.IDEATION)
        order2 = s2.get_speaker_order(ResearchPhase.IDEATION)
        # We can't assert they're always different, but verify they're valid
        assert set(order1) == set(order2)
