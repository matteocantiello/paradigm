"""Tests for the Paradigm display system."""

from unittest.mock import patch

from paradigm.display import DisplayManager, DisplayState
from paradigm.display.fallback import PlainTextFallback
from paradigm.display.theme import (
    AGENT_STYLES,
    PHASE_DISPLAY_ORDER,
    PHASE_ICONS,
)
from paradigm.orchestrator.phases import ResearchPhase

# ---------------------------------------------------------------------------
# DisplayState tests
# ---------------------------------------------------------------------------


class TestDisplayState:
    def test_initial_state(self):
        state = DisplayState()
        assert state.current_phase is None
        assert state.completed_phases == []
        assert state.round_num == 0
        assert state.max_rounds == 0
        assert state.active_agents == {}
        assert state.recent_events == []
        assert state.total_tokens == 0
        assert state.total_searches == 0
        assert state.papers_count == 0

    def test_add_event(self):
        state = DisplayState()
        state.add_event("search", "Found 5 papers")
        assert len(state.recent_events) == 1
        assert state.recent_events[0]["type"] == "search"
        assert state.recent_events[0]["message"] == "Found 5 papers"
        assert "time" in state.recent_events[0]

    def test_events_capped_at_50(self):
        state = DisplayState()
        for i in range(60):
            state.add_event("test", f"Event {i}")
        assert len(state.recent_events) == 50
        # Should keep most recent
        assert state.recent_events[-1]["message"] == "Event 59"
        assert state.recent_events[0]["message"] == "Event 10"

    def test_elapsed_seconds(self):
        state = DisplayState()
        # start_time is set via time.monotonic(), so elapsed should be >= 0
        assert state.elapsed_seconds >= 0


# ---------------------------------------------------------------------------
# Theme completeness tests
# ---------------------------------------------------------------------------


class TestTheme:
    def test_all_roles_have_styles(self):
        expected_roles = [
            "theorist",
            "analyst",
            "experimentalist",
            "synthesizer",
            "skeptic",
            "writer",
            "editor",
            "reviewer",
        ]
        for role in expected_roles:
            assert role in AGENT_STYLES, f"Missing style for role: {role}"
            assert "color" in AGENT_STYLES[role]
            assert "icon" in AGENT_STYLES[role]

    def test_all_phases_have_icons(self):
        for phase in ResearchPhase:
            assert phase in PHASE_ICONS, f"Missing icon for phase: {phase}"

    def test_phase_display_order_covers_main_phases(self):
        # The display order should cover the core pipeline phases
        core_phases = {
            ResearchPhase.SEEDING,
            ResearchPhase.IDEATION,
            ResearchPhase.PLANNING,
            ResearchPhase.EXECUTION,
            ResearchPhase.WRITING,
            ResearchPhase.INTERNAL_REVIEW,
        }
        display_set = set(PHASE_DISPLAY_ORDER)
        assert core_phases.issubset(display_set)


# ---------------------------------------------------------------------------
# PlainTextFallback output tests
# ---------------------------------------------------------------------------


class TestPlainTextFallback:
    def test_phase_transition_with_details(self, capsys):
        fb = PlainTextFallback()
        fb.phase_transition("IDEATION", max_rounds=3, active_agents=5, total_agents=7)
        out = capsys.readouterr().out
        assert "Phase: IDEATION" in out
        assert "3 rounds" in out
        assert "5/7 agents active" in out

    def test_phase_transition_simple(self, capsys):
        fb = PlainTextFallback()
        fb.phase_transition("EXECUTION")
        out = capsys.readouterr().out
        assert "Phase: EXECUTION" in out

    def test_agent_response(self, capsys):
        fb = PlainTextFallback()
        fb.agent_response("theorist-0", 1500)
        out = capsys.readouterr().out
        assert "theorist-0: 1500 tokens" in out

    def test_agent_error(self, capsys):
        fb = PlainTextFallback()
        fb.agent_error("analyst-0", "API timeout")
        out = capsys.readouterr().out
        assert "[!] analyst-0 failed: API timeout" in out

    def test_search_result(self, capsys):
        fb = PlainTextFallback()
        fb.search_result("theorist-0", "stellar oscillations", 10, 7)
        out = capsys.readouterr().out
        assert "theorist-0 searched:" in out
        assert "10 results (7 new)" in out

    def test_round_start(self, capsys):
        fb = PlainTextFallback()
        fb.round_start(2, 5)
        out = capsys.readouterr().out
        assert "Round 2/5" in out

    def test_token_summary(self, capsys):
        fb = PlainTextFallback()
        fb.token_summary(150.5, 100.2, 50.3, "5m 30s")
        out = capsys.readouterr().out
        assert "150.5K total" in out
        assert "100.2K input" in out
        assert "50.3K output" in out
        assert "5m 30s" in out

    def test_debate_start(self, capsys):
        fb = PlainTextFallback()
        fb.debate_start("skeptic-0", "theorist-0", "Whether dark matter exists")
        out = capsys.readouterr().out
        assert "Debate:" in out
        assert "skeptic-0 vs theorist-0" in out

    def test_checkpoint_saved(self, capsys):
        fb = PlainTextFallback()
        fb.checkpoint_saved("round 3")
        out = capsys.readouterr().out
        assert "Checkpoint saved (round 3)" in out

    def test_paper_saved(self, capsys):
        fb = PlainTextFallback()
        fb.paper_saved("paper-abc123")
        out = capsys.readouterr().out
        assert "Paper saved: paper-abc123" in out

    def test_paper_too_short(self, capsys):
        fb = PlainTextFallback()
        fb.paper_too_short(500, 10000)
        out = capsys.readouterr().out
        assert "500 chars" in out
        assert "minimum 10000" in out

    def test_experiment_round(self, capsys):
        fb = PlainTextFallback()
        fb.experiment_round(2, 5)
        out = capsys.readouterr().out
        assert "Experiment round 2/5" in out

    def test_review_recommendation(self, capsys):
        fb = PlainTextFallback()
        fb.review_recommendation("accept", 0)
        out = capsys.readouterr().out
        assert "accept" in out
        assert "0 required changes" in out

    def test_desk_review_passed(self, capsys):
        fb = PlainTextFallback()
        fb.desk_review_result(True)
        out = capsys.readouterr().out
        assert "Desk review passed" in out

    def test_desk_review_rejected(self, capsys):
        fb = PlainTextFallback()
        fb.desk_review_result(False)
        out = capsys.readouterr().out
        assert "Desk REJECTED" in out

    def test_error_to_stderr(self, capsys):
        fb = PlainTextFallback()
        fb.error("Something went wrong", err=True)
        captured = capsys.readouterr()
        assert "Something went wrong" in captured.err

    def test_cycle_complete(self, capsys):
        fb = PlainTextFallback()
        fb.cycle_complete("thread-abc123")
        out = capsys.readouterr().out
        assert "Research cycle complete" in out
        assert "thread-abc123" in out


# ---------------------------------------------------------------------------
# DisplayManager tests
# ---------------------------------------------------------------------------


class TestDisplayManager:
    def test_verbose_mode_uses_fallback(self):
        dm = DisplayManager(verbose=True)
        assert dm._use_rich is False

    def test_non_tty_uses_fallback(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            dm = DisplayManager(verbose=False)
            assert dm._use_rich is False

    def test_state_tracking_phase_transition(self, capsys):
        dm = DisplayManager(verbose=True)
        dm.phase_transition("IDEATION", max_rounds=3, active_agents=5, total_agents=7)
        assert dm.state.current_phase == ResearchPhase.IDEATION
        assert dm.state.max_rounds == 3

    def test_state_tracking_round_start(self, capsys):
        dm = DisplayManager(verbose=True)
        dm.round_start(2, 5)
        assert dm.state.round_num == 2
        assert dm.state.max_rounds == 5

    def test_state_tracking_agent_response(self, capsys):
        dm = DisplayManager(verbose=True)
        dm.agent_response("theorist-0", 1500)
        assert dm.state.total_tokens == 1500
        assert "theorist-0" in dm.state.active_agents

    def test_state_tracking_search_result(self, capsys):
        dm = DisplayManager(verbose=True)
        dm.search_result("analyst-0", "dark matter", 10, 7)
        assert dm.state.total_searches == 1
        assert dm.state.papers_count == 7

    def test_state_tracking_follow_result(self, capsys):
        dm = DisplayManager(verbose=True)
        dm.follow_result("theorist-0", "2301.12345", 5)
        assert dm.state.papers_count == 5

    def test_state_tracking_completed_phases(self, capsys):
        dm = DisplayManager(verbose=True)
        dm.phase_transition("IDEATION")
        dm.phase_transition("PLANNING")
        assert ResearchPhase.IDEATION in dm.state.completed_phases
        assert dm.state.current_phase == ResearchPhase.PLANNING

    def test_state_tracking_events(self, capsys):
        dm = DisplayManager(verbose=True)
        dm.search_result("a-0", "query", 5, 3)
        dm.agent_response("b-0", 1000)
        assert len(dm.state.recent_events) == 2

    def test_start_stop_lifecycle(self, capsys):
        dm = DisplayManager(verbose=True)
        dm.start()
        dm.stop()
        # Should not raise

    def test_all_methods_callable_verbose(self, capsys):
        """Verify all DisplayManager methods can be called without errors in verbose mode."""
        dm = DisplayManager(verbose=True)
        dm.start()

        # Phase transitions
        dm.phase_transition("IDEATION", max_rounds=3, active_agents=5, total_agents=7)
        dm.phase_aborted()
        dm.phase_paused()

        # Rounds
        dm.round_start(1, 3)

        # Agent activity
        dm.agent_response("agent-0", 500)
        dm.agent_error("agent-0", "test error")

        # Search
        dm.search_result("agent-0", "query", 5, 3)
        dm.search_skipped("query", reason="similar")
        dm.search_budget_exhausted(5, "query")
        dm.search_agent_cap("agent-0", 2, "query")
        dm.search_error("query", "error")
        dm.search_stale("agent-0")

        # Literature
        dm.follow_result("agent-0", "2301.12345", 5)
        dm.follow_budget_exhausted("2301.12345")
        dm.follow_skipped("2301.12345")
        dm.follow_error("2301.12345", "error")
        dm.cited_by_result("agent-0", "2301.12345", 3)
        dm.cited_by_budget_exhausted("2301.12345")
        dm.cited_by_skipped("2301.12345")
        dm.cited_by_error("2301.12345", "error")
        dm.read_result("agent-0", "2301.12345", "Paper Title", 5000)
        dm.read_budget_exhausted("2301.12345")
        dm.read_skipped("2301.12345")
        dm.read_error("2301.12345", "error")
        dm.read_not_found("2301.12345")

        # Resources
        dm.resource_detected("https://example.com", "paper")
        dm.resource_ingested("Paper Title")
        dm.resource_resolved("name", "code_repo")
        dm.resource_error("error message")
        dm.resource_fetch_error("https://example.com", "timeout")
        dm.resource_extract_error("https://example.com")
        dm.pdf_saved("paper.pdf")
        dm.pdf_save_error("disk full")
        dm.graveyard_error("db error")

        # Debates
        dm.debate_start("skeptic-0", "theorist-0", "topic")
        dm.debate_turn("skeptic-0", "counter-argument")
        dm.debate_resolved("theorist-0")
        dm.debate_concede("skeptic-0")
        dm.debate_error("skeptic-0", "error")
        dm.debate_complete("resolved", 3)
        dm.debate_skipped("agent-0", "not found")
        dm.debate_budget_exhausted(2, "ideation")
        dm.synthesis_error("error")

        # Experiments
        dm.experiment_round(1, 3)
        dm.experiment_no_agent()
        dm.experiment_declared_sufficient()
        dm.experiment_no_code()
        dm.experiment_running("exp_1")
        dm.experiment_result("exp_1", "success")
        dm.experiment_retry(1, 2)
        dm.experiment_high_failure_rate(3, 4)

        # Writing
        dm.writing_round("1: Section drafting")
        dm.writing_section_drafting()
        dm.writing_assembly()
        dm.writing_no_writer()
        dm.writing_assembly_error("error")
        dm.paper_saved("paper-123")
        dm.paper_too_short(500, 10000)
        dm.figure_copied("figure.png")
        dm.writing_failed_skip_review()
        dm.writing_failed_review_exhausted()

        # Review
        dm.review_iteration(1, 3)
        dm.review_no_editor()
        dm.review_editor_error("error")
        dm.review_recommendation("accept", 0)
        dm.review_revising()
        dm.review_max_iterations()
        dm.review_too_short(500)
        dm.revision_error("error")

        # Desk/peer review
        dm.desk_review_result(True)
        dm.desk_review_no_editor()
        dm.desk_review_error("error")
        dm.peer_review_start(3)
        dm.peer_review_result("reviewer-0", "accept", 8.5)
        dm.peer_review_error("reviewer-0", "error")
        dm.peer_review_decision("accept")

        # Revision
        dm.revision_start()
        dm.revision_no_writer()
        dm.revision_complete()
        dm.revision_phase_error("error")

        # Publication
        dm.paper_published()
        dm.paper_rejected()

        # Checkpoints
        dm.checkpoint_saved("round 3")
        dm.checkpoint_error("error")

        # Token summary
        dm.token_summary(150.5, 100.2, 50.3, "5m 30s")

        # Memory
        dm.memory_generating()
        dm.memory_stored(10, 3)
        dm.memory_error("error")

        # General
        dm.info("info message")
        dm.warning("warning message")
        dm.error("error message")

        # Main.py specific
        dm.testing_mode()
        dm.cycle_complete("thread-123")
        dm.cycle_interrupted()
        dm.cycle_error("error")
        dm.prompt_loaded("prompt.md", 500)
        dm.starting_cycle("directed")
        dm.rounds_override(3)
        dm.interactive_mode()

        dm.stop()
