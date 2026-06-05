"""Tests for Agent streaming side-channel + non-blocking generation (Phase A)."""

from __future__ import annotations

import asyncio

import pytest

from paradigm.agents.base import Agent, TokenUsage


class _FakeStreamingProvider:
    """Provider whose streaming yields chunks then a final usage tuple."""

    default_model = "fake-model"

    def __init__(self, chunks: list[str], in_tok: int = 7, out_tok: int = 11) -> None:
        self._chunks = chunks
        self._in_tok = in_tok
        self._out_tok = out_tok
        self.complete_calls = 0
        self.stream_calls = 0

    def complete(self, **kwargs):  # noqa: ANN003
        self.complete_calls += 1
        return "".join(self._chunks), self._in_tok, self._out_tok

    def complete_streaming(self, **kwargs):  # noqa: ANN003
        self.stream_calls += 1
        for c in self._chunks:
            yield c, 0, 0
        yield "", self._in_tok, self._out_tok


def _make_agent(provider, max_tokens: int = 256) -> Agent:
    return Agent(
        agent_id="theorist-1",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        provider=provider,
        model="fake-model",
        max_tokens=max_tokens,
    )


@pytest.mark.asyncio
async def test_sink_receives_start_chunks_final_in_order():
    provider = _FakeStreamingProvider(["Hello, ", "world", "!"])
    agent = _make_agent(provider)

    events: list[tuple[str, str, str, str]] = []

    def sink(agent_id, stream_id, chunk, event, usage):
        events.append((agent_id, stream_id, event, chunk))
        if event == "final":
            assert isinstance(usage, TokenUsage)
        else:
            assert usage is None

    agent.set_stream_sink(sink)
    resp = await agent.generate("prompt")

    # A sink forces streaming even though max_tokens < threshold.
    assert provider.stream_calls == 1
    assert provider.complete_calls == 0

    kinds = [e[2] for e in events]
    assert kinds == ["start", "chunk", "chunk", "chunk", "final"]
    assert all(e[0] == "theorist-1" for e in events)
    # Returned content equals the concatenated chunks (backward-compat).
    assert resp.content == "Hello, world!"
    assert resp.stream_id  # populated
    # Every event carries the same stream_id as the final response.
    assert {e[1] for e in events} == {resp.stream_id}
    assert resp.usage.input_tokens == 7
    assert resp.usage.output_tokens == 11


@pytest.mark.asyncio
async def test_no_sink_is_byte_identical_and_no_streaming_for_small_calls():
    provider = _FakeStreamingProvider(["abc", "def"])
    agent = _make_agent(provider, max_tokens=256)

    resp = await agent.generate("prompt")

    # Without a sink and below threshold, the non-streaming path is used.
    assert provider.complete_calls == 1
    assert provider.stream_calls == 0
    assert resp.content == "abcdef"
    assert resp.stream_id  # still correlatable


@pytest.mark.asyncio
async def test_min_chars_coalesces_chunks():
    provider = _FakeStreamingProvider(["a", "b", "c", "d", "e"])
    agent = _make_agent(provider)
    chunks: list[str] = []

    def sink(agent_id, stream_id, chunk, event, usage):
        if event == "chunk":
            chunks.append(chunk)

    agent.set_stream_sink(sink, min_chars=3)
    resp = await agent.generate("prompt")

    # 5 single-char deltas, flush at >=3 chars => "abc", then remainder "de".
    assert chunks == ["abc", "de"]
    assert resp.content == "abcde"  # full content preserved regardless of coalescing


@pytest.mark.asyncio
async def test_generate_does_not_block_event_loop():
    """A concurrent ticking task must interleave while generate() runs."""

    class _BlockingProvider(_FakeStreamingProvider):
        def complete(self, **kwargs):  # noqa: ANN003
            import time

            time.sleep(0.2)  # simulate a slow blocking HTTP call
            return super().complete(**kwargs)

    provider = _BlockingProvider(["x"])
    agent = _make_agent(provider, max_tokens=256)

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticks += 1

    tick_task = asyncio.create_task(ticker())
    await agent.generate("prompt")
    await tick_task

    # If generate() had blocked the loop, the ticker could not have advanced
    # during the 0.2s sleep. Require meaningful interleaving.
    assert ticks >= 10
