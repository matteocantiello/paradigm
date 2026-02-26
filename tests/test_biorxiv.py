"""Tests for bioRxiv/medRxiv API client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from paradigm.domains.base import biorxiv_paper_to_source_result
from paradigm.literature.biorxiv import (
    BiorxivClient,
    BiorxivPaper,
    _extract_keywords,
    _filter_by_keywords,
    _parse_biorxiv_entry,
)

# --- Sample API response data ---

SAMPLE_ENTRY = {
    "doi": "10.1101/2023.01.15.123456",
    "title": "Stellar Convection and Mass Loss in Red Supergiants",
    "authors": "Smith, A.; Jones, B.; Davis, C.",
    "abstract": "We present a study of convective processes in red supergiant stars.",
    "date": "2023-01-15",
    "category": "astrophysics",
}

SAMPLE_ENTRY_2 = {
    "doi": "10.1101/2023.02.20.654321",
    "title": "Machine Learning for Genomics",
    "authors": "Lee, D.",
    "abstract": "Application of deep learning to genomic analysis.",
    "date": "2023-02-20",
    "category": "bioinformatics",
}


# --- _parse_biorxiv_entry tests ---


class TestParseBiorxivEntry:
    def test_basic_parsing(self):
        paper = _parse_biorxiv_entry(SAMPLE_ENTRY, "biorxiv")
        assert paper is not None
        assert paper.doi == "10.1101/2023.01.15.123456"
        assert paper.title == "Stellar Convection and Mass Loss in Red Supergiants"
        assert paper.authors == ["Smith, A.", "Jones, B.", "Davis, C."]
        assert paper.server == "biorxiv"
        assert paper.category == "astrophysics"
        assert paper.url == "https://www.biorxiv.org/content/10.1101/2023.01.15.123456"

    def test_medrxiv_server(self):
        paper = _parse_biorxiv_entry(SAMPLE_ENTRY, "medrxiv")
        assert paper is not None
        assert paper.server == "medrxiv"
        assert "medrxiv.org" in paper.url

    def test_missing_doi_returns_none(self):
        entry = {**SAMPLE_ENTRY, "doi": ""}
        assert _parse_biorxiv_entry(entry, "biorxiv") is None

    def test_missing_title_returns_none(self):
        entry = {**SAMPLE_ENTRY, "title": ""}
        assert _parse_biorxiv_entry(entry, "biorxiv") is None

    def test_empty_authors(self):
        entry = {**SAMPLE_ENTRY, "authors": ""}
        paper = _parse_biorxiv_entry(entry, "biorxiv")
        assert paper is not None
        assert paper.authors == []


# --- Keyword filtering tests ---


class TestExtractKeywords:
    def test_basic_extraction(self):
        kw = _extract_keywords("stellar convection in massive stars")
        assert "stellar" in kw
        assert "convection" in kw
        assert "massive" in kw
        assert "stars" in kw

    def test_filters_stop_words(self):
        kw = _extract_keywords("the and for with this")
        assert len(kw) == 0

    def test_filters_short_words(self):
        kw = _extract_keywords("a is in on")
        assert len(kw) == 0


class TestFilterByKeywords:
    def test_matches_title(self):
        papers = [
            BiorxivPaper(doi="1", title="Stellar Convection Study", abstract=""),
            BiorxivPaper(doi="2", title="Unrelated Topic", abstract=""),
        ]
        result = _filter_by_keywords(papers, {"stellar", "convection"})
        assert len(result) == 1
        assert result[0].doi == "1"

    def test_matches_abstract(self):
        papers = [
            BiorxivPaper(doi="1", title="A Study", abstract="stellar processes explored"),
        ]
        result = _filter_by_keywords(papers, {"stellar"})
        assert len(result) == 1

    def test_no_match(self):
        papers = [
            BiorxivPaper(doi="1", title="Quantum Computing", abstract="qubits and gates"),
        ]
        result = _filter_by_keywords(papers, {"stellar", "convection"})
        assert len(result) == 0


# --- BiorxivPaper dataclass tests ---


class TestBiorxivPaper:
    def test_defaults(self):
        paper = BiorxivPaper(doi="10.1101/test", title="Test")
        assert paper.authors == []
        assert paper.abstract == ""
        assert paper.server == "biorxiv"
        assert paper.category == ""

    def test_full_construction(self):
        paper = BiorxivPaper(
            doi="10.1101/test",
            title="Test Paper",
            authors=["A", "B"],
            abstract="Text",
            date="2023-01-01",
            server="medrxiv",
            category="neuroscience",
            url="https://www.medrxiv.org/content/10.1101/test",
        )
        assert paper.server == "medrxiv"


# --- Conversion helper tests ---


class TestBiorxivPaperToSourceResult:
    def test_converts_correctly(self):
        paper = BiorxivPaper(
            doi="10.1101/2023.01.15.123456",
            title="Test Paper",
            authors=["Alice", "Bob"],
            abstract="An abstract.",
            date="2023-01-15",
            server="biorxiv",
            category="astrophysics",
            url="https://www.biorxiv.org/content/10.1101/2023.01.15.123456",
        )
        result = biorxiv_paper_to_source_result(paper)
        assert result.id == "10.1101/2023.01.15.123456"
        assert result.source_type == "biorxiv"
        assert result.title == "Test Paper"
        assert result.date is not None
        assert result.date.year == 2023
        assert result.metadata["server"] == "biorxiv"

    def test_invalid_date(self):
        paper = BiorxivPaper(doi="1", title="No Date", date="not-a-date")
        result = biorxiv_paper_to_source_result(paper)
        assert result.date is None

    def test_empty_date(self):
        paper = BiorxivPaper(doi="1", title="Empty Date", date="")
        result = biorxiv_paper_to_source_result(paper)
        assert result.date is None


# --- BiorxivClient tests ---


class TestBiorxivClient:
    @pytest.mark.asyncio
    async def test_search_returns_filtered_papers(self):
        client = BiorxivClient(rate_limit=0.0)
        client._get_json = AsyncMock(return_value={"collection": [SAMPLE_ENTRY, SAMPLE_ENTRY_2]})

        papers = await client.search("stellar convection")
        # Only the first paper matches "stellar convection"
        assert len(papers) == 1
        assert papers[0].doi == "10.1101/2023.01.15.123456"
        await client.close()

    @pytest.mark.asyncio
    async def test_search_empty_collection(self):
        client = BiorxivClient(rate_limit=0.0)
        client._get_json = AsyncMock(return_value={"collection": []})

        papers = await client.search("test query")
        assert papers == []
        await client.close()

    @pytest.mark.asyncio
    async def test_search_handles_api_error(self):
        client = BiorxivClient(rate_limit=0.0)
        client._get_json = AsyncMock(return_value=None)

        papers = await client.search("test query")
        assert papers == []
        await client.close()

    @pytest.mark.asyncio
    async def test_get_paper_by_doi(self):
        client = BiorxivClient(rate_limit=0.0)
        client._get_json = AsyncMock(return_value={"collection": [SAMPLE_ENTRY]})

        paper = await client.get_paper("10.1101/2023.01.15.123456")
        assert paper is not None
        assert paper.doi == "10.1101/2023.01.15.123456"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_paper_not_found(self):
        client = BiorxivClient(rate_limit=0.0)
        client._get_json = AsyncMock(return_value={"collection": []})

        paper = await client.get_paper("nonexistent")
        assert paper is None
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with BiorxivClient(rate_limit=0.0) as client:
            assert client is not None
