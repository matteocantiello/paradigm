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
    arxiv_ids = [p.id for p in results]
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


async def test_search_excludes_internal_papers(corpus, db, embedding_store):
    """Internal papers (paper-*) are excluded from search() results to prevent self-citation."""
    # Create the paper in the database first (as publish_paper does)
    db.create_paper(
        paper_id="paper-abc123def456",
        title="Internal Stellar Paper",
        abstract="A study of stellar oscillations produced by Paradigm.",
        authors=["theorist-0", "analyst-0"],
        body="Full paper body...",
        status="published",
    )
    # Ingest into ChromaDB
    corpus.ingest_internal_paper(
        paper_id="paper-abc123def456",
        title="Internal Stellar Paper",
        abstract="A study of stellar oscillations produced by Paradigm.",
        authors=["theorist-0", "analyst-0"],
    )

    results = await corpus.search("stellar oscillations", include_arxiv=False)

    # Internal paper-* IDs should be filtered out
    found_ids = [p.id for p in results]
    assert "paper-abc123def456" not in found_ids


async def test_build_literature_context_excludes_internal(corpus, db, mock_arxiv):
    """build_literature_context() excludes internal paper-* IDs from search results."""
    db.create_paper(
        paper_id="paper-111222333444",
        title="Paradigm Paper on Convection",
        abstract="We study convective mixing.",
        authors=["writer-0"],
        body="...",
        status="published",
    )
    corpus.ingest_internal_paper(
        paper_id="paper-111222333444",
        title="Paradigm Paper on Convection",
        abstract="We study convective mixing.",
        authors=["writer-0"],
    )
    mock_arxiv.search.return_value = []

    context = await corpus.build_literature_context("convective mixing", include_arxiv=False)

    # Internal papers should be filtered out — no results
    assert "No relevant papers found" in context
    assert "paper-111222333444" not in context


async def test_search_filters_internal_keeps_arxiv(corpus, db, mock_arxiv, embedding_store):
    """Search results exclude internal paper-* but keep arXiv papers."""
    # Internal paper (should be filtered)
    db.create_paper(
        paper_id="paper-aabbccddeeff",
        title="Internal Results",
        abstract="Internal abstract about mixing.",
        authors=["analyst-0"],
        body="...",
        status="published",
    )
    corpus.ingest_internal_paper(
        paper_id="paper-aabbccddeeff",
        title="Internal Results",
        abstract="Internal abstract about mixing.",
        authors=["analyst-0"],
    )

    # arXiv paper (should be kept)
    arxiv_paper = _make_paper("2401.001", "External Mixing Study", "About stellar mixing")
    mock_arxiv.search.return_value = [arxiv_paper]

    results = await corpus.search("mixing", include_arxiv=True)

    ids = [p.id for p in results]
    assert "paper-aabbccddeeff" not in ids
    assert "2401.001" in ids


async def test_search_excludes_non_published_internal(corpus, db, embedding_store):
    """Internal papers with non-published status are excluded from search results."""
    # Create a draft paper (not published)
    db.create_paper(
        paper_id="paper-draft111222",
        title="Draft Paper on Mixing",
        abstract="A draft study about mixing processes.",
        authors=["theorist-0"],
        body="Draft body...",
        status="draft",
    )
    # Ingest into ChromaDB (simulates a bug where draft gets into embeddings)
    corpus.ingest_internal_paper(
        paper_id="paper-draft111222",
        title="Draft Paper on Mixing",
        abstract="A draft study about mixing processes.",
        authors=["theorist-0"],
    )

    # Also create a rejected paper
    db.create_paper(
        paper_id="paper-rejected333",
        title="Rejected Mixing Paper",
        abstract="A rejected paper about mixing.",
        authors=["analyst-0"],
        body="Rejected body...",
        status="rejected",
    )
    corpus.ingest_internal_paper(
        paper_id="paper-rejected333",
        title="Rejected Mixing Paper",
        abstract="A rejected paper about mixing.",
        authors=["analyst-0"],
    )

    results = await corpus.search("mixing", include_arxiv=False)

    found_ids = [p.id for p in results]
    assert "paper-draft111222" not in found_ids
    assert "paper-rejected333" not in found_ids


async def test_search_includes_external_papers(corpus, db, embedding_store):
    """External (arXiv-ingested) papers with 'external' status are included."""
    # Ingest via the normal arXiv path (sets status='external')
    paper = _make_paper("2501.001", "External Mixing Study", "About stellar mixing processes")
    await corpus.ingest_paper(paper)

    results = await corpus.search("mixing", include_arxiv=False)

    found_ids = [p.id for p in results]
    assert "2501.001" in found_ids


async def test_search_interleaves_local_and_arxiv(corpus, db, mock_arxiv, embedding_store):
    """Search returns both local and arXiv results without local crowding out arXiv."""
    # Ingest 3 local papers
    for i in range(3):
        paper = _make_paper(f"local.{i:03d}", f"Local Paper {i}", f"About local topic {i}")
        await corpus.ingest_paper(paper)

    # arXiv returns 3 different papers
    arxiv_papers = [
        _make_paper(f"arxiv.{i:03d}", f"ArXiv Paper {i}", f"About arxiv topic {i}")
        for i in range(3)
    ]
    mock_arxiv.search.return_value = arxiv_papers

    # Search with max_results=5 — should get locals + arXiv, not just locals
    results = await corpus.search("topic", max_results=5)

    arxiv_ids = {p.id for p in results}

    # Should have at least some arXiv papers (not all crowded out by local)
    arxiv_count = sum(1 for pid in arxiv_ids if pid.startswith("arxiv."))
    local_count = sum(1 for pid in arxiv_ids if pid.startswith("local."))

    assert arxiv_count > 0, "arXiv results should not be crowded out by local results"
    assert local_count > 0, "local results should be present"
    assert len(results) <= 5


async def test_search_arxiv_only_no_local_crowding(corpus, mock_arxiv, embedding_store):
    """With no local papers, arXiv results fill the entire result list."""
    arxiv_papers = [
        _make_paper(f"2401.{i:03d}", f"ArXiv Paper {i}", f"Abstract {i}") for i in range(7)
    ]
    mock_arxiv.search.return_value = arxiv_papers

    results = await corpus.search("topic", max_results=5)

    assert len(results) == 5
    # All should be arXiv papers
    for p in results:
        assert p.id.startswith("2401.")


# --- Semantic Scholar integration tests ---


async def test_get_references_delegates_to_s2(corpus):
    """Verify Corpus.get_references delegates to SemanticScholarClient."""
    from paradigm.literature.semantic_scholar import SemanticPaper

    mock_paper = SemanticPaper(
        paper_id="s2-abc",
        arxiv_id="2301.001",
        title="Referenced Paper",
        authors=["Author"],
        abstract="Abstract",
        year=2023,
        citation_count=5,
        url="https://s2.org/paper",
    )
    corpus._s2 = AsyncMock()
    corpus._s2.get_references = AsyncMock(return_value=[mock_paper])

    results = await corpus.get_references("2301.12345", max_results=10)
    assert len(results) == 1
    assert results[0].title == "Referenced Paper"
    corpus._s2.get_references.assert_called_once_with("2301.12345", limit=10)


async def test_get_citations_delegates_to_s2(corpus):
    """Verify Corpus.get_citations delegates to SemanticScholarClient."""
    from paradigm.literature.semantic_scholar import SemanticPaper

    mock_paper = SemanticPaper(
        paper_id="s2-def",
        arxiv_id="2401.001",
        title="Citing Paper",
        authors=["Author"],
        abstract="Abstract",
        year=2024,
        citation_count=12,
        url="https://s2.org/paper",
    )
    corpus._s2 = AsyncMock()
    corpus._s2.get_citations = AsyncMock(return_value=[mock_paper])

    results = await corpus.get_citations("2301.12345", max_results=5)
    assert len(results) == 1
    assert results[0].title == "Citing Paper"
    corpus._s2.get_citations.assert_called_once_with("2301.12345", limit=5)


async def test_read_paper_from_db(corpus, db):
    """Returns cached body text from database."""
    # Ingest a paper with body text
    paper = _make_paper("2301.001", "Cached Paper", "Abstract text")
    paper = paper.model_copy(
        update={"body": "Abstract\nThis is the abstract.\n\nIntroduction\nThis is the intro."}
    )
    await corpus.ingest_paper(paper, fetch_pdf=False)
    # Update body in DB
    db.update_paper("arxiv:2301.001", body=paper.body)

    result = await corpus.read_paper("2301.001", max_chars=8000)
    assert result is not None
    title, text = result
    assert title == "Cached Paper"
    assert len(text) > 0


async def test_read_paper_from_pdf(corpus, mock_arxiv):
    """Falls back to PDF fetch when not in DB."""
    paper = _make_paper("2301.999", "PDF Paper", "Abstract from PDF")
    mock_arxiv.get_paper = AsyncMock(return_value=paper)
    mock_arxiv.fetch_pdf_text = AsyncMock(
        return_value="Abstract\nThis is the abstract.\n\nIntroduction\nIntro text here."
    )

    result = await corpus.read_paper("2301.999", max_chars=8000)
    assert result is not None
    title, text = result
    assert title == "PDF Paper"
    assert len(text) > 0
    mock_arxiv.fetch_pdf_text.assert_called_once()
