"""Regression: a finished cycle must broadcast its TERMINAL status.

Bug (prompt 102): `_run_cycle` set `state.status = COMPLETED` and sent only a
NotificationMsg — never a SessionStateMsg — so the live UI never left "running".
A completed cycle then looked stuck on its last message (StatusPill: running ->
stalled). The fix broadcasts status in the `finally` block. These tests pin the
mechanism: `_broadcast_status` emits a buffered `session_state` carrying the
terminal status, for every terminal state.
"""

from __future__ import annotations

import json

import pytest

from backend.api.models.session import SessionStatus
from backend.api.services.session_manager import SessionManager


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["completed", "aborted", "failed"])
async def test_terminal_status_is_broadcast_and_buffered(terminal):
    mgr = SessionManager()
    state = await mgr.create_session(cycle_id="c1", seed_prompt="x")
    sid = state.session_id

    # Simulate the engine reaching a terminal state.
    state.status = SessionStatus(terminal)
    await mgr._broadcast_status(sid)

    # The terminal status is in the replay buffer (so reconnecting clients see it).
    buffered = [json.loads(d) for d in mgr._message_buffers[sid]]
    session_states = [m for m in buffered if m.get("type") == "session_state"]
    assert session_states, "no session_state was broadcast"
    assert session_states[-1]["status"] == terminal


@pytest.mark.asyncio
async def test_status_values_match_frontend_states():
    """The enum values must equal the strings the StatusPill switches on."""
    assert SessionStatus.COMPLETED.value == "completed"
    assert SessionStatus.ABORTED.value == "aborted"
    assert SessionStatus.FAILED.value == "failed"
