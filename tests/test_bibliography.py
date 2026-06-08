"""Tests for the bibliography builder module."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from paradigm.literature.bibliography import (
    BibliographyBuilder,
    Reference,
    extract_arxiv_id_from_url,
)

# ---------------------------------------------------------------------------
# extract_arxiv_id_from_url
# ---------------------------------------------------------------------------


class TestExtractArxivId:
    def test_abs_url(self):
        assert extract_arxiv_id_from_url("https://arxiv.org/abs/2301.12345") == "2301.12345"

    def test_pdf_url(self):
        assert extract_arxiv_id_from_url("https://arxiv.org/pdf/2301.12345") == "2301.12345"

    def test_html_url(self):
        assert extract_arxiv_id_from_url("https://arxiv.org/html/2301.12345") == "2301.12345"

    def test_versioned_url(self):
        assert extract_arxiv_id_from_url("https://arxiv.org/abs/2301.12345v2") == "2301.12345"

    def test_five_digit_id(self):
        assert extract_arxiv_id_from_url("https://arxiv.org/abs/2301.00001") == "2301.00001"

    def test_old_style_id(self):
        assert (
            extract_arxiv_id_from_url("https://arxiv.org/abs/astro-ph/0601234")
            == "astro-ph/0601234"
        )

    def test_no_match(self):
        assert extract_arxiv_id_from_url("https://example.com/paper") == ""

    def test_empty_url(self):
        assert extract_arxiv_id_from_url("") == ""


# ---------------------------------------------------------------------------
# BibliographyBuilder.format_bibliography_markdown
# ---------------------------------------------------------------------------


class TestFormatBibliography:
    def test_basic_format(self):
        refs = [
            Reference(
                index=1,
                url="https://arxiv.org/abs/2301.12345",
                arxiv_id="2301.12345",
                title="A Paper on Stars",
                authors="Smith, A., Jones, B.",
                year="2023",
            ),
            Reference(
                index=2,
                url="https://arxiv.org/abs/2205.00001",
                arxiv_id="2205.00001",
                title="Another Paper",
                authors="Chen, C. et al.",
                year="2022",
            ),
        ]
        result = BibliographyBuilder.format_bibliography_markdown(refs)
        assert result.startswith("## References")
        assert "[1]" in result
        assert "[2]" in result
        assert "A Paper on Stars" in result
        assert "arXiv:2301.12345" in result
        assert "Smith, A." in result
        assert "(2023)" in result

    def test_url_only_fallback(self):
        refs = [
            Reference(
                index=1,
                url="https://arxiv.org/abs/2301.12345",
            ),
        ]
        result = BibliographyBuilder.format_bibliography_markdown(refs)
        assert "[1] https://arxiv.org/abs/2301.12345" in result

    def test_empty_references(self):
        result = BibliographyBuilder.format_bibliography_markdown([])
        assert result == ""


# ---------------------------------------------------------------------------
# BibliographyBuilder.renumber_citations
# ---------------------------------------------------------------------------


class TestRenumberCitations:
    def test_single_section(self):
        texts = ["Text with [1] and [2] markers."]
        urls = [["https://arxiv.org/abs/2301.11111", "https://arxiv.org/abs/2301.22222"]]

        combined, global_urls = BibliographyBuilder.renumber_citations(texts, urls)
        assert "[1]" in combined
        assert "[2]" in combined
        assert len(global_urls) == 2

    def test_multi_section_renumbering(self):
        """Two sections with independent local numbering get globally renumbered."""
        texts = [
            "Intro text [1] and [2].",
            "Methods text [1] and [2].",
        ]
        urls = [
            ["https://arxiv.org/abs/A", "https://arxiv.org/abs/B"],
            ["https://arxiv.org/abs/C", "https://arxiv.org/abs/D"],
        ]

        combined, global_urls = BibliographyBuilder.renumber_citations(texts, urls)

        # First section keeps [1], [2]
        # Second section gets [3], [4]
        assert "[3]" in combined
        assert "[4]" in combined
        assert len(global_urls) == 4

    def test_deduplication(self):
        """Same URL in two sections should get the same global number."""
        shared_url = "https://arxiv.org/abs/SAME"
        texts = [
            "Intro text [1].",
            "Methods text [1].",
        ]
        urls = [
            [shared_url],
            [shared_url],
        ]

        combined, global_urls = BibliographyBuilder.renumber_citations(texts, urls)
        assert len(global_urls) == 1
        # Both sections should reference [1]
        assert combined.count("[1]") == 2


# ---------------------------------------------------------------------------
# BibliographyBuilder.build_references (mocked)
# ---------------------------------------------------------------------------


class TestBuildReferences:
    @pytest.mark.asyncio
    async def test_builds_references_from_urls(self):
        """References are built with URL-only data when no clients available."""
        builder = BibliographyBuilder()
        urls = [
            "https://arxiv.org/abs/2301.12345",
            "https://arxiv.org/abs/2205.00001",
        ]
        refs = await builder.build_references(urls)
        assert len(refs) == 2
        assert refs[0].index == 1
        assert refs[0].arxiv_id == "2301.12345"
        assert refs[1].index == 2
        assert refs[1].arxiv_id == "2205.00001"

    @pytest.mark.asyncio
    async def test_deduplicates_urls(self):
        """Duplicate URLs produce only one reference."""
        builder = BibliographyBuilder()
        urls = [
            "https://arxiv.org/abs/2301.12345",
            "https://arxiv.org/abs/2301.12345",
            "https://arxiv.org/abs/2205.00001",
        ]
        refs = await builder.build_references(urls)
        assert len(refs) == 2

    @pytest.mark.asyncio
    async def test_non_arxiv_url(self):
        """Non-arXiv URLs produce a reference with empty arxiv_id."""
        builder = BibliographyBuilder()
        refs = await builder.build_references(["https://example.com/paper"])
        assert len(refs) == 1
        assert refs[0].arxiv_id == ""
        assert refs[0].url == "https://example.com/paper"


# ---------------------------------------------------------------------------
# Metadata resolution: retry/backoff + bounded-concurrent (C2)
# ---------------------------------------------------------------------------


@dataclass
class _FakePaper:
    title: str
    authors: list
    year: int = 2020
    published: str = "2020-01-01"


class _SeqS2:
    """S2 fake returning a scripted sequence (Exception or list[_FakePaper]) per call."""

    def __init__(self, behaviors):
        self._behaviors = behaviors
        self.calls = 0

    async def search(self, query, limit=1):
        b = self._behaviors[min(self.calls, len(self._behaviors) - 1)]
        self.calls += 1
        if isinstance(b, Exception):
            raise b
        return b


class _MapS2:
    """S2 fake mapping ``arXiv:<id>`` queries to a paper (for order tests)."""

    def __init__(self, mapping):
        self._mapping = mapping
        self.calls = 0

    async def search(self, query, limit=1):
        self.calls += 1
        aid = query.split(":", 1)[1]
        p = self._mapping.get(aid)
        return [p] if p else []


@pytest.mark.asyncio
class TestMetadataResolution:
    async def test_retries_transient_then_resolves(self):
        s2 = _SeqS2(
            [RuntimeError("429 Too Many Requests"), [_FakePaper("A Title", ["Smith"], 2021)]]
        )
        builder = BibliographyBuilder(s2_client=s2)
        with patch("paradigm.literature.bibliography.asyncio.sleep", new=AsyncMock()):
            refs = await builder.build_references(["https://arxiv.org/abs/2301.12345"])
        assert refs[0].title == "A Title"
        assert refs[0].year == "2021"
        assert s2.calls == 2  # retried the transient 429 once

    async def test_non_transient_does_not_retry(self):
        s2 = _SeqS2([ValueError("malformed json")])
        builder = BibliographyBuilder(s2_client=s2)
        with patch("paradigm.literature.bibliography.asyncio.sleep", new=AsyncMock()):
            refs = await builder.build_references(["https://arxiv.org/abs/2301.12345"])
        assert s2.calls == 1  # a non-transient error is not retried
        assert refs[0].title == ""  # stays URL-only

    async def test_gives_up_after_max_attempts(self):
        s2 = _SeqS2([RuntimeError("503 unavailable")])  # always transient-fails
        builder = BibliographyBuilder(s2_client=s2)
        with patch("paradigm.literature.bibliography.asyncio.sleep", new=AsyncMock()):
            refs = await builder.build_references(["https://arxiv.org/abs/2301.12345"])
        assert s2.calls == 3  # _METADATA_ATTEMPTS
        assert refs[0].title == ""

    async def test_concurrent_resolution_preserves_order(self):
        mapping = {
            "2301.00001": _FakePaper("First", ["A"], 2001),
            "2301.00002": _FakePaper("Second", ["B"], 2002),
            "2301.00003": _FakePaper("Third", ["C"], 2003),
        }
        s2 = _MapS2(mapping)
        builder = BibliographyBuilder(s2_client=s2)
        urls = [f"https://arxiv.org/abs/{aid}" for aid in mapping]
        refs = await builder.build_references(urls)
        assert [r.title for r in refs] == ["First", "Second", "Third"]
        assert [r.index for r in refs] == [1, 2, 3]
