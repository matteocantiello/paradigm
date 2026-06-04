"""Tests for Phase 1D — eval extension: seeds/splits, calibration, new metrics, persistence."""

from __future__ import annotations

import json

import pytest

from paradigm.eval.calibration import fit_threshold, label_for_status
from paradigm.eval.harness import run_live_eval
from paradigm.eval.metrics import compute_metrics, prereg_verdict, reproduction_pass_rate
from paradigm.eval.models import OUTCOME_SCORES
from paradigm.eval.seeds import DEFAULT_SEEDS, SeedPrompt, split_seeds
from paradigm.storage.database import Database

# ---------------------------------------------------------------------------
# Seeds + splits
# ---------------------------------------------------------------------------


def _seeds(n: int) -> list[SeedPrompt]:
    return [SeedPrompt(id=f"s{i}", prompt=f"prompt {i}") for i in range(n)]


class TestSplitSeeds:
    def test_partitions_all_seeds_once(self):
        seeds = _seeds(50)
        splits = split_seeds(seeds)
        total = splits["train"] + splits["selection"] + splits["test"]
        assert sorted(s.id for s in total) == sorted(s.id for s in seeds)

    def test_deterministic(self):
        seeds = _seeds(40)
        a = split_seeds(seeds)
        b = split_seeds(seeds)
        assert {k: [s.id for s in v] for k, v in a.items()} == {
            k: [s.id for s in v] for k, v in b.items()
        }

    def test_no_test_leakage_when_adding_seeds(self):
        # Adding seeds must not move an existing seed out of its split.
        first = split_seeds(_seeds(20))
        second = split_seeds(_seeds(40))
        for name, seeds in first.items():
            ids = {s.id for s in seeds}
            second_ids = {s.id for s in second[name]}
            assert ids <= second_ids

    def test_rng_seed_changes_assignment(self):
        seeds = _seeds(40)
        a = {s.id for s in split_seeds(seeds, rng_seed="x")["train"]}
        b = {s.id for s in split_seeds(seeds, rng_seed="y")["train"]}
        assert a != b

    def test_default_seeds_split(self):
        splits = split_seeds(DEFAULT_SEEDS)
        assert sum(len(v) for v in splits.values()) == len(DEFAULT_SEEDS)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


class TestCalibration:
    def test_separable_data(self):
        labeled = [(0.9, True), (0.85, True), (0.2, False), (0.1, False)]
        result = fit_threshold(labeled)
        assert result.balanced_accuracy == 1.0
        assert 0.2 < result.threshold <= 0.85
        assert result.n_positive == 2
        assert result.n_negative == 2

    def test_single_class_neutral(self):
        result = fit_threshold([(0.9, True), (0.8, True)])
        assert result.threshold == 0.5
        assert result.balanced_accuracy == 0.0

    def test_label_for_status(self):
        assert label_for_status("published") is True
        assert label_for_status("rejected") is False
        assert label_for_status("review_rejected") is False
        assert label_for_status("draft") is None


# ---------------------------------------------------------------------------
# New metrics
# ---------------------------------------------------------------------------


class TestNewMetrics:
    def test_reproduction_pass_rate(self):
        paper = {
            "verification": json.dumps(
                [{"status": "accepted"}, {"status": "accepted"}, {"status": "nondeterministic"}]
            )
        }
        assert reproduction_pass_rate(paper) == pytest.approx(2 / 3, abs=1e-3)

    def test_reproduction_pass_rate_absent(self):
        assert reproduction_pass_rate({}) is None
        assert reproduction_pass_rate({"verification": ""}) is None

    def test_prereg_verdict_single(self):
        paper = {"prereg": json.dumps([{"verdict": "confirmed"}, {"verdict": "confirmed"}])}
        assert prereg_verdict(paper) == "confirmed"

    def test_prereg_verdict_mixed(self):
        paper = {"prereg": json.dumps([{"verdict": "confirmed"}, {"verdict": "refuted"}])}
        assert prereg_verdict(paper) == "mixed"

    def test_prereg_verdict_absent(self):
        assert prereg_verdict({}) is None

    def test_compute_metrics_populates_new_fields(self):
        paper = {
            "status": "published",
            "body": "# Title\n## Results\nRESULT here.",
            "verification": json.dumps([{"status": "accepted"}]),
            "prereg": json.dumps([{"verdict": "refuted"}]),
        }
        det = compute_metrics(paper)
        assert det.reproduction_pass_rate == 1.0
        assert det.prereg_verdict == "refuted"

    def test_new_outcome_scores_exist(self):
        assert OUTCOME_SCORES["verification_failed"] == 0.10
        assert OUTCOME_SCORES["prereg_failed"] == 0.05


# ---------------------------------------------------------------------------
# DB persistence round-trip
# ---------------------------------------------------------------------------


class TestDbPersistence:
    def test_verification_prereg_provenance_round_trip(self, tmp_path):
        db = Database(tmp_path / "t.db")
        try:
            db.create_paper("p1", "Title", "Abstract", ["a1"], "# Body", status="published")
            db.update_paper(
                "p1",
                verification=[{"experiment_name": "e1", "status": "accepted"}],
                prereg=[{"verdict": "confirmed"}],
                provenance={"framed_by": "human", "verified_by": "kernel+human"},
            )
            paper = db.get_paper("p1")
            assert reproduction_pass_rate(paper) == 1.0
            assert prereg_verdict(paper) == "confirmed"
            assert json.loads(paper["provenance"])["framed_by"] == "human"
        finally:
            db.close()

    def test_columns_idempotent_on_reopen(self, tmp_path):
        db_path = tmp_path / "t.db"
        Database(db_path).close()
        # Re-opening must not error (ALTER guarded by PRAGMA table_info).
        db = Database(db_path)
        db.close()


# ---------------------------------------------------------------------------
# Live eval (fake cycle + db)
# ---------------------------------------------------------------------------


class _FakeDb:
    def __init__(self, paper):
        self._paper = paper

    def get_thread(self, thread_id):
        return {"current_draft_id": "p1"} if thread_id else None

    def get_paper(self, paper_id):
        return self._paper if paper_id == "p1" else None

    def get_thread_id_for_paper(self, paper_id):
        return None


class TestRunLiveEval:
    def test_scores_fresh_paper(self, tmp_path):
        paper = {"id": "p1", "title": "T", "status": "published", "body": "# T\n## R\nx"}
        report = run_live_eval(
            run_cycle=lambda seed: "thread-1",
            seeds=_seeds(2),
            database=_FakeDb(paper),
            papers_dir=tmp_path,
        )
        assert report.count == 2

    def test_skips_failed_cycles(self, tmp_path):
        paper = {"id": "p1", "title": "T", "status": "published", "body": "# T"}

        def run_cycle(seed):
            if seed.id == "s0":
                raise SystemExit(1)
            return "thread-1"

        report = run_live_eval(
            run_cycle=run_cycle,
            seeds=_seeds(2),
            database=_FakeDb(paper),
            papers_dir=tmp_path,
        )
        assert report.count == 1

    def test_skips_when_no_thread(self, tmp_path):
        paper = {"id": "p1", "title": "T", "status": "published", "body": "# T"}
        report = run_live_eval(
            run_cycle=lambda seed: None,
            seeds=_seeds(3),
            database=_FakeDb(paper),
            papers_dir=tmp_path,
        )
        assert report.count == 0
