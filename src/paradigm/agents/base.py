"""Base agent implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from paradigm.agents.providers import LLMProvider


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


class Agent:
    """Base agent class that calls an LLM provider."""

    def __init__(
        self,
        agent_id: str,
        skill_profile: str,
        system_prompt: str,
        provider: LLMProvider,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 4096,
        temperature: float = 1.0,
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
        """
        self.agent_id = agent_id
        self.skill_profile = skill_profile
        self.system_prompt = system_prompt
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        self.skills: list[str] = []

        self._provider = provider
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    # Threshold above which we use streaming to avoid Anthropic's 10-minute timeout
    _STREAMING_THRESHOLD = 8192

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

        if effective_max_tokens >= self._STREAMING_THRESHOLD:
            return self._generate_streaming(messages, effective_max_tokens)
        else:
            return self._generate_sync(messages, effective_max_tokens)

    def _generate_sync(self, messages: list[dict[str, str]], max_tokens: int) -> AgentResponse:
        """Non-streaming API call for small responses."""
        content, input_tokens, output_tokens = self._provider.complete(
            model=self.model,
            system=self.system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=self.temperature,
        )

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens

        return AgentResponse(content=content, usage=usage, model=self.model)

    def _generate_streaming(self, messages: list[dict[str, str]], max_tokens: int) -> AgentResponse:
        """Streaming API call for large responses (avoids 10-min timeout)."""
        content_parts: list[str] = []
        input_tokens = 0
        output_tokens = 0

        for chunk, in_tok, out_tok in self._provider.complete_streaming(
            model=self.model,
            system=self.system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=self.temperature,
        ):
            if chunk:
                content_parts.append(chunk)
            if in_tok or out_tok:
                input_tokens = in_tok
                output_tokens = out_tok

        content = "".join(content_parts)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens

        return AgentResponse(content=content, usage=usage, model=self.model)

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
