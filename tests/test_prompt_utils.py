"""Tests for prompt preprocessing utilities."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from paradigm.domains.base import SourceResult
from paradigm.literature.prompt_utils import (
    extract_search_query,
    extract_urls,
    format_cited_by_results,
    format_follow_results,
    format_read_result,
    format_search_results,
    make_external_paper,
    parse_cited_by_requests,
    parse_follow_requests,
    parse_read_requests,
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


def _make_paper(arxiv_id: str = "2301.12345", title: str = "Test Paper") -> SourceResult:
    """Helper to create a minimal SourceResult for testing format functions."""
    now = datetime.now(UTC)
    return SourceResult(
        id=arxiv_id,
        source_type="arxiv",
        title=title,
        authors=["Alice", "Bob", "Charlie", "Diana"],
        summary="This is a test abstract that is long enough to exercise truncation.",
        url=f"http://arxiv.org/abs/{arxiv_id}",
        date=now,
        metadata={
            "categories": ["astro-ph.SR"],
            "primary_category": "astro-ph.SR",
            "pdf_url": f"http://arxiv.org/pdf/{arxiv_id}",
        },
    )


class TestParseSearchRequests:
    def test_no_markers(self):
        text = "Just a regular response about stellar evolution."
        assert parse_search_requests(text) == []

    def test_single_marker(self):
        text = "I suggest we search for [SEARCH: Cepheid period-luminosity relation]."
        result = parse_search_requests(text)
        assert result == [("Cepheid period-luminosity relation", None)]

    def test_multiple_markers(self):
        text = (
            "Let's look at [SEARCH: convective overshooting] and also "
            "[SEARCH: asteroseismology mixed modes]."
        )
        result = parse_search_requests(text)
        assert len(result) == 2
        queries = [q for q, _p in result]
        assert "convective overshooting" in queries
        assert "asteroseismology mixed modes" in queries

    def test_case_insensitive_prefix(self):
        text = "[search: lower case] and [Search: Mixed Case] and [SEARCH: UPPER CASE]"
        result = parse_search_requests(text)
        assert len(result) == 3

    def test_deduplication(self):
        text = "[SEARCH: Cepheids] and later [SEARCH: cepheids] again"
        result = parse_search_requests(text)
        assert len(result) == 1
        assert result[0][0] == "Cepheids"  # Preserves first occurrence's case

    def test_whitespace_stripped(self):
        text = "[SEARCH:   lots of space   ]"
        result = parse_search_requests(text)
        assert result == [("lots of space", None)]

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


# --- parse_follow_requests tests ---


def _make_s2_paper(
    arxiv_id: str = "2301.12345",
    title: str = "S2 Paper",
    year: int = 2023,
) -> SourceResult:
    """Helper to create a SourceResult (from Semantic Scholar) for testing."""
    return SourceResult(
        id=arxiv_id,
        source_type="semantic_scholar",
        title=title,
        authors=["Alice", "Bob", "Charlie", "Diana"],
        summary="A test abstract about stellar physics.",
        url="https://www.semanticscholar.org/paper/abc123",
        date=datetime(year, 1, 1, tzinfo=UTC),
        metadata={
            "paper_id": "abc123",
            "arxiv_id": arxiv_id,
            "year": year,
            "citation_count": 42,
        },
    )


class TestParseFollowRequests:
    def test_basic_extraction(self):
        text = "Let's follow [FOLLOW: 2301.12345] to see its references."
        result = parse_follow_requests(text)
        assert result == ["2301.12345"]

    def test_dedup(self):
        text = "[FOLLOW: 2301.12345] and again [FOLLOW: 2301.12345]"
        result = parse_follow_requests(text)
        assert len(result) == 1

    def test_strips_prefix(self):
        text = "[FOLLOW: arXiv:2301.12345v2]"
        result = parse_follow_requests(text)
        assert result == ["2301.12345"]

    def test_multiple(self):
        text = "[FOLLOW: 2301.00100] and [FOLLOW: 2301.00200]"
        result = parse_follow_requests(text)
        assert len(result) == 2

    def test_no_markers(self):
        text = "Just a regular response."
        assert parse_follow_requests(text) == []

    def test_rejects_urls(self):
        text = "[FOLLOW: https://www.aanda.org/articles/aa/pdf/2024/paper.pdf]"
        assert parse_follow_requests(text) == []

    def test_rejects_placeholder_text(self):
        text = "[FOLLOW: arxiv_id]"
        assert parse_follow_requests(text) == []

    def test_old_format_id(self):
        text = "[FOLLOW: astro-ph/0601001]"
        result = parse_follow_requests(text)
        assert result == ["astro-ph/0601001"]


class TestParseCitedByRequests:
    def test_basic_extraction(self):
        text = "[CITED_BY: 0901.67890]"
        result = parse_cited_by_requests(text)
        assert result == ["0901.67890"]

    def test_case_insensitive(self):
        text = "[cited_by: 2301.12345]"
        result = parse_cited_by_requests(text)
        assert result == ["2301.12345"]

    def test_rejects_urls(self):
        text = "[CITED_BY: https://www.nature.com/articles/s41550-023-02040-7]"
        assert parse_cited_by_requests(text) == []

    def test_rejects_garbage(self):
        text = "[CITED_BY: some random text]"
        assert parse_cited_by_requests(text) == []


class TestParseReadRequests:
    def test_basic_extraction(self):
        text = "[READ: 2301.12345]"
        result = parse_read_requests(text)
        assert result == ["2301.12345"]

    def test_strips_prefix(self):
        text = "[READ: arxiv:2301.12345v1]"
        result = parse_read_requests(text)
        assert result == ["2301.12345"]

    def test_rejects_urls(self):
        text = "[READ: https://www.aanda.org/articles/aa/pdf/2024/12/aa51419-24.pdf]"
        assert parse_read_requests(text) == []


# --- format tests ---


class TestFormatFollowResults:
    def test_with_papers(self):
        papers = [
            _make_s2_paper("2301.001", "Ref Paper One"),
            _make_s2_paper("2301.002", "Ref Paper Two"),
        ]
        result = format_follow_results("2301.12345", papers)
        assert "References of 2301.12345" in result
        assert "Ref Paper One" in result
        assert "Ref Paper Two" in result
        assert "et al." in result

    def test_empty_results(self):
        result = format_follow_results("2301.12345", [])
        assert "No references found" in result


class TestFormatCitedByResults:
    def test_with_papers(self):
        papers = [_make_s2_paper("2301.001", "Citing Paper")]
        result = format_cited_by_results("2301.12345", papers)
        assert "Papers citing 2301.12345" in result
        assert "Citing Paper" in result
        assert "42 citations" in result

    def test_empty_results(self):
        result = format_cited_by_results("2301.12345", [])
        assert "No citations found" in result


class TestFormatReadResult:
    def test_basic_format(self):
        result = format_read_result("2301.12345", "My Paper", "Abstract text here...")
        assert "Deep Read: My Paper" in result
        assert "2301.12345" in result
        assert "Abstract text here..." in result
