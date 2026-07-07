"""Turn-level responsiveness (Prompt 246).

Steering and pause must take effect within one agent turn, everywhere:
- _interaction_checkpoint (before every discussion turn): park + drain
- _execution_checkpoint (between experiments): steering → OPERATOR DIRECTIVE
- _drain_guidance: structured delivery receipt + (text, round) buffer entries
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.phases import ResearchPhase


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return _record

    def named(self, name: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == name]


def _stub(*, paused_flags: list[bool] | None = None, guidance: list[str] | None = None):
    """Minimal engine stand-in for the checkpoint/drain methods."""
    stub = SimpleNamespace()
    flags = list(paused_flags or [])

    def is_paused() -> bool:
        return flags.pop(0) if flags else False

    gate = asyncio.Event()
    gate.set()
    stub._pause_gate = gate.wait
    stub._is_paused = is_paused

    pending = list(guidance or [])

    async def provider() -> list[str]:
        out, pending[:] = list(pending), []
        return out

    stub._guidance_provider = provider
    stub.state = SimpleNamespace(thread_id="t1", planning_action_items="1. Fit the PSD slope")
    stub._display = _Recorder()
    stub._logger = _Recorder()
    stub._pending_guidance = []
    for name in (
        "_await_pause_gate",
        "_interaction_checkpoint",
        "_execution_checkpoint",
        "_drain_guidance",
    ):
        setattr(stub, name, getattr(OrchestrationEngine, name).__get__(stub))
    return stub


@pytest.mark.asyncio
async def test_drain_guidance_appends_round_tagged_entries_and_receipts():
    stub = _stub(guidance=["use real data", "  ", "cite Bowman"])
    await stub._drain_guidance(ResearchPhase.PLANNING, 2)
    assert stub._pending_guidance == [("use real data", 2), ("cite Bowman", 2)]
    receipts = stub._display.named("guidance_delivered")
    assert [r[1][0] for r in receipts] == ["use real data", "cite Bowman"]
    assert receipts[0][1][1:] == ("planning", 2)


@pytest.mark.asyncio
async def test_interaction_checkpoint_parks_and_signals_when_paused():
    stub = _stub(paused_flags=[True])
    await stub._interaction_checkpoint(ResearchPhase.IDEATION, 1)
    assert stub._display.named("run_parked") and stub._display.named("run_resumed")


@pytest.mark.asyncio
async def test_interaction_checkpoint_silent_when_running():
    stub = _stub(paused_flags=[False], guidance=["go deeper"])
    await stub._interaction_checkpoint(ResearchPhase.IDEATION, 1)
    assert not stub._display.named("run_parked")
    assert stub._pending_guidance == [("go deeper", 1)]


@pytest.mark.asyncio
async def test_interaction_checkpoint_noop_without_backend_hooks():
    """CLI runs (no pause gate / no guidance provider) must be unaffected."""
    stub = _stub()
    stub._pause_gate = None
    stub._guidance_provider = None
    await stub._interaction_checkpoint(ResearchPhase.IDEATION, 1)
    assert stub._pending_guidance == []


@pytest.mark.asyncio
async def test_execution_checkpoint_turns_guidance_into_operator_directives():
    stub = _stub(guidance=["do not use synthetic data"])
    await stub._execution_checkpoint()
    plan = stub.state.planning_action_items
    assert plan.startswith("1. Fit the PSD slope")
    assert "OPERATOR DIRECTIVE (must be honored): do not use synthetic data" in plan
    # Consumed into the plan — not left in the discussion-guidance buffer.
    assert stub._pending_guidance == []


@pytest.mark.asyncio
async def test_execution_checkpoint_preserves_prior_discussion_guidance():
    stub = _stub(guidance=["new directive"])
    stub._pending_guidance = [("earlier note", 1)]
    await stub._execution_checkpoint()
    assert stub._pending_guidance == [("earlier note", 1)]
    assert "new directive" in stub.state.planning_action_items
