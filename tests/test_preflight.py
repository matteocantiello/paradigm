"""Tests for the model pre-flight health check (no network — fake providers)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from paradigm.agents.preflight import preflight_team_models


class _Provider:
    """A fake provider whose 1-token ping succeeds or fails."""

    def __init__(self, ok: bool = True) -> None:
        self._ok = ok
        self.pings = 0

    def complete(self, *, model, system, messages, max_tokens, temperature):
        self.pings += 1
        if not self._ok:
            raise RuntimeError("503 service unavailable")
        return ("pong", 1, 1)


class _RaiseThenOK:
    """Fake provider: raise ``exc`` on the first ``fail_times`` pings, then succeed."""

    def __init__(self, exc: BaseException, fail_times: int = 1) -> None:
        self._exc = exc
        self._fail_times = fail_times
        self.pings = 0

    def complete(self, *, model, system, messages, max_tokens, temperature):
        self.pings += 1
        if self.pings <= self._fail_times:
            raise self._exc
        return ("pong", 1, 1)


class _Override:
    def __init__(self, provider=None, model=None) -> None:
        self.provider = provider
        self.model = model


class _AgentCfg:
    def __init__(self, default_provider, default_model, overrides) -> None:
        self.default_provider = default_provider
        self.default_model = default_model
        self.overrides = overrides


class _Config:
    """Minimal config exposing the surface preflight uses."""

    def __init__(self, *, providers, role_map, default_provider, default_model, overrides) -> None:
        self._providers = providers  # name -> _Provider
        self._role_map = role_map  # role -> (provider_name, model)
        self.agent = _AgentCfg(default_provider, default_model, overrides)

    def get_provider(self, name):
        return self._providers[name]

    def get_provider_and_model_for_role(self, role):
        pname, model = self._role_map[role]
        return (self._providers[pname], model, None)


class TestPreflight:
    @pytest.mark.asyncio
    async def test_all_healthy_no_swaps(self):
        gemini = _Provider(ok=True)
        cfg = _Config(
            providers={"gemini": gemini},
            role_map={
                "theorist": ("gemini", "gemini-2.5-flash-lite"),
                "writer": ("gemini", "gemini-2.5-flash"),
            },
            default_provider="gemini",
            default_model="gemini-2.5-flash-lite",
            overrides={},
        )
        res = await preflight_team_models(cfg, ["theorist", "writer"])
        assert res.overrides == {}
        assert res.swaps == []
        assert res.checked >= 2

    @pytest.mark.asyncio
    async def test_unhealthy_model_swapped_to_healthy_default(self):
        gemini = _Provider(ok=True)
        together = _Provider(ok=False)  # the dead provider (cf. the Together 503)
        cfg = _Config(
            providers={"gemini": gemini, "together": together},
            role_map={
                "theorist": ("gemini", "gemini-2.5-flash-lite"),
                "skeptic": ("together", "some-llama"),
            },
            default_provider="gemini",
            default_model="gemini-2.5-flash-lite",
            overrides={"skeptic": _Override(provider="together", model="some-llama")},
        )
        res = await preflight_team_models(cfg, ["theorist", "skeptic"])

        assert "theorist" not in res.overrides  # healthy — untouched
        assert "skeptic" in res.overrides
        fb_provider, fb_model = res.overrides["skeptic"]
        assert fb_model == "gemini-2.5-flash-lite"  # fell back to the healthy default
        assert fb_provider is gemini
        swap = next(s for s in res.swaps if s[0] == "skeptic")
        assert swap[1] == "some-llama" and swap[2] == "gemini-2.5-flash-lite"
        assert "503" in swap[3]  # the failure REASON is surfaced

    @pytest.mark.asyncio
    async def test_all_unhealthy_reports_no_fallback(self):
        together = _Provider(ok=False)
        cfg = _Config(
            providers={"together": together},
            role_map={"theorist": ("together", "m1"), "skeptic": ("together", "m2")},
            default_provider="together",
            default_model="m1",
            overrides={
                "theorist": _Override(provider="together", model="m1"),
                "skeptic": _Override(provider="together", model="m2"),
            },
        )
        res = await preflight_team_models(cfg, ["theorist", "skeptic"])
        assert res.overrides == {}  # nothing healthy to swap to
        swaps = {s[0]: s for s in res.swaps}
        assert swaps["theorist"][1] == "m1" and swaps["theorist"][2] == ""
        assert swaps["skeptic"][1] == "m2" and swaps["skeptic"][2] == ""
        assert swaps["theorist"][3]  # reason recorded even with no fallback

    @pytest.mark.asyncio
    async def test_output_limit_400_counts_as_healthy(self):
        # Reasoning models (gpt-5.x) burn the tiny ping's budget on hidden reasoning
        # and 400 — but that PROVES they are reachable, so no swap should happen.
        msg = (
            "Error code: 400 - {'error': {'message': 'Could not finish the message "
            "because max_tokens or model output limit was reached. Please try again "
            "with higher max_tokens.', 'type': 'invalid_request_error'}}"
        )
        openai = _RaiseThenOK(RuntimeError(msg), fail_times=99)  # always 400s on the ping
        cfg = _Config(
            providers={"openai": openai},
            role_map={"theorist": ("openai", "gpt-5.5")},
            default_provider="openai",
            default_model="gpt-5.5",
            overrides={"theorist": _Override(provider="openai", model="gpt-5.5")},
        )
        res = await preflight_team_models(cfg, ["theorist"])
        assert res.overrides == {}  # healthy → untouched
        assert res.swaps == []

    @pytest.mark.asyncio
    async def test_retries_once_on_timeout(self):
        # A cold connection times out the first ping but answers the retry → healthy.
        gemini = _RaiseThenOK(TimeoutError("timed out"), fail_times=1)
        cfg = _Config(
            providers={"gemini": gemini},
            role_map={"writer": ("gemini", "gemini-2.5-flash")},
            default_provider="gemini",
            default_model="gemini-2.5-flash",
            overrides={},
        )
        res = await preflight_team_models(cfg, ["writer"])
        assert res.overrides == {}  # recovered on retry → no swap
        assert res.swaps == []
        assert gemini.pings == 2  # one failure + one successful retry

    @pytest.mark.asyncio
    async def test_retries_transient_429_then_resolves(self):
        # A 429 from the concurrent ping burst usually clears — retry, don't swap.
        prov = _RaiseThenOK(RuntimeError("Error code: 429 - rate limit reached"), fail_times=1)
        cfg = _Config(
            providers={"openai": prov},
            role_map={"theorist": ("openai", "gpt-5.4")},
            default_provider="openai",
            default_model="gpt-5.4",
            overrides={"theorist": _Override(provider="openai", model="gpt-5.4")},
        )
        with patch("paradigm.agents.preflight.asyncio.sleep", new=AsyncMock()):
            res = await preflight_team_models(cfg, ["theorist"])
        assert res.overrides == {}  # recovered on retry → not swapped
        assert res.swaps == []
        assert prov.pings == 2

    @pytest.mark.asyncio
    async def test_persistent_429_still_swaps(self):
        # A genuine quota exhaustion keeps 429-ing → swap to the healthy fallback.
        openai = _RaiseThenOK(RuntimeError("429 - you exceeded your current quota"), fail_times=99)
        gemini = _Provider(ok=True)
        cfg = _Config(
            providers={"openai": openai, "gemini": gemini},
            role_map={"theorist": ("openai", "gpt-5.4"), "writer": ("gemini", "gemini-2.5-flash")},
            default_provider="gemini",
            default_model="gemini-2.5-flash",
            overrides={"theorist": _Override(provider="openai", model="gpt-5.4")},
        )
        with patch("paradigm.agents.preflight.asyncio.sleep", new=AsyncMock()):
            res = await preflight_team_models(cfg, ["theorist", "writer"])
        assert "theorist" in res.overrides  # exhausted quota → swapped
        assert res.overrides["theorist"][1] == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_never_raises_on_bad_config(self):
        # A config that throws on resolution must degrade to an empty result.
        class _Boom:
            agent = _AgentCfg("x", "y", {})

            def get_provider_and_model_for_role(self, role):
                raise RuntimeError("boom")

            def get_provider(self, name):
                raise RuntimeError("boom")

        res = await preflight_team_models(_Boom(), ["theorist"])
        assert res.overrides == {}
        assert res.swaps == []
