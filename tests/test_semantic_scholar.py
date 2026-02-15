"""Tests for Semantic Scholar API client."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from paradigm.literature.semantic_scholar import (
    SemanticPaper,
    SemanticScholarClient,
    _normalize_arxiv_id,
    _parse_paper,
)


# --- Helpers ---


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    return response


def _make_s2_paper_data(
    arxiv_id: str | None = "2301.12345",
    title: str = "Test Paper",
    year: int = 2023,
    citation_count: int = 10,
) -> dict:
    """Create a Semantic Scholar paper data dict."""
    return {
        "paperId": "abc123",
        "title": title,
        "authors": [{"name": "Alice"}, {"name": "Bob"}],
        "abstract": "A test abstract about stellar physics.",
        "externalIds": {"ArXiv": arxiv_id} if arxiv_id else {},
        "year": year,
        "citationCount": citation_count,
        "url": "https://www.semanticscholar.org/paper/abc123",
    }


# --- _normalize_arxiv_id tests ---


class TestNormalizeArxivId:
    def test_plain_id(self):
        assert _normalize_arxiv_id("2301.12345") == "2301.12345"

    def test_strips_arxiv_prefix(self):
        assert _normalize_arxiv_id("arXiv:2301.12345") == "2301.12345"

    def test_strips_arxiv_prefix_lowercase(self):
        assert _normalize_arxiv_id("arxiv:2301.12345") == "2301.12345"

    def test_strips_version_suffix(self):
        assert _normalize_arxiv_id("2301.12345v2") == "2301.12345"

    def test_strips_prefix_and_version(self):
        assert _normalize_arxiv_id("arXiv:2301.12345v1") == "2301.12345"

    def test_strips_whitespace(self):
        assert _normalize_arxiv_id("  2301.12345  ") == "2301.12345"


# --- _parse_paper tests ---


class TestParsePaper:
    def test_basic_parsing(self):
        data = _make_s2_paper_data()
        paper = _parse_paper(data)
        assert paper is not None
        assert paper.title == "Test Paper"
        assert paper.arxiv_id == "2301.12345"
        assert paper.year == 2023
        assert paper.citation_count == 10
        assert len(paper.authors) == 2

    def test_missing_title_returns_none(self):
        data = _make_s2_paper_data()
        data["title"] = None
        assert _parse_paper(data) is None

    def test_missing_arxiv_id(self):
        data = _make_s2_paper_data(arxiv_id=None)
        paper = _parse_paper(data)
        assert paper is not None
        assert paper.arxiv_id is None

    def test_empty_authors(self):
        data = _make_s2_paper_data()
        data["authors"] = []
        paper = _parse_paper(data)
        assert paper is not None
        assert paper.authors == []


# --- SemanticScholarClient tests ---


class TestSemanticScholarClient:
    @pytest.mark.asyncio
    async def test_get_references_returns_papers(self):
        """Mock httpx response, verify parsing."""
        client = SemanticScholarClient(rate_limit=0.0)
        response_data = {
            "data": [
                {"citedPaper": _make_s2_paper_data("2301.001", "Ref Paper 1")},
                {"citedPaper": _make_s2_paper_data("2301.002", "Ref Paper 2")},
            ]
        }
        client._get_json = AsyncMock(return_value=response_data)

        papers = await client.get_references("2301.12345")
        assert len(papers) == 2
        assert papers[0].title == "Ref Paper 1"
        assert papers[1].title == "Ref Paper 2"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_references_empty_on_404(self):
        """Returns [] on 404."""
        client = SemanticScholarClient(rate_limit=0.0)
        client._get_json = AsyncMock(return_value=None)

        papers = await client.get_references("9999.99999")
        assert papers == []
        await client.close()

    @pytest.mark.asyncio
    async def test_get_citations_filters_to_arxiv_only(self):
        """Only papers with arXiv IDs are returned."""
        client = SemanticScholarClient(rate_limit=0.0)
        response_data = {
            "data": [
                {"citingPaper": _make_s2_paper_data("2301.001", "With ArXiv", 2023)},
                {"citingPaper": _make_s2_paper_data(None, "Without ArXiv", 2023)},
                {"citingPaper": _make_s2_paper_data("2301.003", "Also ArXiv", 2023)},
            ]
        }
        client._get_json = AsyncMock(return_value=response_data)

        papers = await client.get_citations("2301.12345")
        assert len(papers) == 2
        assert all(p.arxiv_id is not None for p in papers)
        await client.close()

    @pytest.mark.asyncio
    async def test_get_citations_sorted_by_year(self):
        """Most recent first."""
        client = SemanticScholarClient(rate_limit=0.0)
        response_data = {
            "data": [
                {"citingPaper": _make_s2_paper_data("2301.001", "Old", 2019)},
                {"citingPaper": _make_s2_paper_data("2301.002", "New", 2024)},
                {"citingPaper": _make_s2_paper_data("2301.003", "Mid", 2021)},
            ]
        }
        client._get_json = AsyncMock(return_value=response_data)

        papers = await client.get_citations("2301.12345")
        years = [p.year for p in papers]
        assert years == [2024, 2021, 2019]
        await client.close()

    @pytest.mark.asyncio
    async def test_api_key_header_sent(self):
        """x-api-key header when key is set."""
        client = SemanticScholarClient(api_key="test-key-123", rate_limit=0.0)
        assert client._client.headers.get("x-api-key") == "test-key-123"
        await client.close()

    @pytest.mark.asyncio
    async def test_api_key_header_absent(self):
        """No x-api-key header when key is None."""
        client = SemanticScholarClient(api_key=None, rate_limit=0.0)
        assert "x-api-key" not in client._client.headers
        await client.close()

    @pytest.mark.asyncio
    async def test_search_by_title(self):
        """Paper search endpoint."""
        client = SemanticScholarClient(rate_limit=0.0)
        response_data = {
            "data": [
                _make_s2_paper_data("2301.001", "Found Paper"),
            ]
        }
        client._get_json = AsyncMock(return_value=response_data)

        papers = await client.search("stellar convection")
        assert len(papers) == 1
        assert papers[0].title == "Found Paper"
        await client.close()

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """_get_json respects rate limit between requests."""
        client = SemanticScholarClient(rate_limit=0.2)  # 200ms

        # Mock the underlying httpx client
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        client._client.get = AsyncMock(return_value=mock_response)

        # First request sets the baseline
        await client._get_json("https://example.com/api", {})

        # Second request should wait for rate limit
        start = time.monotonic()
        await client._get_json("https://example.com/api", {})
        elapsed = time.monotonic() - start

        # Should have waited at least ~200ms
        assert elapsed >= 0.15
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Async context manager closes client."""
        async with SemanticScholarClient(rate_limit=0.0) as client:
            assert client is not None
        # After context exit, client should be closed
