"""Evaluation harness: collect papers, score them, aggregate, and report.

``score_paper`` is the single scoring unit shared by the offline path (below) and
the future live path (run a cycle, then score its resulting paper).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paradigm.eval.judge import judge_paper
from paradigm.eval.metrics import compute_metrics
from paradigm.eval.models import EvalReport, PaperScore

# Statuses that are not papers this system generated (e.g. ingested arXiv papers).
_NON_GENERATED_STATUSES = {"external"}


@dataclass
class JudgeContext:
    """Everything needed to call the LLM judge (None disables judging)."""

    provider: Any
    model: str
    extra_body: dict | None = None


def _paper_dir(papers_dir: Path, paper_id: str) -> Path | None:
    """Return the per-paper directory (holds figures/aux files) if it exists."""
    candidate = papers_dir / paper_id
    return candidate if candidate.is_dir() else None


def score_paper(
    paper: dict,
    papers_dir: Path,
    database: Any | None = None,
    judge: JudgeContext | None = None,
) -> PaperScore:
    """Score one paper. Shared by offline and live evaluation."""
    paper_id = paper["id"]
    paper_dir = _paper_dir(papers_dir, paper_id)

    total_tokens: int | None = None
    if database is not None:
        thread_id = database.get_thread_id_for_paper(paper_id)
        if thread_id:
            usage = database.get_token_usage(thread_id=thread_id)
            total_tokens = usage.get("total_tokens") or None

    det = compute_metrics(paper, paper_dir, total_tokens)

    judge_scores = None
    if judge is not None:
        judge_scores = judge_paper(
            paper.get("title", ""),
            paper.get("body", "") or "",
            judge.provider,
            judge.model,
            judge.extra_body,
        )

    return PaperScore(
        paper_id=paper_id,
        title=paper.get("title", ""),
        deterministic=det,
        judge=judge_scores,
        quality_score=PaperScore.blend(det, judge_scores),
    )


def score_thread_paper(
    database: Any,
    papers_dir: Path,
    thread_id: str,
    judge: JudgeContext | None = None,
) -> PaperScore | None:
    """Find the paper produced by a thread and score it (None if no paper)."""
    thread = database.get_thread(thread_id)
    paper_id = (thread.get("current_draft_id") if thread else None) or None
    if not paper_id:
        return None
    paper = database.get_paper(paper_id)
    if not paper:
        return None
    return score_paper(paper, papers_dir, database, judge)


def run_live_eval(
    run_cycle: Any,
    seeds: list,
    database: Any,
    papers_dir: Path,
    judge: JudgeContext | None = None,
) -> EvalReport:
    """Run each seed end-to-end via ``run_cycle`` and score the fresh output.

    Args:
        run_cycle: Callable ``seed -> thread_id | None`` (one full research cycle).
        seeds: Seed prompts to run (e.g. one split).
        database: Open database for looking up the produced paper.
        papers_dir: Directory holding per-paper figures/aux files.
        judge: Optional LLM judge context.

    Returns:
        Aggregate report over the scored fresh papers.
    """
    scores: list[PaperScore] = []
    judged_any = False
    for seed in seeds:
        try:
            thread_id = run_cycle(seed)
        except SystemExit:  # a single seed's cycle failing must not kill the eval
            thread_id = None
        if not thread_id:
            continue
        ps = score_thread_paper(database, papers_dir, thread_id, judge)
        if ps is None:
            continue
        judged_any = judged_any or ps.judge is not None
        scores.append(ps)
    return EvalReport(scores=scores, judged=judged_any)


def run_offline_eval(
    database: Any,
    papers_dir: Path,
    limit: int | None = None,
    include_external: bool = False,
    judge: JudgeContext | None = None,
) -> EvalReport:
    """Score papers already in the database. Excludes ingested (external) papers."""
    papers = database.list_papers(limit=None)
    selected = [
        p for p in papers if include_external or p.get("status") not in _NON_GENERATED_STATUSES
    ]
    if limit:
        selected = selected[:limit]

    scores: list[PaperScore] = []
    judged_any = False
    for paper in selected:
        ps = score_paper(paper, papers_dir, database, judge)
        judged_any = judged_any or ps.judge is not None
        scores.append(ps)

    return EvalReport(scores=scores, judged=judged_any)


def render_report(report: EvalReport) -> str:
    """Render the report as a monospaced terminal table + summary."""
    lines: list[str] = []
    header = (
        f"{'PAPER':<22} {'OUTCOME':<19} {'DET':>5} {'JUDGE':>6} "
        f"{'QUAL':>6} {'BODY':>6} {'FIG':>7} {'REFS':>8}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for s in sorted(report.scores, key=lambda x: x.quality_score, reverse=True):
        d = s.deterministic
        judge_cell = f"{s.judge.mean:.2f}" if s.judge is not None else "-"
        fig_cell = f"{d.figures_present}/{d.figures_referenced}"
        ref_cell = f"{d.bare_url_references}/{d.total_references}"
        lines.append(
            f"{s.paper_id[:22]:<22} {d.outcome[:19]:<19} "
            f"{d.deterministic_score:>5.2f} {judge_cell:>6} "
            f"{s.quality_score:>6.1f} {d.body_chars // 1000:>5}k "
            f"{fig_cell:>7} {ref_cell:>8}"
        )

    lines.append("-" * len(header))
    lines.append(f"Papers scored: {report.count}    Mean quality: {report.mean_quality}/100")
    if report.judged:
        lines.append("(JUDGE column = mean of novelty/rigor/clarity/significance/honesty, 0–1)")
    else:
        lines.append("(deterministic-only — run with --judge for LLM taste scores)")
    breakdown = report.outcome_breakdown()
    if breakdown:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(breakdown.items(), key=lambda x: -x[1]))
        lines.append(f"Outcomes: {parts}")
    lines.append("Columns: FIG = figures present/referenced, REFS = bare-URL/total")
    return "\n".join(lines)


def write_report(report: EvalReport, out_dir: Path) -> tuple[Path, Path]:
    """Write the report as JSON + CSV to ``out_dir``. Returns (json_path, csv_path)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "eval_report.json"
    csv_path = out_dir / "eval_report.csv"

    json_path.write_text(json.dumps(report.model_dump(), indent=2, default=str))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "paper_id",
            "title",
            "outcome",
            "outcome_score",
            "deterministic_score",
            "judge_mean",
            "quality_score",
            "body_chars",
            "num_sections",
            "figures_present",
            "figures_referenced",
            "bare_url_references",
            "total_references",
            "citation_quality",
            "total_tokens",
        ]
    )
    for s in report.scores:
        d = s.deterministic
        writer.writerow(
            [
                s.paper_id,
                s.title,
                d.outcome,
                d.outcome_score,
                round(d.deterministic_score, 3),
                round(s.judge.mean, 3) if s.judge else "",
                s.quality_score,
                d.body_chars,
                d.num_sections,
                d.figures_present,
                d.figures_referenced,
                d.bare_url_references,
                d.total_references,
                d.citation_quality,
                d.total_tokens,
            ]
        )
    csv_path.write_text(buf.getvalue())
    return (json_path, csv_path)
