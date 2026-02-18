"""arXiv API client for literature search and retrieval."""

from __future__ import annotations

import asyncio
import io
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import httpx
import pymupdf
from pydantic import BaseModel, Field

from paradigm.logging.events import EventLogger, EventType

# arXiv API constants
ARXIV_API_BASE = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
OPENSEARCH_NS = "{http://a9.com/-/spec/opensearch/1.1/}"


def extract_key_sections(full_text: str, max_chars: int = 8000) -> str:
    """Extract abstract + introduction + conclusion from paper text.

    Strategy:
    1. Find abstract (text between "Abstract" and "Introduction" headers)
    2. Find introduction (text between "Introduction" and next section header)
    3. Find conclusion (text between "Conclusion"/"Summary" and "References"/"Acknowledgements")
    4. Concatenate with section headers, cap at max_chars
    5. If no sections found, return first max_chars of text

    Args:
        full_text: Complete extracted paper text.
        max_chars: Maximum characters to return.

    Returns:
        Extracted key sections as a string.
    """
    if not full_text:
        return ""

    # Common section header patterns (case-insensitive)
    abstract_re = re.compile(
        r"(?:^|\n)\s*(?:abstract)\s*\n",
        re.IGNORECASE,
    )
    intro_re = re.compile(
        r"(?:^|\n)\s*(?:\d+\.?\s*)?(?:introduction)\s*\n",
        re.IGNORECASE,
    )
    conclusion_re = re.compile(
        r"(?:^|\n)\s*(?:\d+\.?\s*)?(?:conclusions?|summary|discussion and conclusions?)\s*\n",
        re.IGNORECASE,
    )
    end_re = re.compile(
        r"(?:^|\n)\s*(?:\d+\.?\s*)?(?:references|acknowledgements?|appendix|bibliography)\s*\n",
        re.IGNORECASE,
    )
    # Generic section header (number + title)
    section_re = re.compile(
        r"(?:^|\n)\s*(?:\d+\.?\s+)[A-Z]",
    )

    sections: list[str] = []

    # Extract abstract
    abs_match = abstract_re.search(full_text)
    intro_match = intro_re.search(full_text)

    if abs_match:
        abs_start = abs_match.end()
        abs_end = intro_match.start() if intro_match else abs_start + 2000
        abstract_text = full_text[abs_start:abs_end].strip()
        if abstract_text:
            sections.append(f"**Abstract:**\n{abstract_text}")

    # Extract introduction
    if intro_match:
        intro_start = intro_match.end()
        # Find next section header after introduction
        next_section = section_re.search(full_text, intro_start + 100)
        intro_end = next_section.start() if next_section else intro_start + 3000
        intro_text = full_text[intro_start:intro_end].strip()
        if intro_text:
            sections.append(f"**Introduction:**\n{intro_text}")

    # Extract conclusion
    conc_match = conclusion_re.search(full_text)
    if conc_match:
        conc_start = conc_match.end()
        end_match = end_re.search(full_text, conc_start)
        conc_end = end_match.start() if end_match else conc_start + 3000
        conc_text = full_text[conc_start:conc_end].strip()
        if conc_text:
            sections.append(f"**Conclusion:**\n{conc_text}")

    if sections:
        result = "\n\n".join(sections)
        return result[:max_chars]

    # Fallback: return first max_chars of text
    return full_text[:max_chars]


class ArxivPaper(BaseModel):
    """Structured representation of an arXiv paper."""

    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: datetime
    updated: datetime
    pdf_url: str
    abs_url: str
    doi: str | None = None
    journal_ref: str | None = None
    comment: str | None = None
    body: str | None = None  # Populated only when PDF is fetched and extracted


class ArxivSearchResult(BaseModel):
    """Metadata about a search result set."""

    total_results: int
    start_index: int
    items_per_page: int
    papers: list[ArxivPaper] = Field(default_factory=list)


class ArxivClient:
    """Async arXiv API client with rate limiting and PDF extraction."""

    def __init__(
        self,
        rate_limit: float = 3.0,
        logger: EventLogger | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize arXiv client.

        Args:
            rate_limit: Minimum seconds between API requests.
            logger: Optional event logger for structured logging.
            timeout: HTTP request timeout in seconds.
        """
        self._rate_limit = rate_limit
        self._logger = logger
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Paradigm/1.0 (scientific research; +https://github.com/matteocantiello/paradigm)",
            },
        )
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def search(
        self,
        query: str,
        max_results: int = 20,
        start: int = 0,
        sort_by: str = "relevance",
        sort_order: str = "descending",
        categories: list[str] | None = None,
    ) -> list[ArxivPaper]:
        """Search arXiv for papers matching query.

        Args:
            query: Search query (keywords, phrases).
            max_results: Maximum number of results to return.
            start: Starting index for pagination.
            sort_by: Sort criterion ("relevance", "lastUpdatedDate", "submittedDate").
            sort_order: Sort direction ("ascending", "descending").
            categories: Optional arXiv category filters (e.g., ["astro-ph.SR"]).

        Returns:
            List of ArxivPaper objects matching the query.
        """
        search_query = self._build_query(query, categories)
        params: dict[str, Any] = {
            "search_query": search_query,
            "start": start,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        response = await self._rate_limited_get(ARXIV_API_BASE, params)
        result = self._parse_feed(response.text)

        if self._logger:
            self._logger.log(
                EventType.LITERATURE_SEARCH,
                content={
                    "query": query,
                    "categories": categories,
                    "results_found": len(result.papers),
                    "total_available": result.total_results,
                },
            )

        return result.papers

    async def get_paper(self, arxiv_id: str) -> ArxivPaper | None:
        """Fetch a single paper by its arXiv ID.

        Args:
            arxiv_id: The arXiv paper ID (e.g., "2301.12345" or "astro-ph/0601001").

        Returns:
            ArxivPaper if found, None otherwise.
        """
        params: dict[str, Any] = {
            "id_list": arxiv_id,
            "max_results": 1,
        }

        response = await self._rate_limited_get(ARXIV_API_BASE, params)
        result = self._parse_feed(response.text)

        if result.papers:
            return result.papers[0]
        return None

    async def fetch_pdf_from_url(self, url: str) -> str | None:
        """Download and extract text from a PDF at the given URL.

        Tries httpx first; falls back to curl if the response is not a PDF
        (some sites block Python HTTP clients via TLS fingerprinting).

        Args:
            url: Direct URL to a PDF file.

        Returns:
            Extracted text content, or None if extraction fails.
        """
        pdf_bytes = await self.fetch_pdf_bytes(url)
        if pdf_bytes is None:
            return None

        try:
            doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            return "\n".join(text_parts).strip() or None
        except Exception as e:
            if self._logger:
                self._logger.log_error(e, metadata_key="pdf_extraction", url=url)
            return None

    async def fetch_pdf_bytes(self, url: str) -> bytes | None:
        """Fetch raw PDF bytes from a URL, with curl fallback.

        Args:
            url: URL to fetch.

        Returns:
            PDF file bytes, or None on failure.
        """
        # Try httpx first
        try:
            response = await self._rate_limited_get(url)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "pdf" in content_type or "octet-stream" in content_type:
                    return response.content
        except Exception:
            pass  # Fall through to curl

        # Fallback: curl (bypasses TLS fingerprint-based bot detection)
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "curl",
                    "-sL",
                    "-A",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "--max-time",
                    "30",
                    "-o",
                    "-",
                    url,
                ],
                capture_output=True,
                timeout=35,
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                # Verify it's actually a PDF (starts with %PDF)
                if result.stdout[:5] == b"%PDF-":
                    return result.stdout
        except Exception as e:
            if self._logger:
                self._logger.log_error(e, metadata_key="pdf_fetch_curl", url=url)

        if self._logger:
            self._logger.log_error(
                Exception("All fetch methods failed"),
                metadata_key="pdf_fetch",
                url=url,
            )
        return None

    async def fetch_pdf_text(self, paper: ArxivPaper) -> str | None:
        """Download and extract text from a paper's PDF.

        Args:
            paper: ArxivPaper with a valid pdf_url.

        Returns:
            Extracted text content, or None if extraction fails.
        """
        return await self.fetch_pdf_from_url(paper.pdf_url)

    async def _rate_limited_get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        """Make a rate-limited GET request with retry on 429.

        Args:
            url: Request URL.
            params: Optional query parameters.
            max_retries: Maximum retries on 429 rate-limit responses.

        Returns:
            HTTP response.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses (after retries exhausted for 429).
        """
        for attempt in range(max_retries + 1):
            async with self._lock:
                elapsed = time.monotonic() - self._last_request_time
                if elapsed < self._rate_limit:
                    await asyncio.sleep(self._rate_limit - elapsed)

                response = await self._client.get(url, params=params)
                self._last_request_time = time.monotonic()

            if response.status_code != 429:
                response.raise_for_status()
                return response

            # Exponential backoff on 429: 10s, 20s, 40s
            if attempt < max_retries:
                backoff = 10.0 * 2**attempt
                await asyncio.sleep(backoff)

        response.raise_for_status()
        return response

    def _build_query(self, query: str, categories: list[str] | None = None) -> str:
        """Build an arXiv API search query string.

        Args:
            query: User search terms.
            categories: Optional category filters.

        Returns:
            Formatted arXiv query string.
        """
        # Split into keywords, sort by length (longer = more specific), cap
        # at 6 terms, and join with AND for targeted matching.
        words = re.sub(r"[^a-zA-Z0-9\s-]", " ", query).split()
        unique_words = list(dict.fromkeys(w for w in words if len(w) > 2))
        terms = sorted(unique_words, key=len, reverse=True)[:6]
        if terms:
            search_query = " AND ".join(f"all:{t}" for t in terms)
        else:
            search_query = f"all:{query}"

        if categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
            search_query = f"({search_query}) AND ({cat_query})"

        return search_query

    def _parse_feed(self, xml_text: str) -> ArxivSearchResult:
        """Parse an arXiv Atom feed response.

        Args:
            xml_text: Raw XML response from arXiv API.

        Returns:
            ArxivSearchResult with parsed papers and metadata.
        """
        root = ET.fromstring(xml_text)

        # Parse search metadata
        total_results = int(root.findtext(f"{OPENSEARCH_NS}totalResults", default="0"))
        start_index = int(root.findtext(f"{OPENSEARCH_NS}startIndex", default="0"))
        items_per_page = int(root.findtext(f"{OPENSEARCH_NS}itemsPerPage", default="0"))

        # Parse entries
        papers = []
        for entry in root.findall(f"{ATOM_NS}entry"):
            paper = self._parse_entry(entry)
            if paper is not None:
                papers.append(paper)

        return ArxivSearchResult(
            total_results=total_results,
            start_index=start_index,
            items_per_page=items_per_page,
            papers=papers,
        )

    def _parse_entry(self, entry: ET.Element) -> ArxivPaper | None:
        """Parse a single Atom entry into an ArxivPaper.

        Args:
            entry: XML Element for an <entry>.

        Returns:
            ArxivPaper, or None if the entry is malformed.
        """
        # Extract arXiv ID from the <id> URL
        raw_id = entry.findtext(f"{ATOM_NS}id", default="")
        if not raw_id:
            return None

        # ID format: http://arxiv.org/abs/2301.12345v1
        arxiv_id = raw_id.split("/abs/")[-1]
        # Strip version suffix for canonical ID
        if "v" in arxiv_id:
            arxiv_id = arxiv_id.rsplit("v", 1)[0]

        title = entry.findtext(f"{ATOM_NS}title", default="").strip()
        title = " ".join(title.split())  # Normalize whitespace

        abstract = entry.findtext(f"{ATOM_NS}summary", default="").strip()
        abstract = " ".join(abstract.split())

        # Authors
        authors = []
        for author_el in entry.findall(f"{ATOM_NS}author"):
            name = author_el.findtext(f"{ATOM_NS}name", default="")
            if name:
                authors.append(name.strip())

        # Categories
        categories = []
        for cat_el in entry.findall(f"{ATOM_NS}category"):
            term = cat_el.get("term", "")
            if term:
                categories.append(term)

        primary_cat_el = entry.find(f"{ARXIV_NS}primary_category")
        primary_category = ""
        if primary_cat_el is not None:
            primary_category = primary_cat_el.get("term", "")

        # Dates
        published_str = entry.findtext(f"{ATOM_NS}published", default="")
        updated_str = entry.findtext(f"{ATOM_NS}updated", default="")

        try:
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
        except ValueError:
            return None

        # Links
        abs_url = raw_id
        pdf_url = ""
        for link_el in entry.findall(f"{ATOM_NS}link"):
            if link_el.get("title") == "pdf":
                pdf_url = link_el.get("href", "")
                break
        if not pdf_url:
            # Construct PDF URL from ID
            pdf_url = f"http://arxiv.org/pdf/{arxiv_id}"

        # Optional fields
        doi_el = entry.find(f"{ARXIV_NS}doi")
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

        journal_ref_el = entry.find(f"{ARXIV_NS}journal_ref")
        journal_ref = (
            journal_ref_el.text.strip()
            if journal_ref_el is not None and journal_ref_el.text
            else None
        )

        comment_el = entry.find(f"{ARXIV_NS}comment")
        comment = comment_el.text.strip() if comment_el is not None and comment_el.text else None

        return ArxivPaper(
            arxiv_id=arxiv_id,
            title=title,
            abstract=abstract,
            authors=authors,
            categories=categories,
            primary_category=primary_category,
            published=published,
            updated=updated,
            pdf_url=pdf_url,
            abs_url=abs_url,
            doi=doi,
            journal_ref=journal_ref,
            comment=comment,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> ArxivClient:
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Context manager exit."""
        await self.close()
