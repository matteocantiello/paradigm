"""Tests for arXiv API client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from paradigm.literature.arxiv import ArxivClient, ArxivPaper

# Sample arXiv Atom feed response for testing
SAMPLE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>ArXiv Query: all:stellar pulsation</title>
  <id>http://arxiv.org/api/query</id>
  <updated>2026-01-15T00:00:00-05:00</updated>
  <opensearch:totalResults>42</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>2</opensearch:itemsPerPage>

  <entry>
    <id>http://arxiv.org/abs/2301.12345v2</id>
    <title>Stellar Pulsation Models for Cepheid Variables</title>
    <summary>We present new models of stellar pulsation in classical Cepheid variables,
    incorporating updated opacity tables and mass-loss prescriptions. Our results
    show improved agreement with observed period-luminosity relations.</summary>
    <published>2023-01-30T12:00:00Z</published>
    <updated>2023-06-15T12:00:00Z</updated>
    <author><name>Jane Smith</name></author>
    <author><name>John Doe</name></author>
    <author><name>Alice Johnson</name></author>
    <category term="astro-ph.SR" scheme="http://arxiv.org/schemas/atom"/>
    <category term="astro-ph.GA" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2301.12345v2" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/2301.12345v2" title="pdf" rel="related" type="application/pdf"/>
    <arxiv:primary_category term="astro-ph.SR"/>
    <arxiv:doi>10.1234/test.2023.001</arxiv:doi>
    <arxiv:comment>15 pages, 8 figures, accepted by ApJ</arxiv:comment>
    <arxiv:journal_ref>ApJ 950 123 (2023)</arxiv:journal_ref>
  </entry>

  <entry>
    <id>http://arxiv.org/abs/2302.67890v1</id>
    <title>Non-radial Oscillations in Red Giant Stars</title>
    <summary>We analyze Kepler data to characterize non-radial oscillation modes
    in a sample of 500 red giant stars. Mixed modes provide constraints on
    core rotation rates and evolutionary state.</summary>
    <published>2023-02-15T12:00:00Z</published>
    <updated>2023-02-15T12:00:00Z</updated>
    <author><name>Bob Williams</name></author>
    <author><name>Carol Davis</name></author>
    <category term="astro-ph.SR" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2302.67890v1" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/2302.67890v1" title="pdf" rel="related" type="application/pdf"/>
    <arxiv:primary_category term="astro-ph.SR"/>
  </entry>
</feed>"""

EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>ArXiv Query</title>
  <id>http://arxiv.org/api/query</id>
  <updated>2026-01-15T00:00:00-05:00</updated>
  <opensearch:totalResults>0</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>0</opensearch:itemsPerPage>
</feed>"""


def _mock_response(text: str, status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        text=text,
        request=httpx.Request("GET", "http://test.com"),
    )


@pytest.fixture
def client():
    """Create an ArxivClient with no rate limiting for tests."""
    return ArxivClient(rate_limit=0.0)


async def test_search_returns_structured_results(client):
    """Test that search parses arXiv XML into ArxivPaper objects."""
    with patch.object(client, "_rate_limited_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(SAMPLE_ATOM_FEED)

        papers = await client.search("stellar pulsation")

        assert len(papers) == 2
        assert all(isinstance(p, ArxivPaper) for p in papers)

        # Check first paper
        p = papers[0]
        assert p.arxiv_id == "2301.12345"
        assert p.title == "Stellar Pulsation Models for Cepheid Variables"
        assert len(p.authors) == 3
        assert p.authors[0] == "Jane Smith"
        assert p.primary_category == "astro-ph.SR"
        assert "astro-ph.GA" in p.categories
        assert p.doi == "10.1234/test.2023.001"
        assert p.journal_ref == "ApJ 950 123 (2023)"
        assert p.comment == "15 pages, 8 figures, accepted by ApJ"
        assert "2301.12345" in p.pdf_url

        # Check second paper
        p2 = papers[1]
        assert p2.arxiv_id == "2302.67890"
        assert len(p2.authors) == 2
        assert p2.doi is None
        assert p2.journal_ref is None


async def test_search_empty_results(client):
    """Test graceful handling of zero results."""
    with patch.object(client, "_rate_limited_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(EMPTY_FEED)

        papers = await client.search("nonexistent_topic_xyz")
        assert papers == []


async def test_get_paper_by_id(client):
    """Test fetching a single paper by ID."""
    with patch.object(client, "_rate_limited_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(SAMPLE_ATOM_FEED)

        paper = await client.get_paper("2301.12345")
        assert paper is not None
        assert paper.arxiv_id == "2301.12345"


async def test_get_paper_not_found(client):
    """Test that get_paper returns None for empty results."""
    with patch.object(client, "_rate_limited_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(EMPTY_FEED)

        paper = await client.get_paper("0000.00000")
        assert paper is None


async def test_build_query_simple(client):
    """Test basic query building."""
    query = client._build_query("stellar pulsation")
    assert query == "all:stellar pulsation"


async def test_build_query_with_categories(client):
    """Test query building with category filters."""
    query = client._build_query("pulsation", categories=["astro-ph.SR", "astro-ph.HE"])
    assert "all:pulsation" in query
    assert "cat:astro-ph.SR" in query
    assert "cat:astro-ph.HE" in query


async def test_parse_feed_extracts_metadata(client):
    """Test that feed-level metadata is extracted correctly."""
    result = client._parse_feed(SAMPLE_ATOM_FEED)
    assert result.total_results == 42
    assert result.start_index == 0
    assert result.items_per_page == 2
    assert len(result.papers) == 2


async def test_parse_entry_strips_version(client):
    """Test that version suffixes are stripped from arXiv IDs."""
    result = client._parse_feed(SAMPLE_ATOM_FEED)
    # First paper has v2 in its ID, should be stripped
    assert result.papers[0].arxiv_id == "2301.12345"
    # Second paper has v1
    assert result.papers[1].arxiv_id == "2302.67890"


async def test_search_with_sort_params(client):
    """Test that sort parameters are passed to the API."""
    with patch.object(client, "_rate_limited_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(EMPTY_FEED)

        await client.search(
            "test",
            sort_by="submittedDate",
            sort_order="ascending",
            max_results=5,
        )

        call_args = mock_get.call_args
        params = call_args[1].get("params") or call_args[0][1]
        assert params["sortBy"] == "submittedDate"
        assert params["sortOrder"] == "ascending"
        assert params["max_results"] == 5


async def test_context_manager(client):
    """Test async context manager protocol."""
    async with ArxivClient(rate_limit=0.0) as c:
        assert c is not None
    # Should not raise after close


async def test_abstract_whitespace_normalization(client):
    """Test that multi-line abstracts are normalized."""
    result = client._parse_feed(SAMPLE_ATOM_FEED)
    # Abstract should have normalized whitespace (no newlines or extra spaces)
    abstract = result.papers[0].abstract
    assert "\n" not in abstract
    assert "  " not in abstract
    assert "stellar pulsation" in abstract.lower()
