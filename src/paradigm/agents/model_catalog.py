"""Model catalog — what models each provider offers, for the agent model picker.

Hybrid by design: a hand-picked CURATED shortlist per provider family is the
default (clean, fast, reliable), and the GUI can request a LIVE list pulled from
each provider's models API (cached) when the user wants the full, current set.

A "family" (anthropic / gemini / together / openai) is derived from a provider's
config entry (type + base_url), since the curated lists + live-fetch quirks are
per-API, while the config keys them by an arbitrary name (e.g. "gemini").
"""

from __future__ import annotations

import os
import time

# Curated, hand-picked models per family — the sensible options for agents. Keep
# reasonably current; the GUI's "refresh from API" pulls the full live list.
CURATED: dict[str, list[tuple[str, str]]] = {
    "anthropic": [
        ("claude-opus-4-8", "Claude Opus 4.8"),
        ("claude-opus-4-7", "Claude Opus 4.7"),
        ("claude-opus-4-6", "Claude Opus 4.6"),
        ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
        ("claude-haiku-4-5", "Claude Haiku 4.5"),
    ],
    "gemini": [
        ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
    ],
    "together": [
        ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B Instruct Turbo"),
        ("meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo", "Llama 3.1 405B Instruct Turbo"),
        ("Qwen/Qwen2.5-72B-Instruct-Turbo", "Qwen2.5 72B Instruct Turbo"),
        ("deepseek-ai/DeepSeek-V3", "DeepSeek V3"),
        ("deepseek-ai/DeepSeek-R1", "DeepSeek R1"),
        ("mistralai/Mixtral-8x7B-Instruct-v0.1", "Mixtral 8x7B Instruct"),
    ],
    # A current top shortlist — use the GUI's "Refresh from API" for the exact set
    # your key can access (versions move fast). Reasoning models (gpt-5*, o*) are
    # handled by the provider shim (max_completion_tokens, no temperature).
    "openai": [
        ("gpt-5.5", "GPT-5.5"),
        ("gpt-5.5-pro", "GPT-5.5 Pro"),
        ("gpt-5.4", "GPT-5.4"),
        ("gpt-5.4-mini", "GPT-5.4 mini"),
        ("gpt-5.4-nano", "GPT-5.4 nano"),
        ("gpt-5.1", "GPT-5.1"),
        ("gpt-4.1", "GPT-4.1"),
        ("gpt-4.1-mini", "GPT-4.1 mini"),
        ("o4-mini", "o4-mini"),
    ],
}

FAMILY_LABELS: dict[str, str] = {
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "together": "TogetherAI",
    "openai": "OpenAI",
    "openai_compatible": "OpenAI-compatible",
}

# Live Together listing returns 100+ entries incl. non-chat models — drop the
# obvious ones so the dropdown is usable.
_NON_CHAT_HINTS = (
    "embed",
    "rerank",
    "guard",
    "whisper",
    "bert",
    "stable-diffusion",
    "flux",
    "-tts",
    "upscal",
    "vision-free",
    # OpenAI non-chat variants (audio / image / realtime / transcription / search)
    "audio",
    "realtime",
    "transcribe",
    "search-preview",
    "image",
    "moderation",
)

_LIVE_TTL_S = 3600.0
# provider name -> (fetched_at_epoch, [(id, label), ...])
_LIVE_CACHE: dict[str, tuple[float, list[tuple[str, str]]]] = {}


def provider_family(provider_type: str | None, base_url: str | None) -> str:
    """Map a provider's (type, base_url) to a catalog family key."""
    ptype = (provider_type or "").lower()
    base = (base_url or "").lower()
    if ptype == "anthropic":
        return "anthropic"
    if "together" in base:
        return "together"
    if "generativelanguage" in base or "googleapis" in base:
        return "gemini"
    if "api.openai.com" in base:
        return "openai"
    return "openai_compatible"


def curated_models(family: str) -> list[tuple[str, str]]:
    """The curated shortlist for a family (empty for unknown families)."""
    return list(CURATED.get(family, []))


def _fetch_anthropic(api_key: str) -> list[tuple[str, str]]:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    out: list[tuple[str, str]] = []
    for m in client.models.list(limit=100):
        out.append((m.id, getattr(m, "display_name", None) or m.id))
    return out


def _fetch_openai_compatible(api_key: str, base_url: str, family: str) -> list[tuple[str, str]]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    out: list[tuple[str, str]] = []
    for m in client.models.list():
        mid = m.id
        if family == "gemini":
            mid = mid.removeprefix("models/")
            if not mid.startswith("gemini") or "embedding" in mid or "aqa" in mid:
                continue
        elif family == "together":
            low = mid.lower()
            if any(h in low for h in _NON_CHAT_HINTS):
                continue
        elif family == "openai":
            low = mid.lower()
            if not (low.startswith("gpt-") or low.startswith(("o1", "o3", "o4"))):
                continue  # drop embeddings / tts / whisper / dall-e / etc.
            if any(h in low for h in _NON_CHAT_HINTS):
                continue
        out.append((mid, mid))
    out.sort(key=lambda t: t[0].lower())
    return out


def fetch_live_models(
    name: str,
    *,
    provider_type: str | None,
    base_url: str | None,
    api_key_env: str | None,
    force: bool = False,
) -> list[tuple[str, str]]:
    """Fetch a provider's live model list (cached for an hour).

    Raises if the API key is unset or the provider call fails — callers fall back
    to the curated list.
    """
    now = time.time()
    cached = _LIVE_CACHE.get(name)
    if cached and not force and now - cached[0] < _LIVE_TTL_S:
        return cached[1]

    api_key = os.getenv(api_key_env or "")
    if not api_key:
        raise ValueError(f"{api_key_env or 'API key'} is not set")

    family = provider_family(provider_type, base_url)
    if (provider_type or "").lower() == "anthropic":
        models = _fetch_anthropic(api_key)
    else:
        if not base_url:
            raise ValueError("base_url required for an openai_compatible provider")
        models = _fetch_openai_compatible(api_key, base_url, family)

    _LIVE_CACHE[name] = (now, models)
    return models
