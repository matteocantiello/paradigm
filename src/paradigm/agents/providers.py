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


# Claude Opus 4.7+ removed the sampling params — sending `temperature` (or top_p/
# top_k) returns a 400. Omit it for these so the ping AND agent calls succeed.
# Extend this tuple as new such models ship.
_NO_TEMPERATURE_PREFIXES = ("claude-opus-4-7", "claude-opus-4-8")


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
    ) -> tuple[str, int, int]:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
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
        return content, response.usage.input_tokens, response.usage.output_tokens

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
    ) -> Iterator[tuple[str, int, int]]:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if _accepts_temperature(model):
            kwargs["temperature"] = temperature
        if extra_body:
            kwargs["extra_body"] = extra_body
        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text, 0, 0
            final = stream.get_final_message()
            yield "", final.usage.input_tokens, final.usage.output_tokens


class OpenAICompatibleProvider:
    """LLM provider for OpenAI-compatible APIs (Together, Fireworks, DeepInfra, etc.)."""

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
    ) -> tuple[str, int, int]:
        full_messages = [{"role": "system", "content": system}] + messages
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        return content, input_tokens, output_tokens

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
    ) -> Iterator[tuple[str, int, int]]:
        full_messages = [{"role": "system", "content": system}] + messages
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        stream = self._client.chat.completions.create(**kwargs)
        input_tokens = 0
        output_tokens = 0
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content, 0, 0
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens
        yield "", input_tokens, output_tokens


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
