"""Unified literature search interface combining arXiv, local embeddings, and citations."""

from __future__ import annotations

import os
from typing import Any

from paradigm.config import LiteratureConfig, StorageConfig
from paradigm.literature.arxiv import ArxivClient, ArxivPaper, extract_key_sections
from paradigm.literature.citations import CitationTracker
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.literature.prompt_utils import make_external_paper
from paradigm.literature.semantic_scholar import SemanticPaper, SemanticScholarClient
from paradigm.logging.events import EventLogger, EventType
from paradigm.storage.database import Database


class Corpus:
    """Unified search interface for scientific literature.

    Combines arXiv API search, local semantic search (ChromaDB),
    and citation tracking into a single high-level API.
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
        """
        self._db = database
        self._config = literature_config
        self._logger = logger

        self._arxiv = arxiv_client or ArxivClient(
            rate_limit=literature_config.arxiv_rate_limit,
            logger=logger,
        )
        self._embeddings = embedding_store or EmbeddingStore(
            vector_db_path=storage_config.vector_db_path,
        )
        self._citations = CitationTracker(database)
        self._s2 = semantic_scholar_client or SemanticScholarClient(
            api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
            logger=logger,
        )

    async def search(
        self,
        query: str,
        max_results: int | None = None,
        include_local: bool = True,
        include_arxiv: bool = True,
        categories: list[str] | None = None,
    ) -> list[ArxivPaper]:
        """Search both local corpus and arXiv, deduplicate, and return.

        Builds local and arXiv result lists independently, then merges them
        (local first, then arXiv-only papers) capped at max_results. This
        ensures arXiv results are not crowded out by local duplicates.

        Args:
            query: Search query text.
            max_results: Maximum results (defaults to config value).
            include_local: Whether to search local embeddings.
            include_arxiv: Whether to search arXiv API.
            categories: Optional arXiv category filters.

        Returns:
            Deduplicated list of ArxivPaper objects.
        """
        if max_results is None:
            max_results = self._config.max_results_per_search

        local_papers: list[ArxivPaper] = []
        local_ids: set[str] = set()
        arxiv_only: list[ArxivPaper] = []
        num_arxiv_results = 0

        # Search local embeddings
        if include_local and self._embeddings.count() > 0:
            local_results = self._embeddings.search(query, n_results=max_results)
            for result in local_results:
                doc_id = result["arxiv_id"]
                # Internal papers use their ID directly; arXiv papers use "arxiv:" prefix
                if doc_id.startswith("paper-"):
                    db_key = doc_id
                else:
                    db_key = f"arxiv:{doc_id}"
                db_paper = self._db.get_paper(db_key)
                if db_paper and db_paper.get("status") in ("published", "external"):
                    paper = self._db_row_to_paper(db_paper)
                    if paper and doc_id not in local_ids:
                        local_papers.append(paper)
                        local_ids.add(doc_id)

        # Search arXiv API
        if include_arxiv:
            arxiv_results = await self._arxiv.search(
                query,
                max_results=max_results,
                categories=categories,
            )
            num_arxiv_results = len(arxiv_results)
            for paper in arxiv_results:
                if paper.arxiv_id not in local_ids:
                    arxiv_only.append(paper)

        # Merge: local first, then arXiv-only, capped at max_results
        papers = (local_papers + arxiv_only)[:max_results]

        if self._logger:
            self._logger.log(
                EventType.LITERATURE_SEARCH,
                content={
                    "query": query,
                    "local_results": len(local_papers),
                    "arxiv_results": num_arxiv_results,
                    "arxiv_new": len(arxiv_only),
                    "total_results": len(papers),
                    "sources": {
                        "local": include_local,
                        "arxiv": include_arxiv,
                    },
                },
            )

        return papers

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
            is_internal = paper.arxiv_id.startswith("paper-")
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += " et al."

            date_str = paper.published.strftime("%Y-%m-%d")

            lines.append(f"### [{i}] {paper.title}")
            lines.append(f"**Authors:** {authors_str}")
            if is_internal:
                lines.append(f"**Published:** {date_str} | **Source:** Paradigm internal")
                lines.append(f"**ID:** {paper.arxiv_id}")
            else:
                cats = ", ".join(paper.categories[:3])
                lines.append(f"**Published:** {date_str} | **Categories:** {cats}")
                lines.append(f"**arXiv:** {paper.arxiv_id}")
            lines.append(f"\n{paper.abstract}\n")
            lines.append("---\n")

        # References section
        lines.append("## References\n")
        for i, paper in enumerate(papers, 1):
            is_internal = paper.arxiv_id.startswith("paper-")
            authors_short = paper.authors[0] if paper.authors else "Unknown"
            if len(paper.authors) > 1:
                authors_short += " et al."
            year = paper.published.strftime("%Y")
            if is_internal:
                lines.append(f'[{i}] {authors_short} ({year}). "{paper.title}". {paper.arxiv_id}')
            else:
                lines.append(
                    f'[{i}] {authors_short} ({year}). "{paper.title}". arXiv:{paper.arxiv_id}'
                )

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
            arxiv_id=paper_id,  # arxiv_id param is just a document ID, accepts any string
            title=title,
            abstract=abstract,
            metadata=metadata,
        )

    async def get_references(self, arxiv_id: str, max_results: int = 20) -> list[SemanticPaper]:
        """Get papers referenced by this paper via Semantic Scholar.

        Args:
            arxiv_id: arXiv paper ID.
            max_results: Maximum number of references to return.

        Returns:
            List of SemanticPaper objects.
        """
        return await self._s2.get_references(arxiv_id, limit=max_results)

    async def get_citations(self, arxiv_id: str, max_results: int = 10) -> list[SemanticPaper]:
        """Get papers that cite this paper via Semantic Scholar.

        Args:
            arxiv_id: arXiv paper ID.
            max_results: Maximum number of citations to return.

        Returns:
            List of SemanticPaper objects (with arXiv IDs, sorted by year).
        """
        return await self._s2.get_citations(arxiv_id, limit=max_results)

    async def read_paper(self, arxiv_id: str, max_chars: int = 8000) -> tuple[str, str] | None:
        """Fetch and extract key sections from a paper.

        Checks local DB body first; falls back to PDF fetch + extraction.

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

        # Fall back to fetching from arXiv
        paper = await self._arxiv.get_paper(arxiv_id)
        if paper is None:
            return None

        pdf_text = await self._arxiv.fetch_pdf_text(paper)
        if pdf_text is None:
            return None

        # Cache the body text in DB
        paper_id = f"arxiv:{arxiv_id}"
        existing = self._db.get_paper(paper_id)
        if existing:
            self._db.update_paper(paper_id, body=pdf_text)
        else:
            await self.ingest_paper(paper.model_copy(update={"body": pdf_text}))

        return paper.title, extract_key_sections(pdf_text, max_chars)

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
        """Close the arXiv and Semantic Scholar clients."""
        await self._arxiv.close()
        await self._s2.close()

    async def __aenter__(self) -> Corpus:
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Context manager exit."""
        await self.close()
