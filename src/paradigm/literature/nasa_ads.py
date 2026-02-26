"""NASA ADS (Astrophysics Data System) API client for literature search."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from paradigm.logging.events import EventLogger


@dataclass
class ADSPaper:
    """Paper metadata from NASA ADS."""

    bibcode: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    citation_count: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str = ""


class ADSClient:
    """Async NASA ADS API client with rate limiting.

    Requires an API key from NASA ADS (env var NASA_ADS_API_KEY).
    Rate limit: ~5000 requests/day (~1 req/sec recommended).
    """

    BASE_URL = "https://api.adsabs.harvard.edu/v1"
    FIELDS = "bibcode,title,author,abstract,year,citation_count,doi,identifier"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit: float = 1.0,
        logger: EventLogger | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize ADS client.

        Args:
            api_key: NASA ADS API key (required for all requests).
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
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        )
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def search(self, query: str, max_results: int = 10) -> list[ADSPaper]:
        """Search ADS for papers matching a query.

        Args:
            query: Search query string (supports ADS query syntax).
            max_results: Maximum number of results.

        Returns:
            List of ADSPaper objects matching the query.
        """
        if not self._api_key:
            return []

        params = {
            "q": query,
            "fl": self.FIELDS,
            "rows": max_results,
            "sort": "score desc",
        }

        data = await self._get_json(f"{self.BASE_URL}/search/query", params)
        if data is None:
            return []

        return _parse_ads_response(data)

    async def get_paper(self, bibcode: str) -> ADSPaper | None:
        """Fetch a single paper by bibcode.

        Args:
            bibcode: ADS bibcode.

        Returns:
            ADSPaper, or None if not found.
        """
        if not self._api_key:
            return None

        params = {
            "q": f"bibcode:{bibcode}",
            "fl": self.FIELDS,
            "rows": 1,
        }

        data = await self._get_json(f"{self.BASE_URL}/search/query", params)
        if data is None:
            return []

        papers = _parse_ads_response(data)
        return papers[0] if papers else None

    async def get_references(self, bibcode: str, limit: int = 20) -> list[ADSPaper]:
        """Get papers referenced by a given paper.

        Args:
            bibcode: ADS bibcode of the source paper.
            limit: Maximum number of references to return.

        Returns:
            List of ADSPaper objects for referenced papers.
        """
        if not self._api_key:
            return []

        params = {
            "q": f"references(bibcode:{bibcode})",
            "fl": self.FIELDS,
            "rows": limit,
            "sort": "score desc",
        }

        data = await self._get_json(f"{self.BASE_URL}/search/query", params)
        if data is None:
            return []

        return _parse_ads_response(data)

    async def get_citations(self, bibcode: str, limit: int = 50) -> list[ADSPaper]:
        """Get papers that cite a given paper.

        Args:
            bibcode: ADS bibcode of the source paper.
            limit: Maximum number of citations to return.

        Returns:
            List of ADSPaper objects for citing papers, sorted by year desc.
        """
        if not self._api_key:
            return []

        params = {
            "q": f"citations(bibcode:{bibcode})",
            "fl": self.FIELDS,
            "rows": limit,
            "sort": "date desc",
        }

        data = await self._get_json(f"{self.BASE_URL}/search/query", params)
        if data is None:
            return []

        return _parse_ads_response(data)

    async def _get_json(
        self, url: str, params: dict[str, Any], max_retries: int = 2
    ) -> dict[str, Any] | None:
        """Make a rate-limited GET request and return parsed JSON.

        Retries with exponential backoff on 429 (rate limit) responses.

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
                    backoff = 3.0 * 2**attempt
                    await asyncio.sleep(backoff)
                    continue

                if self._logger:
                    self._logger.log_error(
                        Exception(f"ADS API returned {response.status_code}"),
                        metadata_key="nasa_ads",
                        url=url,
                        status_code=response.status_code,
                    )
                return None

            except Exception as e:
                if self._logger:
                    self._logger.log_error(e, metadata_key="nasa_ads", url=url)
                return None

        return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> ADSClient:
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Context manager exit."""
        await self.close()


def _parse_ads_response(data: dict[str, Any]) -> list[ADSPaper]:
    """Parse ADS API search response into ADSPaper objects.

    Args:
        data: Parsed JSON response from ADS API.

    Returns:
        List of parsed ADSPaper objects.
    """
    papers: list[ADSPaper] = []
    response = data.get("response", {})
    docs = response.get("docs", [])

    for doc in docs:
        paper = _parse_ads_doc(doc)
        if paper is not None:
            papers.append(paper)

    return papers


def _parse_ads_doc(doc: dict[str, Any]) -> ADSPaper | None:
    """Parse a single ADS document into an ADSPaper.

    Args:
        doc: Document dict from ADS API response.

    Returns:
        ADSPaper, or None if essential fields are missing.
    """
    bibcode = doc.get("bibcode", "")
    if not bibcode:
        return None

    # Title is returned as a list
    title_list = doc.get("title", [])
    title = title_list[0] if title_list else ""
    if not title:
        return None

    # Authors
    authors = doc.get("author", [])

    # DOI is returned as a list
    doi_list = doc.get("doi", [])
    doi = doi_list[0] if doi_list else None

    # Extract arXiv ID from identifiers
    arxiv_id = _extract_arxiv_id(doc.get("identifier", []))

    return ADSPaper(
        bibcode=bibcode,
        title=title,
        authors=authors,
        abstract=doc.get("abstract", ""),
        year=doc.get("year"),
        citation_count=doc.get("citation_count"),
        doi=doi,
        arxiv_id=arxiv_id,
        url=f"https://ui.adsabs.harvard.edu/abs/{bibcode}",
    )


def _extract_arxiv_id(identifiers: list[str]) -> str | None:
    """Extract arXiv ID from ADS identifier list.

    Args:
        identifiers: List of identifiers from ADS (e.g., ["arXiv:2301.12345", ...]).

    Returns:
        arXiv ID string, or None if not found.
    """
    for ident in identifiers:
        if ident.startswith("arXiv:"):
            return ident[6:]
    return None
