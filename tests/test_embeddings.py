"""Tests for ChromaDB embedding store."""

import uuid
from datetime import UTC, datetime

import pytest

from paradigm.literature.arxiv import ArxivPaper
from paradigm.literature.embeddings import EmbeddingStore


@pytest.fixture
def store():
    """Create an ephemeral embedding store with unique collection per test."""
    return EmbeddingStore(ephemeral=True, collection_name=f"test_{uuid.uuid4().hex}")


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


def test_add_and_search(store):
    """Test adding papers and searching by semantic similarity."""
    store.add_paper(
        arxiv_id="2301.001",
        title="Stellar Pulsation in Cepheids",
        abstract="We study pulsation modes in classical Cepheid variable stars.",
    )
    store.add_paper(
        arxiv_id="2301.002",
        title="Dark Matter Annihilation Signals",
        abstract="We search for dark matter annihilation in gamma-ray observations.",
    )

    results = store.search("variable stars and pulsation", n_results=2)
    assert len(results) == 2
    # The stellar pulsation paper should rank higher for this query
    assert results[0]["arxiv_id"] == "2301.001"


def test_add_papers_bulk(store):
    """Test bulk adding papers."""
    papers = [
        _make_paper("2301.001", "Paper One", "First abstract about stars"),
        _make_paper("2301.002", "Paper Two", "Second abstract about galaxies"),
        _make_paper("2301.003", "Paper Three", "Third abstract about planets"),
    ]

    store.add_papers(papers)
    assert store.count() == 3


def test_deduplication(store):
    """Test that adding the same paper twice doesn't create duplicates."""
    store.add_paper(
        arxiv_id="2301.001",
        title="Original Title",
        abstract="Original abstract",
    )
    store.add_paper(
        arxiv_id="2301.001",
        title="Updated Title",
        abstract="Updated abstract",
    )

    assert store.count() == 1

    # Should have the updated version
    paper = store.get_paper("2301.001")
    assert paper is not None
    assert "Updated" in paper["document"]


def test_get_paper(store):
    """Test retrieving a specific paper by ID."""
    store.add_paper(
        arxiv_id="2301.001",
        title="Test Paper",
        abstract="Test abstract content",
        metadata={"title": "Test Paper", "primary_category": "astro-ph.SR"},
    )

    paper = store.get_paper("2301.001")
    assert paper is not None
    assert paper["arxiv_id"] == "2301.001"
    assert "Test Paper" in paper["document"]
    assert paper["metadata"]["primary_category"] == "astro-ph.SR"


def test_get_paper_not_found(store):
    """Test that get_paper returns None for missing papers."""
    result = store.get_paper("nonexistent")
    assert result is None


def test_delete_paper(store):
    """Test deleting a paper."""
    store.add_paper(
        arxiv_id="2301.001",
        title="To Be Deleted",
        abstract="This paper will be deleted",
    )
    assert store.count() == 1

    store.delete_paper("2301.001")
    assert store.count() == 0
    assert store.get_paper("2301.001") is None


def test_count(store):
    """Test the count method."""
    assert store.count() == 0

    store.add_paper("p1", "Title 1", "Abstract 1")
    assert store.count() == 1

    store.add_paper("p2", "Title 2", "Abstract 2")
    assert store.count() == 2


def test_search_empty_store(store):
    """Test searching an empty store."""
    results = store.search("anything")
    assert results == []


def test_search_with_metadata(store):
    """Test adding papers with metadata via add_papers."""
    papers = [
        _make_paper("2301.001", "Stars Paper", "About stars", "astro-ph.SR"),
        _make_paper("2301.002", "Galaxies Paper", "About galaxies", "astro-ph.GA"),
    ]
    store.add_papers(papers)

    results = store.search("stars", n_results=2)
    assert len(results) == 2
    # All results should have metadata
    for r in results:
        assert "metadata" in r
