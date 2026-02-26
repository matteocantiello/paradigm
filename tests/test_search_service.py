"""Tests for LiteratureSearchService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from paradigm.domains.base import SourceDocument, SourceProvider, SourceResult
from paradigm.literature.search_service import LiteratureSearchService

# --- Mock helpers ---


class MockProvider(SourceProvider):
    """Mock SourceProvider for testing."""

    name = "mock"

    def __init__(
        self,
        search_results: list[SourceResult] | None = None,
        fetch_result: SourceDocument | None = None,
        references: list[SourceResult] | None = None,
        citations: list[SourceResult] | None = None,
    ) -> None:
        self._search_results = search_results or []
        self._fetch_result = fetch_result
        self._references = references or []
        self._citations = citations or []

    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        return self._search_results[:max_results]

    async def fetch(self, source_id: str) -> SourceDocument | None:
        return self._fetch_result

    async def get_references(self, source_id: str) -> list[SourceResult]:
        return self._references

    async def get_citing(self, source_id: str) -> list[SourceResult]:
        return self._citations


def _make_result(paper_id: str, source_type: str = "test") -> SourceResult:
    return SourceResult(
        id=paper_id,
        source_type=source_type,
        title=f"Paper {paper_id}",
        authors=["Author"],
        summary=f"Abstract for {paper_id}",
    )


def _make_corpus_mock(search_results: list[SourceResult] | None = None) -> MagicMock:
    corpus = MagicMock()
    corpus.search = AsyncMock(return_value=search_results or [])
    return corpus


# --- Tests ---


class TestLiteratureSearchService:
    @pytest.mark.asyncio
    async def test_search_papers_default(self):
        """Default search delegates to corpus."""
        corpus = _make_corpus_mock([_make_result("p1"), _make_result("p2")])
        service = LiteratureSearchService(corpus=corpus, providers={})

        results = await service.search_papers("test query")
        assert len(results) == 2
        corpus.search.assert_called_once_with("test query", max_results=20)

    @pytest.mark.asyncio
    async def test_search_papers_specific_sources(self):
        """Search specific sources bypasses corpus."""
        provider1 = MockProvider(search_results=[_make_result("p1", "source1")])
        provider2 = MockProvider(search_results=[_make_result("p2", "source2")])
        corpus = _make_corpus_mock()

        service = LiteratureSearchService(
            corpus=corpus,
            providers={"source1": provider1, "source2": provider2},
        )

        results = await service.search_papers("test", sources=["source1"])
        assert len(results) == 1
        assert results[0].source_type == "source1"
        # Corpus should NOT have been called
        corpus.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_papers_unknown_source(self):
        """Unknown source names are silently skipped."""
        service = LiteratureSearchService(
            corpus=_make_corpus_mock(),
            providers={},
        )

        results = await service.search_papers("test", sources=["nonexistent"])
        assert results == []

    @pytest.mark.asyncio
    async def test_get_citations(self):
        """Gathers citations from all providers."""
        p1 = MockProvider(citations=[_make_result("cite1")])
        p2 = MockProvider(citations=[_make_result("cite2")])

        service = LiteratureSearchService(
            corpus=_make_corpus_mock(),
            providers={"p1": p1, "p2": p2},
        )

        results = await service.get_citations("seed")
        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"cite1", "cite2"}

    @pytest.mark.asyncio
    async def test_get_citations_deduplicates(self):
        """Same paper from multiple providers is only returned once."""
        p1 = MockProvider(citations=[_make_result("same_id")])
        p2 = MockProvider(citations=[_make_result("same_id")])

        service = LiteratureSearchService(
            corpus=_make_corpus_mock(),
            providers={"p1": p1, "p2": p2},
        )

        results = await service.get_citations("seed")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_references(self):
        """Gathers references from all providers."""
        p1 = MockProvider(references=[_make_result("ref1")])

        service = LiteratureSearchService(
            corpus=_make_corpus_mock(),
            providers={"p1": p1},
        )

        results = await service.get_references("seed")
        assert len(results) == 1
        assert results[0].id == "ref1"

    @pytest.mark.asyncio
    async def test_follow_chain(self):
        """Citation chain traversal works through service."""
        provider = MockProvider(
            references=[_make_result("ref1")],
        )

        service = LiteratureSearchService(
            corpus=_make_corpus_mock(),
            providers={"mock": provider},
        )

        results = await service.follow_chain("seed", depth=1, direction="references")
        assert len(results) == 1
        assert results[0].id == "ref1"

    @pytest.mark.asyncio
    async def test_get_paper_details(self):
        """Fetches from first provider that succeeds."""
        doc = SourceDocument(
            id="test",
            source_type="test",
            title="Test Doc",
            full_text="Full text content",
        )
        p1 = MockProvider(fetch_result=None)
        p2 = MockProvider(fetch_result=doc)

        service = LiteratureSearchService(
            corpus=_make_corpus_mock(),
            providers={"p1": p1, "p2": p2},
        )

        result = await service.get_paper_details("test")
        assert result is not None
        assert result.title == "Test Doc"

    @pytest.mark.asyncio
    async def test_get_paper_details_not_found(self):
        """Returns None when no provider can fetch."""
        p1 = MockProvider(fetch_result=None)

        service = LiteratureSearchService(
            corpus=_make_corpus_mock(),
            providers={"p1": p1},
        )

        result = await service.get_paper_details("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_provider_error_handling(self):
        """Service handles provider errors gracefully."""
        failing = MockProvider()
        failing.get_citing = AsyncMock(side_effect=Exception("API error"))

        working = MockProvider(citations=[_make_result("cite1")])

        service = LiteratureSearchService(
            corpus=_make_corpus_mock(),
            providers={"failing": failing, "working": working},
        )

        results = await service.get_citations("seed")
        assert len(results) == 1
        assert results[0].id == "cite1"
