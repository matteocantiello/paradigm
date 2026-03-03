"""Tests for the knowledge architecture world model (Stage 1)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from helpers import patch_config_provider

from paradigm.config import Config
from paradigm.knowledge.models import (
    ConfidenceLevel,
    Entity,
    EntityType,
    Evidence,
    EvidenceSource,
    Hypothesis,
    HypothesisStatus,
    OpenQuestion,
    Relationship,
    RelationshipType,
    ResearchGoal,
)
from paradigm.knowledge.world_model import WorldModel
from paradigm.knowledge.world_model_handler import WorldModelHandler
from paradigm.logging.events import EventLogger
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.storage.database import Database

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
    )
    patch_config_provider(config)
    return config


@pytest.fixture
def mock_corpus():
    corpus = MagicMock()
    corpus.search = MagicMock(return_value=[])
    return corpus


def _build_engine(config, db, logger, corpus) -> OrchestrationEngine:
    """Build an engine with minimal state for handler testing."""
    factory = MagicMock()
    factory.create_team = MagicMock(return_value=[])

    engine = OrchestrationEngine(
        config=config,
        database=db,
        corpus=corpus,
        logger=logger,
        agent_factory=factory,
    )
    engine.state.thread_id = "thread-test-wm"
    engine.state.seed_prompt = "Test research topic"
    engine.state.mode = "directed"
    engine._literature.literature_context = ""
    engine.state.checkpoint = None
    engine._memory_store = None
    return engine


# ===========================================================================
# Test Pydantic Models
# ===========================================================================


class TestModels:
    """Test Pydantic model creation and enum validation."""

    def test_entity_creation(self):
        e = Entity(name="dark matter", entity_type=EntityType.CONCEPT)
        assert e.name == "dark matter"
        assert e.entity_type == EntityType.CONCEPT
        assert e.id  # auto-generated

    def test_entity_with_properties(self):
        e = Entity(
            name="stellar mass",
            entity_type=EntityType.QUANTITY,
            description="Mass of a star",
            properties={"unit": "solar masses"},
        )
        assert e.properties["unit"] == "solar masses"

    def test_hypothesis_defaults(self):
        h = Hypothesis(statement="Dark matter is composed of WIMPs")
        assert h.status == HypothesisStatus.PROPOSED
        assert h.confidence == ConfidenceLevel.SPECULATIVE
        assert h.elo_rating == 1500.0
        assert h.supporting_evidence_ids == []

    def test_evidence_creation(self):
        ev = Evidence(
            content="Rotation curves show flat profiles",
            source=EvidenceSource.LITERATURE,
            source_ref="arxiv:1234.5678",
        )
        assert ev.source == EvidenceSource.LITERATURE

    def test_relationship_creation(self):
        r = Relationship(
            source_id="e1",
            target_id="e2",
            relationship_type=RelationshipType.CAUSES,
        )
        assert r.relationship_type == RelationshipType.CAUSES

    def test_open_question(self):
        oq = OpenQuestion(question="What is the mass of the Higgs boson?")
        assert oq.priority == ConfidenceLevel.MODERATE

    def test_research_goal(self):
        g = ResearchGoal(
            description="Determine dark matter composition",
            success_criteria="Identify candidate particle",
        )
        assert g.status == HypothesisStatus.PROPOSED


# ===========================================================================
# Test WorldModel CRUD
# ===========================================================================


class TestWorldModelCRUD:
    """Test WorldModel CRUD operations."""

    def test_add_and_get_entity(self):
        wm = WorldModel()
        e = Entity(name="neutron star", entity_type=EntityType.OBJECT)
        eid = wm.add_entity(e)
        assert wm.get_entity(eid) is e

    def test_remove_entity(self):
        wm = WorldModel()
        e = Entity(name="pulsar", entity_type=EntityType.OBJECT)
        eid = wm.add_entity(e)
        assert wm.remove_entity(eid)
        assert wm.get_entity(eid) is None
        assert not wm.remove_entity("nonexistent")

    def test_add_and_get_hypothesis(self):
        wm = WorldModel()
        h = Hypothesis(statement="Pulsars are neutron stars")
        hid = wm.add_hypothesis(h)
        assert wm.get_hypothesis(hid) is h

    def test_update_hypothesis(self):
        wm = WorldModel()
        h = Hypothesis(statement="Test hypothesis")
        hid = wm.add_hypothesis(h)
        assert wm.update_hypothesis(hid, status=HypothesisStatus.SUPPORTED)
        assert wm.get_hypothesis(hid).status == HypothesisStatus.SUPPORTED

    def test_update_hypothesis_nonexistent(self):
        wm = WorldModel()
        assert not wm.update_hypothesis("nope", status=HypothesisStatus.SUPPORTED)

    def test_add_and_get_evidence(self):
        wm = WorldModel()
        ev = Evidence(content="Observation X", source=EvidenceSource.EXPERIMENT)
        evid = wm.add_evidence(ev)
        assert wm.get_evidence(evid) is ev

    def test_add_and_get_relationship(self):
        wm = WorldModel()
        r = Relationship(
            source_id="a", target_id="b",
            relationship_type=RelationshipType.CORRELATES_WITH,
        )
        rid = wm.add_relationship(r)
        assert wm.get_relationship(rid) is r

    def test_add_and_get_open_question(self):
        wm = WorldModel()
        oq = OpenQuestion(question="Why?")
        oqid = wm.add_open_question(oq)
        assert wm.get_open_question(oqid) is oq

    def test_add_and_get_research_goal(self):
        wm = WorldModel()
        g = ResearchGoal(description="Find it")
        gid = wm.add_research_goal(g)
        assert wm.get_research_goal(gid) is g


# ===========================================================================
# Test Evidence ↔ Hypothesis Linking
# ===========================================================================


class TestEvidenceLinking:
    """Test evidence-hypothesis linking."""

    def test_link_supporting_evidence(self):
        wm = WorldModel()
        h = Hypothesis(statement="H1")
        ev = Evidence(content="E1", source=EvidenceSource.EXPERIMENT)
        hid = wm.add_hypothesis(h)
        evid = wm.add_evidence(ev)

        assert wm.link_evidence_to_hypothesis(evid, hid, supports=True)
        assert hid in ev.supports_hypothesis_ids
        assert evid in h.supporting_evidence_ids

    def test_link_contradicting_evidence(self):
        wm = WorldModel()
        h = Hypothesis(statement="H1")
        ev = Evidence(content="E1", source=EvidenceSource.EXPERIMENT)
        hid = wm.add_hypothesis(h)
        evid = wm.add_evidence(ev)

        assert wm.link_evidence_to_hypothesis(evid, hid, supports=False)
        assert hid in ev.contradicts_hypothesis_ids
        assert evid in h.contradicting_evidence_ids

    def test_link_nonexistent_returns_false(self):
        wm = WorldModel()
        assert not wm.link_evidence_to_hypothesis("no", "nope", supports=True)

    def test_link_idempotent(self):
        wm = WorldModel()
        h = Hypothesis(statement="H1")
        ev = Evidence(content="E1", source=EvidenceSource.EXPERIMENT)
        hid = wm.add_hypothesis(h)
        evid = wm.add_evidence(ev)

        wm.link_evidence_to_hypothesis(evid, hid, supports=True)
        wm.link_evidence_to_hypothesis(evid, hid, supports=True)
        assert len(h.supporting_evidence_ids) == 1


# ===========================================================================
# Test Summarization
# ===========================================================================


class TestSummarize:
    """Test world model summarization."""

    def test_empty_summary(self):
        wm = WorldModel()
        assert wm.summarize_state() == ""

    def test_summary_with_hypotheses(self):
        wm = WorldModel()
        wm.add_hypothesis(Hypothesis(statement="Stars explode"))
        summary = wm.summarize_state()
        assert "Stars explode" in summary
        assert "Hypotheses" in summary

    def test_summary_truncation(self):
        wm = WorldModel()
        for i in range(100):
            wm.add_entity(Entity(
                name=f"entity_{i}",
                entity_type=EntityType.CONCEPT,
                description="A " * 100,
            ))
        summary = wm.summarize_state(max_chars=200)
        assert len(summary) <= 220  # 200 + truncation message
        assert "truncated" in summary

    def test_summary_includes_research_goals(self):
        wm = WorldModel()
        wm.add_research_goal(ResearchGoal(description="Find the answer"))
        summary = wm.summarize_state()
        assert "Find the answer" in summary

    def test_summary_hypothesis_ordering(self):
        wm = WorldModel()
        wm.add_hypothesis(Hypothesis(statement="Low Elo", elo_rating=1200.0))
        wm.add_hypothesis(Hypothesis(statement="High Elo", elo_rating=1800.0))
        summary = wm.summarize_state()
        high_pos = summary.index("High Elo")
        low_pos = summary.index("Low Elo")
        assert high_pos < low_pos


# ===========================================================================
# Test Snapshot Serialization
# ===========================================================================


class TestSnapshot:
    """Test snapshot round-trip serialization."""

    def test_empty_round_trip(self):
        wm = WorldModel()
        snap = wm.to_snapshot()
        wm2 = WorldModel.from_snapshot(snap)
        assert len(wm2.entities) == 0

    def test_populated_round_trip(self):
        wm = WorldModel()
        wm.add_entity(Entity(name="star", entity_type=EntityType.OBJECT))
        wm.add_hypothesis(Hypothesis(statement="Stars shine"))
        wm.add_evidence(Evidence(content="Light detected", source=EvidenceSource.EXPERIMENT))
        wm.add_research_goal(ResearchGoal(description="Study stars"))
        wm.add_open_question(OpenQuestion(question="Why?"))
        wm.add_relationship(Relationship(
            source_id="a", target_id="b",
            relationship_type=RelationshipType.CAUSES,
        ))

        snap = wm.to_snapshot()
        wm2 = WorldModel.from_snapshot(snap)

        assert len(wm2.entities) == 1
        assert len(wm2.hypotheses) == 1
        assert len(wm2.evidence) == 1
        assert len(wm2.research_goals) == 1
        assert len(wm2.open_questions) == 1
        assert len(wm2.relationships) == 1

    def test_json_round_trip(self):
        wm = WorldModel()
        wm.add_hypothesis(Hypothesis(statement="Test", elo_rating=1600.0))
        json_str = wm.to_json()
        wm2 = WorldModel.from_json(json_str)
        hyp = list(wm2.hypotheses.values())[0]
        assert hyp.statement == "Test"
        assert hyp.elo_rating == 1600.0


# ===========================================================================
# Test WorldModelHandler
# ===========================================================================


class TestWorldModelHandler:
    """Test the handler lifecycle and parsing."""

    def test_initialize_creates_goal(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        wm = handler.initialize_world_model()
        assert len(wm.research_goals) == 1
        goal = list(wm.research_goals.values())[0]
        assert "Test research topic" in goal.description

    def test_build_context_empty(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        engine.state.world_model = WorldModel()
        ctx = handler.build_world_model_context()
        assert ctx == ""

    def test_build_context_with_data(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        wm = handler.initialize_world_model()
        engine.state.world_model = wm
        ctx = handler.build_world_model_context()
        assert "## World Model" in ctx
        assert "Research Goals" in ctx

    def test_parse_entity_tag(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        engine.state.world_model = WorldModel()

        content = "Here is an [ENTITY: dark matter | concept | invisible mass] in my analysis."
        handler.update_from_agent_response("agent-1", content, "ideation")

        assert len(engine.state.world_model.entities) == 1
        ent = list(engine.state.world_model.entities.values())[0]
        assert ent.name == "dark matter"
        assert ent.entity_type == EntityType.CONCEPT
        assert "invisible mass" in ent.description

    def test_parse_hypothesis_tag(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        engine.state.world_model = WorldModel()

        content = "I propose [HYPOTHESIS: dark matter is composed of axions]."
        handler.update_from_agent_response("agent-1", content, "ideation")

        assert len(engine.state.world_model.hypotheses) == 1
        hyp = list(engine.state.world_model.hypotheses.values())[0]
        assert "axions" in hyp.statement

    def test_parse_evidence_tag(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        engine.state.world_model = WorldModel()

        content = "[EVIDENCE: rotation curves are flat | literature]"
        handler.update_from_agent_response("agent-1", content, "ideation")

        assert len(engine.state.world_model.evidence) == 1
        ev = list(engine.state.world_model.evidence.values())[0]
        assert "rotation curves" in ev.content
        assert ev.source == EvidenceSource.LITERATURE

    def test_parse_multiple_tags(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        engine.state.world_model = WorldModel()

        content = (
            "[ENTITY: galaxy | object | a large system]\n"
            "[HYPOTHESIS: galaxies contain dark matter]\n"
            "[EVIDENCE: velocity dispersions are high | experiment]\n"
        )
        handler.update_from_agent_response("agent-1", content, "ideation")

        assert len(engine.state.world_model.entities) == 1
        assert len(engine.state.world_model.hypotheses) == 1
        assert len(engine.state.world_model.evidence) == 1

    def test_no_world_model_skips_parsing(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        engine.state.world_model = None

        # Should not raise
        handler.update_from_agent_response("agent-1", "[ENTITY: test]", "ideation")


# ===========================================================================
# Test Database Persistence
# ===========================================================================


class TestPersistence:
    """Test snapshot persistence to database."""

    def test_persist_and_load(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)

        wm = handler.initialize_world_model()
        wm.add_hypothesis(Hypothesis(statement="Test persistence"))
        engine.state.world_model = wm

        handler.persist_snapshot()

        loaded = handler.load_snapshot("thread-test-wm")
        assert loaded is not None
        assert len(loaded.hypotheses) == 1
        hyp = list(loaded.hypotheses.values())[0]
        assert hyp.statement == "Test persistence"

    def test_load_nonexistent_returns_none(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        assert handler.load_snapshot("nonexistent-thread") is None

    def test_save_to_thread(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)

        wm = WorldModel()
        wm.add_entity(Entity(name="test", entity_type=EntityType.CONCEPT))
        engine.state.world_model = wm

        handler.save_to_thread("paper-001")

        path = mock_config.storage.papers_dir / "paper-001" / "knowledge" / "world_model.json"
        assert path.exists()
        loaded = WorldModel.from_json(path.read_text())
        assert len(loaded.entities) == 1
