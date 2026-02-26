"""Unified LiteratureSearchService wrapping Corpus + citation chains."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from paradigm.domains.base import SourceDocument, SourceProvider, SourceResult
from paradigm.literature.citation_chains import follow_citation_chain

if TYPE_CHECKING:
    from paradigm.literature.corpus import Corpus


class LiteratureSearchService:
    """High-level service for multi-source literature search.

    Wraps Corpus (which fans out to all registered SourceProviders),
    citation chain traversal, and enhanced Semantic Scholar features.
    Agents interact with this through the existing bracket notation
    parsed by LiteratureHandler.
    """

    def __init__(
        self,
        corpus: Corpus,
        providers: dict[str, SourceProvider],
    ) -> None:
        """Initialize the search service.

        Args:
            corpus: Corpus instance for unified search.
            providers: Dict mapping provider name to SourceProvider instance.
        """
        self._corpus = corpus
        self._providers = providers

    async def search_papers(
        self,
        query: str,
        sources: list[str] | None = None,
        max_results: int = 20,
    ) -> list[SourceResult]:
        """Search for papers across all or specified sources.

        Delegates to Corpus.search() which fans out to all providers.
        If sources is specified, only searches those providers.

        Args:
            query: Search query string.
            sources: Optional list of provider names to restrict search to.
            max_results: Maximum number of results.

        Returns:
            List of SourceResult objects from all matching providers.
        """
        if sources is not None:
            # Search only specified providers
            results: list[SourceResult] = []
            for name in sources:
                provider = self._providers.get(name)
                if provider is not None:
                    try:
                        provider_results = await provider.search(query, max_results=max_results)
                        results.extend(provider_results)
                    except Exception:
                        continue
            return results[:max_results]

        # Default: use Corpus.search() which fans out to all providers
        return await self._corpus.search(query, max_results=max_results)

    async def get_citations(self, paper_id: str) -> list[SourceResult]:
        """Get papers that cite the given paper.

        Tries multiple providers (Semantic Scholar, ADS, etc.).

        Args:
            paper_id: Paper ID to look up citations for.

        Returns:
            List of citing papers as SourceResult objects.
        """
        results: list[SourceResult] = []
        seen_ids: set[str] = set()

        for provider in self._providers.values():
            try:
                cites = await provider.get_citing(paper_id)
                for paper in cites:
                    if paper.id not in seen_ids:
                        seen_ids.add(paper.id)
                        results.append(paper)
            except Exception:
                continue

        return results

    async def get_references(self, paper_id: str) -> list[SourceResult]:
        """Get papers referenced by the given paper.

        Tries multiple providers.

        Args:
            paper_id: Paper ID to look up references for.

        Returns:
            List of referenced papers as SourceResult objects.
        """
        results: list[SourceResult] = []
        seen_ids: set[str] = set()

        for provider in self._providers.values():
            try:
                refs = await provider.get_references(paper_id)
                for paper in refs:
                    if paper.id not in seen_ids:
                        seen_ids.add(paper.id)
                        results.append(paper)
            except Exception:
                continue

        return results

    async def follow_chain(
        self,
        seed_id: str,
        depth: int = 2,
        direction: str = "both",
        max_papers_per_level: int = 10,
    ) -> list[SourceResult]:
        """Follow citation chain from a seed paper.

        Delegates to citation_chains.follow_citation_chain().

        Args:
            seed_id: Paper ID to start from.
            depth: Maximum BFS depth.
            direction: "references", "citations", or "both".
            max_papers_per_level: Max papers per BFS level.

        Returns:
            List of discovered SourceResult objects.
        """
        return await follow_citation_chain(
            providers=self._providers,
            seed_id=seed_id,
            direction=direction,
            max_depth=depth,
            max_papers_per_level=max_papers_per_level,
        )

    async def get_paper_details(self, paper_id: str) -> SourceDocument | None:
        """Get detailed document content for a paper.

        Tries fetch from multiple providers until one succeeds.

        Args:
            paper_id: Paper ID to fetch.

        Returns:
            SourceDocument, or None if no provider can fetch it.
        """
        for provider in self._providers.values():
            try:
                doc = await provider.fetch(paper_id)
                if doc is not None:
                    return doc
            except Exception:
                continue
        return None

    async def search_by_author(self, author_name: str) -> list[SourceResult]:
        """Search for papers by a specific author.

        Delegates to Semantic Scholar search_by_author if available,
        and ADS author search.

        Args:
            author_name: Author name to search for.

        Returns:
            List of papers by the author.
        """
        results: list[SourceResult] = []
        seen_ids: set[str] = set()

        # Try Semantic Scholar provider
        s2_provider = self._providers.get("semantic_scholar")
        if s2_provider is not None:
            try:
                from paradigm.literature.providers import SemanticScholarSourceProvider

                if isinstance(s2_provider, SemanticScholarSourceProvider):
                    client = s2_provider._client
                    if hasattr(client, "search_by_author"):
                        from paradigm.domains.base import semantic_paper_to_source_result

                        papers = await client.search_by_author(author_name)
                        for p in papers:
                            sr = semantic_paper_to_source_result(p)
                            if sr.id not in seen_ids:
                                seen_ids.add(sr.id)
                                results.append(sr)
            except Exception:
                pass

        # Try ADS provider with author query
        ads_provider = self._providers.get("nasa_ads")
        if ads_provider is not None:
            try:
                author_results = await ads_provider.search(
                    f'author:"{author_name}"', max_results=20
                )
                for paper in author_results:
                    if paper.id not in seen_ids:
                        seen_ids.add(paper.id)
                        results.append(paper)
            except Exception:
                pass

        return results

    async def download_pdf(self, paper_id: str) -> Path | None:
        """Download PDF for an arXiv paper.

        Delegates to ArxivClient.fetch_pdf_text() for arXiv papers.

        Args:
            paper_id: arXiv paper ID.

        Returns:
            Path to downloaded PDF, or None if unavailable.
        """
        arxiv_provider = self._providers.get("arxiv")
        if arxiv_provider is None:
            return None

        try:
            from paradigm.literature.providers import ArxivSourceProvider

            if isinstance(arxiv_provider, ArxivSourceProvider):
                paper = await arxiv_provider._client.get_paper(paper_id)
                if paper is not None:
                    text = await arxiv_provider._client.fetch_pdf_text(paper)
                    if text:
                        # Return the cached PDF path if available
                        return getattr(paper, "_pdf_path", None)
        except Exception:
            pass

        return None
