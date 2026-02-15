"""Tests for the focused debate sub-routine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from helpers import make_mock_agent, patch_config_provider

from paradigm.agents.base import Agent
from paradigm.config import Config
from paradigm.literature.prompt_utils import parse_challenge_requests
from paradigm.orchestrator.debate import DebateHandler
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.phases import ResearchPhase

# ---------------------------------------------------------------------------
# parse_challenge_requests tests
# ---------------------------------------------------------------------------


class TestParseChallengeRequests:
    def test_no_markers(self):
        text = "Just a normal response about research methods."
        assert parse_challenge_requests(text) == []

    def test_single_challenge(self):
        text = "I disagree. [CHALLENGE: theorist-0: Your model ignores metallicity effects]"
        result = parse_challenge_requests(text)
        assert len(result) == 1
        assert result[0].challenged_agent_id == "theorist-0"
        assert result[0].reason == "Your model ignores metallicity effects"

    def test_multiple_challenges_dedup(self):
        text = (
            "[CHALLENGE: theorist-0: ignores metallicity] "
            "[CHALLENGE: theorist-0: also bad assumptions]"
        )
        result = parse_challenge_requests(text)
        # Deduplicates by agent_id — first one wins
        assert len(result) == 1
        assert result[0].reason == "ignores metallicity"

    def test_different_targets(self):
        text = "[CHALLENGE: theorist-0: bad model] [CHALLENGE: analyst-0: wrong data analysis]"
        result = parse_challenge_requests(text)
        assert len(result) == 2

    def test_case_insensitive_tag(self):
        text = "[challenge: theorist-0: reason here]"
        result = parse_challenge_requests(text)
        assert len(result) == 1
        assert result[0].challenged_agent_id == "theorist-0"

    def test_whitespace_handling(self):
        text = "[CHALLENGE:   theorist-0  :   lots of space   ]"
        result = parse_challenge_requests(text)
        assert len(result) == 1
        assert result[0].challenged_agent_id == "theorist-0"
        assert result[0].reason == "lots of space"

    def test_empty_reason_ignored(self):
        text = "[CHALLENGE: theorist-0: ]"
        assert parse_challenge_requests(text) == []

    def test_multiline(self):
        text = "Line one\n[CHALLENGE: theorist-0: reason]\nLine three\n"
        result = parse_challenge_requests(text)
        assert len(result) == 1

    def test_agent_id_format(self):
        # Must match pattern: lowercase letters + dash + digits
        text = "[CHALLENGE: experimentalist-1: bad experiment design]"
        result = parse_challenge_requests(text)
        assert len(result) == 1
        assert result[0].challenged_agent_id == "experimentalist-1"

    def test_invalid_agent_id_ignored(self):
        # No match: agent id must be word-dash-digits
        text = "[CHALLENGE: Agent One: reason]"
        result = parse_challenge_requests(text)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Engine debate integration tests
# ---------------------------------------------------------------------------


def _build_engine(config, db, logger, corpus, agents: dict[str, Agent]) -> OrchestrationEngine:
    """Build an engine with pre-set agents (bypassing factory)."""
    factory = MagicMock()
    factory.create_team = MagicMock(return_value=list(agents.values()))

    engine = OrchestrationEngine(
        config=config,
        database=db,
        corpus=corpus,
        logger=logger,
        agent_factory=factory,
    )

    engine._agents = dict(agents)
    engine._thread_id = "thread-test123"
    engine._seed_prompt = "Test topic"
    engine._messages = []
    engine._debate.debate_counts = {}
    # Set attributes that _build_agent_prompt expects
    engine._literature.literature_context = ""
    engine._checkpoint = None
    engine._graveyard_context = ""
    engine._code_context = ""
    engine._data_context = ""
    engine._reference_context = ""
    engine._mode = "directed"
    engine._memory_store = None
    return engine


@pytest.fixture
def mock_config(tmp_path):
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 1,
            "checkpoint_interval": 10,
            "enable_checkpointing": False,
            "enable_writing": False,
            "enable_experimentation": False,
            "enable_debates": True,
            "max_debate_exchanges": 3,
            "max_debates_per_phase": 2,
        },
    )
    patch_config_provider(config)
    return config


class TestProcessChallengeRequests:
    """Tests for _process_challenge_requests."""

    @pytest.mark.asyncio
    async def test_valid_challenge_triggers_debate(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        """A valid challenge tag triggers _run_debate."""
        theorist = make_mock_agent("theorist-0", "theorist")
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")

        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic, "synthesizer-0": synthesizer},
        )

        response_text = (
            "I think this is wrong. "
            "[CHALLENGE: theorist-0: Your hypothesis ignores convective overshooting]"
        )

        await engine._debate.process_challenge_requests(
            "skeptic-0", response_text, ResearchPhase.IDEATION, 1
        )

        # Debate should have triggered — defender (theorist) should have been called
        assert theorist.generate.call_count >= 1
        # Synthesis message should be in messages
        assert any(m.get("type") == "debate_synthesis" for m in engine._messages)
        # Debate count should be incremented
        assert engine._debate.debate_counts.get("ideation", 0) == 1

    @pytest.mark.asyncio
    async def test_self_challenge_ignored(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """An agent challenging itself is silently skipped."""
        theorist = make_mock_agent("theorist-0", "theorist")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "synthesizer-0": synthesizer},
        )

        response_text = "[CHALLENGE: theorist-0: I disagree with myself]"
        await engine._debate.process_challenge_requests(
            "theorist-0", response_text, ResearchPhase.IDEATION, 1
        )

        # No debate should have occurred
        assert engine._debate.debate_counts.get("ideation", 0) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_target_skipped(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Challenge targeting a non-existent agent is skipped."""
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"skeptic-0": skeptic, "synthesizer-0": synthesizer},
        )

        response_text = "[CHALLENGE: theorist-0: you don't exist]"
        await engine._debate.process_challenge_requests(
            "skeptic-0", response_text, ResearchPhase.IDEATION, 1
        )

        assert engine._debate.debate_counts.get("ideation", 0) == 0

    @pytest.mark.asyncio
    async def test_inactive_target_skipped(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Challenge targeting an agent not active in this phase is skipped."""
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        writer = make_mock_agent("writer-0", "writer")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"skeptic-0": skeptic, "writer-0": writer, "synthesizer-0": synthesizer},
        )

        response_text = "[CHALLENGE: writer-0: you shouldn't be here]"
        await engine._debate.process_challenge_requests(
            "skeptic-0", response_text, ResearchPhase.IDEATION, 1
        )

        assert engine._debate.debate_counts.get("ideation", 0) == 0

    @pytest.mark.asyncio
    async def test_budget_exhausted(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Debate is skipped when phase budget is exhausted."""
        theorist = make_mock_agent("theorist-0", "theorist")
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic, "synthesizer-0": synthesizer},
        )
        # Pre-exhaust the budget
        engine._debate.debate_counts["ideation"] = 2  # max_debates_per_phase = 2

        response_text = "[CHALLENGE: theorist-0: one more debate]"
        await engine._debate.process_challenge_requests(
            "skeptic-0", response_text, ResearchPhase.IDEATION, 1
        )

        # No new debate
        assert engine._debate.debate_counts["ideation"] == 2
        assert theorist.generate.call_count == 0

    @pytest.mark.asyncio
    async def test_disabled_debates(self, tmp_path, tmp_db, tmp_logger, mock_corpus):
        """Debates are skipped when enable_debates is False."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "enable_debates": False,
                "enable_writing": False,
                "enable_experimentation": False,
            },
        )
        patch_config_provider(config)
        theorist = make_mock_agent("theorist-0", "theorist")
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        engine = _build_engine(
            config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic},
        )

        response_text = "[CHALLENGE: theorist-0: reason]"
        await engine._debate.process_challenge_requests(
            "skeptic-0", response_text, ResearchPhase.IDEATION, 1
        )

        assert theorist.generate.call_count == 0

    @pytest.mark.asyncio
    async def test_wrong_phase_ignored(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Challenges in non-debate phases are ignored."""
        theorist = make_mock_agent("theorist-0", "theorist")
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic},
        )

        response_text = "[CHALLENGE: theorist-0: reason]"
        await engine._debate.process_challenge_requests(
            "skeptic-0", response_text, ResearchPhase.WRITING, 1
        )

        assert theorist.generate.call_count == 0


class TestRunDebate:
    """Tests for _run_debate."""

    @pytest.mark.asyncio
    async def test_resolved_debate(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Debate ends early when defender produces [RESOLVED: ...]."""
        # Defender's first response resolves the debate
        theorist = make_mock_agent(
            "theorist-0",
            "theorist",
            "Good point, I agree. [RESOLVED: We both accept overshooting matters]",
        )
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")

        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic, "synthesizer-0": synthesizer},
        )

        await engine._debate.run_debate(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="convective overshooting",
            challenger_position="I think overshooting is critical.",
            phase=ResearchPhase.IDEATION,
            round_num=1,
        )

        # Defender spoke once, challenger should NOT have spoken (resolved on first turn)
        assert theorist.generate.call_count == 1
        assert skeptic.generate.call_count == 0
        # Synthesis was generated
        assert any(m.get("type") == "debate_synthesis" for m in engine._messages)
        # Check resolution type in the synthesis message metadata
        synth_msg = next(m for m in engine._messages if m.get("type") == "debate_synthesis")
        assert synth_msg["metadata"]["resolution_type"] == "resolved"

    @pytest.mark.asyncio
    async def test_concede_debate(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Debate ends when defender concedes."""
        theorist = make_mock_agent(
            "theorist-0",
            "theorist",
            "You're right. [CONCEDE: Metallicity effects are crucial]",
        )
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")

        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic, "synthesizer-0": synthesizer},
        )

        await engine._debate.run_debate(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="metallicity",
            challenger_position="Metallicity matters.",
            phase=ResearchPhase.IDEATION,
            round_num=1,
        )

        synth_msg = next(m for m in engine._messages if m.get("type") == "debate_synthesis")
        assert synth_msg["metadata"]["resolution_type"] == "concede_defender"

    @pytest.mark.asyncio
    async def test_max_turns_debate(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Debate runs to max exchanges without resolution."""
        theorist = make_mock_agent("theorist-0", "theorist", "I still disagree with your analysis.")
        skeptic = make_mock_agent("skeptic-0", "skeptic", "I maintain my position.")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")

        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic, "synthesizer-0": synthesizer},
        )

        await engine._debate.run_debate(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="model assumptions",
            challenger_position="Your model is wrong.",
            phase=ResearchPhase.IDEATION,
            round_num=1,
        )

        # With max_debate_exchanges=3:
        # Exchange 1: defender + challenger
        # Exchange 2: defender + challenger
        # Exchange 3: defender only (final)
        # Total: 3 defender calls + 2 challenger calls = 5
        assert theorist.generate.call_count == 3  # defender
        assert skeptic.generate.call_count == 2  # challenger (not on final)

        synth_msg = next(m for m in engine._messages if m.get("type") == "debate_synthesis")
        assert synth_msg["metadata"]["resolution_type"] == "max_turns"

    @pytest.mark.asyncio
    async def test_challenger_concedes(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Debate ends when challenger concedes."""
        theorist = make_mock_agent("theorist-0", "theorist", "Here's my defense with evidence.")
        skeptic = make_mock_agent(
            "skeptic-0",
            "skeptic",
            "Actually you're right. [CONCEDE: The model is valid]",
        )
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")

        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic, "synthesizer-0": synthesizer},
        )

        await engine._debate.run_debate(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="model validity",
            challenger_position="Your model is invalid.",
            phase=ResearchPhase.IDEATION,
            round_num=1,
        )

        # Exchange 1: defender speaks, then challenger speaks (and concedes)
        assert theorist.generate.call_count == 1
        assert skeptic.generate.call_count == 1

        synth_msg = next(m for m in engine._messages if m.get("type") == "debate_synthesis")
        assert synth_msg["metadata"]["resolution_type"] == "concede_challenger"

    @pytest.mark.asyncio
    async def test_api_error_during_debate(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Debate ends gracefully on API error."""
        theorist = make_mock_agent("theorist-0", "theorist")
        theorist.generate = AsyncMock(side_effect=RuntimeError("API timeout"))
        skeptic = make_mock_agent("skeptic-0", "skeptic")
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")

        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist, "skeptic-0": skeptic, "synthesizer-0": synthesizer},
        )

        await engine._debate.run_debate(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="error test",
            challenger_position="Testing error handling.",
            phase=ResearchPhase.IDEATION,
            round_num=1,
        )

        # Should still produce a synthesis (mechanical fallback)
        assert any(m.get("type") == "debate_synthesis" for m in engine._messages)
        synth_msg = next(m for m in engine._messages if m.get("type") == "debate_synthesis")
        assert synth_msg["metadata"]["resolution_type"] == "error"


class TestSynthesizeDebate:
    """Tests for _synthesize_debate."""

    @pytest.mark.asyncio
    async def test_synthesizer_used(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Synthesizer agent is used when available."""
        synthesizer = make_mock_agent(
            "synthesizer-0", "synthesizer", "This is the debate synthesis."
        )
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"synthesizer-0": synthesizer},
        )

        result = await engine._debate.synthesize_debate(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="test topic",
            transcript=[
                {"agent": "theorist-0", "content": "defense"},
                {"agent": "skeptic-0", "content": "rebuttal"},
            ],
            resolution_type="max_turns",
            resolution_statement="",
            phase=ResearchPhase.IDEATION,
        )

        assert result == "This is the debate synthesis."
        assert synthesizer.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_mechanical_fallback(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Mechanical fallback is used when no synthesizer exists."""
        theorist = make_mock_agent("theorist-0", "theorist")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist},
        )

        result = await engine._debate.synthesize_debate(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="test topic",
            transcript=[
                {"agent": "theorist-0", "content": "my defense position"},
            ],
            resolution_type="resolved",
            resolution_statement="we agree",
            phase=ResearchPhase.IDEATION,
        )

        assert "Debate Summary" in result
        assert "test topic" in result
        assert "resolved" in result
        assert "we agree" in result

    @pytest.mark.asyncio
    async def test_synthesizer_failure_fallback(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Falls back to mechanical synthesis when synthesizer fails."""
        synthesizer = make_mock_agent("synthesizer-0", "synthesizer")
        synthesizer.generate = AsyncMock(side_effect=RuntimeError("API error"))

        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"synthesizer-0": synthesizer},
        )

        result = await engine._debate.synthesize_debate(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="fallback test",
            transcript=[{"agent": "theorist-0", "content": "position"}],
            resolution_type="error",
            resolution_statement="synth failed",
            phase=ResearchPhase.IDEATION,
        )

        # Should still produce a mechanical summary
        assert "Debate Summary" in result
        assert "fallback test" in result


class TestBuildAgentPromptDebate:
    """Tests for debate instruction injection in _build_agent_prompt."""

    def test_debate_instruction_in_ideation(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Challenge instruction is appended during IDEATION."""
        theorist = make_mock_agent("theorist-0", "theorist")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist},
        )

        prompt = engine._build_agent_prompt(theorist, ResearchPhase.IDEATION, 2)
        assert "[CHALLENGE:" in prompt

    def test_debate_instruction_in_planning(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Challenge instruction is appended during PLANNING."""
        theorist = make_mock_agent("theorist-0", "theorist")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist},
        )

        prompt = engine._build_agent_prompt(theorist, ResearchPhase.PLANNING, 2)
        assert "[CHALLENGE:" in prompt

    def test_no_debate_instruction_in_writing(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Challenge instruction is NOT appended during WRITING."""
        theorist = make_mock_agent("theorist-0", "theorist")
        engine = _build_engine(
            mock_config,
            tmp_db,
            tmp_logger,
            mock_corpus,
            {"theorist-0": theorist},
        )

        prompt = engine._build_agent_prompt(theorist, ResearchPhase.WRITING, 1)
        assert "[CHALLENGE:" not in prompt

    def test_no_debate_instruction_when_disabled(self, tmp_path, tmp_db, tmp_logger, mock_corpus):
        """Challenge instruction not appended when debates disabled."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "enable_debates": False,
                "enable_writing": False,
                "enable_experimentation": False,
            },
        )
        patch_config_provider(config)
        theorist = make_mock_agent("theorist-0", "theorist")
        engine = _build_engine(config, tmp_db, tmp_logger, mock_corpus, {"theorist-0": theorist})

        prompt = engine._build_agent_prompt(theorist, ResearchPhase.IDEATION, 2)
        assert "[CHALLENGE:" not in prompt


class TestMechanicalDebateSynthesis:
    """Tests for the static mechanical fallback."""

    def test_basic_output(self):
        result = DebateHandler.mechanical_debate_synthesis(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="mass loss rates",
            transcript=[
                {"agent": "theorist-0", "content": "Mass loss is well-constrained."},
                {"agent": "skeptic-0", "content": "No it isn't."},
            ],
            resolution_type="max_turns",
            resolution_statement="",
        )
        assert "skeptic-0 vs theorist-0" in result
        assert "mass loss rates" in result
        assert "max_turns" in result

    def test_includes_resolution_statement(self):
        result = DebateHandler.mechanical_debate_synthesis(
            challenger_id="skeptic-0",
            defender_id="theorist-0",
            debate_topic="test",
            transcript=[{"agent": "theorist-0", "content": "pos"}],
            resolution_type="resolved",
            resolution_statement="We agreed on X",
        )
        assert "We agreed on X" in result
