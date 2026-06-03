"""Optional LLM "taste judge" — rates a paper on a 1–10 rubric.

Kept resilient: any failure (no provider, API error, unparseable output) returns
None so the harness falls back to deterministic-only scoring.
"""

from __future__ import annotations

import json
from typing import Any

from paradigm.eval.models import JudgeScores

_JUDGE_SYSTEM = (
    "You are an impartial scientific editor scoring a research paper. You are "
    "domain-agnostic: judge on general standards of scholarship, not on whether "
    "you personally find the topic interesting. Be calibrated and skeptical — "
    "reserve 9–10 for genuinely excellent work."
)

_JUDGE_PROMPT = """Score the following paper on a 1–10 scale for each dimension:

- novelty: how new/original the contribution is
- rigor: soundness of methods, analysis, and reasoning
- clarity: how clearly the work is written and structured
- significance: importance/impact of the findings
- honesty: whether claims are supported by evidence and limitations are acknowledged
  (penalize results reported from failed experiments, synthetic data presented as
  real, or fabricated figures/citations)

Respond with ONLY a JSON object, no prose:
{{"novelty": int, "rigor": int, "clarity": int, "significance": int, "honesty": int, "justification": "one sentence"}}

Title: {title}

Paper:
{body}
"""

# Keep the judged body within a sane context budget.
_BODY_LIMIT = 40000


def _parse_judge_json(text: str) -> JudgeScores | None:
    """Parse the judge's JSON response into JudgeScores, tolerating code fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    # Find the first JSON object if the model added stray text.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    try:
        return JudgeScores(
            novelty=int(data.get("novelty", 0)),
            rigor=int(data.get("rigor", 0)),
            clarity=int(data.get("clarity", 0)),
            significance=int(data.get("significance", 0)),
            honesty=int(data.get("honesty", 0)),
            justification=str(data.get("justification", "")),
        )
    except (TypeError, ValueError):
        return None


def judge_paper(
    title: str,
    body: str,
    provider: Any,
    model: str,
    extra_body: dict | None = None,
) -> JudgeScores | None:
    """Score a paper with the LLM judge, or return None on any failure."""
    prompt = _JUDGE_PROMPT.format(title=title, body=body[:_BODY_LIMIT])
    try:
        text, _in, _out = provider.complete(
            model=model,
            system=_JUDGE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            extra_body=extra_body,
        )
    except Exception:
        return None
    return _parse_judge_json(text)
