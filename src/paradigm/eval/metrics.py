"""Deterministic, reproducible metrics computed from a paper without any LLM call.

All functions operate on the paper's markdown body (and, for figures, its on-disk
directory). Nothing here assumes a scientific domain — only general paper structure
(headings, a references section, markdown image tags, citation list items).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paradigm.eval.models import OUTCOME_SCORES, DeterministicMetrics

_HEADING_RE = re.compile(r"^\s{0,3}#{1,3}\s+\S", re.MULTILINE)
_REFERENCES_HEADING_RE = re.compile(
    r"^\s{0,3}#{1,3}\s*(references|bibliography|works cited)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_IMAGE_TAG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_URL_RE = re.compile(r"https?://\S+")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\[\d+\]|\d+[.)])\s*")


def count_sections(body: str) -> int:
    """Count markdown headings (levels 1–3)."""
    return len(_HEADING_RE.findall(body))


def has_references_section(body: str) -> bool:
    """True if the paper contains a References/Bibliography heading."""
    return _REFERENCES_HEADING_RE.search(body) is not None


def _references_block(body: str) -> str:
    """Return the text of the references section (heading → next heading/EOF)."""
    match = _REFERENCES_HEADING_RE.search(body)
    if not match:
        return ""
    start = match.end()
    rest = body[start:]
    next_heading = _HEADING_RE.search(rest)
    return rest[: next_heading.start()] if next_heading else rest


def reference_stats(body: str) -> tuple[int, int]:
    """Count (total references, bare-URL references) in the references section.

    A reference is "bare" when, after stripping the list marker, it is essentially
    just a URL — i.e. there is little descriptive text around the link (a frequent
    failure mode that the internal editor rejects papers for).
    """
    block = _references_block(body)
    if not block:
        return (0, 0)
    total = 0
    bare = 0
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        item = _LIST_MARKER_RE.sub("", line).strip()
        if not item:
            continue
        total += 1
        without_url = _URL_RE.sub("", item)
        alnum = sum(c.isalnum() for c in without_url)
        if _URL_RE.search(item) and alnum < 10:
            bare += 1
    return (total, bare)


def figure_stats(body: str, paper_dir: Path | None) -> tuple[int, int]:
    """Count (figures referenced, figures present).

    Referenced = markdown image tags. Present = those whose source is an embedded
    data URI or resolves to an existing file (checked against the paper dir and its
    ``figures/`` subdir). Without a paper dir, only data URIs count as present.
    """
    srcs = _IMAGE_TAG_RE.findall(body)
    referenced = len(srcs)
    if referenced == 0:
        return (0, 0)
    present = 0
    for src in srcs:
        src = src.strip().split()[0] if src.strip() else src  # drop optional "title"
        if src.startswith("data:"):
            present += 1
            continue
        if paper_dir is None:
            continue
        name = src.lstrip("./")
        candidates = [paper_dir / name, paper_dir / "figures" / Path(name).name]
        if Path(name).is_absolute():
            candidates.append(Path(name))
        if any(c.exists() for c in candidates):
            present += 1
    return (referenced, present)


def _parse_json_list(raw: Any) -> list[dict]:
    """Parse a JSON-list column (verification/prereg); tolerate None/garbage."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def reproduction_pass_rate(paper: dict) -> float | None:
    """accepted / total over the paper's persisted verification records (None if absent)."""
    records = _parse_json_list(paper.get("verification"))
    if not records:
        return None
    accepted = sum(1 for r in records if r.get("status") == "accepted")
    return round(accepted / len(records), 3)


def prereg_verdict(paper: dict) -> str | None:
    """Aggregate the paper's pre-registration verdicts: single value, 'mixed', or None."""
    verdicts = {
        str(v.get("verdict")) for v in _parse_json_list(paper.get("prereg")) if v.get("verdict")
    }
    if not verdicts:
        return None
    return next(iter(verdicts)) if len(verdicts) == 1 else "mixed"


def compute_metrics(
    paper: dict,
    paper_dir: Path | None = None,
    total_tokens: int | None = None,
) -> DeterministicMetrics:
    """Compute all deterministic metrics for a paper DB record."""
    body = paper.get("body") or ""
    outcome = paper.get("status") or "unknown"

    total_refs, bare_refs = reference_stats(body)
    figs_ref, figs_present = figure_stats(body, paper_dir)

    figure_validity = 1.0 if figs_ref == 0 else figs_present / figs_ref
    citation_quality = 1.0 if total_refs == 0 else 1.0 - (bare_refs / total_refs)

    return DeterministicMetrics(
        outcome=outcome,
        outcome_score=OUTCOME_SCORES.get(outcome, 0.0),
        body_chars=len(body),
        num_sections=count_sections(body),
        has_references=has_references_section(body),
        figures_referenced=figs_ref,
        figures_present=figs_present,
        figure_validity=round(figure_validity, 3),
        total_references=total_refs,
        bare_url_references=bare_refs,
        citation_quality=round(citation_quality, 3),
        citation_count=int(paper.get("citation_count") or 0),
        total_tokens=total_tokens,
        reproduction_pass_rate=reproduction_pass_rate(paper),
        prereg_verdict=prereg_verdict(paper),
    )
