"""Novelty checking via Semantic Scholar or FutureHouse.

Verifies idea originality before committing to a full research cycle.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from paradigm.literature.semantic_scholar import SemanticScholarClient
from paradigm.logging.events import EventLogger

logger = logging.getLogger(__name__)


@dataclass
class NoveltyResult:
    """Result of a novelty check."""

    is_novel: bool
    confidence: float  # 0.0 - 1.0
    related_work: list[str] = field(default_factory=list)
    papers_found: int = 0
    source: str = ""  # "semantic_scholar" or "futurehouse"


async def check_novelty_semantic_scholar(
    idea_text: str,
    s2_client: SemanticScholarClient,
    provider: Any,
    model: str,
    max_iterations: int = 5,
    event_logger: EventLogger | None = None,
) -> NoveltyResult:
    """Check idea novelty using iterative Semantic Scholar searches.

    Strategy:
    1. Extract key phrases from the idea text using an LLM.
    2. Search Semantic Scholar for each key phrase.
    3. Collect related papers and assess overlap.
    4. Report novelty based on how closely existing work matches.

    Args:
        idea_text: Description of the research idea.
        s2_client: Semantic Scholar API client.
        provider: LLM provider for keyword extraction.
        model: Model name for the provider.
        max_iterations: Maximum search iterations.
        event_logger: Optional event logger.

    Returns:
        NoveltyResult with assessment.
    """
    # Step 1: Extract search queries from idea text using LLM
    extract_prompt = (
        "Extract 3-5 concise search queries (one per line) that would find "
        "existing work most closely related to this research idea. "
        "Focus on the core technical contribution, not background topics.\n\n"
        f"Research idea:\n{idea_text}\n\n"
        "Respond with ONLY the search queries, one per line."
    )

    try:
        # provider.complete is a blocking SDK call — offload off the event loop.
        text, _in, _out = await asyncio.to_thread(
            provider.complete,
            model=model,
            system="",
            messages=[{"role": "user", "content": extract_prompt}],
            max_tokens=500,
        )
        queries = [
            q.strip().lstrip("- ").lstrip("0123456789.)")
            for q in text.strip().split("\n")
            if q.strip() and len(q.strip()) > 5
        ]
    except Exception as e:
        logger.warning("Failed to extract search queries: %s", e)
        # Fallback: use first 100 chars of idea as query
        queries = [idea_text[:100]]

    # Step 2: Search S2 for each query
    all_papers: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for _iteration, query in enumerate(queries[:max_iterations]):
        try:
            papers = await s2_client.search(query, limit=10)
            for paper in papers:
                if paper.paper_id not in seen_ids:
                    seen_ids.add(paper.paper_id)
                    all_papers.append(
                        {
                            "title": paper.title,
                            "abstract": paper.abstract[:300] if paper.abstract else "",
                            "year": str(paper.year) if paper.year else "",
                            "arxiv_id": paper.arxiv_id or "",
                        }
                    )
        except Exception as e:
            logger.warning("S2 search failed for query '%s': %s", query, e)

    if not all_papers:
        return NoveltyResult(
            is_novel=True,
            confidence=0.5,
            related_work=[],
            papers_found=0,
            source="semantic_scholar",
        )

    # Step 3: Ask LLM to assess novelty
    papers_text = "\n".join(
        f"- {p['title']} ({p['year']}): {p['abstract'][:200]}" for p in all_papers[:15]
    )

    assess_prompt = (
        "Assess whether the following research idea is novel given the existing literature.\n\n"
        f"Research idea:\n{idea_text}\n\n"
        f"Related papers found ({len(all_papers)} total):\n{papers_text}\n\n"
        "Respond in this exact format:\n"
        "NOVEL: yes/no\n"
        "CONFIDENCE: 0.0-1.0\n"
        "REASONING: one sentence explanation"
    )

    try:
        raw, _in, _out = await asyncio.to_thread(
            provider.complete,
            model=model,
            system="",
            messages=[{"role": "user", "content": assess_prompt}],
            max_tokens=300,
        )
        text = raw.strip()

        is_novel = "NOVEL: yes" in text.lower() or "novel: yes" in text.lower()
        confidence = 0.5
        for line in text.split("\n"):
            if line.strip().lower().startswith("confidence:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass

    except Exception as e:
        logger.warning("Novelty assessment LLM call failed: %s", e)
        is_novel = True
        confidence = 0.3

    related = [p["title"] for p in all_papers[:5]]

    return NoveltyResult(
        is_novel=is_novel,
        confidence=confidence,
        related_work=related,
        papers_found=len(all_papers),
        source="semantic_scholar",
    )


async def check_novelty_futurehouse(
    idea_text: str,
    api_key: str,
    event_logger: EventLogger | None = None,
) -> NoveltyResult:
    """Check idea novelty using FutureHouse client.

    Wraps the sync futurehouse_client in asyncio.to_thread().
    Requires the ``futurehouse_client`` package (optional dependency).

    Args:
        idea_text: Description of the research idea.
        api_key: FutureHouse API key.
        event_logger: Optional event logger.

    Returns:
        NoveltyResult with assessment.
    """
    import asyncio

    try:
        from futurehouse_client import FutureHouseClient  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "FutureHouse novelty checking requires the 'futurehouse_client' package. "
            "Install it with: pip install 'paradigm[citations]'"
        ) from exc

    def _run_sync() -> dict:
        client = FutureHouseClient(api_key=api_key)
        return client.check_novelty(idea_text)

    try:
        result = await asyncio.to_thread(_run_sync)

        return NoveltyResult(
            is_novel=result.get("is_novel", True),
            confidence=result.get("confidence", 0.5),
            related_work=result.get("related_papers", []),
            papers_found=len(result.get("related_papers", [])),
            source="futurehouse",
        )
    except ImportError:
        raise
    except Exception as e:
        logger.warning("FutureHouse novelty check failed: %s", e)
        if event_logger:
            event_logger.log_error(e, metadata_key="futurehouse_novelty")
        return NoveltyResult(
            is_novel=True,
            confidence=0.0,
            related_work=[],
            papers_found=0,
            source="futurehouse",
        )
