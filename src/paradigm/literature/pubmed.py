"""PubMed NCBI E-utilities client for literature search."""

from __future__ import annotations

import asyncio
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

from paradigm.logging.events import EventLogger


@dataclass
class PubMedPaper:
    """Paper metadata from PubMed."""

    pmid: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    journal: str = ""
    year: int | None = None
    doi: str | None = None
    url: str = ""


class PubMedClient:
    """Async PubMed client using NCBI E-utilities (esearch + efetch).

    Rate limits: 3 req/sec without API key, 10 req/sec with key.
    Set NCBI_API_KEY env var for higher rate limits.
    """

    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit: float = 0.34,
        logger: EventLogger | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize PubMed client.

        Args:
            api_key: Optional NCBI API key for higher rate limits.
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

        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        )
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def search(self, query: str, max_results: int = 10) -> list[PubMedPaper]:
        """Search PubMed for papers matching a query.

        Two-step process: esearch returns PMIDs, efetch returns full metadata.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of PubMedPaper objects matching the query.
        """
        # Step 1: esearch to get PMIDs
        params: dict[str, str | int] = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        data = await self._get_json(self.ESEARCH_URL, params)
        if data is None:
            return []

        esearch_result = data.get("esearchresult", {})
        pmids = esearch_result.get("idlist", [])
        if not pmids:
            return []

        # Step 2: efetch to get full metadata
        return await self._fetch_papers(pmids)

    async def get_paper(self, pmid: str) -> PubMedPaper | None:
        """Fetch a single paper by PMID.

        Args:
            pmid: PubMed ID.

        Returns:
            PubMedPaper, or None if not found.
        """
        papers = await self._fetch_papers([pmid])
        return papers[0] if papers else None

    async def _fetch_papers(self, pmids: list[str]) -> list[PubMedPaper]:
        """Fetch full metadata for a list of PMIDs via efetch.

        Args:
            pmids: List of PubMed IDs.

        Returns:
            List of PubMedPaper objects.
        """
        params: dict[str, str] = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        xml_text = await self._get_text(self.EFETCH_URL, params)
        if xml_text is None:
            return []

        return _parse_pubmed_xml(xml_text)

    async def _get_json(self, url: str, params: dict[str, str | int]) -> dict | None:
        """Make a rate-limited GET request and return parsed JSON.

        Args:
            url: Request URL.
            params: Query parameters.

        Returns:
            Parsed JSON dict, or None on error.
        """
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self._rate_limit:
                await asyncio.sleep(self._rate_limit - elapsed)

            try:
                response = await self._client.get(url, params=params)
                self._last_request_time = time.monotonic()

                if response.status_code == 200:
                    return response.json()

                if self._logger:
                    self._logger.log_error(
                        Exception(f"PubMed API returned {response.status_code}"),
                        metadata_key="pubmed",
                        url=url,
                        status_code=response.status_code,
                    )
                return None

            except Exception as e:
                if self._logger:
                    self._logger.log_error(e, metadata_key="pubmed", url=url)
                return None

    async def _get_text(self, url: str, params: dict[str, str]) -> str | None:
        """Make a rate-limited GET request and return response text.

        Args:
            url: Request URL.
            params: Query parameters.

        Returns:
            Response text, or None on error.
        """
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self._rate_limit:
                await asyncio.sleep(self._rate_limit - elapsed)

            try:
                response = await self._client.get(url, params=params)
                self._last_request_time = time.monotonic()

                if response.status_code == 200:
                    return response.text

                if self._logger:
                    self._logger.log_error(
                        Exception(f"PubMed API returned {response.status_code}"),
                        metadata_key="pubmed",
                        url=url,
                        status_code=response.status_code,
                    )
                return None

            except Exception as e:
                if self._logger:
                    self._logger.log_error(e, metadata_key="pubmed", url=url)
                return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> PubMedClient:
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Context manager exit."""
        await self.close()


def _parse_pubmed_xml(xml_text: str) -> list[PubMedPaper]:
    """Parse PubMed efetch XML response into PubMedPaper objects.

    Args:
        xml_text: XML response from efetch.

    Returns:
        List of parsed PubMedPaper objects.
    """
    papers: list[PubMedPaper] = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return papers

    for article in root.findall(".//PubmedArticle"):
        try:
            paper = _parse_article(article)
            if paper is not None:
                papers.append(paper)
        except Exception:
            continue

    return papers


def _parse_article(article: ET.Element) -> PubMedPaper | None:
    """Parse a single PubmedArticle XML element.

    Args:
        article: XML element for a PubMed article.

    Returns:
        PubMedPaper, or None if essential fields are missing.
    """
    medline = article.find(".//MedlineCitation")
    if medline is None:
        return None

    # PMID
    pmid_elem = medline.find("PMID")
    if pmid_elem is None or not pmid_elem.text:
        return None
    pmid = pmid_elem.text

    # Article info
    article_elem = medline.find("Article")
    if article_elem is None:
        return None

    # Title
    title_elem = article_elem.find("ArticleTitle")
    title = title_elem.text if title_elem is not None and title_elem.text else ""
    if not title:
        return None

    # Authors
    authors: list[str] = []
    author_list = article_elem.find("AuthorList")
    if author_list is not None:
        for author in author_list.findall("Author"):
            last = author.find("LastName")
            fore = author.find("ForeName")
            if last is not None and last.text:
                name = last.text
                if fore is not None and fore.text:
                    name = f"{fore.text} {last.text}"
                authors.append(name)

    # Abstract
    abstract_elem = article_elem.find("Abstract/AbstractText")
    abstract = abstract_elem.text if abstract_elem is not None and abstract_elem.text else ""

    # Journal
    journal_elem = article_elem.find("Journal/Title")
    journal = journal_elem.text if journal_elem is not None and journal_elem.text else ""

    # Year
    year: int | None = None
    pub_date = article_elem.find("Journal/JournalIssue/PubDate")
    if pub_date is not None:
        year_elem = pub_date.find("Year")
        if year_elem is not None and year_elem.text:
            try:
                year = int(year_elem.text)
            except ValueError:
                pass

    # DOI
    doi: str | None = None
    for id_elem in article_elem.findall("ELocationID"):
        if id_elem.get("EIdType") == "doi" and id_elem.text:
            doi = id_elem.text
            break

    return PubMedPaper(
        pmid=pmid,
        title=title,
        authors=authors,
        abstract=abstract,
        journal=journal,
        year=year,
        doi=doi,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}",
    )
