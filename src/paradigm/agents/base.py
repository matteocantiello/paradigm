"""Base agent implementation."""

from typing import Any

from anthropic import Anthropic
from pydantic import BaseModel, ConfigDict, Field


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
    """Base agent class that calls Claude API."""

    def __init__(
        self,
        agent_id: str,
        skill_profile: str,
        system_prompt: str,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> None:
        """Initialize agent.

        Args:
            agent_id: Unique agent identifier
            skill_profile: Agent skill type (theorist, analyst, etc.)
            system_prompt: System prompt defining agent behavior
            api_key: Anthropic API key
            model: Claude model to use
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

        self.client = Anthropic(api_key=api_key)
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    async def generate(
        self,
        prompt: str,
        context: list[dict[str, str]] | None = None,
        max_tokens: int | None = None,
    ) -> AgentResponse:
        """Generate a response using Claude API.

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

        # Call Claude API
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=self.temperature,
            system=self.system_prompt,
            messages=messages,
        )

        # Extract content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        # Track token usage
        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
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
