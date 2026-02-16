"""Shared fixtures for orchestrator-related tests.

Helper functions live in ``tests/helpers.py`` and are imported directly
by test files that need them.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from helpers import make_mock_agent

from paradigm.logging.events import EventLogger
from paradigm.storage.database import Database

# ---------------------------------------------------------------------------
# Shared fixtures (auto-discovered by pytest)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database."""
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def tmp_logger(tmp_path):
    """Create a temporary event logger."""
    return EventLogger(tmp_path / "events.jsonl")


@pytest.fixture
def mock_factory():
    """Create a mock AgentFactory that produces mock agents."""
    factory = MagicMock()

    def _create_team(roles, skill_mode="default"):
        return [make_mock_agent(f"{role}-0", role) for role in roles]

    factory.create_team = MagicMock(side_effect=_create_team)
    return factory


@pytest.fixture
def mock_corpus():
    """Create a mock Corpus with all search methods stubbed."""
    corpus = MagicMock()
    corpus.build_literature_context = AsyncMock(return_value="## Literature\nNo papers found.")
    corpus.search = AsyncMock(return_value=[])
    corpus.ingest_internal_paper = MagicMock()
    return corpus


@pytest.fixture
def display():
    """Create a DisplayManager in verbose mode (plain text fallback)."""
    from paradigm.display import DisplayManager

    return DisplayManager(verbose=True)
