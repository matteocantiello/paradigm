"""Tests for agent episodic memory system."""

import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from paradigm.agents.memory import (
    AgentMemoryStore,
    Memory,
    ReflectionResult,
    _parse_reflection_response,
    compute_recency_weight,
    format_memory_context,
    rank_memories_with_recency,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    """Create an ephemeral memory store with unique collection per test."""
    name = f"test_memories_{uuid.uuid4().hex[:8]}"
    return AgentMemoryStore(ephemeral=True, collection_name=name)


@pytest.fixture
def sample_memories():
    """Create a set of sample memories."""
    now = datetime.now(UTC)
    return [
        Memory(
            agent_id="theorist-0",
            thread_id="thread-abc",
            memory_type="insight",
            content="The period-luminosity relation breaks down for overtone pulsators",
            created_at=now - timedelta(days=2),
        ),
        Memory(
            agent_id="theorist-0",
            thread_id="thread-abc",
            memory_type="mistake",
            content="Fitting a single power law to multi-modal data obscured bimodal structure",
            created_at=now - timedelta(days=10),
        ),
        Memory(
            agent_id="theorist-0",
            thread_id="thread-def",
            memory_type="strategy",
            content="Starting with a literature survey before proposing hypotheses saved rework",
            created_at=now - timedelta(days=30),
        ),
        Memory(
            agent_id="analyst-0",
            thread_id="thread-abc",
            memory_type="collaboration",
            content="The skeptic's early pushback on sample selection improved final results",
            created_at=now - timedelta(days=5),
        ),
        Memory(
            agent_id="theorist-0",
            thread_id="thread-ghi",
            memory_type="insight",
            content="Stellar pulsation modes are sensitive to metallicity gradients",
            created_at=now,
        ),
    ]


# ---------------------------------------------------------------------------
# AgentMemoryStore tests
# ---------------------------------------------------------------------------


class TestAgentMemoryStore:
    def test_add_and_count(self, store, sample_memories):
        assert store.count() == 0
        store.add_memory(sample_memories[0])
        assert store.count() == 1

    def test_add_memories_bulk(self, store, sample_memories):
        store.add_memories(sample_memories)
        assert store.count() == 5

    def test_add_memories_empty(self, store):
        store.add_memories([])
        assert store.count() == 0

    def test_search_basic(self, store, sample_memories):
        store.add_memories(sample_memories)
        results = store.search("pulsation period luminosity")
        assert len(results) > 0
        # Should have score and metadata
        assert "score" in results[0]
        assert "metadata" in results[0]

    def test_search_agent_filter(self, store, sample_memories):
        store.add_memories(sample_memories)
        results = store.search("research", agent_id="analyst-0")
        assert all(r["metadata"]["agent_id"] == "analyst-0" for r in results)

    def test_search_type_filter(self, store, sample_memories):
        store.add_memories(sample_memories)
        results = store.search("research", memory_type="insight")
        assert all(r["metadata"]["memory_type"] == "insight" for r in results)

    def test_search_combined_filters(self, store, sample_memories):
        store.add_memories(sample_memories)
        results = store.search("pulsation", agent_id="theorist-0", memory_type="insight")
        assert len(results) > 0
        for r in results:
            assert r["metadata"]["agent_id"] == "theorist-0"
            assert r["metadata"]["memory_type"] == "insight"

    def test_search_empty_store(self, store):
        results = store.search("anything")
        assert results == []

    def test_get_memories_for_agent(self, store, sample_memories):
        store.add_memories(sample_memories)
        results = store.get_memories_for_agent("theorist-0")
        assert len(results) == 4  # 4 theorist memories
        # Should be sorted newest first
        epochs = [r["metadata"]["created_at_epoch"] for r in results]
        assert epochs == sorted(epochs, reverse=True)

    def test_get_memories_for_agent_empty(self, store, sample_memories):
        store.add_memories(sample_memories)
        results = store.get_memories_for_agent("nonexistent-0")
        assert results == []

    def test_delete_older_than(self, store, sample_memories):
        store.add_memories(sample_memories)
        assert store.count() == 5
        cutoff = datetime.now(UTC) - timedelta(days=7)
        deleted = store.delete_older_than(cutoff)
        assert deleted == 2  # 10-day and 30-day old memories
        assert store.count() == 3

    def test_delete_older_than_none(self, store, sample_memories):
        store.add_memories(sample_memories)
        cutoff = datetime.now(UTC) - timedelta(days=365)
        deleted = store.delete_older_than(cutoff)
        assert deleted == 0
        assert store.count() == 5

    def test_upsert_deduplicates(self, store, sample_memories):
        mem = sample_memories[0]
        store.add_memory(mem)
        store.add_memory(mem)
        assert store.count() == 1

    def test_persistent_store_requires_path(self):
        with pytest.raises(ValueError, match="vector_db_path required"):
            AgentMemoryStore(vector_db_path=None, ephemeral=False)


# ---------------------------------------------------------------------------
# Recency decay tests
# ---------------------------------------------------------------------------


class TestRecencyDecay:
    def test_brand_new_memory(self):
        now = time.time()
        weight = compute_recency_weight(now, now)
        assert weight == pytest.approx(1.0)

    def test_one_half_life_old(self):
        now = time.time()
        half_life = 30.0
        created = now - (half_life * 86400)
        weight = compute_recency_weight(created, now, half_life)
        assert weight == pytest.approx(0.5)

    def test_two_half_lives_old(self):
        now = time.time()
        half_life = 30.0
        created = now - (2 * half_life * 86400)
        weight = compute_recency_weight(created, now, half_life)
        assert weight == pytest.approx(0.25)

    def test_future_memory_clamps_to_1(self):
        now = time.time()
        future = now + 86400
        weight = compute_recency_weight(future, now)
        assert weight == pytest.approx(1.0)

    def test_rank_memories_with_recency(self):
        now = datetime.now(UTC).timestamp()
        results = [
            {
                "id": "old-high-sim",
                "score": 0.95,
                "metadata": {"created_at_epoch": now - 60 * 86400},  # 60 days old
            },
            {
                "id": "new-low-sim",
                "score": 0.50,
                "metadata": {"created_at_epoch": now - 1 * 86400},  # 1 day old
            },
            {
                "id": "medium-medium",
                "score": 0.70,
                "metadata": {"created_at_epoch": now - 15 * 86400},  # 15 days old
            },
        ]

        ranked = rank_memories_with_recency(results, half_life_days=30.0, top_k=2)
        assert len(ranked) == 2
        # All should have combined_score
        assert all("combined_score" in r for r in ranked)
        # Scores should be descending
        assert ranked[0]["combined_score"] >= ranked[1]["combined_score"]

    def test_rank_empty(self):
        assert rank_memories_with_recency([], top_k=5) == []


# ---------------------------------------------------------------------------
# Context formatting tests
# ---------------------------------------------------------------------------


class TestFormatMemoryContext:
    def test_empty_memories(self):
        assert format_memory_context([]) == ""

    def test_basic_formatting(self):
        memories = [
            {
                "document": "[insight] Pulsation modes depend on metallicity",
                "metadata": {
                    "memory_type": "insight",
                    "created_at": "2025-01-15T00:00:00+00:00",
                },
                "combined_score": 0.85,
            },
        ]
        text = format_memory_context(memories)
        assert "## Agent Memory" in text
        assert "**[insight]**" in text
        assert "Pulsation modes depend on metallicity" in text
        assert "0.85" in text

    def test_truncation(self):
        memories = [
            {
                "document": f"[insight] {'x' * 500}",
                "metadata": {
                    "memory_type": "insight",
                    "created_at": "2025-01-15T00:00:00+00:00",
                },
                "combined_score": 0.5,
            }
            for _ in range(10)
        ]
        text = format_memory_context(memories, max_chars=200)
        assert len(text) <= 250  # Some slack for truncation message
        assert "*(truncated)*" in text


# ---------------------------------------------------------------------------
# Reflection parsing tests
# ---------------------------------------------------------------------------


class TestReflectionParsing:
    def test_parse_standard_response(self):
        text = """\
[insight] The period-luminosity relation breaks down for overtone pulsators
[mistake] Fitting a single power law to multi-modal data obscured bimodal structure
[strategy] Starting with a literature survey before hypotheses saved rework
[collaboration] The skeptic's early pushback improved final results

SUMMARY: Productive cycle that identified key bimodal structure in pulsation data.
"""
        result = _parse_reflection_response(text, "theorist-0", "thread-abc")
        assert result.agent_id == "theorist-0"
        assert len(result.memories) == 4
        assert result.memories[0].memory_type == "insight"
        assert result.memories[1].memory_type == "mistake"
        assert result.memories[2].memory_type == "strategy"
        assert result.memories[3].memory_type == "collaboration"
        assert "bimodal" in result.summary

    def test_parse_empty_response(self):
        result = _parse_reflection_response("", "agent-0", "thread-0")
        assert result.memories == []
        assert result.summary == ""

    def test_parse_skips_invalid_types(self):
        text = """\
[insight] Valid insight
[invalid_type] Should be skipped
[strategy] Valid strategy
"""
        result = _parse_reflection_response(text, "agent-0", "thread-0")
        assert len(result.memories) == 2

    def test_parse_skips_empty_content(self):
        text = "[insight] \n[mistake] actual mistake\n"
        result = _parse_reflection_response(text, "agent-0", "thread-0")
        assert len(result.memories) == 1
        assert result.memories[0].memory_type == "mistake"


# ---------------------------------------------------------------------------
# Integration: store + ranking
# ---------------------------------------------------------------------------


class TestStoreWithRanking:
    def test_search_and_rank(self, store, sample_memories):
        store.add_memories(sample_memories)

        raw = store.search(
            query="pulsation period luminosity relation",
            agent_id="theorist-0",
            n_results=10,
        )
        assert len(raw) > 0

        ranked = rank_memories_with_recency(raw, half_life_days=30.0, top_k=3)
        assert len(ranked) <= 3
        # Newest relevant memory should rank higher than old ones with same similarity
        for r in ranked:
            assert "combined_score" in r
            assert "recency_weight" in r

    def test_format_after_rank(self, store, sample_memories):
        store.add_memories(sample_memories)
        raw = store.search("stellar pulsation", agent_id="theorist-0", n_results=10)
        ranked = rank_memories_with_recency(raw, top_k=3)
        text = format_memory_context(ranked, max_chars=2000)
        assert "## Agent Memory" in text
