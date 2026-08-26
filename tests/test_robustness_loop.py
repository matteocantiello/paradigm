"""Iterate-to-robustness loop: extra focused stress-test passes after the main
sprints, gated by _should_iterate_robustness."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from paradigm.config import Config
from paradigm.orchestrator.constants import _ROBUSTNESS_DIRECTIVE
from paradigm.orchestrator.experimentation import ExperimentationHandler, _ExecutionTally


def _handler(*, enabled=True, max_passes=2):
    eng = MagicMock()
    eng._config.orchestrator = SimpleNamespace(
        enable_robustness_loop=enabled, robustness_max_passes=max_passes
    )
    return ExperimentationHandler(eng)


def _tally(*, successful=1, breaker=False):
    return _ExecutionTally(
        successful_code=[("e", "code")] * successful, circuit_breaker_fired=breaker
    )


class TestRobustnessGate:
    def test_runs_first_robustness_pass_after_main(self):
        h = _handler()
        assert h._should_iterate_robustness(
            pass_num=0, stopped=False, added_this_pass=1, tally=_tally()
        )

    def test_disabled_never_iterates(self):
        h = _handler(enabled=False)
        assert not h._should_iterate_robustness(
            pass_num=0, stopped=False, added_this_pass=1, tally=_tally()
        )

    def test_respects_max_passes(self):
        h = _handler(max_passes=2)
        # After the 2nd robustness pass (pass_num=2), a 3rd would exceed the cap.
        assert not h._should_iterate_robustness(
            pass_num=2, stopped=False, added_this_pass=1, tally=_tally()
        )
        # A 2nd robustness pass is still allowed.
        assert h._should_iterate_robustness(
            pass_num=1, stopped=False, added_this_pass=1, tally=_tally()
        )

    def test_stops_when_no_established_result(self):
        h = _handler()
        assert not h._should_iterate_robustness(
            pass_num=0, stopped=False, added_this_pass=0, tally=_tally(successful=0)
        )

    def test_stops_on_stall_or_breaker(self):
        h = _handler()
        assert not h._should_iterate_robustness(
            pass_num=0, stopped=True, added_this_pass=1, tally=_tally()
        )
        assert not h._should_iterate_robustness(
            pass_num=0, stopped=False, added_this_pass=1, tally=_tally(breaker=True)
        )

    def test_dry_robustness_pass_converges(self):
        # A robustness pass that added no new successful experiment → stop.
        h = _handler()
        assert not h._should_iterate_robustness(
            pass_num=1, stopped=False, added_this_pass=0, tally=_tally()
        )


class TestRobustnessDirective:
    def test_directive_content(self):
        d = _ROBUSTNESS_DIRECTIVE
        assert "ROBUSTNESS PASS" in d
        assert "VARY" in d and "SUBSAMPLE" in d and "CONFOUNDS" in d
        assert "_robust]" in d  # verdict token
        assert "do not" in d.lower() and "re-pull" in d  # keep it reproducible

    def test_directive_injected_only_on_robustness_pass(self):
        import inspect

        from paradigm.orchestrator import experimentation

        src = inspect.getsource(experimentation)
        assert 'if getattr(self, "_robustness_pass", 0) > 0:' in src
        assert "prompt += _ROBUSTNESS_DIRECTIVE" in src


class TestDriverLoop:
    """The run_experimentation_phase driver actually runs extra robustness passes."""

    def _driver_handler(self, *, enabled, max_passes, num_sprints=3):
        from pathlib import Path
        from unittest.mock import AsyncMock

        from paradigm.orchestrator.experimentation import _ExecutionSetup

        h = _handler(enabled=enabled, max_passes=max_passes)
        h._engine._config.orchestrator.enable_checkpointing = False
        h._engine._config.storage.data_dir = Path("/tmp")
        setup = _ExecutionSetup(
            max_rounds=num_sprints * 2,
            repo_paths=[],
            workspace_dir=Path("/tmp"),
            executor=MagicMock(cleanup=AsyncMock()),
            enable_sprints=True,
            num_sprints=num_sprints,
            rounds_per_sprint=2,
        )
        h._setup_execution = MagicMock(return_value=setup)
        h._build_caveats = MagicMock(return_value=[])
        return h, setup

    async def test_runs_main_then_two_robustness_passes(self):
        h, setup = self._driver_handler(enabled=True, max_passes=2)
        calls: list[int] = []

        async def fake_sprint(sprint_num, s, tally, robustness_pass=0):
            calls.append(robustness_pass)
            tally.successful_code.append((f"e{len(calls)}", "code"))  # each pass is productive
            return False

        h._run_sprint = fake_sprint
        await h.run_experimentation_phase()
        # 3 main sprints (pass 0), then 2 single-sprint robustness passes (1, 2).
        assert calls == [0, 0, 0, 1, 2]
        assert setup.max_rounds == 6 + 2 + 2  # budget extended once per robustness pass

    async def test_dry_robustness_pass_stops_early(self):
        h, _ = self._driver_handler(enabled=True, max_passes=3)
        calls: list[int] = []

        async def fake_sprint(sprint_num, s, tally, robustness_pass=0):
            calls.append(robustness_pass)
            if robustness_pass == 0:  # only the main pass produces results
                tally.successful_code.append(("e", "code"))
            return False

        h._run_sprint = fake_sprint
        await h.run_experimentation_phase()
        # Robustness pass 1 adds nothing new → converged, no pass 2/3.
        assert calls == [0, 0, 0, 1]

    async def test_disabled_runs_only_main_sprints(self):
        h, _ = self._driver_handler(enabled=False, max_passes=2)
        calls: list[int] = []

        async def fake_sprint(sprint_num, s, tally, robustness_pass=0):
            calls.append(robustness_pass)
            tally.successful_code.append(("e", "code"))
            return False

        h._run_sprint = fake_sprint
        await h.run_experimentation_phase()
        assert calls == [0, 0, 0]  # back-compat: no extra passes


def test_config_defaults_and_default_yaml(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Off by default (back-compat), on in the operator default config.
    assert Config().orchestrator.enable_robustness_loop is False
    from paradigm.config import load_config

    cfg = load_config("configs/default.yaml").orchestrator
    assert cfg.enable_robustness_loop is True
    assert cfg.robustness_max_passes == 2
