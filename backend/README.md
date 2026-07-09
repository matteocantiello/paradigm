# Paradigm Web API

FastAPI backend for the Paradigm agentic research platform. It wraps the core research engine (`src/paradigm/`) behind REST endpoints and a WebSocket, and is what the React frontend (`frontend/`) talks to.

## Setup

```bash
# Activate the paradigm environment (Python 3.12+)
conda activate paradigm

# Install with API dependencies
pip install -e ".[api]"

# Or install everything
pip install -e ".[api,dev]"
```

## Running

```bash
# Development (auto-reload)
uvicorn backend.api.main:app --reload --port 8000

# Production
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> **Note:** Use `--workers 1` because the SessionManager holds in-memory state.
> For multi-worker deployments, external state (Redis) would be needed.

## API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI spec:** http://localhost:8000/openapi.json

## Authentication

By default, auth is disabled (dev mode). To enable:

```bash
export PARADIGM_API_KEY="your-secret-key"
```

Then pass `X-API-Key: your-secret-key` in request headers.

## Architecture

```
backend/api/
  main.py              # FastAPI app, CORS, lifespan, /health
  routes/
    research.py        # Research cycle CRUD + datasets, resume, stats
    sessions.py        # Session lifecycle, history, event stream, artifacts,
                       # checkpoints, knowledge
    papers.py          # Papers + per-paper artifacts (digest, reviews, PDF, ...)
    agents.py          # Per-role agent configuration
    models.py          # Model catalog for the agent picker
    config.py          # Config mode + model tiers
    settings.py        # Runtime settings (curated config sections)
    ws.py              # WebSocket endpoint
  models/
    research.py        # Research cycle schemas
    session.py         # Session state schemas
    agents.py          # Agent config schemas
    messages.py        # WebSocket message protocol
    papers.py          # Paper/output schemas
    settings.py        # Settings schemas
  services/
    session_manager.py # Core: manages running sessions (approvals, decisions)
    ws_display.py      # DisplayManager -> WebSocket bridge
    cycle_store.py     # SQLite-backed research cycle persistence
    model_tiers.py     # Top-models / open-models tier definitions
    agent_router.py    # Routes user interventions
    checkpoint.py      # Checkpoint/fork logic
    artifact_parser.py # Parses run artifacts for the papers view
    demo_runner.py     # Demo mode cycle simulation
  middleware/
    auth.py            # API key authentication
```

## Endpoints

### Utility

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

### Research cycles (`/api/v1/research`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/research` | Create a research cycle (prompt, mode, interactive flag, model tier) |
| GET | `/api/v1/research` | List cycles |
| GET | `/api/v1/research/stats` | Headline counts for the dashboard (cycles, papers, tokens) |
| GET | `/api/v1/research/{id}` | Cycle detail |
| DELETE | `/api/v1/research/{id}` | Delete a cycle |
| POST | `/api/v1/research/{id}/datasets` | Attach a dataset file to a pending cycle (raw upload; staged into the sandbox-visible data dir at session start) |
| POST | `/api/v1/research/{id}/resume` | Continue a cycle from its last checkpoint as a new run, with optional steering |

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/research/{id}/sessions` | Start a session for a cycle |
| GET | `/api/v1/research/{id}/sessions` | List a cycle's sessions |
| GET | `/api/v1/sessions/{id}` | Session state |
| GET | `/api/v1/sessions/{id}/history` | Message history (reconnect catch-up) |
| GET | `/api/v1/sessions/{id}/event-stream` | Durable per-thread event stream (`data/threads/<id>/events.jsonl`) — powers the epistemic graphs and the Replay page; works for live and finished sessions |
| GET | `/api/v1/sessions/{id}/artifacts/{path}` | Serve a run artifact (e.g. an experiment figure) by data-dir-relative path |
| GET | `/api/v1/sessions/{id}/knowledge` | Knowledge architecture snapshot |
| GET | `/api/v1/sessions/{id}/checkpoints` | List checkpoints |
| POST | `/api/v1/sessions/{id}/checkpoints` | Create a checkpoint |
| POST | `/api/v1/checkpoints/{id}/fork` | Fork a new session from a checkpoint |
| WS | `/api/v1/sessions/{id}/ws` | Live WebSocket |

### Papers and outputs (`/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/sessions/{id}/outputs` | List a session's outputs |
| GET | `/api/v1/sessions/{id}/outputs/{output_id}` | Output detail |
| GET | `/api/v1/papers` | List papers (status filter, judge scores, topics) |
| GET | `/api/v1/papers/{id}` | Paper detail (markdown body) |
| GET | `/api/v1/papers/{id}/artifacts` | Available artifact tabs for this paper |
| GET | `/api/v1/papers/{id}/digest` | Plain-language digest |
| GET | `/api/v1/papers/{id}/literature` | Literature corpus used by the cycle |
| GET | `/api/v1/papers/{id}/reviews` | Internal + peer reviews |
| GET | `/api/v1/papers/{id}/transcript` | Research transcript |
| GET | `/api/v1/papers/{id}/experiments/{filename}` | Experiment code file |
| GET | `/api/v1/papers/{id}/figures/{filename}` | Figure image |
| GET | `/api/v1/papers/{id}/pdf` | PDF export (compiles LaTeX on demand) |

### Agents, models, config, settings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/agents` | List agent types |
| GET | `/api/v1/agents/{type}` | Agent config detail |
| PUT | `/api/v1/agents/{type}` | Update an agent's provider/model (applies next cycle) |
| GET | `/api/v1/models` | Model catalog for the picker, grouped by provider (key-gated); `?refresh=true` fetches live catalogs |
| GET | `/api/v1/config/tiers` | Available model tiers (Top models / Open models) + default |
| GET | `/api/v1/config/mode` | Get config mode (production/testing) |
| PUT | `/api/v1/config/mode` | Switch config mode |
| GET | `/api/v1/settings` | Read curated runtime settings sections |
| PUT | `/api/v1/settings/{section}` | Update a settings section |

## WebSocket Protocol

Connect to `ws://localhost:8000/api/v1/sessions/{session_id}/ws`

### Server -> Client Messages
- `session_state` — Full state sync (on connect)
- `agent_output_stream` — Agent output chunks
- `agent_step_complete` — Agent finished a step
- `phase_transition` — Phase change
- `round_update` — Round progress within a phase
- `approval_request` — Needs user input (phase gates + structured decisions: hypothesis selection, experiment plan, PI reflection; 5-minute timeout falls back to the agents' choice)
- `notification` — Informational events
- `activity_event` — Fine-grained activity feed items
- `draft_update` — Live paper draft status (drafting/drafted/final)
- `experiment_update` — Experiment lifecycle
- `literature_update` — Literature corpus growth
- `knowledge_update` — Knowledge architecture state
- `topics_update` — Topic classification
- `error` — Errors

### Client -> Server Messages
- `approval_response` — Respond to an approval/decision request
- `session_control` — Pause/resume/checkpoint/rewind/abort
- `user_intervention` — Redirect/constrain/inform an agent (lands at the next agent turn)
- `user_message` — Message to an agent

## Export OpenAPI Spec

```bash
python -c "
from backend.api.main import app
import json
print(json.dumps(app.openapi(), indent=2))
" > openapi.json
```
