# Paradigm Web API

FastAPI backend for the Paradigm agentic research platform.

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
  main.py              # FastAPI app, CORS, lifespan
  routes/
    research.py        # CRUD for research cycles
    sessions.py        # Session management + knowledge endpoint
    agents.py          # Agent configuration
    papers.py          # Paper browsing
    config.py          # Config mode (production/testing)
    ws.py              # WebSocket endpoint
  models/
    research.py        # Research cycle schemas
    session.py         # Session state schemas
    agents.py          # Agent config schemas
    messages.py        # WebSocket message protocol
    papers.py          # Paper/output schemas
  services/
    session_manager.py # Core: manages running sessions
    ws_display.py      # DisplayManager -> WebSocket bridge
    agent_router.py    # Routes user interventions
    checkpoint.py      # Checkpoint/fork logic
    demo_runner.py     # Demo mode cycle simulation
  middleware/
    auth.py            # API key authentication
```

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/research` | Create research cycle |
| GET | `/api/v1/research` | List cycles |
| POST | `/api/v1/research/{id}/sessions` | Start session |
| GET | `/api/v1/sessions/{id}` | Session state |
| WS | `/api/v1/sessions/{id}/ws` | Live WebSocket |
| GET | `/api/v1/papers` | List papers |
| GET | `/api/v1/agents` | List agent types |
| GET | `/api/v1/config/mode` | Get config mode (production/testing) |
| PUT | `/api/v1/config/mode` | Switch config mode |
| GET | `/api/v1/sessions/{id}/knowledge` | Knowledge architecture snapshot |

## WebSocket Protocol

Connect to `ws://localhost:8000/api/v1/sessions/{session_id}/ws`

### Server -> Client Messages
- `session_state` — Full state sync (on connect)
- `agent_output_stream` — Agent output chunks
- `agent_step_complete` — Agent finished a step
- `phase_transition` — Phase change
- `round_update` — Round progress within a phase
- `approval_request` — Needs user input
- `notification` — Informational events
- `error` — Errors
- `knowledge_update` — Knowledge architecture state

### Client -> Server Messages
- `approval_response` — Respond to approval request
- `session_control` — Pause/resume/checkpoint/rewind/abort
- `user_intervention` — Redirect agent
- `user_message` — Message to agent

## Export OpenAPI Spec

```bash
python -c "
from backend.api.main import app
import json
print(json.dumps(app.openapi(), indent=2))
" > openapi.json
```
