"""Phase-1 web-deployment guardrails: concurrency cap + sandbox hardening."""

from __future__ import annotations

import pytest

from backend.api.models.session import SessionStatus
from backend.api.services.session_manager import SessionManager
from paradigm.config import SandboxConfig


@pytest.mark.asyncio
async def test_concurrency_cap_blocks_beyond_limit():
    mgr = SessionManager()
    mgr.max_concurrent_sessions = 2
    assert not mgr.at_capacity()

    s1 = await mgr.create_session("c1", "prompt")  # status STARTING
    await mgr.create_session("c2", "prompt")
    assert mgr.active_session_count() == 2
    assert mgr.at_capacity()  # full

    # A finished run frees a slot.
    s1.status = SessionStatus.COMPLETED
    assert mgr.active_session_count() == 1
    assert not mgr.at_capacity()


@pytest.mark.asyncio
async def test_terminal_sessions_do_not_count_as_active():
    mgr = SessionManager()
    mgr.max_concurrent_sessions = 1
    s = await mgr.create_session("c", "p")
    for terminal in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.ABORTED):
        s.status = terminal
        assert mgr.active_session_count() == 0
        assert not mgr.at_capacity()


def test_sandbox_hardening_defaults_are_safe():
    c = SandboxConfig()
    assert c.network_mode == "none"  # no network in the sandbox
    assert c.drop_capabilities is True
    assert c.no_new_privileges is True
    assert c.pids_limit > 0  # fork-bomb guard
