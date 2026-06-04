"""Tests for research phase state machine."""

import pytest

from paradigm.orchestrator.phases import PhaseManager, ResearchPhase


class TestResearchPhase:
    """Test ResearchPhase enum."""

    def test_all_phases_defined(self):
        """All expected phases exist."""
        expected = [
            "seeding",
            "ideation",
            "planning",
            "literature",
            "pre_registration",
            "execution",
            "post_execution",
            "writing",
            "internal",
            "submitted",
            "peer_review",
            "revision",
            "published",
            "rejected",
        ]
        actual = [p.value for p in ResearchPhase]
        assert actual == expected

    def test_str_value(self):
        """Phases are string-valued."""
        assert str(ResearchPhase.IDEATION) == "ideation"
        assert ResearchPhase.SEEDING == "seeding"


class TestPhaseManager:
    """Test PhaseManager transitions."""

    def test_initial_phase(self):
        """Default initial phase is SEEDING."""
        pm = PhaseManager()
        assert pm.current_phase == ResearchPhase.SEEDING

    def test_custom_initial_phase(self):
        """Can start from a custom phase."""
        pm = PhaseManager(ResearchPhase.IDEATION)
        assert pm.current_phase == ResearchPhase.IDEATION

    def test_valid_transition_seeding_to_ideation(self):
        """SEEDING -> IDEATION is valid."""
        pm = PhaseManager()
        assert pm.can_transition_to(ResearchPhase.IDEATION)
        pm.transition_to(ResearchPhase.IDEATION)
        assert pm.current_phase == ResearchPhase.IDEATION

    def test_valid_transition_ideation_to_planning(self):
        """IDEATION -> PLANNING is valid."""
        pm = PhaseManager(ResearchPhase.IDEATION)
        assert pm.can_transition_to(ResearchPhase.PLANNING)
        pm.transition_to(ResearchPhase.PLANNING)
        assert pm.current_phase == ResearchPhase.PLANNING

    def test_full_phase2_progression(self):
        """SEEDING -> IDEATION -> PLANNING works."""
        pm = PhaseManager()
        pm.transition_to(ResearchPhase.IDEATION)
        pm.transition_to(ResearchPhase.PLANNING)
        assert pm.current_phase == ResearchPhase.PLANNING

    def test_invalid_transition_raises(self):
        """Invalid transitions raise ValueError."""
        pm = PhaseManager()
        with pytest.raises(ValueError, match="Invalid transition"):
            pm.transition_to(ResearchPhase.PLANNING)  # Can't skip ideation

    def test_invalid_transition_from_terminal(self):
        """PUBLISHED has no valid transitions."""
        pm = PhaseManager(ResearchPhase.PUBLISHED)
        assert not pm.can_transition_to(ResearchPhase.SEEDING)
        with pytest.raises(ValueError):
            pm.transition_to(ResearchPhase.SEEDING)

    def test_cannot_transition_backwards(self):
        """Can't go IDEATION -> SEEDING."""
        pm = PhaseManager(ResearchPhase.IDEATION)
        assert not pm.can_transition_to(ResearchPhase.SEEDING)

    def test_get_phase_description(self):
        """Phase descriptions are returned."""
        desc = PhaseManager.get_phase_description(ResearchPhase.IDEATION)
        assert "hypotheses" in desc.lower()

        desc = PhaseManager.get_phase_description(ResearchPhase.SEEDING)
        assert "seed" in desc.lower()

    def test_get_phase_description_all_phases(self):
        """Every phase has a description."""
        for phase in ResearchPhase:
            desc = PhaseManager.get_phase_description(phase)
            assert isinstance(desc, str)
            assert len(desc) > 0
