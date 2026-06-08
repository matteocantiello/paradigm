"""Markdown bibliography builder.

Fetches metadata for arXiv/Semantic Scholar URLs and formats a numbered
``## References`` section for markdown papers.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from paradigm.literature.arxiv import ArxivClient
from paradigm.literature.semantic_scholar import SemanticScholarClient
from paradigm.logging.events import EventLogger, EventType

logger = logging.getLogger(__name__)

# Metadata resolution (Semantic Scholar / arXiv) is flaky under load — a momentary
# 429 would otherwise strand a citation as a bare URL. Retry transient failures with
# a short backoff, but cap concurrency so we don't stampede the APIs into MORE 429s.
_METADATA_ATTEMPTS = 3
_METADATA_BACKOFF_S = 2.0
_MAX_CONCURRENT_METADATA = 4
_TRANSIENT_META_HINTS = (
    "429",
    "rate limit",
    "rate-limit",
    "timeout",
    "timed out",
    "502",
    "503",
    "504",
    "temporarily",
    "connection",
)


def _is_transient_meta_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(h in s for h in _TRANSIENT_META_HINTS)


async def _none() -> list:
    """Awaitable empty result — stands in when a metadata client is unconfigured."""
    return []


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

        references = [Reference(index=i, url=url) for i, url in enumerate(unique_urls, 1)]

        # Resolve metadata concurrently (bounded), so the wall-clock is the slowest
        # single lookup rather than the sum — important now that retries+backoff can
        # make any one lookup take a few seconds.
        sem = asyncio.Semaphore(_MAX_CONCURRENT_METADATA)

        async def _resolve(ref: Reference) -> None:
            arxiv_id = extract_arxiv_id_from_url(ref.url)
            if not arxiv_id:
                return
            ref.arxiv_id = arxiv_id
            async with sem:
                await self._fetch_metadata(ref, arxiv_id)

        await asyncio.gather(*(_resolve(r) for r in references), return_exceptions=True)

        # Count and report unverified references. This is a citation-QUALITY note
        # (some refs couldn't be resolved to metadata and would render as bare URLs,
        # often just arXiv rate-limiting), NOT a cycle error — log it under
        # CITATION_GROUNDING so it doesn't pollute the error stream / fail monitors.
        url_only = [r for r in references if not r.title]
        if url_only and self._event_logger:
            self._event_logger.log(
                EventType.CITATION_GROUNDING,
                content={
                    "event": "citation_grounding_incomplete",
                    "total_refs": len(references),
                    "unverified": len(url_only),
                    "unverified_ids": [r.arxiv_id for r in url_only[:10]],
                },
            )

        return references

    async def _fetch_metadata(self, ref: Reference, arxiv_id: str) -> None:
        """Populate ``ref`` from Semantic Scholar, then arXiv, retrying transients.

        Each provider is retried up to ``_METADATA_ATTEMPTS`` times on a transient
        failure (429 / timeout / 5xx) with a short linear backoff, so a momentary
        rate-limit doesn't strand the reference as a bare URL.
        """
        if await self._resolve_from(
            ref,
            lambda: self._s2.search(f"arXiv:{arxiv_id}", limit=1) if self._s2 else _none(),
            year_of=lambda p: str(p.year) if p.year else "",
            label="S2",
            arxiv_id=arxiv_id,
        ):
            return
        if await self._resolve_from(
            ref,
            lambda: self._arxiv.search(f"id:{arxiv_id}", max_results=1) if self._arxiv else _none(),
            year_of=lambda p: p.published[:4] if p.published else "",
            label="arXiv",
            arxiv_id=arxiv_id,
        ):
            return

        # Both lookups failed — reference stays URL-only. The aggregate count is
        # already reported (as a CITATION_GROUNDING quality note) in build_references,
        # so just log a debug line here rather than spamming a per-ref ERROR event.
        logger.debug("Citation metadata unresolved for arXiv:%s (S2 + arXiv both empty)", arxiv_id)

    async def _resolve_from(self, ref, search, *, year_of, label, arxiv_id) -> bool:
        """Run one provider's search with retry/backoff; populate ``ref`` if it hits."""
        for attempt in range(_METADATA_ATTEMPTS):
            try:
                papers = await search()
            except Exception as e:  # noqa: BLE001 — transient vs fatal decided below
                if _is_transient_meta_error(e) and attempt < _METADATA_ATTEMPTS - 1:
                    await asyncio.sleep(_METADATA_BACKOFF_S * (attempt + 1))
                    continue
                logger.debug("%s metadata fetch failed for %s: %s", label, arxiv_id, e)
                return False
            if not papers:
                return False  # resolved-but-empty is not transient; don't retry
            paper = papers[0]
            ref.title = paper.title
            ref.authors = ", ".join(paper.authors[:3]) + (
                " et al." if len(paper.authors) > 3 else ""
            )
            ref.year = year_of(paper)
            return True
        return False

    @staticmethod
    def drop_unresolved_references(
        references: list[Reference],
    ) -> tuple[list[Reference], dict[int, int | None]]:
        """Drop references whose metadata didn't resolve (no title) and renumber.

        Resolve-or-drop discipline (Phase 2): an unresolved reference renders as a
        bare URL, which the editor rejects. Drop those and renumber the survivors.

        Args:
            references: References from :meth:`build_references`.

        Returns:
            ``(kept, remap)`` where ``kept`` is the resolved references renumbered
            from 1, and ``remap`` maps each original ``index`` to its new index, or
            ``None`` if the reference was dropped (so in-text [N] markers can be
            rewritten and dangling citations removed).
        """
        remap: dict[int, int | None] = {}
        kept: list[Reference] = []
        for ref in references:
            if ref.title:
                new_index = len(kept) + 1
                remap[ref.index] = new_index
                ref.index = new_index
                kept.append(ref)
            else:
                remap[ref.index] = None
        return kept, remap

    @staticmethod
    def remap_citation_markers(text: str, remap: dict[int, int | None]) -> str:
        """Rewrite in-text ``[N]`` markers per ``remap``; markers mapped to None are removed.

        Markers not present in ``remap`` are left unchanged (defensive).
        """

        def _replace(match: re.Match) -> str:
            old = int(match.group(1))
            if old not in remap:
                return match.group(0)
            new = remap[old]
            return f"[{new}]" if new is not None else ""

        return re.sub(r"\[(\d+)\]", _replace, text)

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

        for text, urls in zip(section_texts, section_url_lists, strict=False):
            # Build local->global mapping for this section
            local_to_global: dict[int, int] = {}
            for local_idx, url in enumerate(urls):
                if url not in url_to_global:
                    global_idx = len(global_urls) + 1
                    url_to_global[url] = global_idx
                    global_urls.append(url)
                local_to_global[local_idx + 1] = url_to_global[url]

            # Replace [N] markers with global numbers
            mapping = local_to_global

            def _replace_marker(match: re.Match, _m: dict[int, int] = mapping) -> str:
                local_num = int(match.group(1))
                global_num = _m.get(local_num, local_num)
                return f"[{global_num}]"

            renumbered = re.sub(r"\[(\d+)\]", _replace_marker, text)
            renumbered_sections.append(renumbered)

        combined = "\n\n".join(renumbered_sections)
        return combined, global_urls
