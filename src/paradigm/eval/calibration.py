"""Reviewer calibration (1D): map the LLM judge's score to a real accept/reject boundary.

Fits a single decision threshold by maximizing *balanced accuracy* against the
system's real outcomes (published vs rejected) — plain Python, no sklearn. The
threshold lets the judge predict accept/reject and lets us report agreement with
ground truth, which is the selection gate later phases depend on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

# Real-outcome labels: True = the system published it, False = it was rejected.
_POSITIVE_STATUSES = {"published"}
_NEGATIVE_STATUSES = {"rejected", "review_rejected", "revision_exhausted"}


class CalibrationResult(BaseModel):
    """A fitted judge-score threshold and how well it separates real outcomes."""

    threshold: float = 0.5
    balanced_accuracy: float = 0.0
    n_positive: int = 0
    n_negative: int = 0
    fitted_at: str = ""


def fit_threshold(labeled: list[tuple[float, bool]]) -> CalibrationResult:
    """Find the judge-score threshold maximizing balanced accuracy.

    Args:
        labeled: ``(score, is_published)`` pairs; score in 0..1.

    Returns:
        The best threshold (predict accept iff score >= threshold) and its
        balanced accuracy. Degrades to a neutral 0.5 threshold when one class
        is empty (can't calibrate from a single class).
    """
    pos = [s for s, y in labeled if y]
    neg = [s for s, y in labeled if not y]
    if not pos or not neg:
        return CalibrationResult(
            threshold=0.5, balanced_accuracy=0.0, n_positive=len(pos), n_negative=len(neg)
        )

    scores = sorted({s for s, _ in labeled})
    # Candidate thresholds: midpoints between consecutive scores, plus the ends.
    candidates = [0.0]
    prev = 0.0
    for s in scores:
        candidates.append((prev + s) / 2.0)
        prev = s
    candidates.append(min(1.0, prev + 1e-6))

    best_t, best_ba = 0.5, -1.0
    for t in candidates:
        tpr = sum(1 for s in pos if s >= t) / len(pos)
        tnr = sum(1 for s in neg if s < t) / len(neg)
        ba = (tpr + tnr) / 2.0
        if ba > best_ba:
            best_ba, best_t = ba, t

    return CalibrationResult(
        threshold=round(best_t, 4),
        balanced_accuracy=round(best_ba, 4),
        n_positive=len(pos),
        n_negative=len(neg),
    )


def label_for_status(status: str) -> bool | None:
    """Map a paper status to a calibration label (True/False), or None to skip."""
    if status in _POSITIVE_STATUSES:
        return True
    if status in _NEGATIVE_STATUSES:
        return False
    return None


def calibrate_from_db(
    database: Any,
    judge_provider: Any,
    judge_model: str,
    judge_extra_body: dict | None = None,
    limit: int | None = None,
) -> CalibrationResult:
    """Score historical published/rejected papers with the judge and fit a threshold."""
    from paradigm.eval.judge import judge_paper

    labeled: list[tuple[float, bool]] = []
    for paper in database.list_papers(limit=limit):
        label = label_for_status(paper.get("status", ""))
        if label is None:
            continue
        scores = judge_paper(
            paper.get("title", ""),
            paper.get("body", "") or "",
            judge_provider,
            judge_model,
            judge_extra_body,
        )
        if scores is not None:
            labeled.append((scores.mean, label))
    return fit_threshold(labeled)


def save_calibration(result: CalibrationResult, out_dir: Path) -> Path:
    """Persist the calibration to ``out_dir/calibration.json``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "calibration.json"
    path.write_text(json.dumps(result.model_dump(), indent=2))
    return path


def load_calibration(path: Path) -> CalibrationResult | None:
    """Load a persisted calibration, or None if absent/unreadable."""
    try:
        return CalibrationResult(**json.loads(Path(path).read_text()))
    except (OSError, ValueError):
        return None
