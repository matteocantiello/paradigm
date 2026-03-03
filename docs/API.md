# Paradigm Web API Reference

Complete reference for the Paradigm FastAPI backend. The API provides REST endpoints for managing research cycles and sessions, plus a WebSocket endpoint for real-time monitoring and interaction.

---

## Table of Contents

1. [Setup](#1-setup)
2. [Authentication](#2-authentication)
3. [REST Endpoints](#3-rest-endpoints)
4. [WebSocket Protocol](#4-websocket-protocol)
5. [Architecture](#5-architecture)
6. [Configuration](#6-configuration)

---

## 1. Setup

### Installation

```bash
# Install API dependencies
pip install -e ".[api]"
```

This installs FastAPI, Uvicorn, and websockets as optional dependencies.

### Running the Server

```bash
# Development (auto-reload)
uvicorn backend.api.main:app --reload --port 8000

# Production (single worker — required for in-memory state)
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> **Note:** Use `--workers 1` because the SessionManager holds in-memory state. Multi-worker deployments would require external state storage (e.g., Redis).

### Interactive Documentation

Once the server is running:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI spec:** http://localhost:8000/openapi.json

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude agents | Yes (for running cycles) |
| `PARADIGM_CONFIG` | Path to config YAML | No (default: `configs/default.yaml`) |
| `PARADIGM_API_KEY` | API key for request authentication | No (auth disabled if unset) |
| `PARADIGM_CORS_ORIGINS` | Comma-separated allowed CORS origins | No (default: `http://localhost:3000,http://localhost:5173`) |

---

## 2. Authentication

By default, authentication is disabled for development. To enable API key auth:

```bash
export PARADIGM_API_KEY="your-secret-key"
```

Once set, all requests must include the key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8000/api/v1/research
```

The health endpoint (`GET /health`) is always unauthenticated.

---

## 3. REST Endpoints

### Health Check

```
GET /health
```

Returns server health status. Always unauthenticated.

**Response:**

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

### Research Cycles

Research cycles represent a complete research task — from seed prompt to published paper.

#### Create a Research Cycle

```
POST /api/v1/research
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `seed_prompt` | string | Yes | Research question or topic (1-10,000 chars) |
| `mode` | string | No | `directed`, `explore`, or `test` (default: `directed`) |
| `team_roles` | string[] | No | Custom agent roles (default: mode-specific team) |
| `config_overrides` | object | No | Override config values for this cycle |

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -d '{
    "seed_prompt": "Explain the period-luminosity relation for Cepheids",
    "mode": "directed"
  }'
```

**Response:** `201 Created`

```json
{
  "cycle_id": "cycle-abc123",
  "seed_prompt": "Explain the period-luminosity relation for Cepheids",
  "mode": "directed",
  "status": "pending",
  "team_roles": null,
  "thread_id": null,
  "paper_id": null,
  "current_phase": null,
  "created_at": "2026-02-27T12:00:00Z",
  "updated_at": null
}
```

#### List Research Cycles

```
GET /api/v1/research?offset=0&limit=20
```

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `offset` | int | 0 | Pagination offset |
| `limit` | int | 20 | Max items (1-100) |

**Response:**

```json
{
  "items": [...],
  "total": 5,
  "offset": 0,
  "limit": 20
}
```

#### Get a Research Cycle

```
GET /api/v1/research/{cycle_id}
```

Returns a single cycle by ID. Returns `404` if not found.

#### Delete a Research Cycle

```
DELETE /api/v1/research/{cycle_id}
```

Cancels a pending/running cycle or deletes a completed one. Returns `204 No Content`.

---

### Sessions

Sessions are live executions of a research cycle. A cycle can have multiple sessions (e.g., re-runs with different configs).

#### Start a Session

```
POST /api/v1/research/{cycle_id}/sessions
```

Creates and starts a new session for the given cycle. The research cycle runs as a background task.

**Request body (optional):**

| Field | Type | Description |
|-------|------|-------------|
| `config_overrides` | object | Override config values for this session |

**Response:** `201 Created`

```json
{
  "session_id": "sess-xyz789",
  "cycle_id": "cycle-abc123",
  "status": "starting",
  "thread_id": null,
  "current_phase": null,
  "created_at": "2026-02-27T12:00:05Z"
}
```

#### List Sessions for a Cycle

```
GET /api/v1/research/{cycle_id}/sessions
```

#### Get Session State

```
GET /api/v1/sessions/{session_id}
```

Returns the full session state snapshot:

```json
{
  "session_id": "sess-xyz789",
  "cycle_id": "cycle-abc123",
  "status": "running",
  "current_phase": "ideation",
  "round_num": 3,
  "max_rounds": 10,
  "thread_id": "thread-abc",
  "active_agents": {"theorist-0": "active", "analyst-1": "idle"},
  "total_tokens": 45200,
  "total_searches": 4,
  "papers_found": 12,
  "elapsed_seconds": 151.3,
  "created_at": "2026-02-27T12:00:05Z",
  "updated_at": "2026-02-27T12:02:36Z"
}
```

#### Get Session History

```
GET /api/v1/sessions/{session_id}/history?limit=100&offset=0
```

Returns the full interaction event history for a session.

---

### Checkpoints

#### List Checkpoints

```
GET /api/v1/sessions/{session_id}/checkpoints
```

#### Create a Checkpoint

```
POST /api/v1/sessions/{session_id}/checkpoints
```

Manually create a checkpoint of the current session state.

#### Fork from Checkpoint

```
POST /api/v1/checkpoints/{checkpoint_id}/fork
```

Create a new session branching from a previous checkpoint.

---

### Papers

#### List Papers

```
GET /api/v1/papers?status=published&limit=20&offset=0
```

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | all | Filter: `draft`, `submitted`, `published`, `rejected` |
| `limit` | int | 20 | Max items |
| `offset` | int | 0 | Pagination offset |

#### Get Paper Details

```
GET /api/v1/papers/{paper_id}
```

Returns full paper content including body, abstract, review scores, and metadata.

#### Get Session Outputs

```
GET /api/v1/sessions/{session_id}/outputs
```

Returns outputs (papers, figures, etc.) produced by a session.

---

### Agents

#### List Agent Types

```
GET /api/v1/agents
```

Returns all available agent types with their default configurations.

#### Get Agent Config

```
GET /api/v1/agents/{agent_type}
```

#### Update Agent Config

```
PUT /api/v1/agents/{agent_type}
```

**Request body:**

| Field | Type | Description |
|-------|------|-------------|
| `provider` | string | LLM provider name |
| `model` | string | Model identifier |
| `max_tokens` | int | Max output tokens |
| `temperature` | float | Sampling temperature |

---

## 4. WebSocket Protocol

The WebSocket endpoint provides real-time bidirectional communication for monitoring and controlling live research sessions.

### Connection

```
WS /api/v1/sessions/{session_id}/ws?api_key=YOUR_KEY
```

When `PARADIGM_API_KEY` is set, WebSocket connections must include the API key as a query parameter (`api_key`) or via the `X-API-Key` header. Connections without a valid key are rejected with code `4001`.

On connect, the server immediately sends a `session_state` message with the current state snapshot.

### Server -> Client Messages

All messages have a `type` field used for routing.

#### `session_state`

Full state sync. Sent on connect and after major state changes.

```json
{
  "type": "session_state",
  "session_id": "sess-xyz789",
  "status": "running",
  "current_phase": "ideation",
  "round_num": 3,
  "max_rounds": 10,
  "active_agents": {"theorist-0": "active"},
  "total_tokens": 45200,
  "protocol_version": "1.0",
  "timestamp": "2026-02-27T12:02:36Z"
}
```

#### `agent_output_stream`

Streamed agent output chunks. Reassemble by `stream_id`; `is_final` marks the last chunk.

```json
{
  "type": "agent_output_stream",
  "agent_id": "theorist-0",
  "role": "theorist",
  "content": "Based on the literature, I propose...",
  "phase": "ideation",
  "stream_id": "stream-001",
  "is_final": false,
  "tokens": 128,
  "model": "claude-opus-4-6",
  "timestamp": "2026-02-27T12:02:40Z"
}
```

#### `agent_step_complete`

Agent finished a step (one complete response).

```json
{
  "type": "agent_step_complete",
  "agent_id": "theorist-0",
  "role": "theorist",
  "summary": "Proposed 2 hypotheses about period-luminosity relation",
  "output_id": "out-123",
  "next_agent": "analyst-1",
  "phase": "ideation",
  "tokens": 2048,
  "timestamp": "2026-02-27T12:02:55Z"
}
```

#### `phase_transition`

Research phase changed.

```json
{
  "type": "phase_transition",
  "from_phase": "ideation",
  "to_phase": "planning",
  "max_rounds": 10,
  "active_agents": 5,
  "total_agents": 6,
  "timestamp": "2026-02-27T12:10:00Z"
}
```

#### `round_update`

Round progress within a phase.

```json
{
  "type": "round_update",
  "round_num": 4,
  "max_rounds": 10,
  "phase": "ideation",
  "timestamp": "2026-02-27T12:05:00Z"
}
```

#### `approval_request`

System needs user input (e.g., phase transition approval in interactive mode).

```json
{
  "type": "approval_request",
  "request_id": "req-456",
  "title": "Phase Transition",
  "description": "Proceed from ideation to planning?",
  "from_phase": "ideation",
  "to_phase": "planning",
  "options": ["continue", "pause", "abort"],
  "timeout_seconds": 300,
  "timestamp": "2026-02-27T12:10:00Z"
}
```

#### `notification`

Non-blocking informational message.

```json
{
  "type": "notification",
  "level": "info",
  "category": "search",
  "message": "Found 12 papers on Cepheid period-luminosity relation",
  "metadata": {"papers_found": 12, "query": "Cepheid period-luminosity"},
  "timestamp": "2026-02-27T12:03:00Z"
}
```

#### `error`

Error or warning.

```json
{
  "type": "error",
  "code": "agent_failure",
  "message": "theorist-0 failed: rate limit exceeded",
  "recoverable": true,
  "timestamp": "2026-02-27T12:04:00Z"
}
```

### Client -> Server Messages

#### `approval_response`

Respond to an approval request.

```json
{
  "type": "approval_response",
  "request_id": "req-456",
  "decision": "continue",
  "notes": "Looks good, proceed to planning",
  "modifications": null
}
```

`decision` must be one of: `continue`, `pause`, `abort`.

#### `session_control`

Control the session lifecycle.

```json
{
  "type": "session_control",
  "action": "pause",
  "checkpoint_id": null
}
```

`action` must be one of: `pause`, `resume`, `checkpoint`, `rewind`.

#### `user_intervention`

Redirect, constrain, or inform an agent.

```json
{
  "type": "user_intervention",
  "target_agent": "theorist-0",
  "action": "redirect",
  "content": "Focus on the metallicity dependence instead"
}
```

`action` must be one of: `redirect`, `constrain`, `inform`.

#### `user_message`

Send a message to a specific agent or the orchestrator.

```json
{
  "type": "user_message",
  "target_agent": null,
  "content": "Consider looking at the Madore & Freedman (2012) calibration"
}
```

Set `target_agent` to `null` to send to the orchestrator.

---

## 5. Architecture

### Integration with Paradigm Core

The API wraps existing Paradigm internals. Key bridge points:

| Core Component | API Bridge |
|---|---|
| `OrchestrationEngine.run_research_cycle()` | Wrapped in `asyncio.create_task()` per session, tracked by `SessionManager` |
| `InterventionHook` (callable) | Replaced with async hook backed by `asyncio.Event` — blocks until frontend responds via WebSocket |
| `DisplayManager` (100+ methods) | `WebSocketDisplayAdapter` implements the same interface, pushes events to connected WebSocket clients |
| `Database` (SQLite) | Shared instance with WAL mode for concurrent reads |
| `Config` (Pydantic) | Loaded once at startup, injected via FastAPI `app.state` |
| `EventLogger` (JSONL + SQLite) | Reused for audit trail; WebSocket adds real-time forwarding |

### Backend Structure

```
backend/api/
  main.py              FastAPI app, CORS, lifespan
  routes/
    research.py        CRUD for research cycles
    sessions.py        Session management + start/list
    agents.py          Agent configuration
    papers.py          Paper browsing/export
    ws.py              WebSocket endpoint
  models/
    research.py        Research cycle Pydantic schemas
    session.py         Session state schemas
    agents.py          Agent config schemas
    messages.py        WebSocket message protocol (discriminated unions)
    papers.py          Paper/output schemas
  services/
    session_manager.py Core: manages running sessions, intervention queues
    ws_display.py      DisplayManager -> WebSocket bridge
    agent_router.py    Routes user interventions to agents
    checkpoint.py      Checkpoint/fork logic
  middleware/
    auth.py            API key authentication
```

### SessionManager

The `SessionManager` is the core service that manages all running research sessions:

- **In-memory state:** Tracks active sessions, their status, and connected WebSocket clients.
- **Background tasks:** Each session runs `OrchestrationEngine.run_research_cycle()` in an `asyncio.Task`.
- **Intervention bridge:** Converts the synchronous `InterventionHook` callable into an async pattern — the engine blocks on an `asyncio.Event` while the frontend responds via WebSocket.
- **Broadcast:** Pushes display events to all connected WebSocket clients for a session.

### WebSocketDisplayAdapter

The `WebSocketDisplayAdapter` implements the same interface as the terminal `DisplayManager` but serializes each event into a WebSocket message and broadcasts to connected clients. The orchestration engine doesn't know the difference — it calls the same methods regardless of whether output goes to a terminal or a browser.

---

## 6. Configuration

### CORS

CORS origins are configured via the `PARADIGM_CORS_ORIGINS` environment variable. It defaults to localhost development origins. For production, set it to your frontend domain:

```bash
export PARADIGM_CORS_ORIGINS="https://your-frontend.com"
```

Multiple origins can be comma-separated:

```bash
export PARADIGM_CORS_ORIGINS="https://app.example.com,https://staging.example.com"
```

### Export OpenAPI Spec

```bash
python -c "
from backend.api.main import app
import json
print(json.dumps(app.openapi(), indent=2))
" > openapi.json
```

The exported spec can be used to auto-generate TypeScript types for the frontend:

```bash
npx openapi-typescript openapi.json -o frontend/src/api/schema.d.ts
```
