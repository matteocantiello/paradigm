"""Base agent implementation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from paradigm.agents.providers import LLMProvider

# Streaming side-channel. The sink (if attached) is invoked from a worker thread
# (generation runs in ``asyncio.to_thread``), so any implementation MUST be
# thread-safe. Args: (agent_id, stream_id, chunk, event, usage).
StreamEvent = Literal["start", "chunk", "final"]
StreamSink = Callable[[str, str, str, StreamEvent, "TokenUsage | None"], None]


class Message(BaseModel):
    """Structured message for agent communication."""

    model_config = ConfigDict(populate_by_name=True)

    from_agent: str = Field(..., alias="from")
    to: str  # "team", agent_id, or "editor"
    thread_id: str
    phase: str
    message_type: str = Field(..., alias="type")
    content: str
    references: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Token usage tracking."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class AgentResponse(BaseModel):
    """Agent response with content and token usage."""

    content: str
    usage: TokenUsage
    model: str
    # Correlates the streamed chunks (if any) with this final response so the
    # display layer can finalize the right bubble. Empty when streaming is off.
    stream_id: str = ""


class Agent:
    """Base agent class that calls an LLM provider."""

    def __init__(
        self,
        agent_id: str,
        skill_profile: str,
        system_prompt: str,
        provider: LLMProvider,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 8192,
        temperature: float = 1.0,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        """Initialize agent.

        Args:
            agent_id: Unique agent identifier
            skill_profile: Agent skill type (theorist, analyst, etc.)
            system_prompt: System prompt defining agent behavior
            provider: LLM provider for API calls
            model: Model to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            extra_body: Provider-specific extra parameters (e.g. thinking mode)
        """
        self.agent_id = agent_id
        self.skill_profile = skill_profile
        self.system_prompt = system_prompt
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.extra_body = extra_body

        self.skills: list[str] = []

        self._provider = provider
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        # Optional streaming side-channel (set by the orchestrator). When present
        # we stream every turn so the UI animates live; otherwise behavior is
        # byte-identical to before.
        self._stream_sink: StreamSink | None = None
        # Coalesce raw deltas until at least this many chars are buffered before
        # firing a "chunk" event (0 = forward every delta). Tames back-pressure.
        self._stream_min_chars: int = 0

    # Threshold above which we use streaming to avoid Anthropic's 10-minute timeout
    _STREAMING_THRESHOLD = 8192

    @property
    def provider(self) -> Any:
        """The agent's LLM provider (for one-off calls that bypass generate()'s
        streaming side-channel, e.g. topic classification)."""
        return self._provider

    def set_stream_sink(self, sink: StreamSink | None, *, min_chars: int = 0) -> None:
        """Attach (or clear) a streaming side-channel. See ``StreamSink``.

        Args:
            sink: Callback invoked with start/chunk/final events, or ``None``.
            min_chars: Coalesce deltas until this many chars buffer (0 = every delta).
        """
        self._stream_sink = sink
        self._stream_min_chars = max(0, min_chars)

    async def generate(
        self,
        prompt: str,
        context: list[dict[str, str]] | None = None,
        max_tokens: int | None = None,
    ) -> AgentResponse:
        """Generate a response using the LLM provider.

        Uses streaming automatically for large max_tokens to avoid
        Anthropic's 10-minute request timeout.

        Args:
            prompt: User prompt
            context: Optional conversation context as list of {role, content} dicts
            max_tokens: Override max tokens for this call (defaults to agent's max_tokens)

        Returns:
            AgentResponse with content and token usage
        """
        messages = []

        # Add context if provided
        if context:
            messages.extend(context)

        # Add current prompt
        messages.append({"role": "user", "content": prompt})

        effective_max_tokens = max_tokens or self.max_tokens
        stream_id = uuid.uuid4().hex[:12]

        # Run the blocking provider call off the event loop so the loop stays
        # free to service the WebSocket (pings, live broadcasts). When a stream
        # sink is attached we always stream so even short turns animate live;
        # otherwise the size threshold decides (large calls stream to dodge
        # Anthropic's 10-minute timeout).
        response = await self._generate_once(messages, effective_max_tokens, stream_id)
        if response.content.strip():
            return response

        # Empty completion — never a valid answer. Two known causes: a provider
        # flake (Gemini occasionally returns nothing for a large prompt) and a
        # thinking model exhausting max_tokens before any VISIBLE text (a
        # Sonnet-5 editor burned its whole 16384 budget on thinking and returned
        # ""). One retry with doubled headroom covers both; both calls' usage is
        # carried on the returned response so token accounting stays truthful.
        retry_tokens = max(effective_max_tokens, min(effective_max_tokens * 2, 32768))
        _logger.warning(
            "%s returned an empty completion (%d/%d output tokens) — retrying with %d",
            self.agent_id,
            response.usage.output_tokens,
            effective_max_tokens,
            retry_tokens,
        )
        retry = await self._generate_once(messages, retry_tokens, uuid.uuid4().hex[:12])
        retry.usage = TokenUsage(
            input_tokens=response.usage.input_tokens + retry.usage.input_tokens,
            output_tokens=response.usage.output_tokens + retry.usage.output_tokens,
            total_tokens=response.usage.total_tokens + retry.usage.total_tokens,
        )
        return retry

    async def _generate_once(
        self, messages: list[dict[str, str]], max_tokens: int, stream_id: str
    ) -> AgentResponse:
        """One provider call (streaming or sync per the usual thresholds)."""
        if self._stream_sink is not None or max_tokens >= self._STREAMING_THRESHOLD:
            return await asyncio.to_thread(
                self._generate_streaming, messages, max_tokens, stream_id
            )
        return await asyncio.to_thread(self._generate_sync, messages, max_tokens, stream_id)

    def _generate_sync(
        self, messages: list[dict[str, str]], max_tokens: int, stream_id: str = ""
    ) -> AgentResponse:
        """Non-streaming API call for small responses."""
        content, input_tokens, output_tokens = self._provider.complete(
            model=self.model,
            system=self.system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=self.temperature,
            extra_body=self.extra_body,
        )

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens

        return AgentResponse(content=content, usage=usage, model=self.model, stream_id=stream_id)

    def _generate_streaming(
        self, messages: list[dict[str, str]], max_tokens: int, stream_id: str = ""
    ) -> AgentResponse:
        """Streaming API call (avoids 10-min timeout; feeds the live stream sink).

        Chunks are always buffered into the returned ``AgentResponse`` (so every
        caller is unaffected) and, if a sink is attached, also forwarded live.
        """
        content_parts: list[str] = []
        input_tokens = 0
        output_tokens = 0
        sink = self._stream_sink
        min_chars = self._stream_min_chars
        pending: list[str] = []
        pending_len = 0

        def _flush() -> None:
            nonlocal pending, pending_len
            if pending and sink is not None:
                sink(self.agent_id, stream_id, "".join(pending), "chunk", None)
            pending = []
            pending_len = 0

        if sink is not None:
            sink(self.agent_id, stream_id, "", "start", None)

        for chunk, in_tok, out_tok in self._provider.complete_streaming(
            model=self.model,
            system=self.system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=self.temperature,
            extra_body=self.extra_body,
        ):
            if chunk:
                content_parts.append(chunk)
                if sink is not None:
                    pending.append(chunk)
                    pending_len += len(chunk)
                    if pending_len >= min_chars:
                        _flush()
            if in_tok or out_tok:
                input_tokens = in_tok
                output_tokens = out_tok

        _flush()  # emit any buffered remainder before the final event
        content = "".join(content_parts)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens

        if sink is not None:
            sink(self.agent_id, stream_id, "", "final", usage)

        return AgentResponse(content=content, usage=usage, model=self.model, stream_id=stream_id)

    def get_total_usage(self) -> TokenUsage:
        """Get total token usage for this agent.

        Returns:
            TokenUsage with cumulative token counts
        """
        return TokenUsage(
            input_tokens=self.total_input_tokens,
            output_tokens=self.total_output_tokens,
            total_tokens=self.total_input_tokens + self.total_output_tokens,
        )

    def reset_usage(self) -> None:
        """Reset token usage counters."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def format_message(
        self,
        to: str,
        thread_id: str,
        phase: str,
        message_type: str,
        content: str,
        references: list[dict[str, str]] | None = None,
        **metadata: Any,
    ) -> Message:
        """Format a structured message.

        Args:
            to: Recipient (team, agent_id, or editor)
            thread_id: Research thread ID
            phase: Current research phase
            message_type: Message type (proposal, critique, question, etc.)
            content: Message content
            references: Optional references (papers, etc.)
            **metadata: Additional metadata

        Returns:
            Structured Message object
        """
        return Message(
            from_agent=self.agent_id,
            to=to,
            thread_id=thread_id,
            phase=phase,
            message_type=message_type,
            content=content,
            references=references or [],
            metadata=metadata,
        )
