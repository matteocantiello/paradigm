"""Unified literature search interface combining arXiv, local embeddings, and citations."""

from __future__ import annotations

import os
from typing import Any

from paradigm.config import LiteratureConfig, StorageConfig
from paradigm.domains.base import (
    SourceProvider,
    SourceResult,
    arxiv_paper_to_source_result,
)
from paradigm.literature.arxiv import ArxivClient, ArxivPaper, extract_key_sections
from paradigm.literature.citations import CitationTracker
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.literature.prompt_utils import make_external_paper
from paradigm.literature.semantic_scholar import SemanticScholarClient
from paradigm.logging.events import EventLogger, EventType
from paradigm.storage.database import Database


class Corpus:
    """Unified search interface for scientific literature.

    Combines arXiv API search, local semantic search (ChromaDB),
    and citation tracking into a single high-level API.

    When ``source_providers`` is supplied, search/get_references/get_citations/
    read_paper delegate to those providers and return ``SourceResult`` objects.
    When omitted, the legacy path creates clients internally and returns
    ``ArxivPaper`` / ``SemanticPaper`` as before.
    """

    def __init__(
        self,
        database: Database,
        literature_config: LiteratureConfig,
        storage_config: StorageConfig,
        logger: EventLogger | None = None,
        arxiv_client: ArxivClient | None = None,
        embedding_store: EmbeddingStore | None = None,
        semantic_scholar_client: SemanticScholarClient | None = None,
        source_providers: dict[str, SourceProvider] | None = None,
        topic: str = "",
        collection_name: str | None = None,
    ) -> None:
        """Initialize corpus.

        Args:
            database: SQLite database for paper storage.
            literature_config: Literature configuration.
            storage_config: Storage configuration (for vector DB path).
            logger: Optional event logger.
            arxiv_client: Optional pre-configured ArxivClient (for testing).
            embedding_store: Optional pre-configured EmbeddingStore (for testing).
            semantic_scholar_client: Optional pre-configured S2 client (for testing).
            source_providers: Optional dict of named SourceProvider instances.
                When supplied, search/references/citations delegate to these
                providers and return SourceResult. Legacy clients are still
                created for ingestion and PDF fetch.
            topic: Research topic / seed prompt for domain-aware provider routing.
            collection_name: Optional ChromaDB collection name for cycle isolation.
        """
        self._db = database
        self._config = literature_config
        self._logger = logger
        self._providers = source_providers
        self._topic = topic
        self._collection_name = collection_name

        self._arxiv = arxiv_client or ArxivClient(
            rate_limit=literature_config.arxiv_rate_limit,
            logger=logger,
        )
        self._embeddings = embedding_store or EmbeddingStore(
            vector_db_path=storage_config.vector_db_path,
            collection_name=collection_name,
        )
        self._citations = CitationTracker(database)
        self._s2 = semantic_scholar_client or SemanticScholarClient(
            api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
            logger=logger,
        )
        self._embed_fn = None  # lazy sentence-embedder for relevance re-ranking

        # When providers are supplied, extract underlying clients for
        # operations that still need direct access (ingestion, close).
        if source_providers:
            from paradigm.literature.providers import (
                ArxivSourceProvider,
                InternalCorpusProvider,
                SemanticScholarSourceProvider,
            )

            for provider in source_providers.values():
                if isinstance(provider, ArxivSourceProvider):
                    self._arxiv = provider._client
                elif isinstance(provider, SemanticScholarSourceProvider):
                    self._s2 = provider._client
                elif isinstance(provider, InternalCorpusProvider):
                    self._embeddings = provider._embeddings

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int | None = None,
        include_local: bool = True,
        include_arxiv: bool = True,
        categories: list[str] | None = None,
        provider: str | None = None,
    ) -> list[SourceResult]:
        """Search both local corpus and arXiv, deduplicate, and return.

        When providers are configured, delegates to each provider's search()
        and merges + deduplicates the results. Otherwise, falls back to the
        legacy path (direct ArxivClient + EmbeddingStore calls).

        Args:
            query: Search query text.
            max_results: Maximum results (defaults to config value).
            include_local: Whether to search local embeddings.
            include_arxiv: Whether to search arXiv API.
            categories: Optional arXiv category filters.
            provider: Optional provider name. When set, only this provider is
                queried (skipping domain-aware routing).

        Returns:
            Deduplicated list of SourceResult objects.
        """
        if max_results is None:
            max_results = self._config.max_results_per_search

        if self._providers:
            return await self._search_via_providers(
                query, max_results, include_local, include_arxiv, provider=provider
            )

        return await self._search_legacy(
            query, max_results, include_local, include_arxiv, categories
        )

    async def _search_via_providers(
        self,
        query: str,
        max_results: int,
        include_local: bool,
        include_arxiv: bool,
        provider: str | None = None,
    ) -> list[SourceResult]:
        """Provider-based search with domain-aware routing.

        Uses DomainRouter to prioritize providers based on the research
        topic, allocating more result slots to relevant providers and
        skipping irrelevant ones entirely.

        When *provider* is set, domain routing is skipped and only the
        named provider is queried (with the full ``max_results`` budget).
        """
        all_results: list[SourceResult] = []
        seen_ids: set[str] = set()

        # --- Targeted provider path ---
        if provider and provider in self._providers:
            # Local corpus still included when requested
            if include_local and "internal_corpus" in self._providers:
                local_results = await self._providers["internal_corpus"].search(
                    query, max_results=max_results
                )
                for r in local_results:
                    if r.id not in seen_ids:
                        all_results.append(r)
                        seen_ids.add(r.id)

            try:
                results = await self._providers[provider].search(query, max_results=max_results)
                for r in results:
                    if r.id not in seen_ids:
                        all_results.append(r)
                        seen_ids.add(r.id)
            except Exception:
                pass  # Provider can fail silently

            results = all_results[:max_results]

            if self._logger:
                self._logger.log(
                    EventType.LITERATURE_SEARCH,
                    content={
                        "query": query,
                        "total_results": len(results),
                        "targeted_provider": provider,
                        "sources": {
                            "local": include_local,
                        },
                    },
                )

            return results

        # --- Domain-aware routing path (default) ---
        from paradigm.literature.domain_router import (
            compute_result_allocation,
            rank_providers,
        )

        # Determine which external providers to query
        external_providers = [
            name
            for name in self._providers
            if name != "internal_corpus" and (name != "arxiv" or include_arxiv)
        ]

        # Compute domain-aware result allocation
        allocation = compute_result_allocation(
            self._topic or query, external_providers, max_results
        )
        ranked = rank_providers(self._topic or query, external_providers)

        # Local corpus provider first (always gets full allocation)
        if include_local and "internal_corpus" in self._providers:
            local_results = await self._providers["internal_corpus"].search(
                query, max_results=max_results
            )
            for r in local_results:
                if r.id not in seen_ids:
                    all_results.append(r)
                    seen_ids.add(r.id)

        # External providers in relevance order
        providers_queried: list[str] = []
        providers_skipped: list[str] = []
        for name, _score in ranked:
            prov = self._providers.get(name)
            if prov is None:
                continue
            provider_max = allocation.get(name, 0)
            if provider_max <= 0:
                providers_skipped.append(name)
                continue
            try:
                results = await prov.search(query, max_results=provider_max)
                for r in results:
                    if r.id not in seen_ids:
                        all_results.append(r)
                        seen_ids.add(r.id)
                providers_queried.append(name)
            except Exception:
                pass  # Non-critical providers can fail silently

        # Relevance gate: re-rank the aggregated pool by semantic similarity to
        # the query and drop weakly-related results, so broad providers don't
        # inject off-topic papers into agent context.
        results = self._rerank_by_relevance(query, all_results, max_results)

        if self._logger:
            self._logger.log(
                EventType.LITERATURE_SEARCH,
                content={
                    "query": query,
                    "total_results": len(results),
                    "candidates": len(all_results),
                    "relevance_dropped": len(all_results) - len(results),
                    "providers_queried": providers_queried,
                    "providers_skipped": providers_skipped,
                    "allocation": allocation,
                    "sources": {
                        "local": include_local,
                        "arxiv": include_arxiv,
                    },
                },
            )

        return results

    def _get_embed_fn(self):
        """Lazily build a sentence embedder (Chroma's default MiniLM) for
        re-ranking. Cached; returns None if unavailable (caller fails open)."""
        if self._embed_fn is not None:
            return self._embed_fn
        try:
            from chromadb.utils import embedding_functions

            self._embed_fn = embedding_functions.DefaultEmbeddingFunction()
        except Exception:  # noqa: BLE001 — fail open, skip re-ranking
            self._embed_fn = None
        return self._embed_fn

    def _rerank_by_relevance(
        self, query: str, results: list[SourceResult], max_results: int
    ) -> list[SourceResult]:
        """Sort aggregated results by semantic similarity to the query and drop
        weakly-related ones, so broad providers don't inject off-topic papers.

        Domain-agnostic (embedding cosine, no hardcoded topic). Fails open
        (returns the original top-N) whenever embeddings can't be computed.
        """
        if len(results) <= 1 or not query.strip():
            return results[:max_results]
        ef = self._get_embed_fn()
        if ef is None:
            return results[:max_results]
        try:
            import numpy as np

            texts = [f"{r.title}. {(r.summary or '')[:600]}".strip() for r in results]
            arr = np.asarray(ef([query] + texts), dtype=float)
            unit = arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)
            sims = (unit[1:] @ unit[0]).tolist()
        except Exception as e:  # noqa: BLE001 — never break search on a rerank hiccup
            if self._logger:
                self._logger.log_error(e, metadata_key="relevance_rerank")
            return results[:max_results]

        ranked = sorted(zip(results, sims, strict=False), key=lambda rs: rs[1], reverse=True)
        threshold = self._config.relevance_threshold
        kept = [r for r, s in ranked if s >= threshold]
        min_keep = max(1, self._config.relevance_min_keep)
        if len(kept) < min_keep:
            kept = [r for r, _ in ranked[:min_keep]]
        return kept[:max_results]

    async def _search_legacy(
        self,
        query: str,
        max_results: int,
        include_local: bool,
        include_arxiv: bool,
        categories: list[str] | None,
    ) -> list[SourceResult]:
        """Legacy search: direct ArxivClient + EmbeddingStore, converted to SourceResult."""
        local_results: list[SourceResult] = []
        local_ids: set[str] = set()
        arxiv_only: list[SourceResult] = []
        num_arxiv_results = 0

        # Search local embeddings
        if include_local and self._embeddings.count() > 0:
            local_raw = self._embeddings.search(query, n_results=max_results)
            for result in local_raw:
                doc_id = result["arxiv_id"]
                if doc_id.startswith("paper-"):
                    continue
                db_key = f"arxiv:{doc_id}"
                db_paper = self._db.get_paper(db_key)
                if db_paper and db_paper.get("status") in ("published", "external"):
                    paper = self._db_row_to_paper(db_paper)
                    if paper and doc_id not in local_ids:
                        local_results.append(arxiv_paper_to_source_result(paper))
                        local_ids.add(doc_id)

        # Search arXiv API
        if include_arxiv:
            arxiv_papers = await self._arxiv.search(
                query, max_results=max_results, categories=categories
            )
            num_arxiv_results = len(arxiv_papers)
            for paper in arxiv_papers:
                if paper.arxiv_id not in local_ids:
                    arxiv_only.append(arxiv_paper_to_source_result(paper))

        papers = (local_results + arxiv_only)[:max_results]

        if self._logger:
            self._logger.log(
                EventType.LITERATURE_SEARCH,
                content={
                    "query": query,
                    "local_results": len(local_results),
                    "arxiv_results": num_arxiv_results,
                    "arxiv_new": len(arxiv_only),
                    "total_results": len(papers),
                    "sources": {"local": include_local, "arxiv": include_arxiv},
                },
            )

        return papers

    # ------------------------------------------------------------------
    # References & Citations
    # ------------------------------------------------------------------

    async def get_references(self, arxiv_id: str, max_results: int = 20) -> list[SourceResult]:
        """Get papers referenced by this paper.

        Delegates to the semantic_scholar provider if available,
        otherwise falls back to the legacy S2 client.

        Args:
            arxiv_id: arXiv paper ID.
            max_results: Maximum number of references to return.

        Returns:
            List of SourceResult objects.
        """
        if self._providers and "semantic_scholar" in self._providers:
            results = await self._providers["semantic_scholar"].get_references(arxiv_id)
            return results[:max_results]

        from paradigm.domains.base import semantic_paper_to_source_result

        papers = await self._s2.get_references(arxiv_id, limit=max_results)
        return [semantic_paper_to_source_result(p) for p in papers]

    async def get_citations(self, arxiv_id: str, max_results: int = 10) -> list[SourceResult]:
        """Get papers that cite this paper.

        Delegates to the semantic_scholar provider if available,
        otherwise falls back to the legacy S2 client.

        Args:
            arxiv_id: arXiv paper ID.
            max_results: Maximum number of citations to return.

        Returns:
            List of SourceResult objects.
        """
        if self._providers and "semantic_scholar" in self._providers:
            results = await self._providers["semantic_scholar"].get_citing(arxiv_id)
            return results[:max_results]

        from paradigm.domains.base import semantic_paper_to_source_result

        papers = await self._s2.get_citations(arxiv_id, limit=max_results)
        return [semantic_paper_to_source_result(p) for p in papers]

    # ------------------------------------------------------------------
    # Read paper
    # ------------------------------------------------------------------

    async def read_paper(self, arxiv_id: str, max_chars: int = 8000) -> tuple[str, str] | None:
        """Fetch and extract key sections from a paper.

        Checks local DB body first; falls back to PDF fetch + extraction.
        When providers are configured, also tries provider fetch().

        Args:
            arxiv_id: arXiv paper ID.
            max_chars: Maximum characters to return.

        Returns:
            Tuple of (title, extracted_text), or None if paper cannot be read.
        """
        # Check local DB for cached body text
        db_paper = self._db.get_paper(f"arxiv:{arxiv_id}")
        if db_paper and db_paper.get("body"):
            title = db_paper.get("title", arxiv_id)
            return title, extract_key_sections(db_paper["body"], max_chars)

        # Try providers if available
        if self._providers:
            for provider in self._providers.values():
                try:
                    doc = await provider.fetch(arxiv_id)
                    if doc and doc.full_text:
                        # Cache in DB
                        self._cache_body_text(arxiv_id, doc.full_text)
                        return doc.title, extract_key_sections(doc.full_text, max_chars)
                except Exception:
                    continue

        # Fall back to fetching from arXiv directly
        paper = await self._arxiv.get_paper(arxiv_id)
        if paper is None:
            return None

        pdf_text = await self._arxiv.fetch_pdf_text(paper)
        if pdf_text is None:
            return None

        # Cache the body text in DB
        paper_key = f"arxiv:{arxiv_id}"
        existing = self._db.get_paper(paper_key)
        if existing:
            self._db.update_paper(paper_key, body=pdf_text)
        else:
            await self.ingest_paper(paper.model_copy(update={"body": pdf_text}))

        return paper.title, extract_key_sections(pdf_text, max_chars)

    def _cache_body_text(self, arxiv_id: str, body: str) -> None:
        """Cache body text in the database if entry exists."""
        paper_key = f"arxiv:{arxiv_id}"
        existing = self._db.get_paper(paper_key)
        if existing:
            self._db.update_paper(paper_key, body=body)

    # ------------------------------------------------------------------
    # Ingestion (stays on ArxivPaper)
    # ------------------------------------------------------------------

    async def ingest_paper(self, paper: ArxivPaper, fetch_pdf: bool = False) -> None:
        """Add a paper to local storage (SQLite + ChromaDB).

        Args:
            paper: ArxivPaper to ingest.
            fetch_pdf: Whether to fetch and extract PDF text.
        """
        # Optionally fetch PDF text
        if fetch_pdf and paper.body is None and self._config.enable_pdf_fetch:
            body = await self._arxiv.fetch_pdf_text(paper)
            if body:
                paper = paper.model_copy(update={"body": body})

        # Store in SQLite
        paper_id = f"arxiv:{paper.arxiv_id}"
        existing = self._db.get_paper(paper_id)
        if existing is None:
            self._db.create_paper(
                paper_id=paper_id,
                title=paper.title,
                abstract=paper.abstract,
                authors=paper.authors,
                body=paper.body or "",
                status="external",
                keywords=paper.categories,
            )
        else:
            # Update if we now have body text
            if paper.body and not existing.get("body"):
                self._db.update_paper(paper_id, body=paper.body)

        # Store in ChromaDB
        self._embeddings.add_paper(
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            abstract=paper.abstract,
            metadata={
                "title": paper.title,
                "authors": ", ".join(paper.authors),
                "primary_category": paper.primary_category,
                "published": paper.published.isoformat(),
            },
        )

    async def ingest_from_search(
        self,
        query: str,
        max_results: int | None = None,
        categories: list[str] | None = None,
        fetch_pdfs: bool = False,
    ) -> list[ArxivPaper]:
        """Search arXiv and ingest all results into local corpus.

        Args:
            query: Search query.
            max_results: Maximum results to ingest.
            categories: Optional category filters.
            fetch_pdfs: Whether to fetch PDFs for all results.

        Returns:
            List of ingested papers.
        """
        papers = await self._arxiv.search(
            query,
            max_results=max_results or self._config.max_results_per_search,
            categories=categories,
        )

        for paper in papers:
            await self.ingest_paper(paper, fetch_pdf=fetch_pdfs)

        return papers

    async def fetch_and_ingest_url(self, url: str) -> ArxivPaper | None:
        """Fetch a PDF from a URL and ingest it as an external paper.

        Args:
            url: URL pointing to a PDF document.

        Returns:
            The ingested ArxivPaper, or None if fetching/extraction fails.
        """
        pdf_text = await self._arxiv.fetch_pdf_from_url(url)
        if not pdf_text:
            return None

        paper = make_external_paper(url, pdf_text)
        await self.ingest_paper(paper, fetch_pdf=False)
        return paper

    # ------------------------------------------------------------------
    # Other queries
    # ------------------------------------------------------------------

    async def semantic_search(self, query: str, n_results: int = 10) -> list[dict[str, Any]]:
        """Search local corpus by semantic similarity only.

        Args:
            query: Search query text.
            n_results: Maximum number of results.

        Returns:
            List of result dicts from EmbeddingStore.
        """
        return self._embeddings.search(query, n_results=n_results)

    async def get_paper(self, arxiv_id: str) -> ArxivPaper | None:
        """Get a paper, checking local storage first then arXiv.

        Args:
            arxiv_id: arXiv paper ID.

        Returns:
            ArxivPaper if found, None otherwise.
        """
        # Check local DB first
        db_paper = self._db.get_paper(f"arxiv:{arxiv_id}")
        if db_paper:
            paper = self._db_row_to_paper(db_paper)
            if paper:
                return paper

        # Fall back to arXiv API
        return await self._arxiv.get_paper(arxiv_id)

    async def build_literature_context(
        self,
        topic: str,
        max_papers: int = 15,
        include_arxiv: bool = True,
    ) -> str:
        """Build a formatted literature context string for an agent.

        Searches for relevant papers and formats them as markdown
        suitable for inclusion in an agent's context window.

        Args:
            topic: Research topic to search for.
            max_papers: Maximum number of papers to include.
            include_arxiv: Whether to include arXiv results.

        Returns:
            Markdown-formatted literature summary with numbered references.
        """
        papers = await self.search(topic, max_results=max_papers, include_arxiv=include_arxiv)

        if not papers:
            return f"## Literature Search: {topic}\n\nNo relevant papers found."

        lines = [f"## Relevant Literature for: {topic}\n"]

        for i, paper in enumerate(papers, 1):
            is_internal = paper.id.startswith("paper-")
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += " et al."

            date_str = paper.date.strftime("%Y-%m-%d") if paper.date else "Unknown"
            categories = paper.metadata.get("categories", [])

            lines.append(f"### [{i}] {paper.title}")
            lines.append(f"**Authors:** {authors_str}")
            if is_internal:
                lines.append(f"**Published:** {date_str} | **Source:** Paradigm internal")
                lines.append(f"**ID:** {paper.id}")
            else:
                cats = ", ".join(categories[:3]) if categories else ""
                lines.append(f"**Published:** {date_str} | **Categories:** {cats}")
                lines.append(f"**arXiv:** {paper.id}")
            lines.append(f"\n{paper.summary}\n")
            lines.append("---\n")

        # References section
        lines.append("## References\n")
        for i, paper in enumerate(papers, 1):
            is_internal = paper.id.startswith("paper-")
            authors_short = paper.authors[0] if paper.authors else "Unknown"
            if len(paper.authors) > 1:
                authors_short += " et al."
            year = paper.date.strftime("%Y") if paper.date else "?"
            if is_internal:
                lines.append(f'[{i}] {authors_short} ({year}). "{paper.title}". {paper.id}')
            else:
                lines.append(f'[{i}] {authors_short} ({year}). "{paper.title}". arXiv:{paper.id}')

        return "\n".join(lines)

    def ingest_internal_paper(
        self,
        paper_id: str,
        title: str,
        abstract: str,
        authors: list[str],
        published_date: str | None = None,
    ) -> None:
        """Add an internally-produced paper to the ChromaDB embedding store.

        Unlike ingest_paper() which handles ArxivPaper objects, this method
        handles papers generated by the Paradigm research pipeline.

        Args:
            paper_id: Internal paper identifier (used as document ID).
            title: Paper title.
            abstract: Paper abstract.
            authors: List of author agent IDs.
            published_date: Optional ISO date string for when the paper was published.
        """
        from datetime import UTC, datetime

        metadata: dict[str, str] = {
            "title": title,
            "authors": ", ".join(authors),
            "source": "paradigm",
            "published": published_date or datetime.now(UTC).isoformat(),
        }

        self._embeddings.add_paper(
            arxiv_id=paper_id,
            title=title,
            abstract=abstract,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def citations(self) -> CitationTracker:
        """Access the citation tracker."""
        return self._citations

    def _db_row_to_paper(self, row: dict[str, Any]) -> ArxivPaper | None:
        """Convert a database row to an ArxivPaper.

        Args:
            row: Database row dict from papers table.

        Returns:
            ArxivPaper, or None if conversion fails.
        """
        paper_id = row.get("id", "")
        is_internal = paper_id.startswith("paper-")
        arxiv_id = paper_id if is_internal else paper_id.removeprefix("arxiv:")

        try:
            import json

            authors_raw = row.get("authors") or "[]"
            if isinstance(authors_raw, str):
                authors = json.loads(authors_raw)
            else:
                authors = authors_raw

            categories_raw = row.get("keywords") or "[]"
            if isinstance(categories_raw, str):
                categories = json.loads(categories_raw) or []
            else:
                categories = categories_raw or []

            if is_internal:
                pdf_url = ""
                abs_url = ""
            else:
                pdf_url = f"http://arxiv.org/pdf/{arxiv_id}"
                abs_url = f"http://arxiv.org/abs/{arxiv_id}"

            return ArxivPaper(
                arxiv_id=arxiv_id,
                title=row.get("title", ""),
                abstract=row.get("abstract", ""),
                authors=authors,
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=row.get("created_at", "2000-01-01T00:00:00"),
                updated=row.get("updated_at", "2000-01-01T00:00:00"),
                pdf_url=pdf_url,
                abs_url=abs_url,
                body=row.get("body") or None,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    async def close(self) -> None:
        """Close the arXiv/Semantic Scholar clients and all source providers."""
        await self._arxiv.close()
        await self._s2.close()
        # Source providers hold their own network clients (httpx pools / wrapped
        # API clients) that would otherwise leak a connection pool per cycle.
        for provider in (self._providers or {}).values():
            try:
                await provider.close()
            except Exception as e:  # best-effort teardown; never block shutdown
                if self._logger:
                    self._logger.log_error(e, metadata_key="provider_close")

    async def __aenter__(self) -> Corpus:
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Context manager exit."""
        await self.close()
