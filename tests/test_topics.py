"""Tests for topic classification + topic persistence (the badge feature)."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from paradigm.agents.topics import VALID_TOPICS, _parse_topics, classify_topics
from paradigm.storage.database import Database

# --- parsing -------------------------------------------------------------


class TestParseTopics:
    def test_clean_keys_preserve_order(self):
        assert _parse_topics("astro, cs", 3) == ["astro", "cs"]

    def test_natural_language_names_map_to_keys(self):
        assert _parse_topics("Economics, Astrophysics", 3) == ["econ", "astro"]

    def test_empty_and_junk_fall_back_to_other(self):
        assert _parse_topics("", 3) == ["other"]
        assert _parse_topics("zzz qqq nothing", 3) == ["other"]

    def test_other_dropped_when_a_real_field_is_present(self):
        # Cross-pollination shows real fields; the catch-all is discarded.
        assert _parse_topics("other, astro", 3) == ["astro"]

    def test_dedupe_and_cap(self):
        assert _parse_topics("astro astro astro", 3) == ["astro"]
        assert _parse_topics("cs, math, stat, bio", 2) == ["cs", "math"]

    def test_all_keys_are_valid(self):
        for key in _parse_topics("astro physics cs math stat bio med econ eess", 9):
            assert key in VALID_TOPICS


# --- classifier (no network — fake provider) -----------------------------


class _FakeProvider:
    default_model = "fake-model"

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls = 0

    def complete(self, *, model, max_tokens, temperature, system, messages):
        self.calls += 1
        return (self._reply, 5, 3)


class TestClassifyTopics:
    @pytest.mark.asyncio
    async def test_cross_pollination_returns_multiple(self):
        provider = _FakeProvider("econ, astro")
        out = await classify_topics(
            "An economics study using astrophysics techniques",
            provider=provider,
            model="fake-model",
            max_topics=3,
        )
        assert out == ["econ", "astro"]
        assert provider.calls == 1

    @pytest.mark.asyncio
    async def test_empty_text_skips_the_model(self):
        provider = _FakeProvider("astro")
        out = await classify_topics("   ", provider=provider, model="fake-model")
        assert out == ["other"]
        assert provider.calls == 0  # short-circuits without an LLM call

    @pytest.mark.asyncio
    async def test_unparseable_reply_degrades_to_other(self):
        provider = _FakeProvider("I'm not sure, could be anything really")
        out = await classify_topics("something", provider=provider, model="fake-model")
        assert out == ["other"]


# --- persistence round-trip ----------------------------------------------


@pytest.fixture
def db():
    with TemporaryDirectory() as tmpdir:
        database = Database(Path(tmpdir) / "test.db")
        yield database
        database.close()


class TestTopicsPersistence:
    def test_paper_topics_round_trip(self, db):
        db.create_paper(
            paper_id="paper-t1",
            title="T",
            abstract="A",
            authors=["a-0"],
            body="body",
            status="draft",
        )
        db.update_paper("paper-t1", topics=["econ", "astro"])
        row = db.get_paper("paper-t1")
        # Stored as a JSON string column; deserializes back to the list.
        assert json.loads(row["topics"]) == ["econ", "astro"]

    def test_thread_topics_round_trip(self, db):
        db.create_thread(
            thread_id="thread-t1",
            title="T",
            mode="directed",
            participants=["theorist-0"],
        )
        db.update_thread("thread-t1", topics=["astro"])
        row = db.get_thread("thread-t1")
        assert json.loads(row["topics"]) == ["astro"]
