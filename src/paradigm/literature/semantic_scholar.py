"""Semantic Scholar API client for citation graph traversal."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from paradigm.logging.events import EventLogger

# Circuit breaker: after this many consecutive 429s, stop calling S2 for a cooldown
# instead of hammering it (the free tier rate-limits hard — this was the single
# highest-volume error in production, ~288 in one window).
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN = 60.0
_RETRY_AFTER_CAP = 30.0


def _retry_after_seconds(response: httpx.Response, fallback: float) -> float:
    """Honor the server's Retry-After header (seconds), capped; else ``fallback``."""
    ra = response.headers.get("Retry-After")
    if ra:
        try:
            return min(float(ra), _RETRY_AFTER_CAP)
        except ValueError:
            pass
    return fallback


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
    oa_pdf_url: str | None = None  # open-access PDF, when S2 has one


class SemanticScholarClient:
    """Async Semantic Scholar API client with rate limiting."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    FIELDS = "title,authors,abstract,externalIds,year,citationCount,url,openAccessPdf"

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
        # Read the key from the environment when not passed, so EVERY construction
        # site (provider factory, corpus, citation handler, bibliography) gets the
        # higher rate limit without each having to plumb it. A keyed client rarely
        # 429s; this is the root fix for the rate-limit floods.
        self._api_key = api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        self._rate_limit = rate_limit
        self._logger = logger

        headers: dict[str, str] = {
            "User-Agent": "Paradigm/1.0 (scientific research)",
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key

        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        )
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()
        # Circuit-breaker state.
        self._consecutive_429 = 0
        self._breaker_open_until = 0.0

    def _breaker_open(self) -> bool:
        return time.monotonic() < self._breaker_open_until

    def _record_429(self, url: str) -> None:
        """Count a 429 and open the breaker (logging ONCE) when throttling persists."""
        self._consecutive_429 += 1
        if self._consecutive_429 >= _BREAKER_THRESHOLD and not self._breaker_open():
            self._breaker_open_until = time.monotonic() + _BREAKER_COOLDOWN
            if self._logger:
                self._logger.log_error(
                    Exception(
                        f"Semantic Scholar rate-limited — skipping for {_BREAKER_COOLDOWN:.0f}s "
                        "(set SEMANTIC_SCHOLAR_API_KEY for a higher limit)"
                    ),
                    metadata_key="semantic_scholar",
                    url=url,
                    status_code=429,
                )

    def _record_success(self) -> None:
        self._consecutive_429 = 0

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

    async def search_by_author(self, author_name: str, limit: int = 20) -> list[SemanticPaper]:
        """Search for papers by a specific author.

        Two-step: search for author by name, then get their papers.

        Args:
            author_name: Author name to search for.
            limit: Maximum number of papers to return.

        Returns:
            List of SemanticPaper objects by the author.
        """
        # Step 1: Search for author
        url = f"{self.BASE_URL}/author/search"
        params: dict[str, Any] = {"query": author_name, "limit": 1}

        data = await self._get_json(url, params)
        if data is None:
            return []

        authors_data = data.get("data", [])
        if not authors_data:
            return []

        author_id = authors_data[0].get("authorId")
        if not author_id:
            return []

        # Step 2: Get author's papers
        papers_url = f"{self.BASE_URL}/author/{author_id}/papers"
        papers_params: dict[str, Any] = {"fields": self.FIELDS, "limit": limit}

        papers_data = await self._get_json(papers_url, papers_params)
        if papers_data is None:
            return []

        papers = []
        for entry in papers_data.get("data", []):
            paper = _parse_paper(entry)
            if paper is not None:
                papers.append(paper)

        return papers[:limit]

    async def get_paper_details(self, paper_id: str) -> SemanticPaper | None:
        """Get detailed metadata for a single paper by S2 paper ID or arXiv ID.

        Args:
            paper_id: Semantic Scholar paper ID, or arXiv ID (prefixed with ArXiv:).

        Returns:
            SemanticPaper, or None if not found.
        """
        url = f"{self.BASE_URL}/paper/{paper_id}"
        params: dict[str, Any] = {"fields": self.FIELDS}

        data = await self._get_json(url, params)
        if data is None:
            return None

        return _parse_paper(data)

    async def get_papers_batch(self, paper_ids: list[str]) -> list[SemanticPaper]:
        """Batch fetch metadata for multiple papers.

        Args:
            paper_ids: List of paper IDs (S2 IDs, arXiv IDs with ArXiv: prefix, etc.).

        Returns:
            List of SemanticPaper objects for successfully fetched papers.
        """
        if not paper_ids:
            return []

        url = f"{self.BASE_URL}/paper/batch"
        params: dict[str, Any] = {"fields": self.FIELDS}
        max_retries = 2

        if self._breaker_open():
            return []  # cooling down after persistent rate-limiting

        response = None
        for attempt in range(max_retries + 1):
            try:
                async with self._lock:
                    elapsed = time.monotonic() - self._last_request_time
                    if elapsed < self._rate_limit:
                        await asyncio.sleep(self._rate_limit - elapsed)
                    response = await self._client.post(url, params=params, json={"ids": paper_ids})
                    self._last_request_time = time.monotonic()
            except Exception as e:
                if self._logger:
                    self._logger.log_error(e, metadata_key="semantic_scholar", url=url)
                return []

            if response.status_code == 200:
                self._record_success()
                break

            if response.status_code == 429:
                self._record_429(url)
                if attempt < max_retries and not self._breaker_open():
                    await asyncio.sleep(_retry_after_seconds(response, 3.0 * 2**attempt))
                    continue
                return []  # retries exhausted or breaker tripped (logged once)

            if self._logger:
                self._logger.log_error(
                    Exception(f"Semantic Scholar API returned {response.status_code}"),
                    metadata_key="semantic_scholar",
                    url=url,
                    status_code=response.status_code,
                )
            return []

        if response is None or response.status_code != 200:
            return []

        data = response.json()
        papers = []
        for entry in data if isinstance(data, list) else []:
            if entry is not None:
                paper = _parse_paper(entry)
                if paper is not None:
                    papers.append(paper)

        return papers

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
        if self._breaker_open():
            return None  # cooling down after persistent rate-limiting; don't pile on
        for attempt in range(max_retries + 1):
            try:
                async with self._lock:
                    elapsed = time.monotonic() - self._last_request_time
                    if elapsed < self._rate_limit:
                        await asyncio.sleep(self._rate_limit - elapsed)

                    response = await self._client.get(url, params=params)
                    self._last_request_time = time.monotonic()

                if response.status_code == 200:
                    self._record_success()
                    return response.json()

                if response.status_code == 429:
                    self._record_429(url)
                    if attempt < max_retries and not self._breaker_open():
                        await asyncio.sleep(_retry_after_seconds(response, 3.0 * 2**attempt))
                        continue
                    return None  # retries exhausted or breaker tripped (logged once)

                if self._logger:
                    self._logger.log_error(
                        Exception(f"Semantic Scholar API returned {response.status_code}"),
                        metadata_key="semantic_scholar",
                        url=url,
                        status_code=response.status_code,
                    )
                return None

            except Exception as e:
                if self._logger:
                    self._logger.log_error(e, metadata_key="semantic_scholar", url=url)
                return None
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

    oa = data.get("openAccessPdf") or {}

    return SemanticPaper(
        paper_id=paper_id,
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=data.get("abstract") or "",
        year=data.get("year"),
        citation_count=data.get("citationCount"),
        url=data.get("url") or "",
        oa_pdf_url=oa.get("url") or None,
    )
