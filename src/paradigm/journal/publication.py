"""Publication and rejection logic for the peer review pipeline."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

from paradigm.journal.review import PeerReview
from paradigm.literature.citations import extract_citations_from_text
from paradigm.literature.corpus import Corpus
from paradigm.logging.events import EventLogger, EventType
from paradigm.storage.database import Database


async def publish_paper(
    paper_id: str,
    db: Database,
    corpus: Corpus,
    logger: EventLogger,
    reviews: list[PeerReview] | None = None,
) -> None:
    """Publish a paper: update DB, add to ChromaDB, update author reputation.

    Args:
        paper_id: Paper identifier.
        db: Database instance.
        corpus: Literature corpus (for ChromaDB ingestion).
        logger: Event logger.
        reviews: Optional list of peer reviews (for storing scores).
    """
    paper = db.get_paper(paper_id)
    if paper is None:
        raise ValueError(f"Paper not found: {paper_id}")

    now = datetime.now(UTC).isoformat()

    # Build review scores summary
    review_scores = None
    if reviews:
        review_scores = [
            {
                "reviewer_id": r.reviewer_id,
                "scores": r.scores,
                "recommendation": r.recommendation,
            }
            for r in reviews
        ]

    # Update paper status
    update_fields: dict = {
        "status": "published",
        "published_at": now,
    }
    if review_scores is not None:
        update_fields["review_scores"] = review_scores
    db.update_paper(paper_id, **update_fields)

    # Add to ChromaDB via corpus
    authors = paper.get("authors", "[]")
    if isinstance(authors, str):
        authors = json.loads(authors)

    # ChromaDB ingestion computes embeddings (and may load the embedding model on
    # first use) — seconds of CPU-bound work. Offload it so it doesn't block the
    # event loop and freeze WebSocket broadcasts (which read as a UI "stall").
    await asyncio.to_thread(
        corpus.ingest_internal_paper,
        paper_id=paper_id,
        title=paper.get("title", ""),
        abstract=paper.get("abstract", ""),
        authors=authors,
    )

    # Extract and record citations from paper body
    body = paper.get("body", "")
    if body:
        cited_ids = extract_citations_from_text(body)
        for cited_id in cited_ids:
            corpus.citations.add_citation(paper_id, cited_id)

    # Update author reputation (papers_published++)
    for author_id in authors:
        agent = db.get_agent(author_id)
        if agent is not None:
            reputation = agent.get("reputation", "{}")
            if isinstance(reputation, str):
                reputation = json.loads(reputation)
            reputation["papers_published"] = reputation.get("papers_published", 0) + 1
            db.update_agent(author_id, reputation=reputation)

    logger.log(
        EventType.PAPER_SUBMITTED,
        content={
            "paper_id": paper_id,
            "action": "published",
            "title": paper.get("title", ""),
        },
    )


def reject_paper(
    paper_id: str,
    db: Database,
    reviews: list[PeerReview],
    logger: EventLogger,
) -> None:
    """Reject a paper: update status, add to graveyard.

    Args:
        paper_id: Paper identifier.
        db: Database instance.
        reviews: Peer reviews with feedback.
        logger: Event logger.
    """
    paper = db.get_paper(paper_id)
    if paper is None:
        raise ValueError(f"Paper not found: {paper_id}")

    # Build review scores for storage
    review_scores = [
        {
            "reviewer_id": r.reviewer_id,
            "scores": r.scores,
            "recommendation": r.recommendation,
        }
        for r in reviews
    ]

    db.update_paper(paper_id, status="rejected", review_scores=review_scores)

    # Build failure reason and lessons from reviews
    weaknesses = []
    for review in reviews:
        weaknesses.extend(review.weaknesses)
    failure_reason = "; ".join(weaknesses[:5]) if weaknesses else "Did not meet review standards"

    suggestions = []
    for review in reviews:
        suggestions.extend(review.suggestions)
    lessons = "; ".join(suggestions[:5]) if suggestions else "No specific suggestions provided"

    # Add to graveyard
    graveyard_id = f"rejected-{uuid.uuid4().hex[:12]}"
    db.add_to_graveyard(
        graveyard_id=graveyard_id,
        entry_type="rejected_paper",
        content=f"Paper: {paper.get('title', paper_id)}",
        failure_reason=failure_reason,
        lessons_learned=lessons,
    )

    logger.log(
        EventType.PAPER_SUBMITTED,
        content={
            "paper_id": paper_id,
            "action": "rejected",
            "title": paper.get("title", ""),
            "failure_reason": failure_reason,
        },
    )
