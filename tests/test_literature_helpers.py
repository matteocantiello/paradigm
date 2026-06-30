"""Tests for the LiteratureHandler._append_to_context helper and search dedup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from paradigm.literature.prompt_utils import parse_data_requests
from paradigm.orchestrator.constants import (
    _LITERATURE_CONTEXT_LIMIT,
    _PER_AGENT_CAP_MIN,
    _STOP_WORDS,
    _filter_relevant_papers,
    _is_duplicate_query,
    _normalize_query_keywords,
)
from paradigm.orchestrator.literature import LiteratureHandler, _oa_url


def _make_handler() -> LiteratureHandler:
    """Create a LiteratureHandler with a mocked engine."""
    engine = MagicMock()
    return LiteratureHandler(engine)


class TestAppendToEmptyContext:
    def test_from_empty(self):
        handler = _make_handler()
        handler.literature_context = ""
        handler._append_to_context("new content")
        assert handler.literature_context == "new content"


class TestAppendToExistingContext:
    def test_appends_with_newline(self):
        handler = _make_handler()
        handler.literature_context = "existing"
        handler._append_to_context("new")
        assert handler.literature_context == "existing\nnew"


class TestAppendWithTrim:
    def test_trims_at_limit(self):
        handler = _make_handler()
        # Start with a context that is just under the limit
        handler.literature_context = "x" * (_LITERATURE_CONTEXT_LIMIT - 10)
        # Append enough to exceed the limit
        handler._append_to_context("y" * 100)
        assert len(handler.literature_context) == _LITERATURE_CONTEXT_LIMIT
        # Should keep the most recent content (end of string)
        assert handler.literature_context.endswith("y" * 100)


class TestAppendWithoutTrim:
    def test_no_trim(self):
        handler = _make_handler()
        handler.literature_context = "x" * _LITERATURE_CONTEXT_LIMIT
        handler._append_to_context("y" * 100, trim=False)
        # Should exceed the limit because trim=False
        assert len(handler.literature_context) > _LITERATURE_CONTEXT_LIMIT
        assert handler.literature_context.endswith("y" * 100)


# ---------------------------------------------------------------------------
# Search deduplication tests
# ---------------------------------------------------------------------------


class TestStopWordsIncludeScientificFiller:
    """Expanded stop words should remove common scientific filler."""

    def test_scientific_filler_in_stop_words(self):
        scientific_filler = {
            "analysis",
            "based",
            "between",
            "can",
            "during",
            "effect",
            "evidence",
            "evolution",
            "model",
            "new",
            "observation",
            "observed",
            "properties",
            "recent",
            "relation",
            "role",
            "study",
            "using",
            "through",
            "which",
        }
        assert scientific_filler.issubset(_STOP_WORDS)

    def test_filler_stripped_from_query(self):
        kw = _normalize_query_keywords("study of stellar pulsation properties")
        assert "study" not in kw
        assert "properties" not in kw
        assert "stellar" in kw
        assert "pulsation" in kw


class TestJaccardThresholdCatchesRewordedQueries:
    """0.5 threshold should catch reworded queries that 0.7 would miss."""

    def test_reworded_queries_detected_at_half(self):
        # A pair that SHOULD be caught at 0.5:
        q5 = _normalize_query_keywords("red giant oscillation asteroseismology")
        q6 = _normalize_query_keywords("red giant asteroseismology oscillation modes")
        # Overlap: {red, giant, oscillation, asteroseismology} = 4
        # Union: {red, giant, oscillation, asteroseismology, modes} = 5
        # Jaccard = 4/5 = 0.80 — caught at both thresholds
        assert _is_duplicate_query(q6, [q5])

    def test_filler_removal_boosts_overlap(self):
        """Queries that differ only in scientific filler should match."""
        q1 = _normalize_query_keywords("study of stellar pulsation properties")
        q2 = _normalize_query_keywords("analysis of stellar pulsation observations")
        # After filler removal: q1 = {stellar, pulsation}, q2 = {stellar, pulsation}
        # Jaccard = 1.0 — definitely a duplicate
        assert _is_duplicate_query(q2, [q1])

    def test_distinct_queries_not_flagged(self):
        q1 = _normalize_query_keywords("white dwarf cooling sequence")
        q2 = _normalize_query_keywords("neutron star equation of state")
        assert not _is_duplicate_query(q2, [q1])


class TestPerAgentCapMin:
    """Per-agent keyword cap should be 1 to force graph traversal."""

    def test_cap_is_one(self):
        assert _PER_AGENT_CAP_MIN == 1


# ---------------------------------------------------------------------------
# Data request parsing tests
# ---------------------------------------------------------------------------


class TestParseDataRequests:
    """Tests for parse_data_requests() extraction."""

    def test_basic_extraction(self):
        text = "We need this dataset: [DATA: https://example.com/catalog.csv]"
        urls = parse_data_requests(text)
        assert urls == ["https://example.com/catalog.csv"]

    def test_multiple_urls(self):
        text = "[DATA: https://example.com/a.csv] and also [DATA: https://example.com/b.fits]"
        urls = parse_data_requests(text)
        assert len(urls) == 2
        assert "https://example.com/a.csv" in urls
        assert "https://example.com/b.fits" in urls

    def test_dedup_identical_urls(self):
        text = (
            "[DATA: https://example.com/catalog.csv] and again "
            "[DATA: https://example.com/catalog.csv]"
        )
        urls = parse_data_requests(text)
        assert len(urls) == 1

    def test_dedup_case_insensitive(self):
        text = "[DATA: https://Example.COM/Data.csv] and [DATA: https://example.com/data.csv]"
        urls = parse_data_requests(text)
        assert len(urls) == 1

    def test_rejects_non_url_strings(self):
        text = "[DATA: not a url] [DATA: ftp://example.com/file.dat]"
        urls = parse_data_requests(text)
        assert urls == []

    def test_accepts_http_and_https(self):
        text = "[DATA: http://example.com/a.csv] [DATA: https://example.com/b.csv]"
        urls = parse_data_requests(text)
        assert len(urls) == 2

    def test_empty_text(self):
        assert parse_data_requests("") == []

    def test_no_data_markers(self):
        assert parse_data_requests("No data requests here [SEARCH: query]") == []

    def test_case_insensitive_marker(self):
        text = "[data: https://example.com/file.csv]"
        urls = parse_data_requests(text)
        assert len(urls) == 1


# ---------------------------------------------------------------------------
# Relevance filtering tests (Fix 4)
# ---------------------------------------------------------------------------


def _make_paper(title: str, summary: str = "") -> MagicMock:
    """Create a mock paper with title and optional summary."""
    paper = MagicMock()
    paper.title = title
    paper.summary = summary
    return paper


class TestFilterRelevantPapers:
    def test_removes_irrelevant_papers(self):
        """Papers with zero keyword overlap should be removed."""
        papers = [
            _make_paper("Stellar pulsation oscillation modes"),
            _make_paper("Deep learning for image classification"),
        ]
        result = _filter_relevant_papers("stellar pulsation", papers)
        assert len(result) == 1
        assert result[0].title == "Stellar pulsation oscillation modes"

    def test_keeps_relevant_papers(self):
        """Papers with keyword overlap should be kept."""
        papers = [
            _make_paper("Asteroseismology of red giant stars"),
            _make_paper("Red giant oscillation modes and asteroseismology"),
        ]
        result = _filter_relevant_papers("red giant asteroseismology", papers)
        assert len(result) == 2

    def test_threshold_zero_passes_all(self):
        """threshold=0 should keep everything."""
        papers = [
            _make_paper("Completely unrelated topic"),
            _make_paper("Another unrelated thing"),
        ]
        result = _filter_relevant_papers("stellar pulsation", papers, threshold=0)
        assert len(result) == 2

    def test_empty_papers_returns_empty(self):
        result = _filter_relevant_papers("stellar pulsation", [])
        assert result == []

    def test_empty_query_returns_all(self):
        """If query has no keywords after stop word removal, return all."""
        papers = [_make_paper("Some paper")]
        # All words are stop words
        result = _filter_relevant_papers("the and or of", papers)
        assert len(result) == 1

    def test_uses_summary_for_matching(self):
        """Summary text should contribute to matching."""
        papers = [
            _make_paper("A study of X", summary="Stellar pulsation analysis of variable stars"),
        ]
        result = _filter_relevant_papers("stellar pulsation variable", papers)
        assert len(result) == 1


class TestOpenAccessFullText:
    """Non-arXiv full-text reads via an open-access PDF (backlog #3)."""

    def test_oa_url_from_metadata(self):
        assert _oa_url(SimpleNamespace(metadata={"oa_pdf_url": "http://x.pdf"})) == "http://x.pdf"

    def test_oa_url_from_attr(self):
        assert _oa_url(SimpleNamespace(oa_pdf_url="http://y.pdf", metadata={})) == "http://y.pdf"

    def test_oa_url_none(self):
        assert _oa_url(SimpleNamespace(metadata={})) == ""

    def test_track_paper_caches_oa_url(self):
        h = _make_handler()
        h._track_paper("PMID1", "Title", "Author", "abstract", oa_pdf_url="http://oa/x.pdf")
        assert h.discovered_fulltext["PMID1"] == "http://oa/x.pdf"

    def test_track_paper_without_oa_url(self):
        h = _make_handler()
        h._track_paper("PMID1", "Title", "Author", "abstract")
        assert "PMID1" not in h.discovered_fulltext

    @pytest.mark.asyncio
    async def test_reads_oa_pdf_truncated(self):
        h = _make_handler()
        h.discovered_fulltext["PMID1"] = "http://oa/x.pdf"
        h.discovered_abstracts["PMID1"] = ("Cool Paper", "abs")
        h._engine._corpus.fetch_pdf_text_from_url = AsyncMock(return_value="FULL BODY " * 100)

        result = await h._read_external_fulltext("PMID1", max_chars=50)
        assert result is not None
        title, text = result
        assert title == "Cool Paper"
        assert len(text) == 50  # truncated to max_chars

    @pytest.mark.asyncio
    async def test_none_when_no_oa_url(self):
        h = _make_handler()
        assert await h._read_external_fulltext("PMID1", 100) is None

    @pytest.mark.asyncio
    async def test_none_when_fetch_empty(self):
        h = _make_handler()
        h.discovered_fulltext["PMID1"] = "http://oa/x.pdf"
        h._engine._corpus.fetch_pdf_text_from_url = AsyncMock(return_value="")
        assert await h._read_external_fulltext("PMID1", 100) is None
