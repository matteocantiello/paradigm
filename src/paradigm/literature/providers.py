"""Concrete SourceProvider adapters wrapping existing literature clients."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

import httpx

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

_logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Finance-specific source providers
# ---------------------------------------------------------------------------

_SSRN_SEARCH_URL = "https://api.ssrn.com/content/v1/bindings/search"
_SSRN_ABSTRACT_URL = "https://papers.ssrn.com/sol3/papers.cfm"
_SEC_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
_FRED_API_URL = "https://api.stlouisfed.org/fred"


class SSRNSourceProvider(SourceProvider):
    """SourceProvider for SSRN (Social Science Research Network).

    Searches SSRN papers via their public search endpoint and returns
    paper metadata including title, authors, abstract, and URL.
    """

    name = "ssrn"

    def __init__(self, rate_limit: float = 1.0) -> None:
        self._rate_limit = rate_limit
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Paradigm Research Platform (academic use)"},
        )

    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        """Search SSRN for papers matching the query."""
        try:
            encoded_query = quote_plus(query)
            url = f"https://papers.ssrn.com/sol3/results.cfm?txtKey_Words={encoded_query}&npage=1&cnt={max_results}"
            response = await self._client.get(url)
            response.raise_for_status()
            return self._parse_search_results(response.text, max_results)
        except httpx.HTTPError as e:
            _logger.warning("SSRN search failed: %s", e)
            return []

    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Fetch an SSRN paper by abstract ID."""
        try:
            url = f"{_SSRN_ABSTRACT_URL}?abstract_id={source_id}"
            response = await self._client.get(url)
            response.raise_for_status()
            return SourceDocument(
                id=source_id,
                source_type="ssrn",
                title="",
                full_text=response.text[:50000],
                url=url,
            )
        except httpx.HTTPError as e:
            _logger.warning("SSRN fetch failed for %s: %s", source_id, e)
            return None

    @staticmethod
    def _parse_search_results(html: str, max_results: int) -> list[SourceResult]:
        """Parse SSRN search results from HTML response.

        This is a best-effort parser for SSRN's search results page.
        """
        results: list[SourceResult] = []
        # Extract paper entries using simple regex patterns
        # SSRN abstract IDs appear in URLs like abstract_id=1234567
        id_pattern = re.compile(r"abstract_id=(\d+)")
        title_pattern = re.compile(r"<a[^>]*abstract_id=\d+[^>]*>([^<]+)</a>", re.IGNORECASE)

        ids = id_pattern.findall(html)
        titles = title_pattern.findall(html)

        for i, (paper_id, title) in enumerate(zip(ids, titles, strict=False)):
            if i >= max_results:
                break
            results.append(
                SourceResult(
                    id=paper_id,
                    source_type="ssrn",
                    title=title.strip(),
                    url=f"{_SSRN_ABSTRACT_URL}?abstract_id={paper_id}",
                )
            )
        return results


class SECEdgarSourceProvider(SourceProvider):
    """SourceProvider for SEC EDGAR (Electronic Data Gathering, Analysis, and Retrieval).

    Searches SEC EDGAR full-text search API for 10-K, 10-Q, and 8-K filings.
    Required: User-Agent header per SEC EDGAR access policy.
    """

    name = "sec_edgar"

    def __init__(self, user_agent: str = "Paradigm Research Platform academic@example.com") -> None:
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": user_agent},
        )

    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        """Search SEC EDGAR full-text search for filings."""
        try:
            params = {
                "q": query,
                "dateRange": "custom",
                "startdt": "2020-01-01",
                "enddt": datetime.now().strftime("%Y-%m-%d"),
                "forms": "10-K,10-Q,8-K",
            }
            url = "https://efts.sec.gov/LATEST/search-index"
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return self._parse_results(data, max_results)
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            _logger.warning("SEC EDGAR search failed: %s", e)
            return []

    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Fetch a filing by accession number."""
        try:
            # Accession numbers are formatted like 0001234567-20-012345
            clean_id = source_id.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{clean_id}"
            response = await self._client.get(url)
            response.raise_for_status()
            return SourceDocument(
                id=source_id,
                source_type="sec_edgar",
                title="",
                full_text=response.text[:50000],
                url=url,
            )
        except httpx.HTTPError as e:
            _logger.warning("SEC EDGAR fetch failed for %s: %s", source_id, e)
            return None

    @staticmethod
    def _parse_results(data: dict, max_results: int) -> list[SourceResult]:
        """Parse SEC EDGAR search API response."""
        results: list[SourceResult] = []
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits[:max_results]:
            source = hit.get("_source", {})
            filing_id = source.get("file_num", hit.get("_id", ""))
            form_type = source.get("form_type", "")
            entity_name = source.get("entity_name", "")
            filed_date = source.get("file_date", "")
            title = f"{entity_name} — {form_type}" if entity_name else form_type
            results.append(
                SourceResult(
                    id=filing_id,
                    source_type="sec_edgar",
                    title=title,
                    summary=f"Filing type: {form_type}, Filed: {filed_date}",
                    url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={filing_id}",
                    metadata={
                        "form_type": form_type,
                        "entity_name": entity_name,
                        "filed_date": filed_date,
                    },
                )
            )
        return results


class FREDSourceProvider(SourceProvider):
    """SourceProvider for FRED (Federal Reserve Economic Data).

    Searches the FRED series catalog for economic data series metadata.
    Requires a FRED API key (env var FRED_API_KEY).
    """

    name = "fred"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("FRED_API_KEY", "")
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Paradigm Research Platform"},
        )

    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        """Search FRED series catalog."""
        if not self._api_key:
            _logger.warning("FRED API key not set — skipping FRED search")
            return []
        try:
            params = {
                "search_text": query,
                "api_key": self._api_key,
                "file_type": "json",
                "limit": max_results,
            }
            response = await self._client.get(f"{_FRED_API_URL}/series/search", params=params)
            response.raise_for_status()
            data = response.json()
            return self._parse_results(data, max_results)
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            _logger.warning("FRED search failed: %s", e)
            return []

    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Fetch FRED series metadata by series ID."""
        if not self._api_key:
            return None
        try:
            params = {
                "series_id": source_id,
                "api_key": self._api_key,
                "file_type": "json",
            }
            response = await self._client.get(f"{_FRED_API_URL}/series", params=params)
            response.raise_for_status()
            data = response.json()
            series_list = data.get("seriess", [])
            if not series_list:
                return None
            series = series_list[0]
            return SourceDocument(
                id=source_id,
                source_type="fred",
                title=series.get("title", ""),
                full_text=json.dumps(series, indent=2),
                url=f"https://fred.stlouisfed.org/series/{source_id}",
                metadata={
                    "frequency": series.get("frequency", ""),
                    "units": series.get("units", ""),
                    "seasonal_adjustment": series.get("seasonal_adjustment", ""),
                },
            )
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            _logger.warning("FRED fetch failed for %s: %s", source_id, e)
            return None

    @staticmethod
    def _parse_results(data: dict, max_results: int) -> list[SourceResult]:
        """Parse FRED series search response."""
        results: list[SourceResult] = []
        series_list = data.get("seriess", [])
        for series in series_list[:max_results]:
            series_id = series.get("id", "")
            title = series.get("title", "")
            frequency = series.get("frequency", "")
            units = series.get("units", "")
            start = series.get("observation_start", "")
            end = series.get("observation_end", "")
            summary = f"Frequency: {frequency}, Units: {units}, Range: {start} to {end}"
            results.append(
                SourceResult(
                    id=series_id,
                    source_type="fred",
                    title=title,
                    summary=summary,
                    url=f"https://fred.stlouisfed.org/series/{series_id}",
                    metadata={
                        "frequency": frequency,
                        "units": units,
                        "observation_start": start,
                        "observation_end": end,
                    },
                )
            )
        return results
