# CLAUDE.md — Paradigm Project Instructions

## ⚠️ MANDATORY: Project History Logging

**Every time the human gives you a prompt or instruction, you MUST append it to `.planning/HISTORY.md` before doing anything else.** This is non-negotiable.

Record:
- The date (if a new day)
- The prompt number (sequential)
- A brief title describing the request
- The full prompt text (quoted with `>`)
- Key decisions made (if any)
- Artifacts produced or modified (if any)

This creates a complete, reproducible trail of how the project was built. If you forget to log a prompt, add it retroactively as soon as you notice.

---

## Project Overview

Paradigm is an agentic science platform where AI agents collaborate to do research, write papers, and submit them to peer review. See `.planning/SPEC.md` for the full specification and `.planning/ROADMAP.md` for the implementation plan.

## Key Architecture Decisions

Read `.planning/DECISIONS.md` before making architectural changes. Key constraints:

- **Orchestrator is plain Python** (not an agent, not a framework). It must be deterministic and debuggable.
- **Agents are Claude API calls** with differentiated system prompts. No fine-tuning.
- **SQLite + ChromaDB** for storage. Single-node only for now.
- **Docker containers** for code execution sandbox. `--network=none`.
- **Domain-agnostic**: No hardcoded scientific domain assumptions anywhere.
- **Markdown** for paper format (with LaTeX math blocks).

## Project Structure

```
src/paradigm/          ← All source code
  main.py              ← CLI entry point (click or argparse)
  config.py            ← YAML config loader
  orchestrator/        ← Core orchestration engine
  agents/              ← Agent definitions and prompts
  literature/          ← arXiv API, embeddings, corpus
  sandbox/             ← Docker-based code execution
  journal/             ← Peer review pipeline
  storage/             ← Database, checkpoints, graveyard
  logging/             ← Structured event logging
tests/                 ← pytest tests
docker/                ← Dockerfile for sandbox
configs/               ← YAML configuration files
```

## Coding Standards

- **Python 3.12+**. Use type hints everywhere.
- **Async/await** for I/O-bound operations (API calls, Docker).
- **Pydantic** for data models and validation.
- **No classes where functions suffice.** But use classes for stateful components (agents, orchestrator, database).
- **Structured logging**: All events as JSON. Use the `logging/events.py` module.
- **Error handling**: Never silently swallow exceptions. Log and propagate or handle explicitly.
- **Tests**: Write tests as you go. `pytest` with `pytest-asyncio` for async tests.

## Important Patterns

### Agent Communication
All agent interactions go through the orchestrator. Agents NEVER communicate directly. Every message is a structured dict with: `from`, `to`, `thread_id`, `phase`, `type`, `content`, `references`.

### Checkpointing
Research threads must have compressed checkpoints. When an agent resumes work, it receives the checkpoint (not the full conversation history). Use Claude to summarize long conversations into checkpoints.

### State Machine
The research cycle follows a strict phase progression defined in `orchestrator/phases.py`. Phase transitions are explicit and logged.

### Token Budget
Every API call's token usage is tracked. The orchestrator enforces per-thread and per-agent budgets defined in config.

## Dependencies

Core:
- `anthropic` — Claude API SDK
- `chromadb` — Vector search
- `pydantic` — Data validation
- `pyyaml` — Config files
- `docker` — Docker SDK for Python
- `httpx` — HTTP client (for arXiv API)
- `pymupdf` — PDF text extraction

Dev:
- `pytest`, `pytest-asyncio`
- `ruff` — Linting and formatting

## Running the Project

```bash
# Install
pip install -e ".[dev]"

# Run a directed research cycle
paradigm run --mode directed --prompt "Explain the period-luminosity relation for Cepheids"

# Run an exploratory session
paradigm run --mode explore --topic "massive star variability"

# Check status
paradigm status

# View a published paper
paradigm paper <paper_id>
```

## Environment Variables

- `ANTHROPIC_API_KEY` — Required. Claude API key.
- `PARADIGM_CONFIG` — Optional. Path to config YAML (default: `configs/default.yaml`).
- `PARADIGM_DATA_DIR` — Optional. Data directory (default: `./data`).
- `PARADIGM_LOG_LEVEL` — Optional. Logging level (default: `INFO`).

## Common Tasks

### Adding a new agent skill
1. Create a new YAML prompt in `src/paradigm/agents/prompts/`
2. Add the skill to the taxonomy in `agents/skills.py`
3. Register it in the config

### Adding a new research phase
1. Add the phase to the enum in `orchestrator/phases.py`
2. Define transitions in/out
3. Implement the phase handler in `orchestrator/engine.py`

### Modifying the paper format
1. Update the template in `journal/submission.py`
2. Update the review criteria if needed

## What NOT to Do

- Don't use LangChain, CrewAI, AutoGen, or similar frameworks. We need full control.
- Don't add a web server or API until the CLI works end-to-end.
- Don't optimize for performance before the loop works.
- Don't hardcode any domain-specific knowledge in the orchestrator or infrastructure.
- Don't let agents communicate outside the orchestrator's message protocol.
