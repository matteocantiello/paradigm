"""Semantic Scholar API client for citation graph traversal."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from paradigm.logging.events import EventLogger


@dataclass
class SemanticPaper:
    """Paper metadata from Semantic Scholar."""

    paper_id: str
    arxiv_id: str | None
    title: str
    authors: list[str]
    abstract: str
    year: int | None
    citation_count: int | None
    url: str


class SemanticScholarClient:
    """Async Semantic Scholar API client with rate limiting."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    FIELDS = "title,authors,abstract,externalIds,year,citationCount,url"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit: float = 1.0,
        logger: EventLogger | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize Semantic Scholar client.

        Args:
            api_key: Optional API key for higher rate limits.
            rate_limit: Minimum seconds between API requests.
            logger: Optional event logger.
            timeout: HTTP request timeout in seconds.
        """
        self._api_key = api_key
        self._rate_limit = rate_limit
        self._logger = logger

        headers: dict[str, str] = {
            "User-Agent": "Paradigm/1.0 (scientific research)",
        }
        if api_key:
            headers["x-api-key"] = api_key

        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        )
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def get_references(self, arxiv_id: str, limit: int = 20) -> list[SemanticPaper]:
        """Get papers referenced by a given paper.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2301.12345").
            limit: Maximum number of references to return.

        Returns:
            List of SemanticPaper objects for referenced papers.
        """
        arxiv_id = _normalize_arxiv_id(arxiv_id)
        url = f"{self.BASE_URL}/paper/ArXiv:{arxiv_id}/references"
        params = {"fields": self.FIELDS, "limit": limit}

        data = await self._get_json(url, params)
        if data is None:
            return []

        papers = []
        for entry in data.get("data", []):
            cited = entry.get("citedPaper", {})
            paper = _parse_paper(cited)
            if paper is not None:
                papers.append(paper)

        return papers[:limit]

    async def get_citations(self, arxiv_id: str, limit: int = 50) -> list[SemanticPaper]:
        """Get papers that cite a given paper.

        Results are sorted by year descending (most recent first) and
        filtered to only papers that have arXiv IDs.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2301.12345").
            limit: Maximum number of citations to return.

        Returns:
            List of SemanticPaper objects for citing papers.
        """
        arxiv_id = _normalize_arxiv_id(arxiv_id)
        url = f"{self.BASE_URL}/paper/ArXiv:{arxiv_id}/citations"
        params = {"fields": self.FIELDS, "limit": limit}

        data = await self._get_json(url, params)
        if data is None:
            return []

        papers = []
        for entry in data.get("data", []):
            citing = entry.get("citingPaper", {})
            paper = _parse_paper(citing)
            if paper is not None and paper.arxiv_id is not None:
                papers.append(paper)

        # Sort by year descending (most recent first)
        papers.sort(key=lambda p: p.year or 0, reverse=True)
        return papers[:limit]

    async def search(self, query: str, limit: int = 10) -> list[SemanticPaper]:
        """Search for papers by title or keywords.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of SemanticPaper objects matching the query.
        """
        url = f"{self.BASE_URL}/paper/search"
        params = {"query": query, "fields": self.FIELDS, "limit": limit}

        data = await self._get_json(url, params)
        if data is None:
            return []

        papers = []
        for entry in data.get("data", []):
            paper = _parse_paper(entry)
            if paper is not None:
                papers.append(paper)

        return papers[:limit]

    async def _get_json(
        self, url: str, params: dict[str, Any], max_retries: int = 2
    ) -> dict[str, Any] | None:
        """Make a rate-limited GET request and return parsed JSON.

        Retries with exponential backoff on 429 (rate limit) responses.
        Returns None on 404, 5xx errors, or exhausted retries.

        Args:
            url: Request URL.
            params: Query parameters.
            max_retries: Maximum retry attempts on 429 responses.

        Returns:
            Parsed JSON dict, or None on error.
        """
        for attempt in range(max_retries + 1):
            try:
                async with self._lock:
                    elapsed = time.monotonic() - self._last_request_time
                    if elapsed < self._rate_limit:
                        await asyncio.sleep(self._rate_limit - elapsed)

                    response = await self._client.get(url, params=params)
                    self._last_request_time = time.monotonic()

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429 and attempt < max_retries:
                    backoff = 3.0 * 2**attempt  # 3s, 6s
                    await asyncio.sleep(backoff)
                    continue

                if self._logger:
                    self._logger.log_error(
                        Exception(
                            f"Semantic Scholar API returned {response.status_code}"
                        ),
                        metadata_key="semantic_scholar",
                        url=url,
                        status_code=response.status_code,
                    )
                return None

            except Exception as e:
                if self._logger:
                    self._logger.log_error(
                        e, metadata_key="semantic_scholar", url=url
                    )
                return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> SemanticScholarClient:
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Context manager exit."""
        await self.close()


def _normalize_arxiv_id(arxiv_id: str) -> str:
    """Normalize an arXiv ID by stripping common prefixes and version suffixes.

    Args:
        arxiv_id: Raw arXiv ID string.

    Returns:
        Cleaned arXiv ID.
    """
    # Strip common prefixes
    for prefix in ("arXiv:", "arxiv:", "ArXiv:"):
        if arxiv_id.startswith(prefix):
            arxiv_id = arxiv_id[len(prefix) :]
            break

    # Strip version suffix (e.g., v1, v2)
    if "v" in arxiv_id:
        parts = arxiv_id.rsplit("v", 1)
        if len(parts) == 2 and parts[1].isdigit():
            arxiv_id = parts[0]

    return arxiv_id.strip()


def _parse_paper(data: dict[str, Any]) -> SemanticPaper | None:
    """Parse a Semantic Scholar paper dict into a SemanticPaper.

    Args:
        data: Paper data from API response.

    Returns:
        SemanticPaper, or None if essential fields are missing.
    """
    title = data.get("title")
    if not title:
        return None

    paper_id = data.get("paperId", "")
    external_ids = data.get("externalIds") or {}
    arxiv_id = external_ids.get("ArXiv")

    authors_raw = data.get("authors") or []
    authors = [a.get("name", "") for a in authors_raw if a.get("name")]

    return SemanticPaper(
        paper_id=paper_id,
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=data.get("abstract") or "",
        year=data.get("year"),
        citation_count=data.get("citationCount"),
        url=data.get("url") or "",
    )
