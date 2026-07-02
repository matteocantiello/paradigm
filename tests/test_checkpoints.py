"""Tests for checkpoint compression."""

import json
from unittest.mock import MagicMock

import pytest

from paradigm.storage.checkpoints import Checkpoint, CheckpointManager
from paradigm.storage.database import Database


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database."""
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def mock_provider():
    """Create a mock LLM provider for checkpoint tests."""
    provider = MagicMock()
    provider.complete.return_value = ("", 100, 50)
    provider.default_model = "claude-sonnet-4-5-20250929"
    return provider


class TestCheckpoint:
    """Test Checkpoint model."""

    def test_to_context_string_full(self):
        """Full checkpoint renders all sections."""
        cp = Checkpoint(
            thread_id="t1",
            phase="ideation",
            round_number=5,
            hypothesis="Stars vary because of convection",
            key_findings=["Finding A", "Finding B"],
            open_questions=["Question 1"],
            next_steps=["Step 1", "Step 2"],
            conversation_summary="The team discussed stellar variability.",
        )
        text = cp.to_context_string()
        assert "Phase: ideation" in text
        assert "Round: 5" in text
        assert "Stars vary because of convection" in text
        assert "- Finding A" in text
        assert "- Finding B" in text
        assert "- Question 1" in text
        assert "- Step 1" in text
        assert "stellar variability" in text

    def test_to_context_string_minimal(self):
        """Minimal checkpoint (no hypothesis) still renders."""
        cp = Checkpoint(
            thread_id="t1",
            phase="seeding",
            round_number=0,
        )
        text = cp.to_context_string()
        assert "Phase: seeding" in text
        assert "Hypothesis" not in text

    def test_to_context_string_no_optional_sections(self):
        """Empty lists don't produce section headers."""
        cp = Checkpoint(
            thread_id="t1",
            phase="ideation",
            round_number=1,
            hypothesis="Test",
            key_findings=[],
            open_questions=[],
            next_steps=[],
        )
        text = cp.to_context_string()
        assert "Key Findings" not in text
        assert "Open Questions" not in text
        assert "Next Steps" not in text


class TestCheckpointManagerParseSummary:
    """Test _parse_summary static method."""

    def test_valid_json(self):
        """Parses valid JSON correctly."""
        data = {
            "hypothesis": "Test hypothesis",
            "key_findings": ["f1", "f2"],
            "open_questions": ["q1"],
            "next_steps": ["s1"],
            "conversation_summary": "Summary text",
        }
        result = CheckpointManager._parse_summary(json.dumps(data))
        assert result["hypothesis"] == "Test hypothesis"
        assert len(result["key_findings"]) == 2

    def test_json_with_markdown_fences(self):
        """Strips markdown code fences."""
        data = {
            "hypothesis": "H1",
            "key_findings": [],
            "open_questions": [],
            "next_steps": [],
            "conversation_summary": "S",
        }
        raw = f"```json\n{json.dumps(data)}\n```"
        result = CheckpointManager._parse_summary(raw)
        assert result["hypothesis"] == "H1"

    def test_malformed_json_fallback(self):
        """Falls back gracefully on invalid JSON."""
        result = CheckpointManager._parse_summary("This is not JSON at all")
        assert result["hypothesis"] is None
        assert result["key_findings"] == []
        assert "This is not JSON" in result["conversation_summary"]


class TestCheckpointManagerRoundTrip:
    """Test save/load round-trip via database."""

    def test_save_and_load(self, tmp_db, mock_provider):
        """Checkpoint data persists through save/load cycle."""
        # Create a thread first
        tmp_db.create_thread("t1", "Test Thread", "directed", ["agent-0"])

        mgr = CheckpointManager(tmp_db, provider=mock_provider)

        # Simulate what create_checkpoint does to the DB
        tmp_db.update_thread(
            "t1",
            current_phase="ideation",
            hypothesis="Test hypothesis",
            key_findings=["finding 1"],
            open_questions=["question 1"],
            next_steps=["step 1"],
            checkpoint_summary="The team discussed things.",
        )

        # Load it back
        loaded = mgr.load_checkpoint("t1")
        assert loaded is not None
        assert loaded.thread_id == "t1"
        assert loaded.phase == "ideation"
        assert loaded.hypothesis == "Test hypothesis"
        assert loaded.key_findings == ["finding 1"]
        assert loaded.open_questions == ["question 1"]
        assert loaded.next_steps == ["step 1"]
        assert loaded.conversation_summary == "The team discussed things."

    def test_load_nonexistent_thread(self, tmp_db, mock_provider):
        """Loading a nonexistent thread returns None."""
        mgr = CheckpointManager(tmp_db, provider=mock_provider)
        assert mgr.load_checkpoint("nonexistent") is None

    def test_load_thread_without_checkpoint(self, tmp_db, mock_provider):
        """Thread with no checkpoint data returns None."""
        tmp_db.create_thread("t2", "Empty Thread", "directed", ["agent-0"])
        mgr = CheckpointManager(tmp_db, provider=mock_provider)
        assert mgr.load_checkpoint("t2") is None


class TestCheckpointManagerCreateCheckpoint:
    """Test create_checkpoint with mocked provider."""

    @pytest.mark.asyncio
    async def test_create_checkpoint_mocked(self, tmp_db, mock_provider):
        """create_checkpoint calls provider and persists result."""
        tmp_db.create_thread("t1", "Test", "directed", ["agent-0"])

        # Configure mock provider response
        checkpoint_json = json.dumps(
            {
                "hypothesis": "H1",
                "key_findings": ["f1"],
                "open_questions": ["q1"],
                "next_steps": ["s1"],
                "conversation_summary": "Summary",
            }
        )
        mock_provider.complete.return_value = (checkpoint_json, 100, 50)

        mgr = CheckpointManager(tmp_db, provider=mock_provider)
        cp = await mgr.create_checkpoint(
            thread_id="t1",
            phase="ideation",
            round_number=5,
            messages=[{"from": "agent-0", "content": "Test message"}],
        )

        assert cp.hypothesis == "H1"
        assert cp.key_findings == ["f1"]
        assert cp.thread_id == "t1"

        # Verify DB was updated
        thread = tmp_db.get_thread("t1")
        assert thread["checkpoint_summary"] == "Summary"
        assert thread["hypothesis"] == "H1"

        # Verify token usage was recorded
        usage = tmp_db.get_token_usage(thread_id="t1")
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50


class TestDegenerateCompressionRetry:
    """A large context that 'compresses' to no findings and no summary is a failed
    generation (seen live: 30-47k-token contexts -> ~80-token checkpoints that
    downstream agents resume from) — retried once, richer attempt wins."""

    @pytest.mark.asyncio
    async def test_degenerate_compression_retried(self, tmp_db, mock_provider):
        tmp_db.create_thread("t1", "Test Thread", "directed", ["agent-0"])
        good = json.dumps(
            {
                "hypothesis": "h",
                "key_findings": ["a real finding"],
                "open_questions": [],
                "next_steps": [],
                "conversation_summary": "The team found things.",
            }
        )
        mock_provider.complete.side_effect = [("{}", 30000, 80), (good, 30000, 500)]
        mgr = CheckpointManager(tmp_db, provider=mock_provider)
        messages = [{"from": "theorist-0", "content": "x" * 6000}]
        cp = await mgr.create_checkpoint("t1", "ideation", 1, messages)
        assert mock_provider.complete.call_count == 2
        assert cp.key_findings == ["a real finding"]
        assert cp.conversation_summary == "The team found things."

    @pytest.mark.asyncio
    async def test_small_context_not_retried(self, tmp_db, mock_provider):
        tmp_db.create_thread("t2", "Test Thread", "directed", ["agent-0"])
        mock_provider.complete.return_value = ("{}", 100, 10)
        mgr = CheckpointManager(tmp_db, provider=mock_provider)
        cp = await mgr.create_checkpoint("t2", "ideation", 1, [{"from": "a", "content": "hi"}])
        assert mock_provider.complete.call_count == 1
        assert cp.key_findings == []

    @pytest.mark.asyncio
    async def test_degenerate_retry_keeps_first_when_retry_no_better(self, tmp_db, mock_provider):
        tmp_db.create_thread("t3", "Test Thread", "directed", ["agent-0"])
        mock_provider.complete.side_effect = [("{}", 30000, 80), ("{}", 30000, 80)]
        mgr = CheckpointManager(tmp_db, provider=mock_provider)
        messages = [{"from": "a", "content": "x" * 6000}]
        cp = await mgr.create_checkpoint("t3", "ideation", 1, messages)
        assert mock_provider.complete.call_count == 2
        assert cp.key_findings == []  # degrades gracefully, no crash
