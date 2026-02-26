"""Citation chain BFS traversal across multiple providers."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable

from paradigm.domains.base import SourceProvider, SourceResult

_logger = logging.getLogger(__name__)


async def follow_citation_chain(
    providers: dict[str, SourceProvider],
    seed_id: str,
    direction: str = "references",
    max_depth: int = 2,
    max_papers_per_level: int = 10,
    relevance_filter: Callable[[SourceResult], bool] | None = None,
) -> list[SourceResult]:
    """BFS through citation graph with depth control and deduplication.

    Traverses the citation graph starting from a seed paper, following
    references, citations, or both depending on direction. Uses all
    providers that support get_references()/get_citing().

    Args:
        providers: Dict mapping provider name to SourceProvider instance.
        seed_id: Paper ID to start traversal from.
        direction: "references", "citations", or "both".
        max_depth: Maximum BFS depth (number of hops from seed).
        max_papers_per_level: Maximum papers to expand per BFS level.
        relevance_filter: Optional callback to filter out irrelevant papers.
            If provided, papers where this returns False are pruned.

    Returns:
        Flat list of discovered SourceResult objects with
        metadata["chain_depth"] indicating distance from seed.
    """
    seen_ids: set[str] = {seed_id}
    results: list[SourceResult] = []

    # Queue entries: (paper_id, current_depth)
    queue: deque[tuple[str, int]] = deque([(seed_id, 0)])

    while queue:
        paper_id, depth = queue.popleft()

        if depth >= max_depth:
            continue

        next_depth = depth + 1
        discovered: list[SourceResult] = []

        # Collect results from all providers
        for provider in providers.values():
            if direction in ("references", "both"):
                try:
                    refs = await provider.get_references(paper_id)
                    discovered.extend(refs)
                except Exception as e:
                    _logger.debug(
                        "Provider %s get_references failed for %s: %s",
                        getattr(provider, "name", "unknown"),
                        paper_id,
                        e,
                    )

            if direction in ("citations", "both"):
                try:
                    cites = await provider.get_citing(paper_id)
                    discovered.extend(cites)
                except Exception as e:
                    _logger.debug(
                        "Provider %s get_citing failed for %s: %s",
                        getattr(provider, "name", "unknown"),
                        paper_id,
                        e,
                    )

        # Deduplicate and filter
        level_count = 0
        for paper in discovered:
            if paper.id in seen_ids:
                continue

            if relevance_filter is not None and not relevance_filter(paper):
                continue

            seen_ids.add(paper.id)

            # Annotate with chain depth
            paper.metadata["chain_depth"] = next_depth

            results.append(paper)
            level_count += 1

            # Add to queue for further traversal
            if level_count <= max_papers_per_level:
                queue.append((paper.id, next_depth))

            if level_count >= max_papers_per_level:
                break

    return results
