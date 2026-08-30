"""Prompt-cache instrumentation + system-prompt caching (Levers: measure, cache)."""

from __future__ import annotations

from unittest.mock import MagicMock

from paradigm.agents.providers import (
    _CACHE_MIN_CHARS,
    LLMResult,
    _cacheable_system,
    _int_or_zero,
)


class TestLLMResult:
    def test_unpacks_as_three_tuple(self):
        r = LLMResult("hi", 100, 20, cache_read_tokens=900, cache_write_tokens=50)
        text, i, o = r
        assert (text, i, o) == ("hi", 100, 20)

    def test_carries_cache_attrs(self):
        r = LLMResult("hi", 100, 20, cache_read_tokens=900, cache_write_tokens=50)
        assert r.cache_read_tokens == 900 and r.cache_write_tokens == 50

    def test_equals_plain_tuple_ignoring_attrs(self):
        # Old callers comparing against a 3-tuple keep working.
        assert LLMResult("x", 1, 2) == ("x", 1, 2)

    def test_defaults_zero(self):
        r = LLMResult("x", 1, 2)
        assert r.cache_read_tokens == 0 and r.cache_write_tokens == 0


class TestCacheableSystem:
    def test_short_system_stays_plain_string(self):
        assert _cacheable_system("short") == "short"

    def test_long_system_becomes_cache_controlled_block(self):
        out = _cacheable_system("x" * (_CACHE_MIN_CHARS + 1))
        assert isinstance(out, list)
        assert out[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        assert out[0]["text"].startswith("x")

    def test_empty_system_unchanged(self):
        assert _cacheable_system("") == ""


class TestIntOrZero:
    def test_coerces_non_numeric_to_zero(self):
        assert _int_or_zero(MagicMock()) == 0
        assert _int_or_zero(None) == 0
        assert _int_or_zero(-5) == 0
        assert _int_or_zero(42) == 42


class TestAnthropicCaptureCacheTokens:
    def test_complete_returns_cache_tokens(self):
        from paradigm.agents.providers import AnthropicProvider

        prov = AnthropicProvider.__new__(AnthropicProvider)
        resp = MagicMock()
        resp.content = [MagicMock(text="answer")]
        resp.usage.input_tokens = 30
        resp.usage.output_tokens = 12
        resp.usage.cache_read_input_tokens = 900
        resp.usage.cache_creation_input_tokens = 40
        client = MagicMock()
        client.messages.create.return_value = resp
        prov._client = client
        r = prov.complete(model="claude-x", system="s", messages=[], max_tokens=100)
        assert tuple(r) == ("answer", 30, 12)
        assert r.cache_read_tokens == 900 and r.cache_write_tokens == 40

    def test_long_system_marked_cacheable_in_request(self):
        from paradigm.agents.providers import AnthropicProvider

        prov = AnthropicProvider.__new__(AnthropicProvider)
        resp = MagicMock()
        resp.content = [MagicMock(text="a")]
        resp.usage.input_tokens = 1
        resp.usage.output_tokens = 1
        resp.usage.cache_read_input_tokens = 0
        resp.usage.cache_creation_input_tokens = 0
        client = MagicMock()
        client.messages.create.return_value = resp
        prov._client = client
        prov.complete(
            model="claude-x", system="S" * (_CACHE_MIN_CHARS + 1), messages=[], max_tokens=10
        )
        sent_system = client.messages.create.call_args.kwargs["system"]
        assert isinstance(sent_system, list) and "cache_control" in sent_system[0]


class TestDatabaseCacheAccounting:
    def test_record_and_aggregate_cache_tokens(self, tmp_path):
        from paradigm.storage.database import Database

        db = Database(tmp_path / "t.db")
        db.record_token_usage(
            model="m",
            input_tokens=100,
            output_tokens=20,
            thread_id="t1",
            cache_read_tokens=900,
            cache_write_tokens=40,
        )
        usage = db.get_token_usage(thread_id="t1")
        assert usage["input_tokens"] == 100
        assert usage["cache_read_tokens"] == 900
        assert usage["cache_write_tokens"] == 40
        db.close()

    def test_defaults_zero_when_not_provided(self, tmp_path):
        from paradigm.storage.database import Database

        db = Database(tmp_path / "t.db")
        db.record_token_usage(model="m", input_tokens=10, output_tokens=5, thread_id="t1")
        usage = db.get_token_usage(thread_id="t1")
        assert usage["cache_read_tokens"] == 0 and usage["cache_write_tokens"] == 0
        db.close()

    def test_migration_adds_columns_to_legacy_table(self, tmp_path):
        import sqlite3

        # Simulate a pre-cache DB: token_usage without the cache columns.
        p = tmp_path / "legacy.db"
        con = sqlite3.connect(p)
        con.execute(
            "CREATE TABLE token_usage (id INTEGER PRIMARY KEY, timestamp TEXT, agent_id TEXT, "
            "thread_id TEXT, model TEXT NOT NULL, input_tokens INTEGER NOT NULL, "
            "output_tokens INTEGER NOT NULL, created_at TEXT)"
        )
        con.commit()
        con.close()

        from paradigm.storage.database import Database

        db = Database(p)  # _create_schema runs the migration
        db.record_token_usage(
            model="m", input_tokens=1, output_tokens=1, thread_id="t", cache_read_tokens=7
        )
        assert db.get_token_usage(thread_id="t")["cache_read_tokens"] == 7
        db.close()


def test_agent_generate_threads_cache_tokens(monkeypatch):
    """Agent.generate propagates provider cache stats into TokenUsage."""
    from paradigm.agents.base import Agent

    agent = Agent.__new__(Agent)
    agent.agent_id = "a"
    agent.model = "claude-x"
    agent.system_prompt = "sys"
    agent.temperature = 0.7
    agent.extra_body = None
    agent.max_tokens = 100
    agent.total_input_tokens = 0
    agent.total_output_tokens = 0
    agent._stream_sink = None
    agent._STREAMING_THRESHOLD = 10_000

    provider = MagicMock()
    provider.complete.return_value = LLMResult(
        "answer", 50, 10, cache_read_tokens=800, cache_write_tokens=30
    )
    agent._provider = provider

    resp = agent._generate_sync([{"role": "user", "content": "q"}], 100)
    assert resp.usage.cache_read_tokens == 800
    assert resp.usage.cache_write_tokens == 30
    assert resp.usage.input_tokens == 50


class TestSharedContextCachePrefix:
    """Part B: cycle-stable shared context is cached as a leading system block,
    identical across agents, so it is billed once and read by all."""

    def test_anthropic_system_caches_shared_prefix_block(self):
        from paradigm.agents.providers import _anthropic_system

        prefix = "DATA CARDS " * 1000  # well above the cache minimum
        out = _anthropic_system("role prompt", prefix)
        assert isinstance(out, list) and len(out) == 2
        assert out[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        assert out[0]["text"].startswith("DATA CARDS")
        assert out[1]["text"] == "role prompt"  # role block uncached, second

    def test_anthropic_system_falls_back_without_prefix(self):
        from paradigm.agents.providers import _anthropic_system

        # No shared prefix → behaves like plain system caching (short → str).
        assert _anthropic_system("short role", None) == "short role"

    def test_openai_system_prepends_shared_prefix(self):
        from paradigm.agents.providers import _openai_system

        assert _openai_system("role", "shared").startswith("shared")
        assert "role" in _openai_system("role", "shared")

    async def test_provider_receives_cache_prefix_from_agent(self):
        # Agent.generate threads cache_prefix through to the provider call.
        from paradigm.agents.base import Agent

        agent = Agent.__new__(Agent)
        agent.agent_id = "a"
        agent.model = "claude-x"
        agent.system_prompt = "sys"
        agent.temperature = 0.7
        agent.extra_body = None
        agent.max_tokens = 100
        agent.total_input_tokens = 0
        agent.total_output_tokens = 0
        agent._stream_sink = None
        agent._STREAMING_THRESHOLD = 10_000
        provider = MagicMock()
        provider.complete.return_value = LLMResult("ok", 10, 5)
        agent._provider = provider

        await agent.generate("q", cache_prefix="SHARED CONTEXT")
        assert provider.complete.call_args.kwargs["cache_prefix"] == "SHARED CONTEXT"


def test_experimentation_passes_data_cache_prefix():
    """The experimentation phase routes the (big, stable) data context to a
    cached prefix — the fix for caching not firing where the 38k actually lives."""
    import inspect

    from paradigm.orchestrator import experimentation

    src = inspect.getsource(experimentation)
    assert "data_cache_prefix" in src
    assert "cache_prefix=data_cache_prefix" in src


def test_build_agent_prompt_excludes_literature_from_cache_prefix():
    """Literature grows each round and thrashed the cache — it must stay in the
    user prompt, not the cached prefix."""
    import inspect

    from paradigm.orchestrator import engine as engine_mod

    src = inspect.getsource(engine_mod.OrchestrationEngine._build_agent_prompt)
    # literature is appended to checkpoint_context (user prompt), not cache_blocks
    assert 'cache_blocks.append("## Literature Context' not in src
    assert "Literature Context" in src  # still injected, just uncached


def test_cache_control_uses_1h_ttl():
    """The shared-context cache uses the 1h TTL so it survives the long EXECUTION
    gap (5-min default expired between phases → wasteful re-writes)."""
    from paradigm.agents.providers import _CACHE_CONTROL

    assert _CACHE_CONTROL == {"type": "ephemeral", "ttl": "1h"}
