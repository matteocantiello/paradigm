"""Tests for the evaluation harness (deterministic metrics + blending + collection)."""

from __future__ import annotations

from paradigm.eval.harness import run_offline_eval, score_paper
from paradigm.eval.judge import _parse_judge_json
from paradigm.eval.metrics import (
    compute_metrics,
    count_sections,
    figure_stats,
    has_references_section,
    reference_stats,
)
from paradigm.eval.models import DeterministicMetrics, JudgeScores, PaperScore

_SAMPLE = """# A Study of Something

## Abstract
We study something.

## Introduction
Background here.

## Methods
We did things.

## Results
We found ![Figure 1](figures/fig1.png) a trend.

## References
- Smith et al. 2020, A real citation with descriptive text, Journal X
- https://arxiv.org/abs/1234.5678
- [3] Jones 2021, Another proper reference, MNRAS
"""


def test_count_sections_and_references():
    assert count_sections(_SAMPLE) == 6  # title + 5 section headings
    assert has_references_section(_SAMPLE) is True


def test_reference_stats_detects_bare_url():
    total, bare = reference_stats(_SAMPLE)
    assert total == 3
    assert bare == 1  # the lone arxiv URL


def test_figure_stats_missing_and_present(tmp_path):
    # No paper dir → referenced but not present
    ref, present = figure_stats(_SAMPLE, None)
    assert ref == 1
    assert present == 0

    # Create the referenced figure on disk → present
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "fig1.png").write_bytes(b"x")
    ref, present = figure_stats(_SAMPLE, tmp_path)
    assert ref == 1
    assert present == 1


def test_figure_stats_data_uri_counts_present():
    body = "![embedded](data:image/png;base64,AAAA)"
    ref, present = figure_stats(body, None)
    assert (ref, present) == (1, 1)


def test_compute_metrics_outcome_score():
    paper = {"id": "p1", "title": "T", "body": _SAMPLE, "status": "published", "citation_count": 3}
    m = compute_metrics(paper, None)
    assert m.outcome_score == 1.0
    assert m.has_references is True
    assert m.total_references == 3
    assert m.bare_url_references == 1
    assert 0.0 < m.citation_quality < 1.0

    failed = {**paper, "status": "execution_failed"}
    assert compute_metrics(failed, None).outcome_score == 0.10


def test_blend_with_and_without_judge():
    det = DeterministicMetrics(
        outcome="published", outcome_score=1.0, num_sections=6, has_references=True
    )
    no_judge = PaperScore.blend(det, None)
    judge = JudgeScores(novelty=8, rigor=8, clarity=8, significance=8, honesty=8)
    with_judge = PaperScore.blend(det, judge)
    assert 0.0 <= no_judge <= 100.0
    assert 0.0 <= with_judge <= 100.0
    # A strong judge score should not collapse a high deterministic score.
    assert with_judge > 50.0


def test_parse_judge_json_variants():
    good = '{"novelty": 7, "rigor": 6, "clarity": 8, "significance": 5, "honesty": 9}'
    assert _parse_judge_json(good).novelty == 7
    fenced = "```json\n" + good + "\n```"
    assert _parse_judge_json(fenced).rigor == 6
    assert _parse_judge_json("not json at all") is None


class _StubDB:
    """Minimal database stub for run_offline_eval."""

    def __init__(self, papers):
        self._papers = papers

    def list_papers(self, status=None, limit=None):
        return list(self._papers)

    def get_thread_id_for_paper(self, paper_id):
        return None

    def get_token_usage(self, thread_id=None, agent_id=None):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def test_run_offline_eval_excludes_external(tmp_path):
    papers = [
        {
            "id": "p1",
            "title": "Generated",
            "body": _SAMPLE,
            "status": "published",
            "citation_count": 0,
        },
        {"id": "ext1", "title": "Ingested", "body": "x", "status": "external", "citation_count": 0},
    ]
    report = run_offline_eval(_StubDB(papers), tmp_path)
    assert report.count == 1
    assert report.scores[0].paper_id == "p1"
    assert report.judged is False

    # include_external picks up the ingested paper too
    report2 = run_offline_eval(_StubDB(papers), tmp_path, include_external=True)
    assert report2.count == 2


def test_score_paper_returns_quality(tmp_path):
    paper = {"id": "p1", "title": "T", "body": _SAMPLE, "status": "published", "citation_count": 2}
    score = score_paper(paper, tmp_path, database=None, judge=None)
    assert score.paper_id == "p1"
    assert score.judge is None
    assert score.quality_score > 0.0
