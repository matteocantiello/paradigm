"""Tests for the novelty checking module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from paradigm.literature.novelty import (
    NoveltyResult,
    check_novelty_futurehouse,
    check_novelty_semantic_scholar,
)
from paradigm.literature.semantic_scholar import SemanticPaper

# ---------------------------------------------------------------------------
# check_novelty_semantic_scholar
# ---------------------------------------------------------------------------


def _make_s2_paper(title: str, abstract: str = "", year: int = 2023) -> SemanticPaper:
    return SemanticPaper(
        paper_id=f"id-{title[:10]}",
        arxiv_id=None,
        title=title,
        authors=["Author A"],
        abstract=abstract,
        year=year,
        citation_count=10,
        url="",
    )


class TestNoveltySemanticScholar:
    @pytest.mark.asyncio
    async def test_novel_idea(self):
        """LLM assessment says the idea is novel."""
        s2_client = MagicMock()
        s2_client.search = AsyncMock(return_value=[
            _make_s2_paper("Unrelated Paper 1", "About cooking recipes"),
            _make_s2_paper("Unrelated Paper 2", "About quantum gravity"),
        ])

        mock_provider = MagicMock()
        # First call: keyword extraction
        extract_response = MagicMock()
        extract_response.content = "stellar convection overshooting\nmixing length theory"
        # Second call: novelty assessment
        assess_response = MagicMock()
        assess_response.content = "NOVEL: yes\nCONFIDENCE: 0.8\nREASONING: Idea is unique."
        mock_provider.generate = AsyncMock(side_effect=[extract_response, assess_response])

        result = await check_novelty_semantic_scholar(
            "A new theory of stellar convection.",
            s2_client,
            mock_provider,
            "test-model",
            max_iterations=2,
        )

        assert isinstance(result, NoveltyResult)
        assert result.is_novel is True
        assert result.confidence == 0.8
        assert result.source == "semantic_scholar"
        assert result.papers_found > 0

    @pytest.mark.asyncio
    async def test_not_novel_idea(self):
        """LLM assessment says the idea is not novel."""
        s2_client = MagicMock()
        s2_client.search = AsyncMock(return_value=[
            _make_s2_paper("Exact Match Paper", "Exactly what user proposed"),
        ])

        mock_provider = MagicMock()
        extract_response = MagicMock()
        extract_response.content = "matching query"
        assess_response = MagicMock()
        assess_response.content = "NOVEL: no\nCONFIDENCE: 0.9\nREASONING: Already done."
        mock_provider.generate = AsyncMock(side_effect=[extract_response, assess_response])

        result = await check_novelty_semantic_scholar(
            "An idea that was already done.",
            s2_client,
            mock_provider,
            "test-model",
        )

        assert result.is_novel is False
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_no_papers_found(self):
        """When S2 returns no papers, result is novel with low confidence."""
        s2_client = MagicMock()
        s2_client.search = AsyncMock(return_value=[])

        mock_provider = MagicMock()
        extract_response = MagicMock()
        extract_response.content = "obscure query"
        mock_provider.generate = AsyncMock(return_value=extract_response)

        result = await check_novelty_semantic_scholar(
            "A very obscure idea.",
            s2_client,
            mock_provider,
            "test-model",
        )

        assert result.is_novel is True
        assert result.confidence == 0.5
        assert result.papers_found == 0


# ---------------------------------------------------------------------------
# check_novelty_futurehouse (mocked)
# ---------------------------------------------------------------------------


class TestNoveltyFuturehouse:
    @pytest.mark.asyncio
    async def test_missing_package(self):
        """Raises ImportError when futurehouse_client is not installed."""
        # We mock the import to fail
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "futurehouse_client":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            with pytest.raises(ImportError, match="futurehouse_client"):
                await check_novelty_futurehouse("test idea", "fake-key")
        finally:
            builtins.__import__ = real_import


# ---------------------------------------------------------------------------
# NoveltyResult dataclass
# ---------------------------------------------------------------------------


class TestNoveltyResult:
    def test_default_values(self):
        result = NoveltyResult(is_novel=True, confidence=0.5)
        assert result.related_work == []
        assert result.papers_found == 0
        assert result.source == ""

    def test_populated_values(self):
        result = NoveltyResult(
            is_novel=False,
            confidence=0.9,
            related_work=["Paper A", "Paper B"],
            papers_found=5,
            source="semantic_scholar",
        )
        assert result.is_novel is False
        assert len(result.related_work) == 2
