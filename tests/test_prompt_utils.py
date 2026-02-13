"""Tests for prompt preprocessing utilities."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from paradigm.literature.arxiv import ArxivPaper
from paradigm.literature.prompt_utils import (
    extract_search_query,
    extract_urls,
    format_search_results,
    make_external_paper,
    parse_search_requests,
)

# --- extract_urls tests ---


class TestExtractUrls:
    def test_no_urls(self):
        assert extract_urls("Just a plain text prompt about stars") == []

    def test_single_url(self):
        text = "See https://example.com/paper.pdf for details"
        assert extract_urls(text) == ["https://example.com/paper.pdf"]

    def test_multiple_urls(self):
        text = (
            "Check https://arxiv.org/abs/2301.12345 and "
            "https://www.aanda.org/articles/aa/pdf/2024/paper.pdf"
        )
        result = extract_urls(text)
        assert len(result) == 2
        assert "https://arxiv.org/abs/2301.12345" in result
        assert "https://www.aanda.org/articles/aa/pdf/2024/paper.pdf" in result

    def test_trailing_punctuation_stripped(self):
        text = "See https://example.com/paper.pdf."
        assert extract_urls(text) == ["https://example.com/paper.pdf"]

        text2 = "URL: https://example.com/paper.pdf, and more"
        assert extract_urls(text2) == ["https://example.com/paper.pdf"]

    def test_deduplication(self):
        text = "https://example.com/a.pdf and again https://example.com/a.pdf"
        assert extract_urls(text) == ["https://example.com/a.pdf"]

    def test_preserves_order(self):
        text = "https://b.com/2.pdf https://a.com/1.pdf"
        result = extract_urls(text)
        assert result == ["https://b.com/2.pdf", "https://a.com/1.pdf"]

    def test_http_and_https(self):
        text = "http://example.com/a.pdf and https://example.com/b.pdf"
        result = extract_urls(text)
        assert len(result) == 2

    def test_url_with_query_params(self):
        text = "See https://example.com/search?q=test&page=1 for results"
        result = extract_urls(text)
        assert result == ["https://example.com/search?q=test&page=1"]


# --- extract_search_query tests ---


class TestExtractSearchQuery:
    def test_short_prompt_unchanged(self):
        text = "Cepheid period-luminosity relation"
        assert extract_search_query(text) == text

    def test_strips_urls(self):
        text = "Study the paper at https://example.com/paper.pdf about Cepheids"
        result = extract_search_query(text)
        assert result is not None
        assert "https://" not in result
        assert "Cepheids" in result

    def test_strips_markdown(self):
        text = "# Research Topic\n\n**Bold** and *italic* and > quoted"
        result = extract_search_query(text)
        assert result is not None
        assert "#" not in result
        assert "*" not in result
        assert ">" not in result
        assert "Research Topic" in result

    def test_returns_none_for_url_only(self):
        text = "https://example.com/paper1.pdf https://example.com/paper2.pdf"
        assert extract_search_query(text) is None

    def test_truncates_long_prompt_at_sentence(self):
        # Build a long prompt with clear sentence boundaries
        sentences = [
            "This is about stellar variability. ",
            "Cepheids are important distance indicators. ",
            "They follow a period-luminosity relation. ",
        ]
        # Repeat enough to exceed 300 chars
        text = (sentences[0] + sentences[1] + sentences[2]) * 5
        assert len(text) > 300

        result = extract_search_query(text)
        assert result is not None
        assert len(result) <= 300
        # Should end at a sentence boundary
        assert result.rstrip().endswith(".")

    def test_truncates_at_word_boundary_no_sentence(self):
        # One long "sentence" with no periods
        text = "word " * 100  # 500 chars
        result = extract_search_query(text)
        assert result is not None
        assert len(result) <= 300
        # Should not break mid-word
        assert not result.endswith(" wor")

    def test_empty_string(self):
        assert extract_search_query("") is None

    def test_whitespace_only(self):
        assert extract_search_query("   \n\t  ") is None


# --- make_external_paper tests ---


class TestMakeExternalPaper:
    def test_synthetic_id_format(self):
        paper = make_external_paper("https://example.com/paper.pdf", "Title\nBody text")
        assert paper.arxiv_id.startswith("ext-")
        assert len(paper.arxiv_id) == 16  # "ext-" + 12 hex chars

    def test_deterministic_id(self):
        url = "https://example.com/paper.pdf"
        p1 = make_external_paper(url, "Title\nBody")
        p2 = make_external_paper(url, "Different content")
        assert p1.arxiv_id == p2.arxiv_id

    def test_id_matches_sha256(self):
        url = "https://example.com/paper.pdf"
        expected_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
        paper = make_external_paper(url, "Title\nBody")
        assert paper.arxiv_id == f"ext-{expected_hash}"

    def test_title_from_first_line(self):
        paper = make_external_paper("https://example.com/a.pdf", "My Paper Title\nAbstract here")
        assert paper.title == "My Paper Title"

    def test_abstract_from_remaining_text(self):
        paper = make_external_paper("https://example.com/a.pdf", "Title\nThis is the abstract")
        assert paper.abstract == "This is the abstract"

    def test_body_set(self):
        pdf_text = "Title\nBody line 1\nBody line 2"
        paper = make_external_paper("https://example.com/a.pdf", pdf_text)
        assert paper.body == pdf_text

    def test_pdf_url_preserved(self):
        url = "https://example.com/paper.pdf"
        paper = make_external_paper(url, "Title\nBody")
        assert paper.pdf_url == url

    def test_empty_pdf_text(self):
        paper = make_external_paper("https://example.com/a.pdf", "")
        assert paper.title == "External Paper"
        assert paper.abstract == ""


# --- parse_search_requests tests ---


def _make_paper(arxiv_id: str = "2301.12345", title: str = "Test Paper") -> ArxivPaper:
    """Helper to create a minimal ArxivPaper for testing."""
    now = datetime.now(UTC)
    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=title,
        abstract="This is a test abstract that is long enough to exercise truncation.",
        authors=["Alice", "Bob", "Charlie", "Diana"],
        categories=["astro-ph.SR"],
        primary_category="astro-ph.SR",
        published=now,
        updated=now,
        pdf_url=f"http://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"http://arxiv.org/abs/{arxiv_id}",
    )


class TestParseSearchRequests:
    def test_no_markers(self):
        text = "Just a regular response about stellar evolution."
        assert parse_search_requests(text) == []

    def test_single_marker(self):
        text = "I suggest we search for [SEARCH: Cepheid period-luminosity relation]."
        result = parse_search_requests(text)
        assert result == ["Cepheid period-luminosity relation"]

    def test_multiple_markers(self):
        text = (
            "Let's look at [SEARCH: convective overshooting] and also "
            "[SEARCH: asteroseismology mixed modes]."
        )
        result = parse_search_requests(text)
        assert len(result) == 2
        assert "convective overshooting" in result
        assert "asteroseismology mixed modes" in result

    def test_case_insensitive_prefix(self):
        text = "[search: lower case] and [Search: Mixed Case] and [SEARCH: UPPER CASE]"
        result = parse_search_requests(text)
        assert len(result) == 3

    def test_deduplication(self):
        text = "[SEARCH: Cepheids] and later [SEARCH: cepheids] again"
        result = parse_search_requests(text)
        assert len(result) == 1
        assert result[0] == "Cepheids"  # Preserves first occurrence's case

    def test_whitespace_stripped(self):
        text = "[SEARCH:   lots of space   ]"
        result = parse_search_requests(text)
        assert result == ["lots of space"]

    def test_empty_query_ignored(self):
        text = "[SEARCH: ] and [SEARCH:   ]"
        assert parse_search_requests(text) == []

    def test_multiline(self):
        text = "First line\n[SEARCH: query one]\nSecond line\n[SEARCH: query two]\n"
        result = parse_search_requests(text)
        assert len(result) == 2


# --- format_search_results tests ---


class TestFormatSearchResults:
    def test_empty_results(self):
        result = format_search_results("test query", [])
        assert "test query" in result
        assert "No results found" in result

    def test_with_papers(self):
        papers = [
            _make_paper("2301.00001", "Paper One"),
            _make_paper("2301.00002", "Paper Two"),
        ]
        result = format_search_results("stellar evolution", papers)
        assert "stellar evolution" in result
        assert "Paper One" in result
        assert "Paper Two" in result
        assert "2301.00001" in result
        assert "et al." in result  # 4 authors, so et al. should appear

    def test_max_papers_respected(self):
        papers = [_make_paper(f"2301.{i:05d}", f"Paper {i}") for i in range(10)]
        result = format_search_results("query", papers, max_papers=3)
        assert "Paper 0" in result
        assert "Paper 2" in result
        assert "Paper 3" not in result
