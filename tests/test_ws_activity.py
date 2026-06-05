"""Phase B backend tests: ActivityEventMsg emission, narration, durations."""

from __future__ import annotations

import asyncio

import pytest

from backend.api.models.messages import ActivityEventMsg
from backend.api.services.ws_display import WebSocketDisplayAdapter


class _Narration:
    def __init__(self, enabled: bool = True, mode: str = "templated") -> None:
        self.enabled = enabled
        self.mode = mode


class _Display:
    def __init__(self, narration: _Narration | None = None) -> None:
        self.narration = narration or _Narration()


class _Config:
    def __init__(self, narration: _Narration | None = None) -> None:
        self.display = _Display(narration)


class _FakeManager:
    def __init__(self, config=None) -> None:
        self.broadcasts: list[object] = []
        self._config = config

    async def broadcast_message(self, session_id: str, msg: object) -> None:
        self.broadcasts.append(msg)

    def get_state(self, session_id: str):
        return None

    def update_session_state(self, session_id: str, **kwargs: object) -> None:
        pass


def _activities(mgr: _FakeManager) -> list[ActivityEventMsg]:
    return [m for m in mgr.broadcasts if isinstance(m, ActivityEventMsg)]


@pytest.mark.asyncio
async def test_phase_transition_emits_activity_with_narration():
    mgr = _FakeManager(config=_Config())
    adapter = WebSocketDisplayAdapter("sess1234", mgr)
    adapter.phase_transition("EXECUTION")
    await asyncio.sleep(0.05)

    acts = _activities(mgr)
    assert len(acts) == 1
    a = acts[0]
    assert a.category == "phase_transition"
    assert a.phase == "execution"
    assert "execution" in a.narration.lower()
    assert a.event_id


@pytest.mark.asyncio
async def test_experiment_duration_is_measured():
    mgr = _FakeManager(config=_Config())
    adapter = WebSocketDisplayAdapter("sess1234", mgr)
    adapter.experiment_running("exp_alpha")
    await asyncio.sleep(0.02)
    adapter.experiment_result("exp_alpha", "success")
    await asyncio.sleep(0.05)

    results = [a for a in _activities(mgr) if a.category == "experiment_result"]
    assert len(results) == 1
    assert results[0].severity == "success"
    assert results[0].duration_ms is not None and results[0].duration_ms >= 0


@pytest.mark.asyncio
async def test_narration_disabled_yields_empty_narration():
    mgr = _FakeManager(config=_Config(_Narration(enabled=False)))
    adapter = WebSocketDisplayAdapter("sess1234", mgr)
    adapter.convergence_detected("ideation", 1, 2)
    await asyncio.sleep(0.05)

    acts = [a for a in _activities(mgr) if a.category == "convergence_detected"]
    assert len(acts) == 1
    assert acts[0].narration == ""
