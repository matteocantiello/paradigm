"""Tests for citation tracking."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from paradigm.literature.citations import CitationTracker, extract_citations_from_text
from paradigm.storage.database import Database


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        yield database
        database.close()


@pytest.fixture
def tracker(db):
    """Create a citation tracker with test database."""
    return CitationTracker(db)


def test_add_citation(tracker):
    """Test adding a citation."""
    tracker.add_citation("paper-A", "paper-B", context="As shown in [1]...")

    refs = tracker.get_references("paper-A")
    assert len(refs) == 1
    assert refs[0]["cited_paper_id"] == "paper-B"
    assert refs[0]["context"] == "As shown in [1]..."


def test_duplicate_citation(tracker):
    """Test that duplicate citations are ignored."""
    tracker.add_citation("paper-A", "paper-B")
    tracker.add_citation("paper-A", "paper-B")  # Should be ignored

    refs = tracker.get_references("paper-A")
    assert len(refs) == 1


def test_get_references(tracker):
    """Test getting papers cited by a given paper."""
    tracker.add_citation("paper-A", "paper-B")
    tracker.add_citation("paper-A", "paper-C")
    tracker.add_citation("paper-A", "paper-D")

    refs = tracker.get_references("paper-A")
    assert len(refs) == 3
    cited_ids = {r["cited_paper_id"] for r in refs}
    assert cited_ids == {"paper-B", "paper-C", "paper-D"}


def test_get_cited_by(tracker):
    """Test getting papers that cite a given paper."""
    tracker.add_citation("paper-A", "paper-X")
    tracker.add_citation("paper-B", "paper-X")
    tracker.add_citation("paper-C", "paper-X")

    citing = tracker.get_cited_by("paper-X")
    assert len(citing) == 3
    citing_ids = {c["citing_paper_id"] for c in citing}
    assert citing_ids == {"paper-A", "paper-B", "paper-C"}


def test_citation_count(tracker):
    """Test citation count."""
    assert tracker.get_citation_count("paper-X") == 0

    tracker.add_citation("paper-A", "paper-X")
    tracker.add_citation("paper-B", "paper-X")

    assert tracker.get_citation_count("paper-X") == 2


def test_most_cited(tracker):
    """Test getting most cited papers."""
    # paper-X cited 3 times, paper-Y cited 1 time
    tracker.add_citation("paper-A", "paper-X")
    tracker.add_citation("paper-B", "paper-X")
    tracker.add_citation("paper-C", "paper-X")
    tracker.add_citation("paper-A", "paper-Y")

    most_cited = tracker.get_most_cited(limit=2)
    assert len(most_cited) == 2
    assert most_cited[0]["cited_paper_id"] == "paper-X"
    assert most_cited[0]["citation_count"] == 3
    assert most_cited[1]["cited_paper_id"] == "paper-Y"
    assert most_cited[1]["citation_count"] == 1


def test_bulk_add(tracker):
    """Test bulk citation insertion."""
    citations = [
        ("paper-A", "paper-X", "Context 1"),
        ("paper-A", "paper-Y", "Context 2"),
        ("paper-B", "paper-X", None),
    ]
    tracker.add_citations_bulk(citations)

    refs = tracker.get_references("paper-A")
    assert len(refs) == 2

    count = tracker.get_citation_count("paper-X")
    assert count == 2


def test_no_references(tracker):
    """Test getting references for a paper with none."""
    refs = tracker.get_references("paper-with-no-refs")
    assert refs == []


def test_no_citations(tracker):
    """Test getting citations for a paper with none."""
    citing = tracker.get_cited_by("uncited-paper")
    assert citing == []


# --- Tests for extract_citations_from_text ---


def test_extract_citations_arxiv():
    """Extract arXiv IDs from text."""
    text = "As shown by arXiv:2301.12345, and confirmed in arXiv:2305.00001v2."
    result = extract_citations_from_text(text)
    assert "arXiv:2301.12345" in result
    assert "arXiv:2305.00001v2" in result
    assert len(result) == 2


def test_extract_citations_internal():
    """Extract internal Paradigm paper IDs from text."""
    text = "Building on paper-abc123def456, we extend the results of paper-111222333444."
    result = extract_citations_from_text(text)
    assert "paper-abc123def456" in result
    assert "paper-111222333444" in result
    assert len(result) == 2


def test_extract_citations_mixed():
    """Extract both arXiv and internal IDs from text."""
    text = (
        "Previous work (arXiv:2301.12345) established the baseline. "
        "Our earlier paper paper-aabbccddeeff extended this. "
        "See also arXiv:2302.67890."
    )
    result = extract_citations_from_text(text)
    assert len(result) == 3
    assert "arXiv:2301.12345" in result
    assert "paper-aabbccddeeff" in result
    assert "arXiv:2302.67890" in result


def test_extract_citations_deduplicates():
    """Duplicate citations are returned only once."""
    text = "See arXiv:2301.12345. We confirm arXiv:2301.12345 again."
    result = extract_citations_from_text(text)
    assert result.count("arXiv:2301.12345") == 1
