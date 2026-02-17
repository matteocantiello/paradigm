"""Tests for the citation handler orchestrator integration."""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradigm.config import Config
from paradigm.journal.paper import PaperDraft
from paradigm.literature.arxiv import ArxivPaper
from paradigm.orchestrator.citation_handler import CitationHandler
from paradigm.orchestrator.literature import LiteratureHandler


def _make_draft_with_body() -> PaperDraft:
    """Create a PaperDraft with assembled_body that has an introduction and methods."""
    draft = PaperDraft()
    draft.assembled_body = (
        "# Test Paper\n\n"
        "## Abstract\n\nThis paper studies stellar convection.\n\n"
        "## Introduction\n\n"
        "Stellar convection is a fundamental process in stellar physics "
        "that governs energy transport, chemical mixing, and angular momentum "
        "redistribution in stellar interiors. Understanding convective processes "
        "is essential for modeling stellar evolution accurately.\n\n"
        "## Methods\n\n"
        "We use one-dimensional stellar evolution models computed with the "
        "MESA code to investigate the effects of convective overshooting "
        "on the main-sequence width. Our models span a mass range of "
        "1.5 to 8 solar masses.\n\n"
        "## Results\n\nOur results show significant effects.\n\n"
        "## Conclusion\n\nWe conclude things."
    )
    return draft


def _make_mock_engine(enable_grounding=True, api_key="test-perplexity-key"):
    """Create a mock OrchestrationEngine with citation config."""
    engine = MagicMock()

    # Config
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    config = Config()
    config.citation.enable_citation_grounding = enable_grounding
    engine._config = config

    # Logger
    engine._logger = MagicMock()
    engine._logger.log = MagicMock()
    engine._logger.log_error = MagicMock()

    # Display
    engine._display = MagicMock()

    # Thread ID
    engine._thread_id = "test-thread-001"

    # Corpus
    engine._corpus = MagicMock()
    engine._corpus._arxiv = MagicMock()

    # Set API key
    if api_key:
        os.environ["PERPLEXITY_API_KEY"] = api_key
    elif "PERPLEXITY_API_KEY" in os.environ:
        del os.environ["PERPLEXITY_API_KEY"]

    return engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCitationHandlerDisabled:
    @pytest.mark.asyncio
    async def test_grounding_disabled_config(self):
        """Returns draft unchanged when citation grounding is disabled."""
        engine = _make_mock_engine(enable_grounding=False)
        handler = CitationHandler(engine)
        draft = _make_draft_with_body()
        original_body = draft.assembled_body

        result = await handler.run_citation_grounding(draft)

        assert result.assembled_body == original_body
        assert result.references == []
        engine._display.citation_grounding_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_grounding_disabled_no_key(self):
        """Returns draft unchanged when API key is missing."""
        engine = _make_mock_engine(enable_grounding=True, api_key=None)
        # Explicitly remove the key
        if "PERPLEXITY_API_KEY" in os.environ:
            del os.environ["PERPLEXITY_API_KEY"]

        handler = CitationHandler(engine)
        draft = _make_draft_with_body()
        original_body = draft.assembled_body

        result = await handler.run_citation_grounding(draft)

        assert result.assembled_body == original_body
        engine._logger.log_error.assert_called_once()


class TestCitationHandlerEnabled:
    @pytest.mark.asyncio
    async def test_grounding_injects_references(self):
        """Mock Perplexity and verify references section is added."""
        engine = _make_mock_engine(enable_grounding=True)
        handler = CitationHandler(engine)
        draft = _make_draft_with_body()

        # Mock the PerplexityClient.cite_section
        mock_cite_section = AsyncMock(
            return_value=(
                "Stellar convection is important [1]. Models show [2].",
                ["https://arxiv.org/abs/2301.11111", "https://arxiv.org/abs/2301.22222"],
            )
        )

        with patch("paradigm.orchestrator.citation_handler.PerplexityClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.cite_section = mock_cite_section
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            result = await handler.run_citation_grounding(draft)

        assert "## References" in result.assembled_body
        assert len(result.references) > 0
        engine._display.citation_grounding_start.assert_called_once()
        engine._display.citation_grounding_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_only_intro_methods_cited(self):
        """Only introduction and methods sections are processed by default."""
        engine = _make_mock_engine(enable_grounding=True)
        handler = CitationHandler(engine)
        draft = _make_draft_with_body()

        # Track which sections were cited
        cited_sections = []

        async def mock_cite_section(text, section_name):
            cited_sections.append(section_name)
            return text, []

        with patch("paradigm.orchestrator.citation_handler.PerplexityClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.cite_section = AsyncMock(side_effect=mock_cite_section)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            await handler.run_citation_grounding(draft)

        # Default citation_sections is ["introduction", "methods"]
        assert "introduction" in cited_sections
        assert "methods" in cited_sections
        assert "results" not in cited_sections
        assert "conclusion" not in cited_sections
        assert "abstract" not in cited_sections


class TestNoveltyCheck:
    @pytest.mark.asyncio
    async def test_check_novelty_semantic_scholar(self):
        """Test novelty check dispatches to semantic_scholar mode."""
        engine = _make_mock_engine()
        handler = CitationHandler(engine)

        with patch(
            "paradigm.orchestrator.citation_handler.check_novelty_semantic_scholar"
        ) as mock_check:
            from paradigm.literature.novelty import NoveltyResult

            mock_check.return_value = NoveltyResult(
                is_novel=True,
                confidence=0.8,
                papers_found=5,
                source="semantic_scholar",
            )

            with patch("paradigm.literature.semantic_scholar.SemanticScholarClient") as mock_s2_cls:
                mock_s2 = AsyncMock()
                mock_s2.close = AsyncMock()
                mock_s2_cls.return_value = mock_s2

                result = await handler.check_novelty("test idea", "semantic_scholar")

        assert result.is_novel is True
        assert result.source == "semantic_scholar"
        engine._display.novelty_check_start.assert_called_once_with("semantic_scholar")
        engine._display.novelty_confirmed.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_novelty_not_novel(self):
        """When idea is not novel, warning is displayed."""
        engine = _make_mock_engine()
        handler = CitationHandler(engine)

        with patch(
            "paradigm.orchestrator.citation_handler.check_novelty_semantic_scholar"
        ) as mock_check:
            from paradigm.literature.novelty import NoveltyResult

            mock_check.return_value = NoveltyResult(
                is_novel=False,
                confidence=0.9,
                papers_found=10,
                source="semantic_scholar",
            )

            with patch("paradigm.literature.semantic_scholar.SemanticScholarClient") as mock_s2_cls:
                mock_s2 = AsyncMock()
                mock_s2.close = AsyncMock()
                mock_s2_cls.return_value = mock_s2

                result = await handler.check_novelty("old idea", "semantic_scholar")

        assert result.is_novel is False
        engine._display.novelty_warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_futurehouse_missing_key(self):
        """FutureHouse mode with missing key returns novel=True, confidence=0."""
        engine = _make_mock_engine()
        # Remove futurehouse key
        if "FUTURE_HOUSE_API_KEY" in os.environ:
            del os.environ["FUTURE_HOUSE_API_KEY"]

        handler = CitationHandler(engine)
        result = await handler.check_novelty("test idea", "futurehouse")

        assert result.is_novel is True
        assert result.confidence == 0.0
        engine._logger.log_error.assert_called_once()


# ---------------------------------------------------------------------------
# Seed discovery
# ---------------------------------------------------------------------------


def _make_arxiv_paper(arxiv_id: str, title: str = "Test Paper") -> ArxivPaper:
    """Create a minimal ArxivPaper for testing."""
    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=title,
        abstract="Abstract text.",
        authors=["Author One", "Author Two"],
        categories=["astro-ph.SR"],
        primary_category="astro-ph.SR",
        published=datetime(2024, 1, 15, tzinfo=UTC),
        updated=datetime(2024, 1, 15, tzinfo=UTC),
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )


class TestSeedDiscovery:
    @pytest.mark.asyncio
    async def test_seed_discovery_disabled(self):
        """Returns 0 when enable_seed_discovery is False."""
        engine = _make_mock_engine()
        engine._config.citation.enable_seed_discovery = False
        handler = LiteratureHandler(engine)

        result = await handler.run_seed_discovery("stellar convection")
        assert result == 0
        engine._display.seed_discovery_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_seed_discovery_no_api_key(self):
        """Returns 0 when PERPLEXITY_API_KEY is missing."""
        engine = _make_mock_engine(api_key=None)
        if "PERPLEXITY_API_KEY" in os.environ:
            del os.environ["PERPLEXITY_API_KEY"]
        engine._config.citation.enable_seed_discovery = True
        handler = LiteratureHandler(engine)

        result = await handler.run_seed_discovery("stellar convection")
        assert result == 0
        engine._logger.log_error.assert_called()

    @pytest.mark.asyncio
    async def test_seed_discovery_populates_context(self):
        """Mock Perplexity + arXiv, verify literature_context populated."""
        engine = _make_mock_engine()
        engine._config.citation.enable_seed_discovery = True
        engine._config.citation.seed_discovery_max_papers = 5

        handler = LiteratureHandler(engine)

        paper1 = _make_arxiv_paper("2301.12345", "Convective Overshooting in Stars")
        paper2 = _make_arxiv_paper("2302.67890", "Mixing Length Theory Revisited")

        mock_discover = AsyncMock(
            return_value=[
                "https://arxiv.org/abs/2301.12345",
                "https://arxiv.org/abs/2302.67890",
            ]
        )
        mock_get_paper = AsyncMock(side_effect=[paper1, paper2])
        mock_ingest = AsyncMock()

        engine._corpus._arxiv.get_paper = mock_get_paper
        engine._corpus.ingest_paper = mock_ingest

        with patch("paradigm.orchestrator.literature.PerplexityClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.discover_papers = mock_discover
            mock_instance.close = AsyncMock()
            mock_client_cls.return_value = mock_instance

            result = await handler.run_seed_discovery("stellar convection")

        assert result == 2
        assert handler.literature_context != ""
        assert "2301.12345" in handler.seen_paper_ids
        assert "2302.67890" in handler.seen_paper_ids
        assert len(handler.discovered_papers) == 2
        assert mock_ingest.call_count == 2
        engine._display.seed_discovery_start.assert_called_once()
