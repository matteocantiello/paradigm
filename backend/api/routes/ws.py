"""WebSocket endpoint for live session interaction."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.middleware.auth import verify_api_key_sync
from backend.api.models.messages import (
    ApprovalResponseMsg,
    ErrorMsg,
    SessionControlMsg,
    UserInterventionMsg,
    UserMessageMsg,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/sessions/{session_id}/ws")
async def session_websocket(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for live session interaction.

    On connect, sends a session_state message with current state.
    Then listens for client messages and routes them appropriately.
    """
    # Authenticate: check API key from query param or first header
    api_key = websocket.query_params.get("api_key")
    if api_key is None:
        # Fall back to header (some WS clients support custom headers)
        api_key = websocket.headers.get("x-api-key")
    if not verify_api_key_sync(api_key):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    manager = websocket.app.state.session_manager

    # Verify session exists
    state = manager.get_state(session_id)
    if state is None:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    await manager.connect_ws(session_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    ErrorMsg(
                        code="invalid_json",
                        message="Could not parse message as JSON",
                    ).model_dump_json()
                )
                continue

            msg_type = data.get("type")

            if msg_type == "approval_response":
                msg = ApprovalResponseMsg(**data)
                await manager.respond_to_approval(msg.request_id, msg.decision)

            elif msg_type == "session_control":
                msg = SessionControlMsg(**data)
                await _handle_session_control(manager, session_id, msg)

            elif msg_type == "user_intervention":
                msg = UserInterventionMsg(**data)
                logger.info(
                    "User intervention for session %s: %s -> %s",
                    session_id,
                    msg.target_agent,
                    msg.action,
                )
                # TODO: Route to agent via agent_router service

            elif msg_type == "user_message":
                msg = UserMessageMsg(**data)
                logger.info(
                    "User message for session %s -> %s",
                    session_id,
                    msg.target_agent or "orchestrator",
                )
                # TODO: Inject into agent conversation

            else:
                await websocket.send_text(
                    ErrorMsg(
                        code="unknown_message_type",
                        message=f"Unknown message type: {msg_type}",
                    ).model_dump_json()
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception:
        logger.exception("WebSocket error for session %s", session_id)
    finally:
        await manager.disconnect_ws(session_id, websocket)


async def _handle_session_control(manager, session_id: str, msg: SessionControlMsg) -> None:
    """Handle session control actions (pause, resume, checkpoint, rewind)."""
    if msg.action == "pause":
        await manager.pause_session(session_id)
    elif msg.action == "resume":
        await manager.resume_session(session_id)
    elif msg.action == "checkpoint":
        # TODO: Trigger manual checkpoint
        pass
    elif msg.action == "rewind":
        # TODO: Rewind to checkpoint
        pass
    elif msg.action == "abort":
        await manager.abort_session(session_id)
