"""Tests for event logging."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from paradigm.logging.events import Event, EventLogger, EventType


def test_event_serialization():
    """Test event serialization to JSON."""
    event = Event(
        event_type=EventType.AGENT_MESSAGE,
        agent_id="agent-001",
        thread_id="thread-001",
        phase="ideation",
        content="Test message",
        metadata={"key": "value"},
    )

    json_str = event.to_json()
    assert "agent_message" in json_str
    assert "agent-001" in json_str
    assert "Test message" in json_str


@pytest.fixture
def event_logger():
    """Create a temporary event logger for testing."""
    with TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "events.jsonl"
        logger = EventLogger(log_path)
        yield logger


def test_event_logger_creation(event_logger):
    """Test event logger creates log file."""
    assert event_logger.log_path.exists()


def test_log_basic_event(event_logger):
    """Test logging a basic event."""
    event_logger.log(
        EventType.STATE_CHANGE,
        content="State changed",
        thread_id="thread-001",
    )

    # Read back events
    events = event_logger.read_events()
    assert len(events) == 1
    assert events[0].event_type == EventType.STATE_CHANGE
    assert events[0].thread_id == "thread-001"


def test_log_agent_message(event_logger):
    """Test logging an agent message."""
    message = {
        "from": "agent-001",
        "to": "team",
        "type": "proposal",
        "content": "I propose we investigate X",
    }

    event_logger.log_agent_message(
        agent_id="agent-001",
        thread_id="thread-001",
        phase="ideation",
        message=message,
    )

    events = event_logger.read_events(event_type=EventType.AGENT_MESSAGE)
    assert len(events) == 1
    assert events[0].agent_id == "agent-001"
    assert isinstance(events[0].content, dict)


def test_log_api_call(event_logger):
    """Test logging an API call."""
    event_logger.log_api_call(
        agent_id="agent-001",
        model="claude-sonnet-4-5",
        input_tokens=100,
        output_tokens=200,
    )

    events = event_logger.read_events(event_type=EventType.API_CALL)
    assert len(events) == 1
    assert events[0].content["model"] == "claude-sonnet-4-5"
    assert events[0].content["input_tokens"] == 100


def test_log_code_execution(event_logger):
    """Test logging code execution."""
    code = "print('hello')"
    output = "hello\n"

    event_logger.log_code_execution(
        agent_id="agent-001",
        thread_id="thread-001",
        code=code,
        success=True,
        output=output,
    )

    events = event_logger.read_events(event_type=EventType.CODE_EXECUTION)
    assert len(events) == 1
    assert events[0].content["code"] == code
    assert events[0].content["success"] is True


def test_log_error(event_logger):
    """Test logging an error."""
    error = ValueError("Something went wrong")

    event_logger.log_error(error, agent_id="agent-001")

    events = event_logger.read_events(event_type=EventType.ERROR)
    assert len(events) == 1
    assert "Something went wrong" in events[0].content
    assert events[0].metadata["exception_type"] == "ValueError"


def test_read_events_filtering(event_logger):
    """Test reading events with filters."""
    # Log multiple events
    event_logger.log(
        EventType.AGENT_MESSAGE,
        agent_id="agent-001",
        thread_id="thread-001",
    )
    event_logger.log(
        EventType.AGENT_MESSAGE,
        agent_id="agent-002",
        thread_id="thread-001",
    )
    event_logger.log(
        EventType.STATE_CHANGE,
        thread_id="thread-002",
    )

    # Filter by thread_id
    thread1_events = event_logger.read_events(thread_id="thread-001")
    assert len(thread1_events) == 2

    # Filter by event_type
    message_events = event_logger.read_events(event_type=EventType.AGENT_MESSAGE)
    assert len(message_events) == 2

    # Filter by agent_id
    agent1_events = event_logger.read_events(agent_id="agent-001")
    assert len(agent1_events) == 1


def test_read_events_with_limit(event_logger):
    """Test reading events with limit."""
    # Log 10 events
    for i in range(10):
        event_logger.log(EventType.STATE_CHANGE, content=f"Event {i}")

    # Read only last 5
    events = event_logger.read_events(limit=5)
    assert len(events) == 5


def test_log_state_change(event_logger):
    """Test logging state changes."""
    event_logger.log_state_change(
        thread_id="thread-001",
        old_state="ideation",
        new_state="planning",
    )

    events = event_logger.read_events(event_type=EventType.STATE_CHANGE)
    assert len(events) == 1
    assert events[0].content["old_state"] == "ideation"
    assert events[0].content["new_state"] == "planning"
