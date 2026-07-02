"""WebSocket endpoint for live session interaction."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

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

# If no message received within this window, assume connection is dead.
# The frontend sends a ping every 30s, so 90s gives 3 missed pings of slack.
RECEIVE_TIMEOUT = 90


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

    # Accept BEFORE the session-existence check so a "session not found" close
    # (4004) actually reaches the browser. Closing BEFORE accept is a rejected
    # handshake (HTTP 403), which browsers surface as a generic abnormal close
    # (1006) — so the client never sees 4004 and reconnects forever. A stale tab
    # pointed at a deleted session (or one lost on a backend restart) then floods
    # the log with 403s every ~30s. Post-accept, the client reads 4004 and stops.
    await websocket.accept()

    # Verify session exists
    state = manager.get_state(session_id)
    if state is None:
        await websocket.close(code=4004, reason="Session not found")
        return

    await manager.connect_ws(session_id, websocket)

    try:
        while True:
            # Timeout detects dead connections when the client stops sending
            # heartbeats. The frontend pings every 30s, so 90s allows 3 misses.
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=RECEIVE_TIMEOUT)
            except TimeoutError:
                logger.info(
                    "WebSocket receive timeout for session %s — closing dead connection",
                    session_id,
                )
                await websocket.close(code=1000, reason="Idle timeout")
                break

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

            # Heartbeat: client pings, server pongs
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            # A malformed-but-JSON payload (missing/typed-wrong field) or a
            # handler error must NOT tear down the whole socket — reply with an
            # error frame and keep the connection alive.
            try:
                if msg_type == "approval_response":
                    msg = ApprovalResponseMsg(**data)
                    await manager.respond_to_approval(msg.request_id, msg.decision)

                elif msg_type == "session_control":
                    msg = SessionControlMsg(**data)
                    await _handle_session_control(manager, websocket, session_id, msg)

                elif msg_type == "user_intervention":
                    msg = UserInterventionMsg(**data)
                    logger.info(
                        "User intervention for session %s: %s -> %s",
                        session_id,
                        msg.target_agent,
                        msg.action,
                    )
                    # Carry the action so the agents know how to treat the note.
                    text = msg.content or ""
                    if msg.action and msg.action not in ("message", "guidance"):
                        text = f"[{msg.action}] {text}".strip()
                    await manager.queue_user_guidance(session_id, text, msg.target_agent)

                elif msg_type == "user_message":
                    msg = UserMessageMsg(**data)
                    logger.info(
                        "User message for session %s -> %s",
                        session_id,
                        msg.target_agent or "orchestrator",
                    )
                    await manager.queue_user_guidance(session_id, msg.content, msg.target_agent)

                else:
                    await websocket.send_text(
                        ErrorMsg(
                            code="unknown_message_type",
                            message=f"Unknown message type: {msg_type}",
                        ).model_dump_json()
                    )
            except ValidationError as e:
                await websocket.send_text(
                    ErrorMsg(
                        code="invalid_message",
                        message=f"Invalid {msg_type} payload: {e.error_count()} error(s)",
                    ).model_dump_json()
                )
            except Exception:
                logger.exception("Error handling %s message for session %s", msg_type, session_id)
                await websocket.send_text(
                    ErrorMsg(
                        code="message_handler_error",
                        message=f"Failed to handle {msg_type} message",
                    ).model_dump_json()
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception:
        logger.exception("WebSocket error for session %s", session_id)
    finally:
        await manager.disconnect_ws(session_id, websocket)


async def _handle_session_control(
    manager, websocket: WebSocket, session_id: str, msg: SessionControlMsg
) -> None:
    """Handle session control actions (pause, resume, abort).

    Manual checkpoint and rewind-to-checkpoint are NOT implemented; the client
    gets an explicit error frame instead of a silent no-op.
    """
    if msg.action == "pause":
        await manager.pause_session(session_id)
    elif msg.action == "resume":
        await manager.resume_session(session_id)
    elif msg.action in ("checkpoint", "rewind"):
        await websocket.send_text(
            ErrorMsg(
                code="not_supported",
                message=f"Session control action '{msg.action}' is not supported",
            ).model_dump_json()
        )
    elif msg.action == "abort":
        await manager.abort_session(session_id)
    else:
        await websocket.send_text(
            ErrorMsg(
                code="unknown_action",
                message=f"Unknown session control action: {msg.action}",
            ).model_dump_json()
        )
