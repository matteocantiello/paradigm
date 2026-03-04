"""WebSocket message protocol models (discriminated unions)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

PROTOCOL_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Server → Client messages
# ---------------------------------------------------------------------------


class ServerMessageType(str, Enum):
    """Types of messages sent from server to client."""

    AGENT_OUTPUT_STREAM = "agent_output_stream"
    AGENT_STEP_COMPLETE = "agent_step_complete"
    APPROVAL_REQUEST = "approval_request"
    SESSION_STATE = "session_state"
    PHASE_TRANSITION = "phase_transition"
    ROUND_UPDATE = "round_update"
    ERROR = "error"
    NOTIFICATION = "notification"
    KNOWLEDGE_UPDATE = "knowledge_update"
    LITERATURE_UPDATE = "literature_update"


class AgentOutputStreamMsg(BaseModel):
    """Streamed agent output chunks."""

    type: Literal["agent_output_stream"] = "agent_output_stream"
    agent_id: str
    role: str = ""
    content: str
    phase: str = ""
    stream_id: str = ""
    is_final: bool = False
    tokens: int = 0
    model: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentStepCompleteMsg(BaseModel):
    """Agent finished a step."""

    type: Literal["agent_step_complete"] = "agent_step_complete"
    agent_id: str
    role: str = ""
    summary: str = ""
    output_id: str | None = None
    next_agent: str | None = None
    phase: str = ""
    tokens: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ApprovalRequestMsg(BaseModel):
    """System needs user input (phase transition approval, etc.)."""

    type: Literal["approval_request"] = "approval_request"
    request_id: str
    title: str = ""
    description: str = ""
    from_phase: str = ""
    to_phase: str = ""
    options: list[str] = Field(default_factory=lambda: ["continue", "pause", "abort"])
    timeout_seconds: int | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SessionStateMsg(BaseModel):
    """Full state sync (sent on connect and after major changes)."""

    type: Literal["session_state"] = "session_state"
    session_id: str
    status: str
    current_phase: str | None = None
    round_num: int = 0
    max_rounds: int = 0
    thread_id: str | None = None
    active_agents: dict[str, str] = Field(default_factory=dict)
    total_tokens: int = 0
    total_searches: int = 0
    papers_found: int = 0
    elapsed_seconds: float = 0.0
    completed_phases: list[str] = Field(default_factory=list)
    protocol_version: str = PROTOCOL_VERSION
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PhaseTransitionMsg(BaseModel):
    """Phase transition notification."""

    type: Literal["phase_transition"] = "phase_transition"
    from_phase: str | None = None
    to_phase: str
    max_rounds: int | None = None
    active_agents: int | None = None
    total_agents: int | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RoundUpdateMsg(BaseModel):
    """Round start/progress notification."""

    type: Literal["round_update"] = "round_update"
    round_num: int
    max_rounds: int
    phase: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorMsg(BaseModel):
    """Error or warning."""

    type: Literal["error"] = "error"
    code: str = "unknown"
    message: str
    recoverable: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class NotificationMsg(BaseModel):
    """Non-blocking informational message."""

    type: Literal["notification"] = "notification"
    level: str = "info"  # info, warning, success
    category: str = ""  # search, debate, experiment, writing, review, etc.
    message: str
    metadata: dict[str, object] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LiteraturePaperMsg(BaseModel):
    """A single discovered paper (used inside LiteratureUpdateMsg)."""

    arxiv_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: str = ""


class LiteratureSearchMsg(BaseModel):
    """A single search entry (used inside LiteratureUpdateMsg)."""

    query: str
    agent_id: str
    phase: str = ""
    papers: list[LiteraturePaperMsg] = Field(default_factory=list)


class LiteratureUpdateMsg(BaseModel):
    """Live literature data streamed during a research cycle."""

    type: Literal["literature_update"] = "literature_update"
    searches: list[LiteratureSearchMsg] = Field(default_factory=list)
    unique_papers: list[LiteraturePaperMsg] = Field(default_factory=list)
    total_searches: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class KnowledgeUpdateMsg(BaseModel):
    """Full knowledge architecture snapshot (world model + evidence graph + tournament)."""

    type: Literal["knowledge_update"] = "knowledge_update"
    # World model
    entities: list[dict[str, object]] = Field(default_factory=list)
    relationships: list[dict[str, object]] = Field(default_factory=list)
    hypotheses: list[dict[str, object]] = Field(default_factory=list)
    evidence: list[dict[str, object]] = Field(default_factory=list)
    open_questions: list[dict[str, object]] = Field(default_factory=list)
    research_goals: list[dict[str, object]] = Field(default_factory=list)
    # Evidence graph
    conflicts: list[dict[str, object]] = Field(default_factory=list)
    assumptions: list[dict[str, object]] = Field(default_factory=list)
    provenance_chains: list[dict[str, object]] = Field(default_factory=list)
    # Tournament
    tournament_rankings: list[dict[str, object]] = Field(default_factory=list)
    matchup_results: list[dict[str, object]] = Field(default_factory=list)
    tournament_status: str = ""
    # Pre-rendered summaries
    world_model_summary: str = ""
    evidence_landscape_summary: str = ""
    tournament_summary: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Discriminated union of all server messages
ServerMessage = Annotated[
    AgentOutputStreamMsg
    | AgentStepCompleteMsg
    | ApprovalRequestMsg
    | SessionStateMsg
    | PhaseTransitionMsg
    | RoundUpdateMsg
    | ErrorMsg
    | NotificationMsg
    | KnowledgeUpdateMsg
    | LiteratureUpdateMsg,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Client → Server messages
# ---------------------------------------------------------------------------


class ClientMessageType(str, Enum):
    """Types of messages sent from client to server."""

    USER_INTERVENTION = "user_intervention"
    APPROVAL_RESPONSE = "approval_response"
    USER_MESSAGE = "user_message"
    SESSION_CONTROL = "session_control"


class UserInterventionMsg(BaseModel):
    """Redirect/constrain/inform an agent."""

    type: Literal["user_intervention"] = "user_intervention"
    target_agent: str | None = None
    action: str  # "redirect", "constrain", "inform"
    content: str


class ApprovalResponseMsg(BaseModel):
    """Respond to an approval request."""

    type: Literal["approval_response"] = "approval_response"
    request_id: str
    decision: str  # "continue", "pause", "abort"
    notes: str = ""
    modifications: dict[str, object] | None = None


class UserMessageMsg(BaseModel):
    """Message to agent or orchestrator."""

    type: Literal["user_message"] = "user_message"
    target_agent: str | None = None  # None = orchestrator
    content: str


class SessionControlMsg(BaseModel):
    """Pause/resume/checkpoint/rewind."""

    type: Literal["session_control"] = "session_control"
    action: str  # "pause", "resume", "checkpoint", "rewind"
    checkpoint_id: str | None = None


# Discriminated union of all client messages
ClientMessage = Annotated[
    UserInterventionMsg | ApprovalResponseMsg | UserMessageMsg | SessionControlMsg,
    Field(discriminator="type"),
]
