"""Tests for the evidence graph layer (Stage 2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from helpers import patch_config_provider

from paradigm.config import Config
from paradigm.knowledge.conflict_detection import ConflictDetector
from paradigm.knowledge.evidence_graph import (
    Assumption,
    AssumptionStatus,
    ConflictEdge,
    ConflictResolution,
    ConflictType,
    EvidenceGraph,
    ProvenanceChain,
    ProvenanceStep,
)
from paradigm.knowledge.models import (
    Evidence,
    EvidenceSource,
    Hypothesis,
    HypothesisStatus,
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
        knowledge={"enable_evidence_graph": True},
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
        config=config, database=db, corpus=corpus, logger=logger,
        agent_factory=factory,
    )
    engine.state.thread_id = "thread-test-eg"
    engine.state.seed_prompt = "Test research topic"
    engine.state.mode = "directed"
    engine._literature.literature_context = ""
    engine.state.checkpoint = None
    engine._memory_store = None
    return engine


# ===========================================================================
# Test models
# ===========================================================================


class TestConflictEdge:
    def test_creation(self):
        c = ConflictEdge(
            evidence_a_id="e1", evidence_b_id="e2",
            conflict_type=ConflictType.DIRECT_CONTRADICTION,
        )
        assert c.resolution_status == ConflictResolution.UNRESOLVED

    def test_resolution_status(self):
        c = ConflictEdge(
            evidence_a_id="e1", evidence_b_id="e2",
            conflict_type=ConflictType.METHODOLOGICAL,
            resolution_status=ConflictResolution.RESOLVED_SYNTHESIS,
        )
        assert c.resolution_status == ConflictResolution.RESOLVED_SYNTHESIS


class TestAssumption:
    def test_creation(self):
        a = Assumption(statement="Stars are spherical", basis="Simplifying assumption")
        assert a.status == AssumptionStatus.ACTIVE
        assert a.invalidated_by_evidence_id is None

    def test_with_dependents(self):
        a = Assumption(
            statement="No rotation",
            dependent_hypothesis_ids=["h1", "h2"],
        )
        assert len(a.dependent_hypothesis_ids) == 2


# ===========================================================================
# Test EvidenceGraph
# ===========================================================================


class TestEvidenceGraph:
    def _make_graph(self) -> EvidenceGraph:
        wm = WorldModel()
        return EvidenceGraph(wm)

    def test_add_and_get_conflict(self):
        eg = self._make_graph()
        c = ConflictEdge(
            evidence_a_id="e1", evidence_b_id="e2",
            conflict_type=ConflictType.DIRECT_CONTRADICTION,
        )
        cid = eg.add_conflict(c)
        assert eg.get_conflict(cid) is c

    def test_unresolved_conflicts(self):
        eg = self._make_graph()
        c1 = ConflictEdge(
            evidence_a_id="e1", evidence_b_id="e2",
            conflict_type=ConflictType.DIRECT_CONTRADICTION,
        )
        c2 = ConflictEdge(
            evidence_a_id="e3", evidence_b_id="e4",
            conflict_type=ConflictType.METHODOLOGICAL,
            resolution_status=ConflictResolution.RESOLVED_A,
        )
        eg.add_conflict(c1)
        eg.add_conflict(c2)
        unresolved = eg.get_unresolved_conflicts()
        assert len(unresolved) == 1
        assert unresolved[0].evidence_a_id == "e1"

    def test_resolve_conflict(self):
        eg = self._make_graph()
        c = ConflictEdge(
            evidence_a_id="e1", evidence_b_id="e2",
            conflict_type=ConflictType.DIRECT_CONTRADICTION,
        )
        cid = eg.add_conflict(c)
        assert eg.resolve_conflict(cid, ConflictResolution.RESOLVED_A, "A wins")
        assert c.resolution_status == ConflictResolution.RESOLVED_A
        assert c.resolution_notes == "A wins"

    def test_resolve_nonexistent(self):
        eg = self._make_graph()
        assert not eg.resolve_conflict("nope", ConflictResolution.RESOLVED_A)

    def test_assumption_cascade(self):
        wm = WorldModel()
        h1 = Hypothesis(statement="H1")
        h2 = Hypothesis(statement="H2")
        hid1 = wm.add_hypothesis(h1)
        hid2 = wm.add_hypothesis(h2)

        eg = EvidenceGraph(wm)
        a = Assumption(
            statement="Spherical symmetry",
            dependent_hypothesis_ids=[hid1, hid2],
        )
        aid = eg.add_assumption(a)

        ev = Evidence(content="Observed asymmetry", source=EvidenceSource.EXPERIMENT)
        evid = wm.add_evidence(ev)

        affected = eg.invalidate_assumption(aid, evid)
        assert len(affected) == 2
        assert a.status == AssumptionStatus.INVALIDATED
        assert h1.status == HypothesisStatus.CONTRADICTED
        assert h2.status == HypothesisStatus.CONTRADICTED

    def test_assumption_cascade_skips_already_abandoned(self):
        wm = WorldModel()
        h1 = Hypothesis(statement="H1", status=HypothesisStatus.ABANDONED)
        hid1 = wm.add_hypothesis(h1)

        eg = EvidenceGraph(wm)
        a = Assumption(statement="X", dependent_hypothesis_ids=[hid1])
        aid = eg.add_assumption(a)

        affected = eg.invalidate_assumption(aid, "ev1")
        assert len(affected) == 0  # Already abandoned, not affected

    def test_hypothesis_strength(self):
        wm = WorldModel()
        h = Hypothesis(statement="H1")
        hid = wm.add_hypothesis(h)

        ev1 = Evidence(content="Supports", source=EvidenceSource.EXPERIMENT)
        ev2 = Evidence(content="Also supports", source=EvidenceSource.LITERATURE)
        ev3 = Evidence(content="Contradicts", source=EvidenceSource.EXPERIMENT)
        evid1 = wm.add_evidence(ev1)
        evid2 = wm.add_evidence(ev2)
        evid3 = wm.add_evidence(ev3)

        wm.link_evidence_to_hypothesis(evid1, hid, supports=True)
        wm.link_evidence_to_hypothesis(evid2, hid, supports=True)
        wm.link_evidence_to_hypothesis(evid3, hid, supports=False)

        eg = EvidenceGraph(wm)
        strength = eg.assess_hypothesis_strength(hid)
        assert strength["support_count"] == 2
        assert strength["contradict_count"] == 1
        assert strength["strength_score"] == 1  # 2 - 1

    def test_hypothesis_strength_nonexistent(self):
        eg = self._make_graph()
        result = eg.assess_hypothesis_strength("nope")
        assert "error" in result

    def test_provenance_chain(self):
        eg = self._make_graph()
        chain = ProvenanceChain(
            conclusion_id="h1",
            steps=[
                ProvenanceStep(evidence_id="e1", description="Step 1"),
                ProvenanceStep(evidence_id="e2", description="Step 2"),
            ],
            confidence=0.8,
        )
        cid = eg.add_provenance(chain)
        assert eg.get_provenance(cid) is chain
        chains = eg.get_provenance_for_hypothesis("h1")
        assert len(chains) == 1

    def test_evidence_landscape_summary(self):
        wm = WorldModel()
        h = Hypothesis(statement="Test hypothesis")
        hid = wm.add_hypothesis(h)

        eg = EvidenceGraph(wm)
        eg.add_conflict(ConflictEdge(
            evidence_a_id="e1", evidence_b_id="e2",
            conflict_type=ConflictType.DIRECT_CONTRADICTION,
        ))
        eg.add_assumption(Assumption(
            statement="Linear regime",
            dependent_hypothesis_ids=[hid],
        ))

        summary = eg.summarize_evidence_landscape()
        assert "Unresolved Conflicts" in summary
        assert "Active Assumptions" in summary
        assert "Linear regime" in summary

    def test_snapshot_round_trip(self):
        wm = WorldModel()
        wm.add_hypothesis(Hypothesis(statement="Test"))
        eg = EvidenceGraph(wm)
        eg.add_conflict(ConflictEdge(
            evidence_a_id="e1", evidence_b_id="e2",
            conflict_type=ConflictType.DIRECT_CONTRADICTION,
        ))
        eg.add_assumption(Assumption(statement="Linear"))

        snap = eg.to_snapshot()
        eg2 = EvidenceGraph.from_snapshot(snap)
        assert len(eg2.conflicts) == 1
        assert len(eg2.assumptions) == 1
        assert len(eg2.world_model.hypotheses) == 1


# ===========================================================================
# Test ConflictDetector
# ===========================================================================


class TestConflictDetector:
    def test_detect_contradiction(self):
        """New evidence contradicts H while existing evidence supports H."""
        wm = WorldModel()
        h = Hypothesis(statement="Gravity is repulsive")
        hid = wm.add_hypothesis(h)

        ev_support = Evidence(content="Repulsion observed", source=EvidenceSource.EXPERIMENT)
        ev_support_id = wm.add_evidence(ev_support)
        wm.link_evidence_to_hypothesis(ev_support_id, hid, supports=True)

        eg = EvidenceGraph(wm)
        detector = ConflictDetector(eg)

        ev_contradict = Evidence(
            content="Attraction measured",
            source=EvidenceSource.EXPERIMENT,
            contradicts_hypothesis_ids=[hid],
        )
        ev_contradict_id = wm.add_evidence(ev_contradict)

        conflicts = detector.check_new_evidence(ev_contradict)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.DIRECT_CONTRADICTION
        assert conflicts[0].evidence_a_id == ev_contradict_id
        assert conflicts[0].evidence_b_id == ev_support_id

    def test_detect_support_vs_contradiction(self):
        """New evidence supports H while existing evidence contradicts H."""
        wm = WorldModel()
        h = Hypothesis(statement="Dark energy exists")
        hid = wm.add_hypothesis(h)

        ev_contra = Evidence(content="No expansion", source=EvidenceSource.LITERATURE)
        ev_contra_id = wm.add_evidence(ev_contra)
        wm.link_evidence_to_hypothesis(ev_contra_id, hid, supports=False)

        eg = EvidenceGraph(wm)
        detector = ConflictDetector(eg)

        ev_support = Evidence(
            content="Accelerating expansion",
            source=EvidenceSource.EXPERIMENT,
            supports_hypothesis_ids=[hid],
        )
        wm.add_evidence(ev_support)

        conflicts = detector.check_new_evidence(ev_support)
        assert len(conflicts) == 1

    def test_no_false_positives(self):
        """Evidence supporting H with no contradicting evidence → no conflicts."""
        wm = WorldModel()
        h = Hypothesis(statement="Photons are massless")
        hid = wm.add_hypothesis(h)

        ev1 = Evidence(content="E=pc confirmed", source=EvidenceSource.EXPERIMENT)
        wm.add_evidence(ev1)
        wm.link_evidence_to_hypothesis(ev1.id, hid, supports=True)

        eg = EvidenceGraph(wm)
        detector = ConflictDetector(eg)

        ev2 = Evidence(
            content="More confirmation",
            source=EvidenceSource.EXPERIMENT,
            supports_hypothesis_ids=[hid],
        )
        wm.add_evidence(ev2)

        conflicts = detector.check_new_evidence(ev2)
        assert len(conflicts) == 0

    def test_no_conflicts_on_unrelated_evidence(self):
        """Evidence unrelated to any hypothesis → no conflicts."""
        wm = WorldModel()
        wm.add_hypothesis(Hypothesis(statement="H1"))

        eg = EvidenceGraph(wm)
        detector = ConflictDetector(eg)

        ev = Evidence(content="Unrelated finding", source=EvidenceSource.LITERATURE)
        wm.add_evidence(ev)

        conflicts = detector.check_new_evidence(ev)
        assert len(conflicts) == 0


# ===========================================================================
# Test Handler Integration
# ===========================================================================


class TestHandlerIntegration:
    def test_initialize_evidence_graph(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        engine.state.world_model = handler.initialize_world_model()

        eg = handler.initialize_evidence_graph()
        assert isinstance(eg, EvidenceGraph)
        assert eg.world_model is engine.state.world_model

    def test_detect_and_register_conflicts(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        wm = handler.initialize_world_model()
        engine.state.world_model = wm
        eg = handler.initialize_evidence_graph()
        engine.state.evidence_graph = eg

        h = Hypothesis(statement="Test H")
        hid = wm.add_hypothesis(h)

        ev_support = Evidence(content="Supports", source=EvidenceSource.EXPERIMENT)
        wm.add_evidence(ev_support)
        wm.link_evidence_to_hypothesis(ev_support.id, hid, supports=True)

        ev_contradict = Evidence(
            content="Contradicts",
            source=EvidenceSource.EXPERIMENT,
            contradicts_hypothesis_ids=[hid],
        )
        wm.add_evidence(ev_contradict)

        conflicts = handler.detect_and_register_conflicts(ev_contradict)
        assert len(conflicts) == 1
        assert len(eg.conflicts) == 1

    def test_build_evidence_landscape_context(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        wm = handler.initialize_world_model()
        engine.state.world_model = wm

        eg = handler.initialize_evidence_graph()
        engine.state.evidence_graph = eg

        h = Hypothesis(statement="Test")
        wm.add_hypothesis(h)
        eg.add_assumption(Assumption(
            statement="Linear approx",
            dependent_hypothesis_ids=[h.id],
        ))

        ctx = handler.build_evidence_landscape_context()
        assert "## Evidence Landscape" in ctx
        assert "Linear approx" in ctx

    def test_no_evidence_graph_returns_empty(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        engine = _build_engine(mock_config, tmp_db, tmp_logger, mock_corpus)
        handler = WorldModelHandler(engine)
        engine.state.evidence_graph = None

        assert handler.build_evidence_landscape_context() == ""
        assert handler.detect_and_register_conflicts(
            Evidence(content="test", source=EvidenceSource.EXPERIMENT)
        ) == []
