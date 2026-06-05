"""Phase A backend tests: thread-safe token streaming + replay-buffer guard."""

from __future__ import annotations

import asyncio
from collections import deque

import pytest

from backend.api.models.messages import AgentOutputStreamMsg, PhaseTransitionMsg
from backend.api.services.session_manager import SessionManager
from backend.api.services.ws_display import WebSocketDisplayAdapter


class _FakeManager:
    """Minimal SessionManager stand-in capturing broadcasts."""

    def __init__(self) -> None:
        self.broadcasts: list[object] = []

    async def broadcast_message(self, session_id: str, msg: object) -> None:
        self.broadcasts.append(msg)

    def get_state(self, session_id: str):
        return None

    def update_session_state(self, session_id: str, **kwargs: object) -> None:
        pass


@pytest.mark.asyncio
async def test_stream_chunk_from_worker_thread_reaches_manager():
    """Proves the run_coroutine_threadsafe path (sink fires from a worker thread)."""
    mgr = _FakeManager()
    adapter = WebSocketDisplayAdapter("s1", mgr)  # captures the running loop

    # Generation runs in asyncio.to_thread; emulate the sink firing from there.
    await asyncio.to_thread(
        adapter.agent_stream_chunk, "theorist-1", "sid1", "hello", role="theorist", phase="ideation"
    )
    await asyncio.sleep(0.05)  # let the scheduled coroutine run on the loop

    assert len(mgr.broadcasts) == 1
    m = mgr.broadcasts[0]
    assert isinstance(m, AgentOutputStreamMsg)
    assert m.is_final is False
    assert m.content == "hello"
    assert m.stream_id == "sid1"
    assert m.agent_id == "theorist-1"


@pytest.mark.asyncio
async def test_agent_response_final_carries_full_content_and_stream_id():
    mgr = _FakeManager()
    adapter = WebSocketDisplayAdapter("s1", mgr)

    long_content = "x" * 2000  # well beyond the old 500-char truncation
    adapter.agent_response(
        "writer-1", 1234, role="writer", model="m", content=long_content, stream_id="sid9"
    )
    await asyncio.sleep(0.05)

    finals = [
        m
        for m in mgr.broadcasts
        if isinstance(m, AgentOutputStreamMsg) and m.is_final
    ]
    assert len(finals) == 1
    assert finals[0].content == long_content  # NOT truncated
    assert finals[0].stream_id == "sid9"
    assert finals[0].tokens == 1234


@pytest.mark.asyncio
async def test_replay_buffer_excludes_nonfinal_chunks():
    mgr = SessionManager()
    sid = "s-replay"
    mgr._message_buffers[sid] = deque(maxlen=200)

    # An early structural message that must survive.
    await mgr._broadcast(sid, PhaseTransitionMsg(from_phase="ideation", to_phase="planning"))
    # A long stream of chunks that must NOT evict it.
    for i in range(500):
        await mgr._broadcast(
            sid, AgentOutputStreamMsg(agent_id="a", content=f"c{i}", stream_id="sid", is_final=False)
        )
    # The final message IS buffered.
    await mgr._broadcast(
        sid, AgentOutputStreamMsg(agent_id="a", content="full", stream_id="sid", is_final=True)
    )

    buffered = list(mgr._message_buffers[sid])
    assert any('"to_phase":"planning"' in d for d in buffered), "phase transition was evicted"
    assert any('"is_final":true' in d for d in buffered), "final stream msg not buffered"
    assert not any('"is_final":false' in d for d in buffered), "chunks should not be buffered"
    assert len(buffered) == 2  # phase_transition + the single final
