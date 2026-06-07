"""Tests for the agent model catalog (curated + live refresh) and its endpoint."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from paradigm.agents import model_catalog as mc
from paradigm.agents.model_catalog import curated_models, provider_family

# --- pure helpers --------------------------------------------------------


class TestProviderFamily:
    def test_anthropic_by_type(self):
        assert provider_family("anthropic", None) == "anthropic"

    def test_together_and_gemini_by_base_url(self):
        assert provider_family("openai_compatible", "https://api.together.xyz/v1") == "together"
        assert (
            provider_family(
                "openai_compatible", "https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            == "gemini"
        )

    def test_unknown_openai_compatible(self):
        assert provider_family("openai_compatible", "https://api.fireworks.ai/v1") == "openai"

    def test_curated_lists(self):
        assert any(i == "claude-opus-4-8" for i, _ in curated_models("anthropic"))
        assert curated_models("does-not-exist") == []


# --- live fetch (monkeypatched SDKs, no network) -------------------------


class _Model:
    def __init__(self, mid: str, display_name: str | None = None) -> None:
        self.id = mid
        if display_name is not None:
            self.display_name = display_name


class _Models:
    def __init__(self, ids):
        self._ids = ids

    def list(self, *a, **k):
        return [_Model(i) for i in self._ids]


class _FakeOpenAI:
    ids: list[str] = []

    def __init__(self, api_key, base_url, **kw):
        self.models = _Models(_FakeOpenAI.ids)


class TestLiveFetchFiltering:
    def test_gemini_strips_prefix_and_drops_non_gemini(self, monkeypatch):
        import openai

        _FakeOpenAI.ids = [
            "models/gemini-2.5-pro",
            "models/text-embedding-004",
            "models/gemini-2.0-flash",
            "models/aqa",
        ]
        monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
        ids = [
            i
            for i, _ in mc._fetch_openai_compatible(
                "k", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini"
            )
        ]
        assert "gemini-2.5-pro" in ids and "gemini-2.0-flash" in ids
        assert "text-embedding-004" not in ids and "aqa" not in ids

    def test_together_drops_obvious_non_chat(self, monkeypatch):
        import openai

        _FakeOpenAI.ids = [
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "togethercomputer/m2-bert-80M",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
            "black-forest-labs/FLUX.1-schnell",
        ]
        monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
        ids = [
            i
            for i, _ in mc._fetch_openai_compatible("k", "https://api.together.xyz/v1", "together")
        ]
        assert "meta-llama/Llama-3.3-70B-Instruct-Turbo" in ids
        assert "Qwen/Qwen2.5-72B-Instruct-Turbo" in ids
        assert not any("m2-bert" in i for i in ids)  # 'bert' hint
        assert not any("FLUX" in i for i in ids)  # 'flux' hint

    def test_fetch_live_requires_key(self, monkeypatch):
        monkeypatch.delenv("NOPE_KEY", raising=False)
        with pytest.raises(ValueError):
            mc.fetch_live_models(
                "x", provider_type="anthropic", base_url=None, api_key_env="NOPE_KEY", force=True
            )

    def test_fetch_live_anthropic_and_caches(self, monkeypatch):
        import anthropic

        class _AModels:
            def list(self, *a, **k):
                return [_Model("claude-opus-4-8", "Claude Opus 4.8")]

        class _FakeAnthropic:
            def __init__(self, api_key):
                self.models = _AModels()

        monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        mc._LIVE_CACHE.clear()
        out = mc.fetch_live_models(
            "anthropic",
            provider_type="anthropic",
            base_url=None,
            api_key_env="ANTHROPIC_API_KEY",
            force=True,
        )
        assert ("claude-opus-4-8", "Claude Opus 4.8") in out

        # Second non-forced call must hit the cache (don't reconstruct the client).
        def _boom(*a, **k):
            raise AssertionError("should have used the cache")

        monkeypatch.setattr(anthropic, "Anthropic", _boom)
        again = mc.fetch_live_models(
            "anthropic",
            provider_type="anthropic",
            base_url=None,
            api_key_env="ANTHROPIC_API_KEY",
            force=False,
        )
        assert again == out


# --- endpoint ------------------------------------------------------------


def _request(config):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))


def _prod_config():
    return SimpleNamespace(
        providers={
            "anthropic": SimpleNamespace(
                type="anthropic",
                base_url=None,
                api_key_env="ANTHROPIC_API_KEY",
                default_model="claude-haiku-4-5",
            ),
            "gemini": SimpleNamespace(
                type="openai_compatible",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key_env="GEMINI_API_KEY",
                default_model="gemini-2.5-flash",
            ),
            "together": SimpleNamespace(
                type="openai_compatible",
                base_url="https://api.together.xyz/v1",
                api_key_env="TOGETHER_API_KEY",
                default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            ),
        }
    )


class TestCatalogEndpoint:
    def test_curated_and_key_gating(self, monkeypatch):
        from backend.api.routes.models import list_models

        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)

        resp = asyncio.run(list_models(_request(_prod_config()), refresh=False))
        by = {p.name: p for p in resp.providers}

        assert by["anthropic"].available and by["gemini"].available
        assert by["together"].available is False  # no key -> hidden in the picker
        assert by["anthropic"].source == "curated"
        assert by["anthropic"].label == "Anthropic" and by["together"].label == "TogetherAI"
        assert any(m.id == "claude-opus-4-8" for m in by["anthropic"].models)
        # Together is still described (so the UI can hint "set TOGETHER_API_KEY").
        assert any("Llama" in m.label for m in by["together"].models)

    def test_configured_default_is_injected_when_not_curated(self, monkeypatch):
        from backend.api.routes.models import list_models

        monkeypatch.setenv("GEMINI_API_KEY", "x")
        cfg = SimpleNamespace(
            providers={
                "gemini": SimpleNamespace(
                    type="openai_compatible",
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key_env="GEMINI_API_KEY",
                    default_model="gemini-7.0-ultra-secret",  # not in the curated list
                )
            }
        )
        resp = asyncio.run(list_models(_request(cfg), refresh=False))
        ids = [m.id for m in resp.providers[0].models]
        assert ids[0] == "gemini-7.0-ultra-secret"  # prepended so it's selectable

    def test_refresh_falls_back_to_curated_on_error(self, monkeypatch):
        from backend.api.routes import models as route

        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

        def _boom(*a, **k):
            raise RuntimeError("provider down")

        monkeypatch.setattr(mc, "fetch_live_models", _boom)
        cfg = SimpleNamespace(
            providers={
                "anthropic": SimpleNamespace(
                    type="anthropic",
                    base_url=None,
                    api_key_env="ANTHROPIC_API_KEY",
                    default_model="claude-haiku-4-5",
                )
            }
        )
        resp = asyncio.run(route.list_models(_request(cfg), refresh=True))
        a = resp.providers[0]
        assert a.source == "curated"
        assert "provider down" in a.error

    def test_falls_back_to_default_providers_without_registry(self, monkeypatch):
        from backend.api.routes.models import list_models

        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        # config with no `providers` attr -> default provider set is used.
        resp = asyncio.run(list_models(_request(SimpleNamespace()), refresh=False))
        names = {p.name for p in resp.providers}
        assert {"anthropic", "gemini", "together"} <= names
