"""Tests for database operations."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from paradigm.storage.database import Database


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        yield database
        database.close()


def test_database_creation(db):
    """Test database schema creation."""
    # Check that tables exist by querying them
    cursor = db.conn.cursor()

    tables = ["papers", "agents", "threads", "graveyard", "events", "token_usage"]
    for table in tables:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        result = cursor.fetchone()
        assert result is not None, f"Table {table} should exist"


def test_create_and_get_paper(db):
    """Test creating and retrieving a paper."""
    paper_id = "paper-001"
    title = "Test Paper"
    abstract = "This is a test abstract"
    authors = ["agent-001", "agent-002"]
    body = "# Test Paper\n\nThis is the body."

    db.create_paper(
        paper_id=paper_id,
        title=title,
        abstract=abstract,
        authors=authors,
        body=body,
        status="draft",
        keywords=["test", "paper"],
    )

    paper = db.get_paper(paper_id)
    assert paper is not None
    assert paper["id"] == paper_id
    assert paper["title"] == title
    assert paper["abstract"] == abstract
    assert paper["body"] == body
    assert paper["status"] == "draft"


def test_update_paper(db):
    """Test updating paper fields."""
    paper_id = "paper-002"
    db.create_paper(
        paper_id=paper_id,
        title="Original Title",
        abstract="Original abstract",
        authors=["agent-001"],
        body="Original body",
    )

    db.update_paper(paper_id, status="submitted", title="Updated Title")

    paper = db.get_paper(paper_id)
    assert paper["status"] == "submitted"
    assert paper["title"] == "Updated Title"
    assert paper["abstract"] == "Original abstract"  # Unchanged


def test_list_papers(db):
    """Test listing papers with filters."""
    # Create multiple papers
    for i in range(5):
        status = "draft" if i < 3 else "published"
        db.create_paper(
            paper_id=f"paper-{i}",
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            authors=["agent-001"],
            body=f"Body {i}",
            status=status,
        )

    # List all papers
    all_papers = db.list_papers()
    assert len(all_papers) == 5

    # List only drafts
    drafts = db.list_papers(status="draft")
    assert len(drafts) == 3

    # List with limit
    limited = db.list_papers(limit=2)
    assert len(limited) == 2


def test_create_and_get_agent(db):
    """Test creating and retrieving an agent."""
    agent_id = "agent-001"
    skill_profile = "theorist"
    personality = {"risk_tolerance": 0.7, "rigor_preference": 0.9}
    reputation = {"h_index": 5, "papers_published": 10}

    db.create_agent(
        agent_id=agent_id,
        skill_profile=skill_profile,
        personality=personality,
        reputation=reputation,
    )

    agent = db.get_agent(agent_id)
    assert agent is not None
    assert agent["id"] == agent_id
    assert agent["skill_profile"] == skill_profile


def test_update_agent(db):
    """Test updating agent fields."""
    agent_id = "agent-002"
    db.create_agent(
        agent_id=agent_id,
        skill_profile="analyst",
        personality={"risk_tolerance": 0.5},
    )

    new_reputation = {"h_index": 10, "papers_published": 20}
    db.update_agent(agent_id, reputation=new_reputation)

    agent = db.get_agent(agent_id)
    assert agent["skill_profile"] == "analyst"


def test_create_and_get_thread(db):
    """Test creating and retrieving a research thread."""
    thread_id = "thread-001"
    title = "Test Research Thread"
    mode = "directed"
    participants = ["agent-001", "agent-002"]

    db.create_thread(
        thread_id=thread_id,
        title=title,
        mode=mode,
        participants=participants,
    )

    thread = db.get_thread(thread_id)
    assert thread is not None
    assert thread["id"] == thread_id
    assert thread["title"] == title
    assert thread["mode"] == mode
    assert thread["status"] == "active"


def test_update_thread(db):
    """Test updating thread fields."""
    thread_id = "thread-002"
    db.create_thread(
        thread_id=thread_id,
        title="Test Thread",
        mode="explore",
        participants=["agent-001"],
    )

    db.update_thread(
        thread_id,
        status="completed",
        hypothesis="Test hypothesis",
        key_findings=["Finding 1", "Finding 2"],
    )

    thread = db.get_thread(thread_id)
    assert thread["status"] == "completed"
    assert thread["hypothesis"] == "Test hypothesis"


def test_token_usage_tracking(db):
    """Test token usage recording and retrieval."""
    thread_id = "thread-001"
    agent_id = "agent-001"

    # Record some usage
    db.record_token_usage(
        model="claude-sonnet-4-5",
        input_tokens=100,
        output_tokens=200,
        agent_id=agent_id,
        thread_id=thread_id,
    )

    db.record_token_usage(
        model="claude-sonnet-4-5",
        input_tokens=150,
        output_tokens=250,
        agent_id=agent_id,
        thread_id=thread_id,
    )

    # Get usage for thread
    thread_usage = db.get_token_usage(thread_id=thread_id)
    assert thread_usage["input_tokens"] == 250
    assert thread_usage["output_tokens"] == 450
    assert thread_usage["total_tokens"] == 700

    # Get usage for agent
    agent_usage = db.get_token_usage(agent_id=agent_id)
    assert agent_usage["total_tokens"] == 700


def test_graveyard(db):
    """Test graveyard operations."""
    graveyard_id = "grave-001"
    db.add_to_graveyard(
        graveyard_id=graveyard_id,
        entry_type="rejected_paper",
        content="This paper was rejected",
        failure_reason="Lack of novelty",
        lessons_learned="Need more original hypotheses",
    )

    # Verify it was stored (basic check)
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM graveyard WHERE id = ?", (graveyard_id,))
    result = cursor.fetchone()
    assert result is not None
    assert result["type"] == "rejected_paper"
