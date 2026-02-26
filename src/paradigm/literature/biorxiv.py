"""bioRxiv/medRxiv API client for preprint literature search."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

from paradigm.logging.events import EventLogger


@dataclass
class BiorxivPaper:
    """Paper metadata from bioRxiv/medRxiv."""

    doi: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    date: str = ""
    server: str = "biorxiv"  # "biorxiv" or "medrxiv"
    category: str = ""
    url: str = ""


class BiorxivClient:
    """Async bioRxiv/medRxiv API client.

    Uses the bioRxiv content API for date-range browsing and DOI lookup.
    Keyword search is done client-side since the API only supports
    date-range browsing.
    """

    BASE_URL = "https://api.biorxiv.org/details"

    def __init__(
        self,
        rate_limit: float = 1.0,
        logger: EventLogger | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize bioRxiv client.

        Args:
            rate_limit: Minimum seconds between API requests.
            logger: Optional event logger.
            timeout: HTTP request timeout in seconds.
        """
        self._rate_limit = rate_limit
        self._logger = logger

        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Paradigm/1.0 (scientific research)"},
        )
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def search(
        self,
        query: str,
        server: str = "biorxiv",
        max_results: int = 10,
    ) -> list[BiorxivPaper]:
        """Search bioRxiv/medRxiv for papers matching a query.

        Since the bioRxiv API only supports date-range browsing, we fetch
        recent papers and filter client-side by query keywords.

        Args:
            query: Search query string.
            server: "biorxiv" or "medrxiv".
            max_results: Maximum number of results.

        Returns:
            List of BiorxivPaper objects matching the query.
        """
        # Search recent papers (last 30 days) and filter by keywords
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        date_from = start_date.strftime("%Y-%m-%d")
        date_to = end_date.strftime("%Y-%m-%d")

        # Fetch a larger batch to filter from
        fetch_count = max_results * 5
        url = f"{self.BASE_URL}/{server}/{date_from}/{date_to}/0/{fetch_count}"

        data = await self._get_json(url)
        if data is None:
            return []

        collection = data.get("collection", [])
        if not collection:
            return []

        # Parse all papers
        papers = [_parse_biorxiv_entry(entry, server) for entry in collection]
        papers = [p for p in papers if p is not None]

        # Filter by query keywords
        keywords = _extract_keywords(query)
        if keywords:
            papers = _filter_by_keywords(papers, keywords)

        return papers[:max_results]

    async def get_paper(self, doi: str) -> BiorxivPaper | None:
        """Fetch a single paper by DOI.

        Args:
            doi: Paper DOI.

        Returns:
            BiorxivPaper, or None if not found.
        """
        # Try bioRxiv first, then medRxiv
        for server in ("biorxiv", "medrxiv"):
            url = f"{self.BASE_URL}/{server}/{doi}/na/na"
            data = await self._get_json(url)
            if data is not None:
                collection = data.get("collection", [])
                if collection:
                    paper = _parse_biorxiv_entry(collection[0], server)
                    if paper is not None:
                        return paper

        return None

    async def _get_json(self, url: str) -> dict | None:
        """Make a rate-limited GET request and return parsed JSON.

        Args:
            url: Request URL.

        Returns:
            Parsed JSON dict, or None on error.
        """
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self._rate_limit:
                await asyncio.sleep(self._rate_limit - elapsed)

            try:
                response = await self._client.get(url)
                self._last_request_time = time.monotonic()

                if response.status_code == 200:
                    return response.json()

                if self._logger:
                    self._logger.log_error(
                        Exception(f"bioRxiv API returned {response.status_code}"),
                        metadata_key="biorxiv",
                        url=url,
                        status_code=response.status_code,
                    )
                return None

            except Exception as e:
                if self._logger:
                    self._logger.log_error(e, metadata_key="biorxiv", url=url)
                return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> BiorxivClient:
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Context manager exit."""
        await self.close()


def _parse_biorxiv_entry(entry: dict, server: str) -> BiorxivPaper | None:
    """Parse a bioRxiv API entry into a BiorxivPaper.

    Args:
        entry: Dict from API response collection.
        server: "biorxiv" or "medrxiv".

    Returns:
        BiorxivPaper, or None if essential fields are missing.
    """
    doi = entry.get("doi", "")
    title = entry.get("title", "")
    if not doi or not title:
        return None

    # Authors come as a semicolon-separated string
    authors_str = entry.get("authors", "")
    authors = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []

    return BiorxivPaper(
        doi=doi,
        title=title,
        authors=authors,
        abstract=entry.get("abstract", ""),
        date=entry.get("date", ""),
        server=server,
        category=entry.get("category", ""),
        url=f"https://www.{server}.org/content/{doi}",
    )


def _extract_keywords(query: str) -> set[str]:
    """Extract meaningful keywords from a search query.

    Args:
        query: Search query string.

    Returns:
        Set of lowercase keywords (length >= 3).
    """
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "been",
        "have",
        "has",
        "had",
        "will",
        "can",
        "may",
        "not",
        "but",
        "its",
        "all",
        "each",
        "how",
        "than",
        "use",
        "our",
        "new",
    }
    words = query.lower().split()
    return {w for w in words if len(w) >= 3 and w not in stop_words}


def _filter_by_keywords(papers: list[BiorxivPaper], keywords: set[str]) -> list[BiorxivPaper]:
    """Filter papers by keyword match in title and abstract.

    Args:
        papers: List of papers to filter.
        keywords: Set of keywords to match.

    Returns:
        Papers that match at least one keyword.
    """
    results: list[BiorxivPaper] = []
    for paper in papers:
        text = f"{paper.title} {paper.abstract}".lower()
        if any(kw in text for kw in keywords):
            results.append(paper)
    return results
