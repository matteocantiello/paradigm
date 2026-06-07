"""Tests for the model pre-flight health check (no network — fake providers)."""

from __future__ import annotations

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
        assert ("skeptic", "some-llama", "gemini-2.5-flash-lite") in res.swaps

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
        assert ("theorist", "m1", "") in res.swaps
        assert ("skeptic", "m2", "") in res.swaps

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
