"""Evaluation harness — repeatable, comparable quality scoring of research output.

Two modes share one rubric:
- Offline: score papers already in ``data/`` (fast, free baseline).
- Live (opt-in): run cycles end-to-end and score the fresh output.

Scoring blends deterministic metrics (outcome, structure, figure/citation grounding)
with an optional LLM "taste judge" (novelty, rigor, clarity, significance, honesty).
"""

from paradigm.eval.calibration import CalibrationResult, fit_threshold
from paradigm.eval.models import (
    DeterministicMetrics,
    EvalReport,
    JudgeScores,
    PaperScore,
)
from paradigm.eval.seeds import SeedPrompt, split_seeds

__all__ = [
    "CalibrationResult",
    "DeterministicMetrics",
    "EvalReport",
    "JudgeScores",
    "PaperScore",
    "SeedPrompt",
    "fit_threshold",
    "split_seeds",
]
