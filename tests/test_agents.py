"""Tests for agent base class."""

from unittest.mock import MagicMock

import pytest

from paradigm.agents.base import Agent, Message


@pytest.fixture
def mock_provider():
    """Create a mock LLM provider for testing."""
    provider = MagicMock()
    provider.complete.return_value = ("test response", 10, 20)
    provider.default_model = "claude-sonnet-4-5-20250929"
    return provider


def test_agent_initialization(mock_provider):
    """Test agent initialization."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        provider=mock_provider,
    )

    assert agent.agent_id == "test-agent"
    assert agent.skill_profile == "theorist"
    assert agent.model == "claude-sonnet-4-5-20250929"
    assert agent.total_input_tokens == 0
    assert agent.total_output_tokens == 0


def test_agent_custom_model(mock_provider):
    """Test agent with custom model."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        provider=mock_provider,
        model="claude-opus-4-6",
        max_tokens=8192,
        temperature=0.5,
    )

    assert agent.model == "claude-opus-4-6"
    assert agent.max_tokens == 8192
    assert agent.temperature == 0.5


def test_format_message(mock_provider):
    """Test message formatting."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        provider=mock_provider,
    )

    message = agent.format_message(
        to="team",
        thread_id="thread-001",
        phase="ideation",
        message_type="proposal",
        content="I propose we study X",
        references=[{"type": "arxiv", "id": "2301.12345"}],
        priority="high",
    )

    assert isinstance(message, Message)
    assert message.from_agent == "test-agent"
    assert message.to == "team"
    assert message.thread_id == "thread-001"
    assert message.phase == "ideation"
    assert message.message_type == "proposal"
    assert message.content == "I propose we study X"
    assert len(message.references) == 1
    assert message.metadata["priority"] == "high"


def test_message_model():
    """Test Message pydantic model."""
    message = Message(
        from_agent="agent-001",
        to="team",
        thread_id="thread-001",
        phase="ideation",
        message_type="proposal",
        content="Test content",
    )

    assert message.from_agent == "agent-001"
    assert message.to == "team"
    assert message.message_type == "proposal"

    # Test alias support
    message_dict = message.model_dump(by_alias=True)
    assert "from" in message_dict
    assert "type" in message_dict


def test_get_total_usage(mock_provider):
    """Test getting total token usage."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        provider=mock_provider,
    )

    # Manually set token counts (simulating API calls)
    agent.total_input_tokens = 1000
    agent.total_output_tokens = 2000

    usage = agent.get_total_usage()
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 2000
    assert usage.total_tokens == 3000


def test_reset_usage(mock_provider):
    """Test resetting token usage."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        provider=mock_provider,
    )

    agent.total_input_tokens = 1000
    agent.total_output_tokens = 2000

    agent.reset_usage()

    assert agent.total_input_tokens == 0
    assert agent.total_output_tokens == 0


class TestEmptyCompletionRetry:
    """An empty completion is never a valid answer (provider flake, or a thinking
    model exhausting max_tokens before any visible text) — generate() retries once
    with doubled headroom and carries BOTH calls' usage."""

    @pytest.mark.asyncio
    async def test_empty_completion_retried_with_more_headroom(self, mock_provider):
        # max_tokens kept under the 8192 streaming threshold so the mocked
        # sync path (provider.complete) is exercised for BOTH attempts.
        mock_provider.complete.side_effect = [("", 100, 1000), ("real review text", 100, 50)]
        agent = Agent(
            agent_id="editor-0",
            skill_profile="editor",
            system_prompt="You are an editor.",
            provider=mock_provider,
            max_tokens=1000,
        )
        resp = await agent.generate("review this")
        assert resp.content == "real review text"
        assert mock_provider.complete.call_count == 2
        # Token accounting carries the failed attempt too.
        assert resp.usage.input_tokens == 200
        assert resp.usage.output_tokens == 1050
        first = mock_provider.complete.call_args_list[0].kwargs["max_tokens"]
        second = mock_provider.complete.call_args_list[1].kwargs["max_tokens"]
        assert second > first

    @pytest.mark.asyncio
    async def test_empty_twice_returns_empty_without_looping(self, mock_provider):
        mock_provider.complete.side_effect = [("", 10, 0), ("   ", 10, 0)]
        agent = Agent(
            agent_id="a",
            skill_profile="theorist",
            system_prompt="x",
            provider=mock_provider,
            max_tokens=1000,
        )
        resp = await agent.generate("q")
        assert resp.content.strip() == ""
        assert mock_provider.complete.call_count == 2  # exactly one retry

    @pytest.mark.asyncio
    async def test_nonempty_completion_not_retried(self, mock_provider):
        agent = Agent(
            agent_id="a",
            skill_profile="theorist",
            system_prompt="x",
            provider=mock_provider,
            max_tokens=1000,
        )
        resp = await agent.generate("q")
        assert resp.content == "test response"
        assert mock_provider.complete.call_count == 1
