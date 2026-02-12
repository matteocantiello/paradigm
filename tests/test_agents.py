"""Tests for agent base class."""

import os

import pytest

from paradigm.agents.base import Agent, Message


@pytest.fixture
def mock_api_key():
    """Set a mock API key for testing."""
    original_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "test-api-key"
    yield "test-api-key"
    if original_key:
        os.environ["ANTHROPIC_API_KEY"] = original_key
    else:
        del os.environ["ANTHROPIC_API_KEY"]


def test_agent_initialization(mock_api_key):
    """Test agent initialization."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        api_key=mock_api_key,
    )

    assert agent.agent_id == "test-agent"
    assert agent.skill_profile == "theorist"
    assert agent.model == "claude-sonnet-4-5-20250929"
    assert agent.total_input_tokens == 0
    assert agent.total_output_tokens == 0


def test_agent_custom_model(mock_api_key):
    """Test agent with custom model."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        api_key=mock_api_key,
        model="claude-opus-4-6",
        max_tokens=8192,
        temperature=0.5,
    )

    assert agent.model == "claude-opus-4-6"
    assert agent.max_tokens == 8192
    assert agent.temperature == 0.5


def test_format_message(mock_api_key):
    """Test message formatting."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        api_key=mock_api_key,
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


def test_get_total_usage(mock_api_key):
    """Test getting total token usage."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        api_key=mock_api_key,
    )

    # Manually set token counts (simulating API calls)
    agent.total_input_tokens = 1000
    agent.total_output_tokens = 2000

    usage = agent.get_total_usage()
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 2000
    assert usage.total_tokens == 3000


def test_reset_usage(mock_api_key):
    """Test resetting token usage."""
    agent = Agent(
        agent_id="test-agent",
        skill_profile="theorist",
        system_prompt="You are a theorist.",
        api_key=mock_api_key,
    )

    agent.total_input_tokens = 1000
    agent.total_output_tokens = 2000

    agent.reset_usage()

    assert agent.total_input_tokens == 0
    assert agent.total_output_tokens == 0
