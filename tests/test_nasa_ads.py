"""Tests for NASA ADS API client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from paradigm.domains.base import ads_paper_to_source_result
from paradigm.literature.nasa_ads import (
    ADSClient,
    ADSPaper,
    _extract_arxiv_id,
    _parse_ads_doc,
    _parse_ads_response,
)

# --- Sample API response data ---


def _make_ads_doc(
    bibcode: str = "2023ApJ...123..456S",
    title: str = "Stellar Convection in Massive Stars",
    year: int = 2023,
    arxiv_id: str | None = "2301.12345",
) -> dict:
    """Create a sample ADS document dict."""
    identifiers = []
    if arxiv_id:
        identifiers.append(f"arXiv:{arxiv_id}")
    return {
        "bibcode": bibcode,
        "title": [title],
        "author": ["Smith, Alice", "Jones, Bob"],
        "abstract": "A study of convective processes.",
        "year": year,
        "citation_count": 42,
        "doi": ["10.3847/1538-4357/test"],
        "identifier": identifiers,
    }


SAMPLE_RESPONSE = {
    "response": {
        "numFound": 2,
        "docs": [
            _make_ads_doc("2023ApJ...123..456S", "Paper One", 2023, "2301.001"),
            _make_ads_doc("2022MNRAS.789..012J", "Paper Two", 2022, "2201.002"),
        ],
    }
}


# --- _extract_arxiv_id tests ---


class TestExtractArxivId:
    def test_extracts_arxiv_id(self):
        assert _extract_arxiv_id(["arXiv:2301.12345"]) == "2301.12345"

    def test_returns_none_when_missing(self):
        assert _extract_arxiv_id(["doi:10.1234/test"]) is None

    def test_empty_list(self):
        assert _extract_arxiv_id([]) is None

    def test_multiple_identifiers(self):
        ids = ["doi:10.1234/test", "arXiv:2301.99999", "2023ApJ"]
        assert _extract_arxiv_id(ids) == "2301.99999"


# --- _parse_ads_doc tests ---


class TestParseAdsDoc:
    def test_basic_parsing(self):
        doc = _make_ads_doc()
        paper = _parse_ads_doc(doc)
        assert paper is not None
        assert paper.bibcode == "2023ApJ...123..456S"
        assert paper.title == "Stellar Convection in Massive Stars"
        assert paper.authors == ["Smith, Alice", "Jones, Bob"]
        assert paper.year == 2023
        assert paper.citation_count == 42
        assert paper.doi == "10.3847/1538-4357/test"
        assert paper.arxiv_id == "2301.12345"
        assert "adsabs.harvard.edu" in paper.url

    def test_missing_bibcode_returns_none(self):
        doc = _make_ads_doc()
        doc["bibcode"] = ""
        assert _parse_ads_doc(doc) is None

    def test_missing_title_returns_none(self):
        doc = _make_ads_doc()
        doc["title"] = []
        assert _parse_ads_doc(doc) is None

    def test_no_arxiv_id(self):
        doc = _make_ads_doc(arxiv_id=None)
        paper = _parse_ads_doc(doc)
        assert paper is not None
        assert paper.arxiv_id is None

    def test_no_doi(self):
        doc = _make_ads_doc()
        doc["doi"] = []
        paper = _parse_ads_doc(doc)
        assert paper is not None
        assert paper.doi is None


# --- _parse_ads_response tests ---


class TestParseAdsResponse:
    def test_parses_multiple_docs(self):
        papers = _parse_ads_response(SAMPLE_RESPONSE)
        assert len(papers) == 2

    def test_empty_response(self):
        papers = _parse_ads_response({"response": {"docs": []}})
        assert papers == []

    def test_missing_response_key(self):
        papers = _parse_ads_response({})
        assert papers == []


# --- ADSPaper dataclass tests ---


class TestADSPaper:
    def test_defaults(self):
        paper = ADSPaper(bibcode="2023test", title="Test")
        assert paper.authors == []
        assert paper.abstract == ""
        assert paper.year is None
        assert paper.citation_count is None
        assert paper.doi is None
        assert paper.arxiv_id is None

    def test_full_construction(self):
        paper = ADSPaper(
            bibcode="2023ApJ...123..456S",
            title="Test Paper",
            authors=["Smith, A."],
            abstract="Abstract",
            year=2023,
            citation_count=10,
            doi="10.1234/test",
            arxiv_id="2301.12345",
            url="https://ui.adsabs.harvard.edu/abs/2023ApJ...123..456S",
        )
        assert paper.bibcode == "2023ApJ...123..456S"


# --- Conversion helper tests ---


class TestAdsPaperToSourceResult:
    def test_converts_with_arxiv_id(self):
        paper = ADSPaper(
            bibcode="2023ApJ...123..456S",
            title="Test Paper",
            authors=["Smith, A.", "Jones, B."],
            abstract="An abstract.",
            year=2023,
            citation_count=42,
            doi="10.1234/test",
            arxiv_id="2301.12345",
            url="https://ui.adsabs.harvard.edu/abs/2023ApJ...123..456S",
        )
        result = ads_paper_to_source_result(paper)
        assert result.id == "2301.12345"  # Uses arxiv_id when available
        assert result.source_type == "nasa_ads"
        assert result.title == "Test Paper"
        assert result.metadata["bibcode"] == "2023ApJ...123..456S"
        assert result.metadata["citation_count"] == 42
        assert result.date is not None
        assert result.date.year == 2023

    def test_converts_without_arxiv_id(self):
        paper = ADSPaper(
            bibcode="2023ApJ...123..456S",
            title="Test Paper",
            arxiv_id=None,
        )
        result = ads_paper_to_source_result(paper)
        assert result.id == "2023ApJ...123..456S"  # Falls back to bibcode

    def test_none_year(self):
        paper = ADSPaper(bibcode="test", title="No Year", year=None)
        result = ads_paper_to_source_result(paper)
        assert result.date is None


# --- ADSClient tests ---


class TestADSClient:
    @pytest.mark.asyncio
    async def test_search_returns_papers(self):
        client = ADSClient(api_key="test-key", rate_limit=0.0)
        client._get_json = AsyncMock(return_value=SAMPLE_RESPONSE)

        papers = await client.search("stellar convection")
        assert len(papers) == 2
        assert papers[0].bibcode == "2023ApJ...123..456S"
        await client.close()

    @pytest.mark.asyncio
    async def test_search_without_api_key(self):
        client = ADSClient(api_key=None, rate_limit=0.0)

        papers = await client.search("test query")
        assert papers == []
        await client.close()

    @pytest.mark.asyncio
    async def test_search_handles_api_error(self):
        client = ADSClient(api_key="test-key", rate_limit=0.0)
        client._get_json = AsyncMock(return_value=None)

        papers = await client.search("test query")
        assert papers == []
        await client.close()

    @pytest.mark.asyncio
    async def test_get_paper(self):
        client = ADSClient(api_key="test-key", rate_limit=0.0)
        client._get_json = AsyncMock(
            return_value={
                "response": {"docs": [_make_ads_doc()]},
            }
        )

        paper = await client.get_paper("2023ApJ...123..456S")
        assert paper is not None
        assert paper.bibcode == "2023ApJ...123..456S"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_references(self):
        client = ADSClient(api_key="test-key", rate_limit=0.0)
        client._get_json = AsyncMock(return_value=SAMPLE_RESPONSE)

        refs = await client.get_references("2023ApJ...123..456S")
        assert len(refs) == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_get_citations(self):
        client = ADSClient(api_key="test-key", rate_limit=0.0)
        client._get_json = AsyncMock(return_value=SAMPLE_RESPONSE)

        cites = await client.get_citations("2023ApJ...123..456S")
        assert len(cites) == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_api_key_header(self):
        client = ADSClient(api_key="test-key-abc", rate_limit=0.0)
        assert client._client.headers.get("Authorization") == "Bearer test-key-abc"
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with ADSClient(api_key="test", rate_limit=0.0) as client:
            assert client is not None
