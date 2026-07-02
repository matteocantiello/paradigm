"""Tests for WS session-control handling.

Unsupported actions (manual checkpoint, rewind) must send an explicit error
frame back to the client instead of silently no-oping.
"""

from __future__ import annotations

import json

import pytest

from backend.api.models.messages import SessionControlMsg
from backend.api.routes.ws import _handle_session_control


class _FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def pause_session(self, session_id: str) -> None:
        self.calls.append(("pause", session_id))

    async def resume_session(self, session_id: str) -> None:
        self.calls.append(("resume", session_id))

    async def abort_session(self, session_id: str) -> None:
        self.calls.append(("abort", session_id))


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["checkpoint", "rewind"])
async def test_unsupported_actions_send_explicit_error(action: str) -> None:
    manager = _FakeManager()
    ws = _FakeWebSocket()
    msg = SessionControlMsg(action=action)

    await _handle_session_control(manager, ws, "s1", msg)

    assert manager.calls == []
    assert len(ws.sent) == 1
    payload = json.loads(ws.sent[0])
    assert payload["type"] == "error"
    assert payload["code"] == "not_supported"
    assert action in payload["message"]


@pytest.mark.asyncio
async def test_unknown_action_sends_explicit_error() -> None:
    manager = _FakeManager()
    ws = _FakeWebSocket()

    await _handle_session_control(manager, ws, "s1", SessionControlMsg(action="defragment"))

    assert manager.calls == []
    payload = json.loads(ws.sent[0])
    assert payload["type"] == "error"
    assert payload["code"] == "unknown_action"
    assert "defragment" in payload["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pause", "resume", "abort"])
async def test_supported_actions_still_routed(action: str) -> None:
    manager = _FakeManager()
    ws = _FakeWebSocket()

    await _handle_session_control(manager, ws, "s1", SessionControlMsg(action=action))

    assert manager.calls == [(action, "s1")]
    assert ws.sent == []
