# CLAUDE.md — Paradigm Project Instructions

## ⚠️ MANDATORY: Project History Logging

**Every time the human gives you a prompt or instruction, you MUST append it to `HISTORY.md` before doing anything else.** This is non-negotiable.

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

Paradigm is an agentic science platform where AI agents collaborate to do research, write papers, and submit them to peer review. See `SPEC.md` (founding specification) and `ROADMAP.md` (original build plan) — both are HISTORICAL; `docs/MANUAL.md` is the current operator manual and `README.md` the current overview.

## Key Architecture Decisions

Read `DECISIONS.md` (repo root) before making architectural changes. Key constraints:

- **Orchestrator is plain Python** (not an agent, not a framework). It must be deterministic and debuggable.
- **Agents are Claude API calls** with differentiated system prompts. No fine-tuning.
- **SQLite + ChromaDB** for storage. Single-node only for now.
- **Docker containers** for code execution sandbox. Network mode is `bridge` by default (experiments can fetch public data); test-harness configs pin `none`.
- **Domain-agnostic**: No hardcoded scientific domain assumptions anywhere.
- **Markdown** for paper format (with LaTeX math blocks).

## Project Structure

```
src/paradigm/          ← Core library
  main.py              ← CLI entry point
  config.py            ← YAML config loader (providers, tiers, policies)
  orchestrator/        ← Engine + handlers (writing, review, experimentation,
                          literature, reflection, data_provenance, …)
  agents/              ← Agent definitions, prompts, model catalog
  literature/          ← Source providers, corpus, novelty, data_providers
  display/             ← Rich terminal UI (mirrored by the WS adapter)
  sandbox/             ← Docker-based code execution
  journal/             ← Paper models, review pipeline, LaTeX export
  storage/             ← Database, checkpoints, graveyard
  logging/             ← Structured events + per-thread events.jsonl stream
backend/api/           ← FastAPI web API (routes, session manager, WS display
                          adapter, model tiers) — the web platform's backend
frontend/              ← React "Observatory" web app (Vite; landing, wizard,
                          live session view, papers, replay)
tests/                 ← pytest tests
docker/                ← Dockerfile for sandbox
configs/               ← YAML configs (default/production = premium tier,
                          open = open-weights tier, + test harness configs)
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
- Don't optimize for performance before the loop works.
- Don't hardcode any domain-specific knowledge in the orchestrator or infrastructure.
- Don't let agents communicate outside the orchestrator's message protocol.


## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

