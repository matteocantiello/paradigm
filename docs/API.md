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
| `interactive` | bool | No | Interactive supervision: the user approves key decisions during the run (hypothesis selection, experiment plan, PI reflection). Default: `false` |
| `model_tier` | string | No | `premium` or `open`. `null` = whatever the active config runs |
| `config_overrides` | object | No | Override config values for this cycle |

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -d '{
    "seed_prompt": "Explain the period-luminosity relation for Cepheids",
    "mode": "directed",
    "interactive": true,
    "model_tier": "premium"
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
  "interactive": true,
  "model_tier": "premium",
  "datasets": null,
  "resumed_from": null,
  "created_at": "2026-02-27T12:00:00Z",
  "updated_at": null
}
```

#### Attach a Dataset to a Cycle

```
POST /api/v1/research/{cycle_id}/datasets?filename=catalog.csv
```

Attach a dataset file to a **pending** cycle (returns `409` once the session has started). The request body is the **raw file bytes** — no multipart encoding:

```bash
curl -X POST "http://localhost:8000/api/v1/research/cycle-abc123/datasets?filename=catalog.csv" \
  --data-binary @catalog.csv
```

| Parameter | In | Required | Description |
|-----------|-----|----------|-------------|
| `filename` | query | Yes | Original filename; sanitized server-side |

Files land in a per-cycle holding dir (`data/uploads/<cycle_id>/`) and are staged into the sandbox-visible shared data dir (with data-card schema previews) when the session starts. Allowed extensions: `.csv .tsv .txt .json .dat .fits .parquet .npy .npz .h5 .hdf5` (`415` otherwise). Max 100 MB (`413`); empty bodies are rejected (`400`).

**Response:** `201 Created` — the updated cycle, with the stored path appended to `datasets`.

#### Resume / Continue a Cycle

```
POST /api/v1/research/{cycle_id}/resume
```

Continue a cycle from its last checkpoint as a **new run**, with optional steering. Resume is checkpoint-granularity: the prior cycle's checkpoint plus your comment are delivered to a fresh continuation run as first-round guidance. A new cycle is created (linked via `resumed_from`); the original is untouched. Works for interrupted/failed/aborted *and* completed cycles (the latter = "extend this further"). Returns `429` when the server is at its concurrent-session capacity.

**Request body (optional):**

| Field | Type | Description |
|-------|------|-------------|
| `comment` | string | Steering note delivered with the continuation context (max 10,000 chars) |

**Response:** `201 Created` — the new cycle (already `running`, with `resumed_from` set).

#### Research Stats

```
GET /api/v1/research/stats
```

Headline counts for the dashboard overview.

**Response:**

```json
{
  "total_cycles": 42,
  "papers_published": 17,
  "total_tokens": 128394502
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
  "completed_phases": ["seeding"],
  "created_at": "2026-02-27T12:00:05Z",
  "updated_at": "2026-02-27T12:02:36Z"
}
```

#### Get Session History

```
GET /api/v1/sessions/{session_id}/history?limit=100&offset=0
```

Returns the full interaction event history for a session.

#### Get Session Knowledge

```
GET /api/v1/sessions/{session_id}/knowledge
```

Returns the current knowledge architecture snapshot for a running session (entities, hypotheses, evidence, open questions, research goals, tournament state).

**Response:**

```json
{
  "session_id": "sess-xyz789",
  "knowledge": {
    "entities": [...],
    "relationships": [...],
    "hypotheses": [...],
    "evidence": [...],
    "open_questions": [...],
    "research_goals": [...],
    "conflicts": [...],
    "assumptions": [...],
    "tournament_rankings": [...],
    "world_model_summary": "...",
    "evidence_landscape_summary": "...",
    "tournament_summary": "..."
  }
}
```

#### Get Session Event Stream

```
GET /api/v1/sessions/{session_id}/event-stream
```

Returns the per-thread, seq-ordered dashboard event stream — the durable record the orchestrator writes to `data/threads/<thread_id>/events.jsonl` and the source for the epistemic graphs (literature constellation, evidence, replay). Works for live sessions and finished ones (the thread is resolved via the cycle store after the session is evicted).

**Response:**

```json
{
  "thread_id": "thread-abc",
  "events": [
    {"seq": 142, "ts": "...", "type": "hypothesis.created",
     "phase": "ideation", "round": 2, "agent": "theorist-0", "payload": {}}
  ]
}
```

Events are ordered by `seq` (monotonic within a run) — never by timestamp.

If the session has no thread yet, returns `{"thread_id": null, "events": []}`.

#### Get Session Artifact

```
GET /api/v1/sessions/{session_id}/artifacts/{artifact_path}
```

Serves a run artifact (e.g. an experiment figure) by its data-dir-relative path, as a binary file response with the guessed media type. The orchestrator records artifact paths relative to the data dir; paths are resolved and confined to the data dir AND a known artifact root (`executions/`, `workspaces/`, `papers/`, `threads/`) — anything else is a `404`.

```
GET /api/v1/sessions/sess-xyz789/artifacts/executions/exec-123/figure_1.png
```

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

Returns full paper content including body, abstract, review scores, and metadata. Both paper summaries and details include `judge_scores` — the quality ledger's auto-judge result when `orchestrator.enable_quality_ledger` is on (`null` otherwise):

```json
{
  "judge_scores": {
    "novelty": 7, "rigor": 8, "clarity": 8, "significance": 6, "honesty": 9,
    "composite": 76.0,
    "justification": "…one sentence…",
    "judge_model": "gemini-3.5-flash"
  }
}
```

#### Get Session Outputs

```
GET /api/v1/sessions/{session_id}/outputs
```

Returns outputs (papers, figures, etc.) produced by a session.

#### Get Paper Artifacts

```
GET /api/v1/papers/{paper_id}/artifacts
```

Returns which artifacts are available for a paper (literature searches, reviews, transcript, experiments, figures).

**Response:**

```json
{
  "paper_id": "paper-abc123",
  "has_paper": true,
  "has_literature": true,
  "has_reviews": true,
  "has_transcript": true,
  "has_experiments": true,
  "has_figures": true,
  "experiment_files": ["analysis.py", "simulation.py"],
  "figure_files": ["plot1.png", "spectrum.png"]
}
```

#### Get Paper Literature

```
GET /api/v1/papers/{paper_id}/literature
```

Returns parsed literature search log with structured data about all searches performed and unique papers found.

**Response:**

```json
{
  "thread_id": "",
  "total_searches": 3,
  "searches": [
    {
      "search_num": 1,
      "phase": "seeding",
      "agent_id": "agent-theorist-1",
      "query": "stochastic low-frequency variability massive OB stars",
      "papers": [
        {
          "rank": 1,
          "title": "Low-frequency photometric variability in massive stars",
          "authors": "Bowman, D. M. et al.",
          "year": "2019",
          "arxiv_id": "1901.04515",
          "arxiv_url": "https://arxiv.org/abs/1901.04515"
        }
      ]
    }
  ],
  "unique_papers": [...]
}
```

#### Get Paper Reviews

```
GET /api/v1/papers/{paper_id}/reviews
```

Returns raw review markdown content.

**Response:**

```json
{
  "paper_id": "paper-abc123",
  "filename": "reviews.md",
  "content_type": "text/markdown",
  "content": "# Peer Review Report\n..."
}
```

#### Get Paper Digest

```
GET /api/v1/papers/{paper_id}/digest
```

Returns the plain-language Digest (layman summary) markdown for a paper, generated at cycle end when `journal.enable_digest` is on. Same response shape as reviews (`PaperArtifactContent`); `404` if no digest was generated. The artifacts endpoint reports availability via `has_digest`.

#### Get Paper PDF

```
GET /api/v1/papers/{paper_id}/pdf
```

Serves the paper's PDF as a binary response. Returns a pre-built PDF if present; otherwise renders the stored body to LaTeX and compiles it on demand (figures resolve from the paper's `figures/` dir). Responds `503` with a clear message if no LaTeX engine is installed, `404` if the paper body is unavailable. The artifacts endpoint reports availability via `has_pdf`.

#### Get Paper Transcript

```
GET /api/v1/papers/{paper_id}/transcript
```

Returns raw conversation transcript markdown.

#### Get Paper Experiment

```
GET /api/v1/papers/{paper_id}/experiments/{filename}
```

Returns experiment source code content. Filenames are validated against path traversal.

#### Get Paper Figure

```
GET /api/v1/papers/{paper_id}/figures/{filename}
```

Serves a figure image file as a binary response with appropriate content type. Filenames are validated against path traversal.

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

**Request body (all fields optional):**

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Model identifier |
| `provider` | string | LLM provider name |
| `max_tokens` | int | Max output tokens |
| `token_budget` | int | Token budget for this agent |
| `extra_body` | object | Extra parameters passed to the LLM provider |

---

### Model Catalog

#### List Models

```
GET /api/v1/models?refresh=false
```

Models the agent picker can offer, grouped by provider. Returns a curated shortlist per provider by default; with `?refresh=true`, each provider whose API key is set is queried for its live model list (cached ~1h; a failed live fetch falls back to that provider's curated list, with the failure reason in `error`).

**Response:**

```json
{
  "providers": [
    {
      "name": "anthropic",
      "family": "anthropic",
      "label": "Anthropic",
      "available": true,
      "source": "curated",
      "error": "",
      "models": [
        {"id": "claude-opus-4-8", "label": "Claude Opus 4.8"}
      ]
    }
  ]
}
```

`available` reflects whether the provider's API key env var is set. The provider's configured default model is always selectable even if it's not in the shortlist.

---

### Config Mode & Tiers

Switch between production and testing configurations at runtime, and inspect the per-cycle model tiers.

#### Get Model Tiers

```
GET /api/v1/config/tiers
```

The model tiers a new cycle can choose between (the Setup Wizard's Models toggle) plus which one the active config resembles.

**Response:**

```json
{
  "tiers": [
    {"id": "premium", "label": "Top models",
     "description": "Frontier closed models (GPT-5.5, Claude Opus/Sonnet 5, Gemini) — best quality, roughly $15–25 per cycle.",
     "available": true},
    {"id": "open", "label": "Open models",
     "description": "Open weights on Together serverless (GLM-5.2, Kimi K2.6, MiniMax M3) — roughly $2–3 per cycle.",
     "available": true}
  ],
  "default": "premium"
}
```

`available` is key-gated (e.g. the `open` tier needs `TOGETHER_API_KEY`). Pass the chosen tier as `model_tier` when creating a cycle.

#### Get Config Mode

```
GET /api/v1/config/mode
```

**Response:**

```json
{
  "mode": "production",
  "testing_available": true
}
```

#### Set Config Mode

```
PUT /api/v1/config/mode
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mode` | string | Yes | `production` or `testing` |

**Example:**

```bash
curl -X PUT http://localhost:8000/api/v1/config/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "testing"}'
```

**Response:**

```json
{
  "mode": "testing",
  "testing_available": true
}
```

---

### Settings

Runtime settings, organized by config section. Changes apply to the live config (next cycle picks them up) — they are not written back to the YAML file.

#### Get All Settings

```
GET /api/v1/settings
```

Returns all sections with current values:

```json
{
  "orchestrator": {"max_rounds_per_phase": 10, "...": "..."},
  "sandbox": {"enabled": true, "network_mode": "bridge", "...": "..."},
  "literature": {"...": "..."},
  "knowledge": {"...": "..."},
  "memory": {"...": "..."},
  "citation": {"...": "..."},
  "journal": {"...": "..."}
}
```

#### Update a Settings Section

```
PUT /api/v1/settings/{section}
```

`section` is one of: `orchestrator`, `sandbox`, `literature`, `knowledge`, `memory`, `citation`, `journal` (`404` otherwise). The body is a partial object of that section's fields; only the fields you send (non-null) are applied. Returns the full updated settings.

```bash
curl -X PUT http://localhost:8000/api/v1/settings/orchestrator \
  -H "Content-Type: application/json" \
  -d '{"enable_verification": true, "max_loop_backs": 1}'
```

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
  "model": "claude-opus-4-8",
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
  "decision_type": "",
  "choices": [],
  "multi_select": false,
  "default_ids": [],
  "timeout_seconds": 300,
  "timestamp": "2026-02-27T12:10:00Z"
}
```

**Structured decisions (interactive mode):** typed decision points fill the extra fields; plain phase-transition approvals leave them empty.

| Field | Description |
|-------|-------------|
| `decision_type` | The decision kind: `hypothesis_selection`, `experiment_plan`, or `pi_reflection` |
| `choices` | Selectable choices, each `{id, label, detail, score}` (`score` = Elo rating for hypothesis selection) |
| `multi_select` | Whether multiple choices may be selected (true for hypothesis selection) |
| `default_ids` | The preselected choice ids (e.g. the tournament winners, or the PI's proposed verdict) |

If no `approval_response` arrives within `timeout_seconds` (300), the server auto-continues with the defaults, so an unattended run never stalls.

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

Categories worth handling for responsiveness UX:

| Category | Meaning |
|----------|---------|
| `guidance_delivered` | A user steering message was drained into the agents' prompts (metadata carries the text, phase, and round) — confirm delivery in the UI |
| `run_parked` | The engine actually parked at the pause gate — agents have stopped (a pause click before this is only *requested*) |
| `run_resumed` | The engine resumed after a pause |

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

#### `knowledge_update`

Knowledge architecture state update. Sent when the session's world model, evidence graph, or hypothesis tournament changes.

```json
{
  "type": "knowledge_update",
  "entities": [{"name": "Cepheids", "type": "object", "description": "..."}],
  "relationships": [...],
  "hypotheses": [{"id": "h1", "text": "...", "status": "active"}],
  "evidence": [...],
  "open_questions": [...],
  "research_goals": [...],
  "conflicts": [...],
  "assumptions": [...],
  "tournament_rankings": [...],
  "world_model_summary": "Current understanding of...",
  "evidence_landscape_summary": "Evidence supports...",
  "tournament_summary": "Leading hypothesis is...",
  "timestamp": "2026-02-27T12:06:00Z"
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
  "modifications": {"selected_ids": ["hyp-2", "hyp-5"]}
}
```

`decision` must be one of: `continue`, `pause`, `abort`.

For structured decisions (`decision_type` set on the request):

- `notes` — free text; becomes guidance for the team (e.g. staged for the next discussion round, or appended to the experiment plan as an `OPERATOR DIRECTIVE`).
- `modifications.selected_ids` — the chosen choice ids. For `hypothesis_selection` this is the set of hypotheses to carry forward; for `pi_reflection` the first id is the chosen verdict (`proceed` / `loop_back_execution` / `loop_back_planning` / `call_it`). Omit to accept the defaults.

#### `session_control`

Control the session lifecycle.

```json
{
  "type": "session_control",
  "action": "pause",
  "checkpoint_id": null
}
```

`action` must be one of: `pause`, `resume`, `checkpoint`, `rewind`, `abort`.

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
    sessions.py        Session management + start/list + knowledge
    agents.py          Agent configuration
    papers.py          Paper browsing/export + artifact endpoints
    config.py          Config mode (production/testing) + model tiers
    models.py          Model catalog for the agent picker
    settings.py        Settings (orchestrator, sandbox, literature, etc.)
    ws.py              WebSocket endpoint
  models/
    research.py        Research cycle Pydantic schemas
    session.py         Session state schemas
    agents.py          Agent config schemas
    messages.py        WebSocket message protocol (discriminated unions)
    papers.py          Paper/output schemas + artifact models
    settings.py        Settings Pydantic schemas
  services/
    session_manager.py Core: manages running sessions, intervention queues
    ws_display.py      DisplayManager -> WebSocket bridge
    agent_router.py    Routes user interventions to agents
    checkpoint.py      Checkpoint/fork logic
    demo_runner.py     Demo mode cycle simulation
    artifact_parser.py Paper artifact parsing (literature logs, directory scanning)
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
