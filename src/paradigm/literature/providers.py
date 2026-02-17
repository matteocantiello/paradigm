"""Concrete SourceProvider adapters wrapping existing literature clients."""

from __future__ import annotations

import json
from typing import Any

from paradigm.domains.base import (
    SourceDocument,
    SourceProvider,
    SourceResult,
    arxiv_paper_to_source_result,
    semantic_paper_to_source_result,
)
from paradigm.literature.arxiv import ArxivClient, extract_key_sections
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.literature.semantic_scholar import SemanticScholarClient
from paradigm.storage.database import Database


class ArxivSourceProvider(SourceProvider):
    """SourceProvider wrapping the existing ArxivClient.

    Delegates search to the arXiv API and converts results to SourceResult.
    Provides PDF-based full-text fetch via SourceDocument.
    """

    name = "arxiv"

    def __init__(self, client: ArxivClient) -> None:
        self._client = client

    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        """Search arXiv and convert results to SourceResult."""
        papers = await self._client.search(query, max_results=max_results)
        return [arxiv_paper_to_source_result(p) for p in papers]

    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Fetch a paper by arXiv ID and extract key sections from PDF."""
        paper = await self._client.get_paper(source_id)
        if paper is None:
            return None

        pdf_text = await self._client.fetch_pdf_text(paper)
        sections: dict[str, str] = {}
        full_text = ""
        if pdf_text:
            full_text = pdf_text
            extracted = extract_key_sections(pdf_text)
            if extracted:
                sections["key_sections"] = extracted

        return SourceDocument(
            id=paper.arxiv_id,
            source_type="arxiv",
            title=paper.title,
            authors=paper.authors,
            full_text=full_text,
            sections=sections,
            url=paper.abs_url,
            metadata={
                "categories": paper.categories,
                "primary_category": paper.primary_category,
                "pdf_url": paper.pdf_url,
            },
        )


class SemanticScholarSourceProvider(SourceProvider):
    """SourceProvider wrapping the existing SemanticScholarClient.

    Provides citation graph traversal (references and citations).
    Search delegates to the S2 keyword search API.
    Full-text fetch returns None since S2 doesn't provide full text.
    """

    name = "semantic_scholar"

    def __init__(self, client: SemanticScholarClient) -> None:
        self._client = client

    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        """Search Semantic Scholar and convert results to SourceResult."""
        papers = await self._client.search(query, limit=max_results)
        return [semantic_paper_to_source_result(p) for p in papers]

    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Semantic Scholar doesn't provide full text."""
        return None

    async def get_references(self, source_id: str) -> list[SourceResult]:
        """Get papers referenced by this paper."""
        papers = await self._client.get_references(source_id)
        return [semantic_paper_to_source_result(p) for p in papers]

    async def get_citing(self, source_id: str) -> list[SourceResult]:
        """Get papers that cite this paper."""
        papers = await self._client.get_citations(source_id)
        return [semantic_paper_to_source_result(p) for p in papers]


class InternalCorpusProvider(SourceProvider):
    """SourceProvider wrapping EmbeddingStore + Database for local papers.

    Searches the local ChromaDB vector store and returns results
    from the SQLite database. Excludes internally-generated papers
    (paper-* IDs) to prevent self-citation.
    """

    name = "internal_corpus"

    def __init__(self, embedding_store: EmbeddingStore, database: Database) -> None:
        self._embeddings = embedding_store
        self._db = database

    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        """Search local corpus by semantic similarity."""
        if self._embeddings.count() == 0:
            return []

        local_results = self._embeddings.search(query, n_results=max_results)
        results: list[SourceResult] = []

        for result in local_results:
            doc_id = result["arxiv_id"]
            # Skip internally-generated papers
            if doc_id.startswith("paper-"):
                continue
            db_key = f"arxiv:{doc_id}"
            db_paper = self._db.get_paper(db_key)
            if db_paper and db_paper.get("status") in ("published", "external"):
                sr = self._db_row_to_source_result(db_paper)
                if sr is not None:
                    results.append(sr)

        return results

    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Fetch a paper from local database."""
        db_paper = self._db.get_paper(f"arxiv:{source_id}")
        if db_paper is None:
            return None

        authors = _parse_json_field(db_paper.get("authors"), [])
        return SourceDocument(
            id=source_id,
            source_type="internal",
            title=db_paper.get("title", ""),
            authors=authors,
            full_text=db_paper.get("body", ""),
            url="",
        )

    def _db_row_to_source_result(self, row: dict[str, Any]) -> SourceResult | None:
        """Convert a database row to a SourceResult."""
        paper_id = row.get("id", "")
        is_internal = paper_id.startswith("paper-")
        doc_id = paper_id if is_internal else paper_id.removeprefix("arxiv:")

        try:
            authors = _parse_json_field(row.get("authors"), [])
            categories = _parse_json_field(row.get("keywords"), [])

            from datetime import datetime

            date_str = row.get("created_at", "2000-01-01T00:00:00")
            if isinstance(date_str, str):
                try:
                    date = datetime.fromisoformat(date_str)
                except ValueError:
                    date = datetime(2000, 1, 1)
            else:
                date = date_str

            return SourceResult(
                id=doc_id,
                source_type="internal" if is_internal else "arxiv",
                title=row.get("title", ""),
                authors=authors,
                summary=row.get("abstract", ""),
                url=f"http://arxiv.org/abs/{doc_id}" if not is_internal else "",
                date=date,
                content=row.get("body") or None,
                metadata={
                    "categories": categories,
                    "primary_category": categories[0] if categories else "",
                },
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None


def _parse_json_field(value: Any, default: Any) -> Any:
    """Parse a JSON string field, returning default on failure."""
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return default
    return value
