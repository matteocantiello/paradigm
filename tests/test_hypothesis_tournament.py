"""Tests for the hypothesis tournament (Stage 3)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from helpers import patch_config_provider

from paradigm.config import Config
from paradigm.knowledge.hypothesis_tournament import (
    HypothesisPopulation,
    MatchupResult,
    swiss_num_rounds,
)
from paradigm.knowledge.models import Hypothesis
from paradigm.knowledge.tournament_handler import (
    TournamentHandler,
    _first_json_object,
    parse_judge_verdict,
)
from paradigm.knowledge.world_model import WorldModel
from paradigm.logging.events import EventLogger
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.storage.database import Database


class TestParseJudgeVerdict:
    """The judge verdict must survive truncation — a response cut off mid-JSON
    (max_tokens) previously scored None for every matchup → all Elos stuck 1500."""

    def test_truncated_json_recovers_winner(self) -> None:
        truncated = '```json\n{\n  "winner": "A",\n  "reasoning": "Hypothesis A is better because'
        v = parse_judge_verdict(truncated)
        assert v is not None and v["winner"] == "A"

    def test_clean_fenced_json(self) -> None:
        v = parse_judge_verdict('```json\n{"winner":"B","margin":0.7,"reasoning":"x"}\n```')
        assert v == {"winner": "B", "margin": 0.7, "reasoning": "x"}

    def test_prose_winner(self) -> None:
        v = parse_judge_verdict("After analysis, the winner is Hypothesis B by a clear margin.")
        assert v is not None and v["winner"] == "B"

    def test_numeric_winner_maps_to_letter_via_fallback(self) -> None:
        # Non-JSON prose with a numeric winner exercises the regex fallback,
        # which normalizes 1->A / 2->B.
        assert parse_judge_verdict("winner: 2 — the second hypothesis wins")["winner"] == "B"

    def test_unparseable_returns_none(self) -> None:
        assert parse_judge_verdict("I cannot decide between them.") is None
        assert parse_judge_verdict("") is None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def tmp_logger(tmp_path):
    return EventLogger(tmp_path / "events.jsonl")


@pytest.fixture
def mock_config(tmp_path):
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 2,
            "checkpoint_interval": 1,
            "enable_writing": False,
            "enable_experimentation": False,
        },
        knowledge={
            "enable_hypothesis_tournament": True,
            "tournament_population_size": 8,
            "tournament_winners": 2,
            "tournament_k_factor": 32.0,
        },
    )
    patch_config_provider(config)
    return config


@pytest.fixture
def mock_corpus():
    corpus = MagicMock()
    corpus.search = MagicMock(return_value=[])
    return corpus


def _build_engine(config, db, logger, corpus) -> OrchestrationEngine:
    factory = MagicMock()
    factory.create_team = MagicMock(return_value=[])
    engine = OrchestrationEngine(
        config=config,
        database=db,
        corpus=corpus,
        logger=logger,
        agent_factory=factory,
    )
    engine.state.thread_id = "thread-test-tournament"
    engine.state.seed_prompt = "Test research topic"
    engine.state.mode = "directed"
    engine._literature.literature_context = ""
    engine.state.checkpoint = None
    engine._memory_store = None
    return engine


# ===========================================================================
# Test HypothesisPopulation (pure Elo logic)
# ===========================================================================


class TestHypothesisPopulation:
    def _make_hypotheses(self, n: int = 4) -> list[Hypothesis]:
        return [
            Hypothesis(
                id=f"h{i}",
                statement=f"Hypothesis {i}",
                rationale=f"Rationale {i}",
            )
            for i in range(n)
        ]

    def test_initial_elo(self):
        hyps = self._make_hypotheses(3)
        pop = HypothesisPopulation(hyps)
        for h in pop.ranked:
            assert h.elo_rating == 1500.0

    def test_ranked_sorting(self):
        hyps = self._make_hypotheses(3)
        hyps[0].elo_rating = 1600.0
        hyps[1].elo_rating = 1400.0
        hyps[2].elo_rating = 1800.0
        pop = HypothesisPopulation(hyps)
        ranked = pop.ranked
        assert ranked[0].id == "h2"  # 1800
        assert ranked[1].id == "h0"  # 1600
        assert ranked[2].id == "h1"  # 1400

    def test_round_robin_matchups(self):
        hyps = self._make_hypotheses(4)
        pop = HypothesisPopulation(hyps)
        matchups = pop.generate_matchups()
        # 4 choose 2 = 6
        assert len(matchups) == 6
        # All unique pairs
        pair_set = set(matchups)
        assert len(pair_set) == 6

    def test_elo_update_winner_gains(self):
        hyps = self._make_hypotheses(2)
        pop = HypothesisPopulation(hyps, k_factor=32.0)

        result = MatchupResult(
            hypothesis_a_id="h0",
            hypothesis_b_id="h1",
            winner_id="h0",
        )
        pop.record_result(result)

        assert pop.hypotheses["h0"].elo_rating > 1500.0
        assert pop.hypotheses["h1"].elo_rating < 1500.0

    def test_elo_zero_sum(self):
        """Elo updates should be zero-sum (rating gained = rating lost)."""
        hyps = self._make_hypotheses(2)
        pop = HypothesisPopulation(hyps, k_factor=32.0)

        result = MatchupResult(
            hypothesis_a_id="h0",
            hypothesis_b_id="h1",
            winner_id="h0",
        )
        pop.record_result(result)

        total = pop.hypotheses["h0"].elo_rating + pop.hypotheses["h1"].elo_rating
        assert abs(total - 3000.0) < 0.01  # 1500 + 1500

    def test_upset_gives_more_points(self):
        """A lower-rated player beating a higher-rated one gains more."""
        # Match 1: equal ratings
        hyps1 = self._make_hypotheses(2)
        pop1 = HypothesisPopulation(hyps1, k_factor=32.0)
        r1 = MatchupResult(hypothesis_a_id="h0", hypothesis_b_id="h1", winner_id="h0")
        pop1.record_result(r1)
        gain_equal = pop1.hypotheses["h0"].elo_rating - 1500.0

        # Match 2: underdog wins
        hyps2 = self._make_hypotheses(2)
        hyps2[0].elo_rating = 1300.0  # underdog
        hyps2[1].elo_rating = 1700.0  # favorite
        pop2 = HypothesisPopulation(hyps2, k_factor=32.0)
        r2 = MatchupResult(hypothesis_a_id="h0", hypothesis_b_id="h1", winner_id="h0")
        pop2.record_result(r2)
        gain_upset = pop2.hypotheses["h0"].elo_rating - 1300.0

        assert gain_upset > gain_equal

    def test_select_winners(self):
        hyps = self._make_hypotheses(4)
        hyps[2].elo_rating = 1800.0
        hyps[0].elo_rating = 1700.0
        pop = HypothesisPopulation(hyps)
        winners = pop.select_winners(n=2)
        assert len(winners) == 2
        assert winners[0].id == "h2"
        assert winners[1].id == "h0"

    def test_select_more_winners_than_population(self):
        hyps = self._make_hypotheses(2)
        pop = HypothesisPopulation(hyps)
        winners = pop.select_winners(n=5)
        assert len(winners) == 2

    def test_tournament_summary(self):
        hyps = self._make_hypotheses(3)
        hyps[1].elo_rating = 1600.0
        pop = HypothesisPopulation(hyps)
        summary = pop.get_tournament_summary()
        assert "Tournament Rankings" in summary
        assert "Hypothesis 1" in summary

    def test_record_result_nonexistent_hypothesis(self):
        hyps = self._make_hypotheses(2)
        pop = HypothesisPopulation(hyps)
        result = MatchupResult(
            hypothesis_a_id="h0",
            hypothesis_b_id="nonexistent",
            winner_id="h0",
        )
        # Should not raise
        pop.record_result(result)
        # h0 should be unchanged
        assert pop.hypotheses["h0"].elo_rating == 1500.0


# ===========================================================================
# Test TournamentHandler
# ===========================================================================


class TestTournamentHandler:
    @pytest.mark.asyncio
    async def test_extract_hypotheses(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Test hypothesis extraction from discussion."""
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = TournamentHandler(engine)

        # Set up messages
        engine.state.messages = [
            {"from": "theorist-0", "content": "I propose dark matter is axions."},
            {"from": "skeptic-0", "content": "I think it's WIMPs instead."},
        ]

        # Mock the provider to return structured JSON
        mock_provider = MagicMock()
        mock_provider.complete = MagicMock(
            return_value=(
                json.dumps(
                    [
                        {"statement": "Dark matter is axions", "rationale": "Light particles"},
                        {"statement": "Dark matter is WIMPs", "rationale": "Heavy particles"},
                    ]
                ),
                100,
                50,
            )
        )
        object.__setattr__(
            engine._config,
            "get_provider_and_model_for_role",
            MagicMock(return_value=(mock_provider, "test-model", None)),
        )

        hypotheses = await handler._extract_hypotheses_from_discussion()
        assert len(hypotheses) == 2
        assert "axions" in hypotheses[0].statement

    @pytest.mark.asyncio
    async def test_judge_matchup(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Test matchup judging."""
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = TournamentHandler(engine)

        h_a = Hypothesis(id="ha", statement="Hypothesis A", rationale="Good reasons")
        h_b = Hypothesis(id="hb", statement="Hypothesis B", rationale="Also good")

        mock_provider = MagicMock()
        mock_provider.complete = MagicMock(
            return_value=(
                json.dumps({"winner": "A", "reasoning": "A is better", "margin": 0.8}),
                50,
                30,
            )
        )
        object.__setattr__(
            engine._config,
            "get_provider_and_model_for_role",
            MagicMock(return_value=(mock_provider, "test-model", None)),
        )

        result = await handler._judge_matchup(h_a, h_b)
        assert result is not None
        assert result.winner_id == "ha"
        assert result.margin == 0.8

    @pytest.mark.asyncio
    async def test_full_tournament(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Test full tournament flow."""
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = TournamentHandler(engine)

        engine.state.world_model = WorldModel()
        engine.state.messages = [
            {"from": "theorist-0", "content": "H1 is good. H2 is also good. H3 is interesting."},
        ]

        call_count = [0]

        def mock_complete(*, model, system, messages, max_tokens, temperature=0.7, extra_body=None):
            call_count[0] += 1
            if call_count[0] == 1:
                # Extraction call
                return (
                    json.dumps(
                        [
                            {"statement": "H1", "rationale": "R1"},
                            {"statement": "H2", "rationale": "R2"},
                            {"statement": "H3", "rationale": "R3"},
                        ]
                    ),
                    100,
                    50,
                )
            else:
                # Judge calls — always pick A
                return (
                    json.dumps({"winner": "A", "reasoning": "A wins", "margin": 0.6}),
                    50,
                    30,
                )

        mock_provider = MagicMock()
        mock_provider.complete = MagicMock(side_effect=mock_complete)
        object.__setattr__(
            engine._config,
            "get_provider_and_model_for_role",
            MagicMock(return_value=(mock_provider, "test-model", None)),
        )

        engine.emit_event = MagicMock(wraps=engine.emit_event)

        winners = await handler.run_tournament()
        assert len(winners) == 2
        # All hypotheses should be in world model
        assert len(engine.state.world_model.hypotheses) == 3

        # C2 step 1: tournament belief updates route through revise_hypothesis,
        # tagging each hypothesis.updated with its source (+ selected for winners).
        updated = [
            c.args[1]
            for c in engine.emit_event.call_args_list
            if c.args and c.args[0] == "hypothesis.updated"
        ]
        assert updated, "tournament should emit hypothesis.updated events"
        assert all(u.get("source") == "tournament" for u in updated)
        assert any(u.get("selected") for u in updated)  # winners are flagged

    @pytest.mark.asyncio
    async def test_graceful_degradation_single_hypothesis(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        """Tournament with <2 hypotheses should skip and return as-is."""
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = TournamentHandler(engine)

        engine.state.world_model = WorldModel()
        engine.state.messages = [
            {"from": "theorist-0", "content": "Only one idea."},
        ]

        mock_provider = MagicMock()
        mock_provider.complete = MagicMock(
            return_value=(
                json.dumps([{"statement": "Single H", "rationale": "Only one"}]),
                100,
                50,
            )
        )
        object.__setattr__(
            engine._config,
            "get_provider_and_model_for_role",
            MagicMock(return_value=(mock_provider, "test-model", None)),
        )

        winners = await handler.run_tournament()
        assert len(winners) == 1
        assert winners[0].statement == "Single H"

    @pytest.mark.asyncio
    async def test_fallback_on_extraction_error(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Extraction failure should fall back to world model hypotheses."""
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = TournamentHandler(engine)

        wm = WorldModel()
        wm.add_hypothesis(Hypothesis(statement="Existing H1"))
        wm.add_hypothesis(Hypothesis(statement="Existing H2"))
        engine.state.world_model = wm
        engine.state.messages = [{"from": "agent", "content": "Discussion"}]

        call_count = [0]

        def mock_complete(*, model, system, messages, max_tokens, temperature=0.7, extra_body=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("LLM error")
            return (
                json.dumps({"winner": "A", "reasoning": "ok", "margin": 0.5}),
                50,
                30,
            )

        mock_provider = MagicMock()
        mock_provider.complete = MagicMock(side_effect=mock_complete)
        object.__setattr__(
            engine._config,
            "get_provider_and_model_for_role",
            MagicMock(return_value=(mock_provider, "test-model", None)),
        )

        winners = await handler.run_tournament()
        assert len(winners) == 2  # Fell back to world model hypotheses

    @pytest.mark.asyncio
    async def test_no_messages_returns_empty(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Empty messages should return empty list."""
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = TournamentHandler(engine)
        engine.state.messages = []
        engine.state.world_model = WorldModel()

        winners = await handler.run_tournament()
        assert winners == []


# ===========================================================================
# Test backward compatibility
# ===========================================================================


class TestBackwardCompatibility:
    def test_tournament_disabled_by_default(self, tmp_path):
        """When KnowledgeConfig uses defaults, tournament is disabled."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
        )
        assert not config.knowledge.enable_hypothesis_tournament
        assert config.knowledge.enable_world_model  # On by default
        assert not config.knowledge.enable_evidence_graph  # Off by default

    def test_config_with_knowledge_section(self, tmp_path):
        """KnowledgeConfig can be set from dict."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            knowledge={
                "enable_hypothesis_tournament": True,
                "tournament_population_size": 4,
            },
        )
        assert config.knowledge.enable_hypothesis_tournament
        assert config.knowledge.tournament_population_size == 4


class TestRobustJudgeParse:
    """The matchup judge must survive fences + chatty preamble — a brittle parse
    silently dropped every verdict and froze the whole tournament at Elo 1500."""

    def test_clean_json(self):
        assert _first_json_object('{"winner": "A", "margin": 0.7}') == {
            "winner": "A",
            "margin": 0.7,
        }

    def test_code_fenced(self):
        raw = '```json\n{\n  "winner": "B",\n  "margin": 0.6\n}\n```'
        assert _first_json_object(raw) == {"winner": "B", "margin": 0.6}

    def test_chatty_preamble(self):
        raw = 'Here is my verdict:\n{"winner": "B", "reasoning": "stronger", "margin": 0.8}\nDone.'
        out = _first_json_object(raw)
        assert out is not None and out["winner"] == "B"

    def test_garbage_returns_none(self):
        assert _first_json_object("the winner is A, clearly") is None
        assert _first_json_object("") is None

    def test_non_object_returns_none(self):
        assert _first_json_object("[1, 2, 3]") is None


# ===========================================================================
# C2 step 2 — tournament ranks the canonical world-model hypotheses
# ===========================================================================


class TestCanonicalPopulation:
    """_select_canonical_population: rank/dedup the canonical wm.hypotheses."""

    def _handler(self, mock_config, tmp_db, tmp_logger, mock_corpus, *, size=8):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        engine._config.knowledge.tournament_population_size = size
        engine.state.world_model = WorldModel()
        return engine, TournamentHandler(engine)

    def test_selects_canonical_objects_by_reference(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        engine, handler = self._handler(mock_config, tmp_db, tmp_logger, mock_corpus)
        a = Hypothesis(statement="Alpha causes beta")
        b = Hypothesis(statement="Gamma inhibits delta")
        engine.state.world_model.add_hypothesis(a)
        engine.state.world_model.add_hypothesis(b)

        pop = handler._select_canonical_population()
        assert len(pop) == 2
        # The SAME objects (identity), not copies — so Elo/status mutate canonically.
        assert any(h is a for h in pop)
        assert any(h is b for h in pop)

    def test_dedups_normalized_restatements(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine, handler = self._handler(mock_config, tmp_db, tmp_logger, mock_corpus)
        wm = engine.state.world_model
        wm.add_hypothesis(Hypothesis(statement="X drives Y"))
        wm.add_hypothesis(Hypothesis(statement="  x   DRIVES  y  "))  # same normalized
        wm.add_hypothesis(Hypothesis(statement="Z blocks W"))

        pop = handler._select_canonical_population()
        assert len(pop) == 2  # one X-drives-Y survives + Z-blocks-W

    def test_ranks_by_evidence_then_caps(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine, handler = self._handler(mock_config, tmp_db, tmp_logger, mock_corpus, size=2)
        wm = engine.state.world_model
        h_poor = Hypothesis(statement="poorly supported")
        h_mid = Hypothesis(statement="mid supported")
        h_rich = Hypothesis(statement="well supported")
        wm.add_hypothesis(h_poor)
        wm.add_hypothesis(h_mid)
        wm.add_hypothesis(h_rich)
        h_rich.supporting_evidence_ids = ["e1", "e2"]
        h_mid.contradicting_evidence_ids = ["e3"]

        pop = handler._select_canonical_population()
        assert pop[0] is h_rich  # most evidence leads
        assert h_poor not in pop  # poorest dropped by the size-2 cap

    def test_skips_blank_statements(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine, handler = self._handler(mock_config, tmp_db, tmp_logger, mock_corpus)
        wm = engine.state.world_model
        wm.add_hypothesis(Hypothesis(statement="a real hypothesis"))
        wm.add_hypothesis(Hypothesis(statement="   "))

        pop = handler._select_canonical_population()
        assert len(pop) == 1

    def test_empty_world_model_returns_empty(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine, handler = self._handler(mock_config, tmp_db, tmp_logger, mock_corpus)
        engine.state.world_model = None
        assert handler._select_canonical_population() == []


class TestUnifiedTournament:
    """run_tournament with knowledge.unified_hypotheses=True."""

    @pytest.mark.asyncio
    async def test_ranks_canonical_set_without_re_extracting(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        engine._config.knowledge.unified_hypotheses = True
        handler = TournamentHandler(engine)

        wm = WorldModel()
        engine.state.world_model = wm
        a = Hypothesis(statement="Alpha")
        b = Hypothesis(statement="Beta")
        c = Hypothesis(statement="Gamma")
        for h in (a, b, c):
            wm.add_hypothesis(h)

        # Re-extraction must NOT run in unified mode.
        handler._extract_hypotheses_from_discussion = AsyncMock()

        # Judge always picks A.
        mock_provider = MagicMock()
        mock_provider.complete = MagicMock(
            return_value=(
                json.dumps({"winner": "A", "reasoning": "A wins", "margin": 0.6}),
                50,
                30,
            )
        )
        object.__setattr__(
            engine._config,
            "get_provider_and_model_for_role",
            MagicMock(return_value=(mock_provider, "test-model", None)),
        )

        winners = await handler.run_tournament()

        handler._extract_hypotheses_from_discussion.assert_not_called()
        # No NEW hypotheses minted — the canonical 3 are ranked in place.
        assert len(wm.hypotheses) == 3
        # Canonical objects were mutated by reference (Elo moved off the 1500 start).
        assert any(h.elo_rating != 1500.0 for h in (a, b, c))
        # Winners come from the canonical set.
        assert winners and all(w in (a, b, c) for w in winners)


# ===========================================================================
# C2 step 5 — Swiss pairing (bounded judge calls for a larger field)
# ===========================================================================


class TestSwissPairing:
    def _pop(self, n: int) -> HypothesisPopulation:
        return HypothesisPopulation([Hypothesis(id=f"h{i}", statement=f"H{i}") for i in range(n)])

    def test_num_rounds(self):
        assert swiss_num_rounds(1) == 0
        assert swiss_num_rounds(2) == 1
        assert swiss_num_rounds(3) == 2
        assert swiss_num_rounds(4) == 2
        assert swiss_num_rounds(5) == 3
        assert swiss_num_rounds(8) == 3
        assert swiss_num_rounds(9) == 4

    def test_round_pairs_everyone_when_even(self):
        pairs = self._pop(4).generate_swiss_round(set())
        assert len(pairs) == 2
        assert len({x for p in pairs for x in p}) == 4

    def test_odd_field_gives_a_bye(self):
        pairs = self._pop(5).generate_swiss_round(set())
        assert len(pairs) == 2  # 2 matches, 1 competitor byed
        assert len({x for p in pairs for x in p}) == 4

    def test_avoids_rematch(self):
        pop = self._pop(4)
        r1 = pop.generate_swiss_round(set())
        played = {frozenset(p) for p in r1}
        r2 = pop.generate_swiss_round(played)
        assert all(frozenset(p) not in played for p in r2)

    def test_rematch_allowed_when_no_fresh_opponent(self):
        pop = self._pop(2)
        played = {frozenset(("h0", "h1"))}
        pairs = pop.generate_swiss_round(played)
        assert len(pairs) == 1 and set(pairs[0]) == {"h0", "h1"}

    def test_deterministic(self):
        pop = self._pop(6)
        assert pop.generate_swiss_round(set()) == pop.generate_swiss_round(set())

    @pytest.mark.asyncio
    async def test_large_field_uses_swiss_bounded_matchups(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        engine._config.knowledge.unified_hypotheses = True
        engine._config.knowledge.tournament_population_size = 8
        engine._config.knowledge.tournament_winners = 2
        handler = TournamentHandler(engine)

        wm = WorldModel()
        engine.state.world_model = wm
        for i in range(8):
            wm.add_hypothesis(Hypothesis(statement=f"Hypothesis number {i}"))

        mock_provider = MagicMock()
        mock_provider.complete = MagicMock(
            return_value=(
                json.dumps({"winner": "A", "reasoning": "A wins", "margin": 0.6}),
                50,
                30,
            )
        )
        object.__setattr__(
            engine._config,
            "get_provider_and_model_for_role",
            MagicMock(return_value=(mock_provider, "test-model", None)),
        )

        await handler.run_tournament()
        n_matchups = len(handler.get_tournament_data()["matchup_results"])
        # Swiss: 3 rounds x 4 = 12, far below round-robin's C(8,2) = 28.
        assert n_matchups == 12
