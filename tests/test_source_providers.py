"""Tests for source provider adapters, factory, and conversion functions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

import pytest

from paradigm.config import LiteratureConfig, StorageConfig
from paradigm.domains.base import (
    SourceDocument,
    SourceProviderConfig,
    SourceResult,
    arxiv_paper_to_source_result,
    semantic_paper_to_source_result,
    source_result_to_arxiv_paper,
)
from paradigm.literature.arxiv import ArxivClient, ArxivPaper
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.literature.provider_factory import create_source_providers
from paradigm.literature.providers import (
    ArxivSourceProvider,
    InternalCorpusProvider,
    SemanticScholarSourceProvider,
)
from paradigm.literature.semantic_scholar import SemanticPaper, SemanticScholarClient
from paradigm.storage.database import Database

# ---------------------------------------------------------------------------
# Conversion function tests
# ---------------------------------------------------------------------------


class TestArxivPaperToSourceResult:
    def test_basic_conversion(self):
        now = datetime(2023, 6, 15, tzinfo=UTC)
        paper = ArxivPaper(
            arxiv_id="2306.12345",
            title="Test Paper",
            abstract="This is the abstract.",
            authors=["Alice", "Bob"],
            categories=["astro-ph.SR", "astro-ph.HE"],
            primary_category="astro-ph.SR",
            published=now,
            updated=now,
            pdf_url="http://arxiv.org/pdf/2306.12345",
            abs_url="http://arxiv.org/abs/2306.12345",
        )
        result = arxiv_paper_to_source_result(paper)

        assert result.id == "2306.12345"
        assert result.source_type == "arxiv"
        assert result.title == "Test Paper"
        assert result.summary == "This is the abstract."
        assert result.authors == ["Alice", "Bob"]
        assert result.date == now
        assert result.url == "http://arxiv.org/abs/2306.12345"
        assert result.metadata["categories"] == ["astro-ph.SR", "astro-ph.HE"]
        assert result.metadata["primary_category"] == "astro-ph.SR"
        assert result.metadata["pdf_url"] == "http://arxiv.org/pdf/2306.12345"

    def test_body_mapped_to_content(self):
        now = datetime(2023, 1, 1, tzinfo=UTC)
        paper = ArxivPaper(
            arxiv_id="2301.00001",
            title="Paper With Body",
            abstract="Abstract",
            authors=[],
            categories=[],
            primary_category="",
            published=now,
            updated=now,
            pdf_url="",
            abs_url="",
            body="Full text here",
        )
        result = arxiv_paper_to_source_result(paper)
        assert result.content == "Full text here"


class TestSemanticPaperToSourceResult:
    def test_basic_conversion(self):
        paper = SemanticPaper(
            paper_id="s2-abc123",
            arxiv_id="2306.12345",
            title="S2 Paper",
            authors=["Alice", "Bob"],
            abstract="S2 abstract.",
            year=2023,
            citation_count=42,
            url="https://www.semanticscholar.org/paper/s2-abc123",
        )
        result = semantic_paper_to_source_result(paper)

        assert result.id == "2306.12345"
        assert result.source_type == "semantic_scholar"
        assert result.title == "S2 Paper"
        assert result.summary == "S2 abstract."
        assert result.authors == ["Alice", "Bob"]
        assert result.date == datetime(2023, 1, 1)
        assert result.metadata["paper_id"] == "s2-abc123"
        assert result.metadata["citation_count"] == 42

    def test_no_arxiv_id_uses_paper_id(self):
        paper = SemanticPaper(
            paper_id="s2-only",
            arxiv_id=None,
            title="S2 Only",
            authors=[],
            abstract="",
            year=None,
            citation_count=None,
            url="",
        )
        result = semantic_paper_to_source_result(paper)
        assert result.id == "s2-only"
        assert result.date is None


class TestSourceResultToArxivPaper:
    def test_round_trip(self):
        now = datetime(2023, 6, 15, tzinfo=UTC)
        original = ArxivPaper(
            arxiv_id="2306.12345",
            title="Test Paper",
            abstract="This is the abstract.",
            authors=["Alice", "Bob"],
            categories=["astro-ph.SR"],
            primary_category="astro-ph.SR",
            published=now,
            updated=now,
            pdf_url="http://arxiv.org/pdf/2306.12345",
            abs_url="http://arxiv.org/abs/2306.12345",
        )
        source_result = arxiv_paper_to_source_result(original)
        back = source_result_to_arxiv_paper(source_result)

        assert back.arxiv_id == "2306.12345"
        assert back.title == "Test Paper"
        assert back.abstract == "This is the abstract."
        assert back.authors == ["Alice", "Bob"]
        assert back.categories == ["astro-ph.SR"]
        assert back.published == now


# ---------------------------------------------------------------------------
# ArxivSourceProvider tests
# ---------------------------------------------------------------------------


class TestArxivSourceProvider:
    @pytest.fixture
    def mock_client(self):
        client = AsyncMock(spec=ArxivClient)
        client.search = AsyncMock(return_value=[])
        client.get_paper = AsyncMock(return_value=None)
        client.fetch_pdf_text = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def provider(self, mock_client):
        return ArxivSourceProvider(mock_client)

    @pytest.mark.asyncio
    async def test_search_delegates_and_converts(self, provider, mock_client):
        now = datetime(2023, 1, 1, tzinfo=UTC)
        mock_client.search.return_value = [
            ArxivPaper(
                arxiv_id="2301.001",
                title="Paper One",
                abstract="Abstract one",
                authors=["Alice"],
                categories=["astro-ph.SR"],
                primary_category="astro-ph.SR",
                published=now,
                updated=now,
                pdf_url="http://arxiv.org/pdf/2301.001",
                abs_url="http://arxiv.org/abs/2301.001",
            )
        ]

        results = await provider.search("test query", max_results=5)

        assert len(results) == 1
        assert isinstance(results[0], SourceResult)
        assert results[0].id == "2301.001"
        assert results[0].title == "Paper One"
        mock_client.search.assert_called_once_with("test query", max_results=5)

    @pytest.mark.asyncio
    async def test_fetch_returns_source_document(self, provider, mock_client):
        now = datetime(2023, 1, 1, tzinfo=UTC)
        paper = ArxivPaper(
            arxiv_id="2301.001",
            title="Paper One",
            abstract="Abstract",
            authors=["Alice"],
            categories=["astro-ph.SR"],
            primary_category="astro-ph.SR",
            published=now,
            updated=now,
            pdf_url="http://arxiv.org/pdf/2301.001",
            abs_url="http://arxiv.org/abs/2301.001",
        )
        mock_client.get_paper.return_value = paper
        mock_client.fetch_pdf_text.return_value = "Full text content"

        doc = await provider.fetch("2301.001")

        assert doc is not None
        assert isinstance(doc, SourceDocument)
        assert doc.id == "2301.001"
        assert doc.full_text == "Full text content"

    @pytest.mark.asyncio
    async def test_fetch_returns_none_when_paper_not_found(self, provider, mock_client):
        mock_client.get_paper.return_value = None
        doc = await provider.fetch("nonexistent")
        assert doc is None


# ---------------------------------------------------------------------------
# SemanticScholarSourceProvider tests
# ---------------------------------------------------------------------------


class TestSemanticScholarSourceProvider:
    @pytest.fixture
    def mock_client(self):
        client = AsyncMock(spec=SemanticScholarClient)
        client.search = AsyncMock(return_value=[])
        client.get_references = AsyncMock(return_value=[])
        client.get_citations = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def provider(self, mock_client):
        return SemanticScholarSourceProvider(mock_client)

    @pytest.mark.asyncio
    async def test_search_delegates(self, provider, mock_client):
        mock_client.search.return_value = [
            SemanticPaper(
                paper_id="s2-1",
                arxiv_id="2301.001",
                title="S2 Paper",
                authors=["Bob"],
                abstract="Abstract",
                year=2023,
                citation_count=10,
                url="https://s2.org/1",
            )
        ]

        results = await provider.search("query", max_results=5)

        assert len(results) == 1
        assert results[0].id == "2301.001"
        mock_client.search.assert_called_once_with("query", limit=5)

    @pytest.mark.asyncio
    async def test_get_references(self, provider, mock_client):
        mock_client.get_references.return_value = [
            SemanticPaper(
                paper_id="s2-ref",
                arxiv_id="2301.002",
                title="Referenced",
                authors=[],
                abstract="",
                year=2022,
                citation_count=5,
                url="",
            )
        ]

        results = await provider.get_references("2301.001")
        assert len(results) == 1
        assert results[0].id == "2301.002"

    @pytest.mark.asyncio
    async def test_get_citing(self, provider, mock_client):
        mock_client.get_citations.return_value = [
            SemanticPaper(
                paper_id="s2-cite",
                arxiv_id="2401.001",
                title="Citing Paper",
                authors=["Eve"],
                abstract="Cites the other",
                year=2024,
                citation_count=3,
                url="",
            )
        ]

        results = await provider.get_citing("2301.001")
        assert len(results) == 1
        assert results[0].id == "2401.001"

    @pytest.mark.asyncio
    async def test_fetch_returns_none(self, provider):
        doc = await provider.fetch("2301.001")
        assert doc is None


# ---------------------------------------------------------------------------
# InternalCorpusProvider tests
# ---------------------------------------------------------------------------


class TestInternalCorpusProvider:
    @pytest.fixture
    def tmpdir(self):
        with TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def db(self, tmpdir):
        database = Database(tmpdir / "test.db")
        yield database
        database.close()

    @pytest.fixture
    def embedding_store(self):
        return EmbeddingStore(ephemeral=True, collection_name=f"test_{uuid.uuid4().hex}")

    @pytest.fixture
    def provider(self, embedding_store, db):
        return InternalCorpusProvider(embedding_store, db)

    @pytest.mark.asyncio
    async def test_search_empty_store(self, provider):
        results = await provider.search("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_external_papers(self, provider, db, embedding_store):
        # Create an external paper
        db.create_paper(
            paper_id="arxiv:2301.001",
            title="External Paper",
            abstract="About stellar physics",
            authors=["Alice"],
            body="",
            status="external",
        )
        embedding_store.add_paper(
            arxiv_id="2301.001",
            title="External Paper",
            abstract="About stellar physics",
        )

        results = await provider.search("stellar physics")
        assert len(results) >= 1
        assert results[0].id == "2301.001"

    @pytest.mark.asyncio
    async def test_search_excludes_internal_papers(self, provider, db, embedding_store):
        # Internal paper (paper-*) should be excluded
        db.create_paper(
            paper_id="paper-abc",
            title="Internal Paper",
            abstract="Internal abstract",
            authors=["agent-0"],
            body="",
            status="published",
        )
        embedding_store.add_paper(
            arxiv_id="paper-abc",
            title="Internal Paper",
            abstract="Internal abstract",
        )

        results = await provider.search("internal")
        found_ids = [r.id for r in results]
        assert "paper-abc" not in found_ids

    @pytest.mark.asyncio
    async def test_fetch_returns_document(self, provider, db):
        db.create_paper(
            paper_id="arxiv:2301.001",
            title="Test Paper",
            abstract="Abstract",
            authors=["Alice"],
            body="Full body text",
            status="external",
        )

        doc = await provider.fetch("2301.001")
        assert doc is not None
        assert doc.id == "2301.001"
        assert doc.full_text == "Full body text"

    @pytest.mark.asyncio
    async def test_fetch_returns_none_when_not_found(self, provider):
        doc = await provider.fetch("nonexistent")
        assert doc is None


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestCreateSourceProviders:
    @pytest.fixture
    def tmpdir(self):
        with TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def db(self, tmpdir):
        database = Database(tmpdir / "test.db")
        yield database
        database.close()

    @pytest.fixture
    def lit_config(self):
        return LiteratureConfig()

    @pytest.fixture
    def storage_config(self, tmpdir):
        return StorageConfig(data_dir=tmpdir / "data")

    def test_creates_arxiv_provider(self, lit_config, storage_config, db):
        configs = [SourceProviderConfig(name="arxiv", enabled=True)]
        providers = create_source_providers(configs, lit_config, storage_config, db)

        assert "arxiv" in providers
        assert isinstance(providers["arxiv"], ArxivSourceProvider)

    def test_creates_semantic_scholar_provider(self, lit_config, storage_config, db):
        configs = [SourceProviderConfig(name="semantic_scholar", enabled=True)]
        providers = create_source_providers(configs, lit_config, storage_config, db)

        assert "semantic_scholar" in providers
        assert isinstance(providers["semantic_scholar"], SemanticScholarSourceProvider)

    def test_creates_internal_corpus_provider(self, lit_config, storage_config, db):
        configs = [SourceProviderConfig(name="internal_corpus", enabled=True)]
        providers = create_source_providers(configs, lit_config, storage_config, db)

        assert "internal_corpus" in providers
        assert isinstance(providers["internal_corpus"], InternalCorpusProvider)

    def test_skips_disabled_providers(self, lit_config, storage_config, db):
        configs = [SourceProviderConfig(name="arxiv", enabled=False)]
        providers = create_source_providers(configs, lit_config, storage_config, db)

        assert "arxiv" not in providers

    def test_skips_unknown_providers(self, lit_config, storage_config, db):
        configs = [SourceProviderConfig(name="unknown_source", enabled=True)]
        providers = create_source_providers(configs, lit_config, storage_config, db)

        assert len(providers) == 0

    def test_creates_multiple_providers(self, lit_config, storage_config, db):
        configs = [
            SourceProviderConfig(name="arxiv", enabled=True),
            SourceProviderConfig(name="semantic_scholar", enabled=True),
            SourceProviderConfig(name="internal_corpus", enabled=True),
        ]
        providers = create_source_providers(configs, lit_config, storage_config, db)

        assert len(providers) == 3
        assert "arxiv" in providers
        assert "semantic_scholar" in providers
        assert "internal_corpus" in providers

    def test_empty_config_returns_empty(self, lit_config, storage_config, db):
        providers = create_source_providers([], lit_config, storage_config, db)
        assert providers == {}
