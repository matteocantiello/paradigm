"""Markdown bibliography builder.

Fetches metadata for arXiv/Semantic Scholar URLs and formats a numbered
``## References`` section for markdown papers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from paradigm.literature.arxiv import ArxivClient
from paradigm.literature.semantic_scholar import SemanticScholarClient
from paradigm.logging.events import EventLogger

logger = logging.getLogger(__name__)


@dataclass
class Reference:
    """A single numbered reference entry."""

    index: int
    url: str
    arxiv_id: str = ""
    title: str = ""
    authors: str = ""
    year: str = ""


def extract_arxiv_id_from_url(url: str) -> str:
    """Extract arXiv paper ID from various URL formats.

    Handles:
        - https://arxiv.org/abs/2301.12345
        - https://arxiv.org/pdf/2301.12345v2
        - https://arxiv.org/html/2301.12345
        - https://arxiv.org/abs/astro-ph/0601234

    Args:
        url: An arXiv URL.

    Returns:
        Extracted arXiv ID, or empty string if not recognized.
    """
    # New-style IDs: YYMM.NNNNN
    match = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", url)
    if match:
        return match.group(1)

    # Old-style IDs: category/YYMMNNN
    match = re.search(r"([\w-]+/\d{7})(?:v\d+)?", url)
    if match:
        return match.group(1)

    return ""


class BibliographyBuilder:
    """Builds a markdown bibliography from citation URLs."""

    def __init__(
        self,
        arxiv_client: ArxivClient | None = None,
        s2_client: SemanticScholarClient | None = None,
        event_logger: EventLogger | None = None,
    ) -> None:
        self._arxiv = arxiv_client
        self._s2 = s2_client
        self._event_logger = event_logger

    async def build_references(self, citation_urls: list[str]) -> list[Reference]:
        """Fetch metadata for citation URLs and build Reference entries.

        Args:
            citation_urls: Ordered list of citation URLs (typically arXiv URLs).

        Returns:
            List of Reference objects with metadata populated where available.
        """
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_urls: list[str] = []
        for url in citation_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        references: list[Reference] = []
        for i, url in enumerate(unique_urls, 1):
            ref = Reference(index=i, url=url)
            arxiv_id = extract_arxiv_id_from_url(url)

            if arxiv_id:
                ref.arxiv_id = arxiv_id
                await self._fetch_metadata(ref, arxiv_id)

            references.append(ref)

        return references

    async def _fetch_metadata(self, ref: Reference, arxiv_id: str) -> None:
        """Try to fetch metadata from Semantic Scholar, then arXiv as fallback.

        Args:
            ref: Reference to populate.
            arxiv_id: arXiv paper ID.
        """
        # Try Semantic Scholar first (faster, structured)
        if self._s2:
            try:
                papers = await self._s2.search(f"arXiv:{arxiv_id}", limit=1)
                if papers:
                    paper = papers[0]
                    ref.title = paper.title
                    ref.authors = (
                        ", ".join(paper.authors[:3])
                        + (" et al." if len(paper.authors) > 3 else "")
                    )
                    ref.year = str(paper.year) if paper.year else ""
                    return
            except Exception as e:
                logger.debug("S2 metadata fetch failed for %s: %s", arxiv_id, e)

        # Fallback: arXiv API
        if self._arxiv:
            try:
                papers = await self._arxiv.search(f"id:{arxiv_id}", max_results=1)
                if papers:
                    paper = papers[0]
                    ref.title = paper.title
                    ref.authors = (
                        ", ".join(paper.authors[:3])
                        + (" et al." if len(paper.authors) > 3 else "")
                    )
                    ref.year = paper.published[:4] if paper.published else ""
                    return
            except Exception as e:
                logger.debug("arXiv metadata fetch failed for %s: %s", arxiv_id, e)

    @staticmethod
    def format_bibliography_markdown(references: list[Reference]) -> str:
        """Format references as a markdown bibliography section.

        Args:
            references: List of Reference objects.

        Returns:
            Markdown string starting with ``## References``.
        """
        if not references:
            return ""

        lines = ["## References", ""]
        for ref in references:
            if ref.title:
                entry = f"[{ref.index}] "
                if ref.authors:
                    entry += f"{ref.authors} "
                if ref.year:
                    entry += f"({ref.year}). "
                entry += f'"{ref.title}".'
                if ref.arxiv_id:
                    entry += f" arXiv:{ref.arxiv_id}."
                entry += f" {ref.url}"
            else:
                # Fallback: URL-only entry
                entry = f"[{ref.index}] {ref.url}"

            lines.append(entry)

        return "\n".join(lines)

    @staticmethod
    def renumber_citations(
        section_texts: list[str], section_url_lists: list[list[str]]
    ) -> tuple[str, list[str]]:
        """Globally renumber [N] citation markers across multiple sections.

        Each section may have been cited independently with local [1], [2], etc.
        This method assigns global numbers and deduplicates URLs.

        Args:
            section_texts: List of section texts with local [N] markers.
            section_url_lists: Corresponding URL lists for each section.

        Returns:
            Tuple of (combined_text, global_url_list).
        """
        global_urls: list[str] = []
        url_to_global: dict[str, int] = {}

        renumbered_sections: list[str] = []

        for text, urls in zip(section_texts, section_url_lists):
            # Build local->global mapping for this section
            local_to_global: dict[int, int] = {}
            for local_idx, url in enumerate(urls):
                if url not in url_to_global:
                    global_idx = len(global_urls) + 1
                    url_to_global[url] = global_idx
                    global_urls.append(url)
                local_to_global[local_idx + 1] = url_to_global[url]

            # Replace [N] markers with global numbers
            def _replace_marker(match: re.Match) -> str:
                local_num = int(match.group(1))
                global_num = local_to_global.get(local_num, local_num)
                return f"[{global_num}]"

            renumbered = re.sub(r"\[(\d+)\]", _replace_marker, text)
            renumbered_sections.append(renumbered)

        combined = "\n\n".join(renumbered_sections)
        return combined, global_urls
