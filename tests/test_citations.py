"""Tests for citation tracking."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from paradigm.literature.citations import CitationTracker
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
