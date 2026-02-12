"""Tests for unified corpus search interface."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

import pytest

from paradigm.config import LiteratureConfig, StorageConfig
from paradigm.literature.arxiv import ArxivClient, ArxivPaper
from paradigm.literature.corpus import Corpus
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.storage.database import Database


def _make_paper(
    arxiv_id: str,
    title: str = "Test Paper",
    abstract: str = "Test abstract",
    category: str = "astro-ph.SR",
) -> ArxivPaper:
    """Create a test ArxivPaper."""
    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        authors=["Author One", "Author Two"],
        categories=[category],
        primary_category=category,
        published=datetime(2023, 1, 15, tzinfo=UTC),
        updated=datetime(2023, 1, 15, tzinfo=UTC),
        pdf_url=f"http://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"http://arxiv.org/abs/{arxiv_id}",
    )


@pytest.fixture
def tmpdir():
    """Provide a temporary directory."""
    with TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def db(tmpdir):
    """Create a temporary database."""
    database = Database(tmpdir / "test.db")
    yield database
    database.close()


@pytest.fixture
def lit_config():
    """Create a literature config."""
    return LiteratureConfig()


@pytest.fixture
def storage_config(tmpdir):
    """Create a storage config."""
    return StorageConfig(data_dir=tmpdir / "data")


@pytest.fixture
def mock_arxiv():
    """Create a mock ArxivClient."""
    client = AsyncMock(spec=ArxivClient)
    client.search = AsyncMock(return_value=[])
    client.get_paper = AsyncMock(return_value=None)
    client.fetch_pdf_text = AsyncMock(return_value=None)
    client.close = AsyncMock()
    return client


@pytest.fixture
def embedding_store():
    """Create an ephemeral embedding store with unique collection."""
    return EmbeddingStore(ephemeral=True, collection_name=f"test_{uuid.uuid4().hex}")


@pytest.fixture
def corpus(db, lit_config, storage_config, mock_arxiv, embedding_store):
    """Create a Corpus with mock arXiv and ephemeral embeddings."""
    return Corpus(
        database=db,
        literature_config=lit_config,
        storage_config=storage_config,
        arxiv_client=mock_arxiv,
        embedding_store=embedding_store,
    )


async def test_search_arxiv_only(corpus, mock_arxiv):
    """Test searching arXiv only."""
    papers = [
        _make_paper("2301.001", "Paper One", "About stellar pulsation"),
        _make_paper("2301.002", "Paper Two", "About stellar winds"),
    ]
    mock_arxiv.search.return_value = papers

    results = await corpus.search("stellar pulsation", include_local=False)

    assert len(results) == 2
    mock_arxiv.search.assert_called_once()


async def test_search_local_only(corpus, embedding_store):
    """Test searching local corpus only when papers are ingested."""
    # First ingest a paper to populate both DB and embeddings
    paper = _make_paper("2301.001", "Stellar Pulsation", "About pulsating stars")
    await corpus.ingest_paper(paper)

    results = await corpus.search("pulsation", include_arxiv=False)

    # Should find the ingested paper
    assert len(results) >= 1


async def test_search_deduplicates(corpus, mock_arxiv, embedding_store):
    """Test that duplicate papers from arXiv and local are deduplicated."""
    paper = _make_paper("2301.001", "Duplicate Paper", "Same paper in both sources")

    # Ingest locally first
    await corpus.ingest_paper(paper)

    # Also return from arXiv search
    mock_arxiv.search.return_value = [paper]

    results = await corpus.search("duplicate paper")

    # Should appear only once
    arxiv_ids = [p.arxiv_id for p in results]
    assert arxiv_ids.count("2301.001") == 1


async def test_ingest_paper(corpus, db, embedding_store):
    """Test that ingesting a paper stores it in both SQLite and ChromaDB."""
    paper = _make_paper("2301.001", "Test Paper", "Test abstract content")

    await corpus.ingest_paper(paper)

    # Check SQLite
    db_paper = db.get_paper("arxiv:2301.001")
    assert db_paper is not None
    assert db_paper["title"] == "Test Paper"
    assert db_paper["status"] == "external"

    # Check ChromaDB
    assert embedding_store.count() == 1
    embedded = embedding_store.get_paper("2301.001")
    assert embedded is not None


async def test_ingest_paper_idempotent(corpus, db):
    """Test that ingesting the same paper twice doesn't fail."""
    paper = _make_paper("2301.001", "Test Paper", "Test abstract")

    await corpus.ingest_paper(paper)
    await corpus.ingest_paper(paper)

    # Should still have just one in SQLite
    db_paper = db.get_paper("arxiv:2301.001")
    assert db_paper is not None


async def test_ingest_from_search(corpus, mock_arxiv, embedding_store):
    """Test searching arXiv and ingesting results."""
    papers = [
        _make_paper("2301.001", "Paper One", "First paper"),
        _make_paper("2301.002", "Paper Two", "Second paper"),
    ]
    mock_arxiv.search.return_value = papers

    result = await corpus.ingest_from_search("test query")

    assert len(result) == 2
    assert embedding_store.count() == 2


async def test_build_literature_context(corpus, mock_arxiv):
    """Test building formatted literature context for agents."""
    papers = [
        _make_paper("2301.001", "Cepheid Period-Luminosity Relations", "We study Cepheids..."),
        _make_paper("2301.002", "RR Lyrae in Globular Clusters", "We analyze RR Lyrae..."),
    ]
    mock_arxiv.search.return_value = papers

    context = await corpus.build_literature_context("variable stars")

    # Check formatting
    assert "## Relevant Literature for: variable stars" in context
    assert "Cepheid Period-Luminosity Relations" in context
    assert "RR Lyrae in Globular Clusters" in context
    assert "Author One" in context
    assert "## References" in context
    assert "arXiv:2301.001" in context
    assert "arXiv:2301.002" in context


async def test_build_literature_context_no_results(corpus, mock_arxiv):
    """Test literature context with no results."""
    mock_arxiv.search.return_value = []

    context = await corpus.build_literature_context("nonexistent topic")

    assert "No relevant papers found" in context


async def test_semantic_search(corpus, embedding_store):
    """Test local semantic search."""
    embedding_store.add_paper("p1", "Stars and Galaxies", "About stellar physics")
    embedding_store.add_paper("p2", "Dark Matter Models", "About dark matter")

    results = await corpus.semantic_search("stellar physics")

    assert len(results) >= 1
    assert results[0]["arxiv_id"] == "p1"


async def test_get_paper_from_local(corpus, db):
    """Test getting a paper from local storage."""
    paper = _make_paper("2301.001", "Local Paper", "Stored locally")
    await corpus.ingest_paper(paper)

    result = await corpus.get_paper("2301.001")
    assert result is not None
    assert result.title == "Local Paper"


async def test_get_paper_fallback_to_arxiv(corpus, mock_arxiv):
    """Test falling back to arXiv when paper isn't local."""
    paper = _make_paper("2301.999", "Remote Paper", "From arXiv")
    mock_arxiv.get_paper.return_value = paper

    result = await corpus.get_paper("2301.999")
    assert result is not None
    assert result.title == "Remote Paper"
    mock_arxiv.get_paper.assert_called_with("2301.999")


async def test_context_manager(db, lit_config, storage_config, mock_arxiv, embedding_store):
    """Test async context manager."""
    async with Corpus(
        database=db,
        literature_config=lit_config,
        storage_config=storage_config,
        arxiv_client=mock_arxiv,
        embedding_store=embedding_store,
    ) as c:
        assert c is not None
    mock_arxiv.close.assert_called_once()


async def test_citations_accessible(corpus):
    """Test that the citation tracker is accessible."""
    corpus.citations.add_citation("paper-A", "paper-B")
    count = corpus.citations.get_citation_count("paper-B")
    assert count == 1
