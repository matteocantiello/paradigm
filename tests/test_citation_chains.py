"""Tests for citation chain BFS traversal."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from paradigm.domains.base import SourceProvider, SourceResult
from paradigm.literature.citation_chains import follow_citation_chain

# --- Mock provider ---


class MockProvider(SourceProvider):
    """Mock SourceProvider for testing citation chains."""

    name = "mock"

    def __init__(
        self,
        references: dict[str, list[SourceResult]] | None = None,
        citations: dict[str, list[SourceResult]] | None = None,
    ) -> None:
        self._references = references or {}
        self._citations = citations or {}

    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        return []

    async def fetch(self, source_id: str) -> None:
        return None

    async def get_references(self, source_id: str) -> list[SourceResult]:
        return self._references.get(source_id, [])

    async def get_citing(self, source_id: str) -> list[SourceResult]:
        return self._citations.get(source_id, [])


def _make_result(paper_id: str, title: str = "Paper") -> SourceResult:
    return SourceResult(
        id=paper_id,
        source_type="test",
        title=f"{title} {paper_id}",
        authors=["Author"],
        summary=f"Abstract for {paper_id}",
    )


# --- Tests ---


class TestFollowCitationChain:
    @pytest.mark.asyncio
    async def test_basic_references(self):
        """Follow references one level deep."""
        provider = MockProvider(
            references={
                "seed": [_make_result("ref1"), _make_result("ref2")],
            }
        )

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="references",
            max_depth=1,
        )

        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"ref1", "ref2"}
        assert all(r.metadata["chain_depth"] == 1 for r in results)

    @pytest.mark.asyncio
    async def test_basic_citations(self):
        """Follow citations one level deep."""
        provider = MockProvider(
            citations={
                "seed": [_make_result("cite1"), _make_result("cite2")],
            }
        )

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="citations",
            max_depth=1,
        )

        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"cite1", "cite2"}

    @pytest.mark.asyncio
    async def test_both_directions(self):
        """Follow both references and citations."""
        provider = MockProvider(
            references={"seed": [_make_result("ref1")]},
            citations={"seed": [_make_result("cite1")]},
        )

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="both",
            max_depth=1,
        )

        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"ref1", "cite1"}

    @pytest.mark.asyncio
    async def test_depth_two(self):
        """Follow references two levels deep."""
        provider = MockProvider(
            references={
                "seed": [_make_result("ref1")],
                "ref1": [_make_result("ref2")],
            }
        )

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="references",
            max_depth=2,
        )

        assert len(results) == 2
        depths = {r.id: r.metadata["chain_depth"] for r in results}
        assert depths["ref1"] == 1
        assert depths["ref2"] == 2

    @pytest.mark.asyncio
    async def test_deduplication(self):
        """Same paper referenced by multiple paths is only counted once."""
        provider = MockProvider(
            references={
                "seed": [_make_result("ref1"), _make_result("ref2")],
                "ref1": [_make_result("shared")],
                "ref2": [_make_result("shared")],
            }
        )

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="references",
            max_depth=2,
        )

        ids = [r.id for r in results]
        assert ids.count("shared") == 1

    @pytest.mark.asyncio
    async def test_seed_not_in_results(self):
        """The seed paper itself should not appear in results."""
        provider = MockProvider(
            references={"seed": [_make_result("ref1")]},
        )

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="references",
            max_depth=1,
        )

        assert all(r.id != "seed" for r in results)

    @pytest.mark.asyncio
    async def test_max_papers_per_level(self):
        """Respects max_papers_per_level limit."""
        refs = [_make_result(f"ref{i}") for i in range(20)]
        provider = MockProvider(references={"seed": refs})

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="references",
            max_depth=1,
            max_papers_per_level=5,
        )

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_relevance_filter(self):
        """Relevance filter prunes irrelevant papers."""
        provider = MockProvider(
            references={
                "seed": [
                    _make_result("good1"),
                    _make_result("bad1"),
                    _make_result("good2"),
                ],
            }
        )

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="references",
            max_depth=1,
            relevance_filter=lambda r: r.id.startswith("good"),
        )

        assert len(results) == 2
        assert all(r.id.startswith("good") for r in results)

    @pytest.mark.asyncio
    async def test_empty_graph(self):
        """No results when provider returns no references."""
        provider = MockProvider()

        results = await follow_citation_chain(
            providers={"mock": provider},
            seed_id="seed",
            direction="references",
            max_depth=2,
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_providers(self):
        """Results from multiple providers are merged."""
        provider1 = MockProvider(references={"seed": [_make_result("p1_ref")]})
        provider2 = MockProvider(references={"seed": [_make_result("p2_ref")]})

        results = await follow_citation_chain(
            providers={"p1": provider1, "p2": provider2},
            seed_id="seed",
            direction="references",
            max_depth=1,
        )

        ids = {r.id for r in results}
        assert ids == {"p1_ref", "p2_ref"}

    @pytest.mark.asyncio
    async def test_provider_error_handled(self):
        """If a provider raises, other providers still work."""
        failing = MockProvider()
        failing.get_references = AsyncMock(side_effect=Exception("API error"))

        working = MockProvider(references={"seed": [_make_result("ref1")]})

        results = await follow_citation_chain(
            providers={"failing": failing, "working": working},
            seed_id="seed",
            direction="references",
            max_depth=1,
        )

        assert len(results) == 1
        assert results[0].id == "ref1"
