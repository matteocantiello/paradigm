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

# Metadata resolution. Resolve in BATCH (one request per source for ALL ids) rather
# than N rate-limited single lookups — the per-id approach trips arXiv's 429 + our
# circuit breaker late in a cycle and leaves every reference a bare URL. Each batch
# is retried once on a transient failure with a short backoff. CRITICAL: use each
# source's EXACT id endpoint (S2 /paper/batch with ArXiv: ids, arXiv id_list) — a
# fuzzy text search returns the WRONG paper.
_METADATA_ATTEMPTS = 2
_METADATA_BACKOFF_S = 2.0
_BATCH_SIZE = 100  # S2 /paper/batch caps at 500; keep arXiv id_list well-bounded too
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
_VERSION_RE = re.compile(r"v\d+$")


def _is_transient_meta_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(h in s for h in _TRANSIENT_META_HINTS)


def _base_arxiv_id(arxiv_id: str | None) -> str:
    """Strip a trailing version (``v2``) so ids match across sources."""
    return _VERSION_RE.sub("", (arxiv_id or "").strip())


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _apply_paper(ref: Reference, *, title: str, authors: list[str], year: str) -> None:
    ref.title = title
    ref.authors = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
    ref.year = year


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

        # Group references by (versionless) arXiv id and resolve metadata in BATCH.
        id_to_refs: dict[str, list[Reference]] = {}
        for ref in references:
            arxiv_id = extract_arxiv_id_from_url(ref.url)
            if arxiv_id:
                ref.arxiv_id = arxiv_id
                id_to_refs.setdefault(_base_arxiv_id(arxiv_id), []).append(ref)
        if id_to_refs:
            await self._resolve_metadata_batch(id_to_refs)

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

    async def _resolve_metadata_batch(self, id_to_refs: dict[str, list[Reference]]) -> None:
        """Resolve metadata for all ids via Semantic Scholar, then arXiv for the rest.

        Each source is queried in ONE batched, EXACT-id request (chunked) — far
        gentler on rate limits than per-id lookups, and exact ids avoid the wrong-
        paper hits a fuzzy text search produces.
        """
        ids = list(id_to_refs)

        # 1) Semantic Scholar batch — /paper/batch with ArXiv: ids (returns each
        #    paper tagged with its arxiv_id, so order/nulls don't matter).
        if self._s2 is not None:
            for chunk in _chunked(ids, _BATCH_SIZE):
                papers = await self._batch_call(
                    lambda c=chunk: self._s2.get_papers_batch([f"ArXiv:{a}" for a in c]),
                    "S2",
                )
                for p in papers:
                    for ref in id_to_refs.get(_base_arxiv_id(p.arxiv_id), []):
                        if not ref.title:
                            _apply_paper(
                                ref,
                                title=p.title,
                                authors=p.authors,
                                year=str(p.year) if p.year else "",
                            )

        # 2) arXiv batch for whatever S2 didn't resolve.
        missing = [a for a in ids if not id_to_refs[a][0].title]
        if missing and self._arxiv is not None:
            for chunk in _chunked(missing, _BATCH_SIZE):
                papers = await self._batch_call(lambda c=chunk: self._arxiv.get_papers(c), "arXiv")
                for p in papers:
                    for ref in id_to_refs.get(_base_arxiv_id(p.arxiv_id), []):
                        if not ref.title:
                            _apply_paper(
                                ref,
                                title=p.title,
                                authors=p.authors,
                                year=p.published[:4] if p.published else "",
                            )

        still_missing = sum(1 for refs in id_to_refs.values() if not refs[0].title)
        if still_missing:
            logger.debug("%d/%d citations unresolved after S2+arXiv batch", still_missing, len(ids))

    async def _batch_call(self, fn, label: str) -> list:
        """Run a batched metadata fetch with one retry on a transient failure."""
        for attempt in range(_METADATA_ATTEMPTS):
            try:
                return await fn() or []
            except Exception as e:  # noqa: BLE001 — transient vs fatal decided below
                if _is_transient_meta_error(e) and attempt < _METADATA_ATTEMPTS - 1:
                    await asyncio.sleep(_METADATA_BACKOFF_S * (attempt + 1))
                    continue
                logger.debug("%s batch metadata fetch failed: %s", label, e)
                return []
        return []

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
