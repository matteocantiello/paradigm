"""Journal module for paper writing, review, and publication."""

from paradigm.journal.paper import (
    SECTION_ASSIGNMENTS,
    PaperDraft,
    PaperSection,
    ReviewFeedback,
    SectionDraft,
    parse_review_feedback,
    parse_sections_from_markdown,
)
from paradigm.journal.publication import publish_paper, reject_paper
from paradigm.journal.review import (
    PeerReview,
    parse_peer_review,
    synthesize_decision,
)

__all__ = [
    "PaperDraft",
    "PaperSection",
    "PeerReview",
    "ReviewFeedback",
    "SectionDraft",
    "SECTION_ASSIGNMENTS",
    "parse_peer_review",
    "parse_review_feedback",
    "parse_sections_from_markdown",
    "publish_paper",
    "reject_paper",
    "synthesize_decision",
]
