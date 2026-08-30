"""LLM provider abstraction for multi-backend support."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel


def _llm_timeout() -> httpx.Timeout:
    """Per-request timeout applied to every LLM client.

    Without this a hung provider call (a stalled stream, a connection that never
    closes) blocks the worker thread forever and the whole research cycle stalls
    indefinitely — we have seen multi-hour stalls in peer review and memory
    generation from a single call that never returned.

    ``read`` is a PER-READ timeout, so a healthy stream that keeps emitting
    chunks is never clipped no matter how long the full response takes; only a
    genuine stall (no bytes for this many seconds) trips it. On timeout the SDKs
    raise (and retry a couple of times first), so the call fails fast instead of
    hanging. Override the read timeout with PARADIGM_LLM_TIMEOUT (seconds).
    """
    try:
        read = float(os.getenv("PARADIGM_LLM_TIMEOUT", "180"))
    except ValueError:
        read = 180.0
    return httpx.Timeout(connect=15.0, read=read, write=60.0, pool=15.0)


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    type: str  # "anthropic" or "openai_compatible"
    api_key_env: str  # env var name, NOT the key itself
    base_url: str | None = None  # required for openai_compatible
    default_model: str | None = None


# Minimum prefix size worth a cache breakpoint. Anthropic only caches prefixes
# above a model-dependent minimum (1024 tokens most models, 2048 for Haiku);
# below it the cache_control marker is silently ignored (wasted). Gate on a
# conservative char proxy (~4 chars/token) sized for the largest minimum, so we
# never mark a prefix that won't actually cache.
_CACHE_MIN_CHARS = 8192

# Cache retention. The default ephemeral cache is 5 min, which EXPIRES across a
# long phase (agents fire in early and late phases with a multi-minute EXECUTION
# gap between), forcing wasteful re-writes (measured: writes >> reads). The 1h TTL
# keeps the shared-context prefix warm for the whole cycle — 2x write cost vs
# 1.25x, but it converts those re-writes into 0.1x reads. GA in the SDK (no beta
# header needed).
_CACHE_CONTROL = {"type": "ephemeral", "ttl": "1h"}


class LLMResult(tuple):
    """A ``(text, input_tokens, output_tokens)`` result carrying optional cache
    stats as attributes.

    Subclasses ``tuple`` so the historical 3-tuple unpacking every caller uses
    (``text, i, o = provider.complete(...)``) is unchanged, while instrumentation
    can read ``.cache_read_tokens`` / ``.cache_write_tokens`` off the same object.
    ``input_tokens`` is the UNcached input; cache reads/writes are separate (that
    is how the providers report them), so the true billed input is
    ``input_tokens + cache_read_tokens + cache_write_tokens``.
    """

    cache_read_tokens: int
    cache_write_tokens: int

    def __new__(
        cls,
        text: str,
        input_tokens: int,
        output_tokens: int,
        *,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> LLMResult:
        obj = super().__new__(cls, (text, input_tokens, output_tokens))
        obj.cache_read_tokens = cache_read_tokens
        obj.cache_write_tokens = cache_write_tokens
        return obj


def _int_or_zero(value: Any) -> int:
    """Coerce a usage field to a non-negative int (0 for None/missing/non-numeric).

    Providers' usage objects (and test mocks) may leave cache fields absent or
    non-numeric; caching accounting must never crash a call over that.
    """
    return value if isinstance(value, int) and value >= 0 else 0


def _openai_cached_tokens(usage: Any) -> int:
    """Cached prompt tokens from an OpenAI-compatible usage object (0 if absent)."""
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return 0
    return _int_or_zero(getattr(details, "cached_tokens", 0))


def _cacheable_system(system: str) -> Any:
    """Wrap a long system prompt in a cache-controlled block (Anthropic).

    System prompts are stable per role and reused across every round, so caching
    the prefix turns 10-16 full re-sends per role into one write + cheap reads.
    Short prompts stay plain strings (below the cache minimum a marker only costs).
    """
    if system and len(system) >= _CACHE_MIN_CHARS:
        return [{"type": "text", "text": system, "cache_control": _CACHE_CONTROL}]
    return system


def _anthropic_system(system: str, cache_prefix: str | None) -> Any:
    """Build the Anthropic ``system`` param, caching a shared-context prefix.

    ``cache_prefix`` is the cycle-stable context (data cards + literature) that is
    IDENTICAL across every agent in a cycle. Placing it as the first system block
    with a cache breakpoint means it is written to cache once and read cheaply by
    all ~50 agent calls — the dominant re-injection cost. The role-specific system
    prompt follows as a second (uncached) block. Falls back to caching the system
    prompt alone when there is no usable shared prefix.
    """
    if cache_prefix and len(cache_prefix) >= _CACHE_MIN_CHARS:
        blocks: list[dict[str, Any]] = [
            {"type": "text", "text": cache_prefix, "cache_control": _CACHE_CONTROL}
        ]
        if system:
            blocks.append({"type": "text", "text": system})
        return blocks
    return _cacheable_system(system)


def _openai_system(system: str, cache_prefix: str | None) -> str:
    """OpenAI-compatible system string: shared prefix + role prompt (auto-cached).

    OpenAI-family endpoints auto-cache identical prefixes, so a stable shared
    context placed first is cached without an explicit breakpoint.
    """
    if cache_prefix:
        return f"{cache_prefix}\n\n{system}" if system else cache_prefix
    return system


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM backends (Anthropic, OpenAI-compatible, etc.)."""

    @property
    def default_model(self) -> str: ...

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.7,
        extra_body: dict[str, Any] | None = None,
        cache_prefix: str | None = None,
    ) -> tuple[str, int, int]:
        """Synchronous completion.

        Returns:
            (text, input_tokens, output_tokens)
        """
        ...

    def complete_streaming(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.7,
        extra_body: dict[str, Any] | None = None,
        cache_prefix: str | None = None,
    ) -> Iterator[tuple[str, int, int]]:
        """Streaming completion.

        Yields partial text chunks as (chunk, 0, 0).
        Final yield has token counts: ("", input_tokens, output_tokens).
        """
        ...

    def build_image_message(self, text: str, images: list[tuple[str, bytes]]) -> dict:
        """Build a multimodal user message (text + base64 images) in provider format.

        Args:
            text: The prompt text.
            images: List of ``(media_type, raw_bytes)`` (e.g. ``("image/png", b"...")``).

        Returns:
            A ``{"role": "user", "content": [...]}`` dict for use with ``complete``.
        """
        ...


# Claude Opus 4.7+ and Sonnet 5 removed the sampling params — sending `temperature`
# (or top_p/top_k) at a non-default value returns a 400. Omit it for these so the
# ping AND agent calls succeed. (Sonnet 4.6 still ACCEPTS temperature, so match the
# exact "-5" family, not all sonnets.) Extend this tuple as new such models ship.
_NO_TEMPERATURE_PREFIXES = ("claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-5")


def _accepts_temperature(model: str) -> bool:
    return not any(model.startswith(p) for p in _NO_TEMPERATURE_PREFIXES)


class AnthropicProvider:
    """LLM provider wrapping the Anthropic SDK."""

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-5-20250929") -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key, timeout=_llm_timeout())
        self._default_model = default_model

    @property
    def default_model(self) -> str:
        return self._default_model

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.7,
        extra_body: dict[str, Any] | None = None,
        cache_prefix: str | None = None,
    ) -> tuple[str, int, int]:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": _anthropic_system(system, cache_prefix),
            "messages": messages,
        }
        if _accepts_temperature(model):
            kwargs["temperature"] = temperature
        if extra_body:
            # Per-role overrides (e.g. extended thinking) from config — forward
            # them as request body params, matching the OpenAI-compatible path.
            kwargs["extra_body"] = extra_body
        response = self._client.messages.create(**kwargs)
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
        u = response.usage
        return LLMResult(
            content,
            u.input_tokens,
            u.output_tokens,
            cache_read_tokens=_int_or_zero(getattr(u, "cache_read_input_tokens", 0)),
            cache_write_tokens=_int_or_zero(getattr(u, "cache_creation_input_tokens", 0)),
        )

    @staticmethod
    def build_image_message(text: str, images: list[tuple[str, bytes]]) -> dict:
        """Anthropic vision format: text block + base64 image blocks."""
        import base64

        content: list[dict] = [{"type": "text", "text": text}]
        for media_type, data in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(data).decode("ascii"),
                    },
                }
            )
        return {"role": "user", "content": content}

    def complete_streaming(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.7,
        extra_body: dict[str, Any] | None = None,
        cache_prefix: str | None = None,
    ) -> Iterator[tuple[str, int, int]]:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": _anthropic_system(system, cache_prefix),
            "messages": messages,
        }
        if _accepts_temperature(model):
            kwargs["temperature"] = temperature
        if extra_body:
            kwargs["extra_body"] = extra_body
        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text, 0, 0
            u = stream.get_final_message().usage
            # Final yield carries the usage; cache stats ride as attributes on it.
            yield LLMResult(
                "",
                u.input_tokens,
                u.output_tokens,
                cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            )


# OpenAI reasoning models (o-series, GPT-5) reject `temperature` (only the default
# is allowed, so a 0.0 ping 400s) and require `max_completion_tokens` instead of
# `max_tokens`. Gemini/Together/non-reasoning models keep the classic params.
_OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def _is_openai_reasoning(model: str) -> bool:
    return model.lower().startswith(_OPENAI_REASONING_PREFIXES)


def _token_sampling_kwargs(model: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    if _is_openai_reasoning(model):
        return {"max_completion_tokens": max_tokens}  # no temperature (default only)
    return {"max_tokens": max_tokens, "temperature": temperature}


class OpenAICompatibleProvider:
    """LLM provider for OpenAI-compatible APIs (OpenAI, Together, Gemini, Fireworks, …)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        default_model: str = "meta-llama/Llama-3-70b-chat-hf",
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "The 'openai' package is required for OpenAI-compatible providers. "
                "Install it with: pip install paradigm[openai]"
            ) from e

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=_llm_timeout())
        self._default_model = default_model

    @property
    def default_model(self) -> str:
        return self._default_model

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.7,
        extra_body: dict[str, Any] | None = None,
        cache_prefix: str | None = None,
    ) -> tuple[str, int, int]:
        full_messages = [
            {"role": "system", "content": _openai_system(system, cache_prefix)}
        ] + messages
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": full_messages,
            **_token_sampling_kwargs(model, max_tokens, temperature),
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        # OpenAI-compatible endpoints auto-cache; report cached-prompt tokens as
        # reads (no explicit write/read split). prompt_tokens already INCLUDES the
        # cached portion, so subtract it to keep input_tokens = uncached input,
        # matching the Anthropic convention.
        cached = _openai_cached_tokens(usage)
        return LLMResult(
            content,
            max(0, input_tokens - cached),
            output_tokens,
            cache_read_tokens=cached,
        )

    @staticmethod
    def build_image_message(text: str, images: list[tuple[str, bytes]]) -> dict:
        """OpenAI-compatible vision format: text part + data-URL image_url parts."""
        import base64

        content: list[dict] = [{"type": "text", "text": text}]
        for media_type, data in images:
            b64 = base64.standard_b64encode(data).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}}
            )
        return {"role": "user", "content": content}

    def complete_streaming(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.7,
        extra_body: dict[str, Any] | None = None,
        cache_prefix: str | None = None,
    ) -> Iterator[tuple[str, int, int]]:
        full_messages = [
            {"role": "system", "content": _openai_system(system, cache_prefix)}
        ] + messages
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": full_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            **_token_sampling_kwargs(model, max_tokens, temperature),
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        stream = self._client.chat.completions.create(**kwargs)
        input_tokens = 0
        output_tokens = 0
        cached = 0
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content, 0, 0
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens
                cached = _openai_cached_tokens(chunk.usage)
        yield LLMResult("", max(0, input_tokens - cached), output_tokens, cache_read_tokens=cached)


def create_provider(config: ProviderConfig) -> LLMProvider:
    """Factory to create an LLMProvider from config.

    Args:
        config: Provider configuration.

    Returns:
        Configured LLMProvider instance.

    Raises:
        ValueError: If provider type is unknown or API key env var is not set.
    """
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise ValueError(
            f"Environment variable '{config.api_key_env}' is not set. "
            f"Required for provider type '{config.type}'."
        )

    if config.type == "anthropic":
        kwargs: dict = {"api_key": api_key}
        if config.default_model:
            kwargs["default_model"] = config.default_model
        return AnthropicProvider(**kwargs)

    if config.type == "openai_compatible":
        if not config.base_url:
            raise ValueError("base_url is required for openai_compatible providers")
        kwargs = {"api_key": api_key, "base_url": config.base_url}
        if config.default_model:
            kwargs["default_model"] = config.default_model
        return OpenAICompatibleProvider(**kwargs)

    raise ValueError(
        f"Unknown provider type: '{config.type}'. Use 'anthropic' or 'openai_compatible'."
    )
