"""Peer review models, parsing, and decision synthesis."""

import re
from pathlib import Path

from pydantic import BaseModel, Field

# Score categories for peer review
SCORE_CATEGORIES = ["novelty", "rigor", "clarity", "significance"]

# Image types a vision model can ingest (PDFs/SVGs are excluded).
_REVIEW_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def encode_figures_for_review(
    figures: list[tuple[str, Path]],
    max_figures: int = 6,
    max_bytes: int = 5_000_000,
) -> list[tuple[str, str, bytes]]:
    """Read figure files for multimodal review (Phase 2 P2-VLM).

    Args:
        figures: ``(name, path)`` pairs (e.g. ``state.execution_figures``).
        max_figures: Cap on how many images to include.
        max_bytes: Skip any single image larger than this.

    Returns:
        ``(name, media_type, raw_bytes)`` for each supported, existing, in-budget image.
    """
    out: list[tuple[str, str, bytes]] = []
    for name, path in figures:
        if len(out) >= max_figures:
            break
        p = Path(path)
        media_type = _REVIEW_IMAGE_MEDIA_TYPES.get(p.suffix.lower())
        if media_type is None or not p.exists():
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if not data or len(data) > max_bytes:
            continue
        out.append((name, media_type, data))
    return out


def score_categories_from_criteria(criteria: list) -> list[str]:
    """Convert a list of CriterionDef objects to a list of category names.

    Args:
        criteria: List of CriterionDef from a DocumentTemplate.

    Returns:
        List of criterion name strings.
    """
    return [c.name for c in criteria]


# Valid recommendation values
VALID_RECOMMENDATIONS = {"accept", "minor_revision", "major_revision", "reject"}


class PeerReview(BaseModel):
    """Structured peer review from an external reviewer."""

    reviewer_id: str
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    scores: dict[str, int] = Field(
        default_factory=dict
    )  # novelty, rigor, clarity, significance (1-10)
    recommendation: str = "major_revision"  # accept, minor_revision, major_revision, reject


def _extract_list(content: str) -> list[str]:
    """Extract bullet points from markdown list."""
    items = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith(("- ", "* ", "• ")):
            items.append(line.lstrip("-*• ").strip())
        elif line and not line.startswith("#"):
            items.append(line)
    return [item for item in items if item]


def _parse_scores(content: str, categories: list[str] | None = None) -> dict[str, int]:
    """Parse score lines like 'Novelty: 7/10' from text.

    Args:
        content: Text containing score lines.
        categories: Score category names to look for. Defaults to SCORE_CATEGORIES.

    Returns:
        Dict mapping category name to score (1-10).
    """
    if categories is None:
        categories = SCORE_CATEGORIES
    scores: dict[str, int] = {}
    for category in categories:
        pattern = rf"{category}\s*:\s*(\d+)\s*/\s*10"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            score = int(match.group(1))
            scores[category] = max(1, min(10, score))
    return scores


def _parse_recommendation(content: str) -> str:
    """Parse recommendation from text."""
    text = content.strip().lower()
    # Check in specificity order (most specific first)
    if "minor_revision" in text or "minor revision" in text:
        return "minor_revision"
    if "major_revision" in text or "major revision" in text:
        return "major_revision"
    if "reject" in text:
        return "reject"
    if "accept" in text:
        return "accept"
    return "major_revision"


def parse_peer_review(
    reviewer_id: str, text: str, categories: list[str] | None = None
) -> PeerReview:
    """Parse a structured peer review from reviewer agent output.

    Expects markdown with ## headers: Summary, Strengths, Weaknesses,
    Questions, Suggestions, Scores, Recommendation.

    Args:
        reviewer_id: ID of the reviewing agent.
        text: Raw review text from the agent.
        categories: Optional score category names (from domain template).
            Defaults to SCORE_CATEGORIES.

    Returns:
        Parsed PeerReview.
    """
    # Split on ## headers
    sections: dict[str, str] = {}
    pattern = r"^##\s+(.+?)$"
    parts = re.split(pattern, text, flags=re.MULTILINE)

    for i in range(1, len(parts) - 1, 2):
        header = parts[i].strip().lower()
        content = parts[i + 1].strip()
        sections[header] = content

    summary = sections.get("summary", "")
    strengths = _extract_list(sections.get("strengths", ""))
    weaknesses = _extract_list(sections.get("weaknesses", ""))
    questions = _extract_list(sections.get("questions", ""))
    suggestions = _extract_list(sections.get("suggestions", ""))
    scores = _parse_scores(sections.get("scores", ""), categories=categories)
    recommendation = _parse_recommendation(sections.get("recommendation", ""))

    return PeerReview(
        reviewer_id=reviewer_id,
        summary=summary,
        strengths=strengths,
        weaknesses=weaknesses,
        questions=questions,
        suggestions=suggestions,
        scores=scores,
        recommendation=recommendation,
    )


def synthesize_decision(reviews: list[PeerReview]) -> str:
    """Deterministic decision synthesis from peer reviews.

    Rules:
    - avg >= 7 and no reviewer recommends reject → "accept"
    - avg >= 5 and no reviewer recommends reject → "minor_revision"
    - avg >= 4 → "major_revision"
    - avg < 4 or any reviewer recommends reject → "reject"

    Args:
        reviews: List of PeerReview objects.

    Returns:
        Decision string: "accept", "minor_revision", "major_revision", or "reject".
    """
    if not reviews:
        return "reject"

    # Check if any reviewer recommends reject
    any_reject = any(r.recommendation == "reject" for r in reviews)

    # Compute average score across all reviewers and categories
    all_scores: list[int] = []
    for review in reviews:
        all_scores.extend(review.scores.values())

    if not all_scores:
        # No numeric scores — fall back to recommendation consensus
        if any_reject:
            return "reject"
        return "major_revision"

    avg_score = sum(all_scores) / len(all_scores)

    if any_reject or avg_score < 4:
        return "reject"
    if avg_score >= 7:
        return "accept"
    if avg_score >= 5:
        return "minor_revision"
    return "major_revision"
