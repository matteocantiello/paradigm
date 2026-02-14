"""LLM provider abstraction for multi-backend support."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


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
    ) -> Iterator[tuple[str, int, int]]:
        """Streaming completion.

        Yields partial text chunks as (chunk, 0, 0).
        Final yield has token counts: ("", input_tokens, output_tokens).
        """
        ...


class AnthropicProvider:
    """LLM provider wrapping the Anthropic SDK."""

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-5-20250929") -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
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
    ) -> tuple[str, int, int]:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
        return content, response.usage.input_tokens, response.usage.output_tokens

    def complete_streaming(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.7,
    ) -> Iterator[tuple[str, int, int]]:
        with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        ) as stream:
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

        self._client = OpenAI(api_key=api_key, base_url=base_url)
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
    ) -> tuple[str, int, int]:
        full_messages = [{"role": "system", "content": system}] + messages
        response = self._client.chat.completions.create(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        return content, input_tokens, output_tokens

    def complete_streaming(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.7,
    ) -> Iterator[tuple[str, int, int]]:
        full_messages = [{"role": "system", "content": system}] + messages
        stream = self._client.chat.completions.create(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
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
