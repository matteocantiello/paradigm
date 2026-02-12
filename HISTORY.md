# Paradigm — Project History

This file records every prompt and instruction given during the development of Paradigm, in chronological order. It serves as a reproducible trail of how the project was conceived, planned, and built.

---

## 2026-02-11

### Prompt 1 — Initial Vision & Planning Request

> I am starting an ambitious project to create an agentic AI platform. I need to carefully plan and want to build this with Claude Code. I need some help to decide how to plan, make the right architectural choices, and get started with a minimal working version of this so that I can test.

Accompanied by a detailed notes document covering: multi-agent research swarm, literature corpus access, hypothesis generation, peer review system, sandbox safety, incentive design, and references to moltbook/OpenClaw/agent skills frameworks.

**Key decisions made in discussion:**
- Domain-agnostic from the start (not specialized to one field)
- Python scripts in Docker containers for computational experiments
- Full arXiv API access (live search) for literature corpus
- No AI frameworks (CrewAI, AutoGen, etc.) — plain Python orchestrator

**Artifacts produced:**
- `.planning/SPEC.md` — Full system specification
- `.planning/ROADMAP.md` — 7-phase implementation plan
- `.planning/ARCHITECTURE.md` — Component diagrams and data flows
- `.planning/DECISIONS.md` — 7 architecture decision records
- `CLAUDE.md` — Claude Code project instructions
- `README.md` — Project README

### Prompt 2 — Add Project History Tracking

> One thing I'd like to add, is recording (in a history.md file) all the prompts that I will give you during the process of creating this project, so that we maintain a history of the project. Could you create that file and add the instructions so that claude always record this as we move forward?

**Action:** Created `.planning/HISTORY.md` and added history-keeping instructions to `CLAUDE.md`.

### Prompt 3 — Phase 0 Implementation Start

> Read all files in .planning/ and CLAUDE.md. Then start Phase 0 from the ROADMAP: initialize the Python project with pyproject.toml, set up the directory structure from the SPEC, implement config.py (YAML config loader with defaults), storage/database.py (SQLite schema for papers, agents, threads, graveyard, events), agents/base.py (base agent class that calls Claude API and tracks token usage), and logging/events.py (structured JSONL event logger). Write unit tests for each. Make sure python -m paradigm --help works at the end. Remember to log this prompt in .planning/HISTORY.md.

**Key decisions:**
- Setting up the full directory structure from SPEC.md
- Using Python 3.12+ with type hints everywhere
- Pydantic for data models and validation
- Async/await for I/O-bound operations

**Artifacts produced:**
- `pyproject.toml` — Project metadata and dependencies
- `src/paradigm/` — Full directory structure (all subdirectories)
- `src/paradigm/__init__.py` — Package initialization
- `src/paradigm/__main__.py` — Module entry point
- `src/paradigm/main.py` — CLI entry point with Click commands
- `src/paradigm/config.py` — YAML config loader with Pydantic validation
- `src/paradigm/storage/database.py` — SQLite schema (6 tables) with CRUD operations
- `src/paradigm/agents/base.py` — Base agent class with Claude API integration
- `src/paradigm/logging/events.py` — Structured JSON-lines event logger
- `configs/default.yaml` — Default configuration
- `tests/test_config.py` — Configuration tests (7 tests)
- `tests/test_database.py` — Database tests (11 tests)
- `tests/test_logging.py` — Event logging tests (10 tests)
- `tests/test_agents.py` — Agent tests (6 tests)
- `verify_setup.py` — Setup verification script
- `INSTALL.md` — Installation guide
- `PHASE0_COMPLETE.md` — Phase 0 completion report
- `README.md` — Updated with Phase 0 status

**Phase 0 Status:** Complete — All exit criteria met

### Prompt 4: Debug CI Failure

> we just implemented CI, but I received a notification from github actions that something didn't work

**Key decisions:** Investigating and fixing CI failures in `.github/workflows/ci.yml`
**Artifacts modified:**
- `src/paradigm/agents/prompts/.gitkeep` — created (missing dir caused verify_setup.py to fail)
- `tests/test_database.py` — removed spurious f-string prefix (F541)
- `src/paradigm/agents/base.py` — migrated Pydantic v1 `class Config` to v2 `model_config`

### Prompt 5: CI Error Log Analysis

> (User shared CI error log showing `src/paradigm/agents/prompts` directory missing)

**Root cause:** The `prompts/` directory was empty and had no `.gitkeep`, so git didn't track it. The `verify_setup.py` script checks for it and exits with code 1.
**Fix:** Added `.gitkeep` to `src/paradigm/agents/prompts/`

### Prompt 6: Move to Phase 1

> CI passed. We can move to phase 1

**Key decisions:** Begin Phase 1 implementation per ROADMAP.md
**Artifacts created:**
- `src/paradigm/literature/arxiv.py` — ArxivClient + ArxivPaper model (async, rate-limited, XML parsing)
- `src/paradigm/literature/embeddings.py` — EmbeddingStore (ChromaDB wrapper, semantic search)
- `src/paradigm/literature/citations.py` — CitationTracker (SQLite-based citation graph)
- `src/paradigm/literature/corpus.py` — Corpus (unified search combining arXiv + local + citations)
- `src/paradigm/literature/__init__.py` — Public exports
- `tests/test_arxiv.py` — 11 tests for arXiv client
- `tests/test_embeddings.py` — 9 tests for embeddings
- `tests/test_citations.py` — 9 tests for citations
- `tests/test_corpus.py` — 13 tests for corpus
**Artifacts modified:**
- `src/paradigm/config.py` — Fixed Pydantic v2 `validate_default=True` for api_key validator
- `tests/test_config.py` — Fixed macOS path resolution in tests

### Prompt 7: Integrate Scientific Skills from External Repo

> I would like to implement in the plan the ability (for the agents) to acquire scientific skills from https://github.com/K-Dense-AI/claude-scientific-skills. I think it would be good to have the ability to either load all the agents with all the skills, or only load them with one skill, or assign a set of different skills, to mimic a diverse population of scientific expertise. Can we adapt the plan accordingly?

**Key decisions:** Explore the external skills repo and design a flexible skill-loading system for agents.

### Prompt 8: Implement Scientific Skills Integration

> Implement the following plan: Scientific Skills Integration — Implementation Plan.
> Full plan covering: git submodule, skill loader/registry, role prompts, agent factory, config updates, tests.

**Key decisions**: Follow the approved plan exactly.
**Artifacts produced or modified**:
- `vendor/claude-scientific-skills/` — git submodule (142 scientific skills)
- `src/paradigm/agents/skills.py` — SkillRegistry + compose_system_prompt
- `src/paradigm/agents/factory.py` — AgentFactory with skill_mode support
- `src/paradigm/agents/prompts/*.yaml` — 8 role prompts (theorist, analyst, synthesizer, experimentalist, writer, skeptic, editor, reviewer)
- `src/paradigm/config.py` — Added SkillsConfig
- `src/paradigm/agents/base.py` — Added skills attribute
- `src/paradigm/agents/__init__.py` — Updated exports
- `configs/default.yaml` — Added skills config section
- `tests/test_skills.py` — 28 tests
- `tests/test_factory.py` — 15 tests

### Prompt 9: History Logging & Roadmap Update

> It seems history.md has only prompts from phase 0. What about our recent prompts? Also did you adapt the roadmap to include that modification (addition of skills)?

**Key decisions:** Update ROADMAP.md to reflect completed phases and the new skills integration step.
**Artifacts modified:**
- `.planning/HISTORY.md` — added this prompt
- `ROADMAP.md` — marked Phase 0 and Phase 1 complete, added skills integration to Phase 0

### Prompt 10: Move to Phase 2

> Let's move to the next phase

**Key decisions:** Plan and implement Phase 2 — Orchestrator + Ideation Loop.

## 2026-02-12

### Prompt 11 — Implement Phase 2: Orchestrator + Ideation Loop

> Implement the following plan: Phase 2: Orchestrator + Ideation Loop — Implementation Plan. Create phases.py (phase state machine), scheduler.py (agent turn-taking), checkpoints.py (checkpoint compression), engine.py (main orchestration loop). Update main.py CLI to wire to engine. Write tests for all new modules.

**Key decisions**: Follow the approved plan exactly. Implementation order: phases → scheduler → checkpoints → engine → main.py → tests → verification.

**Artifacts**: New files: `orchestrator/phases.py`, `orchestrator/scheduler.py`, `storage/checkpoints.py`, `orchestrator/engine.py`. Modified: `main.py`, `__init__.py` files. Tests: `test_phases.py`, `test_scheduler.py`, `test_checkpoints.py`, `test_orchestrator.py`.

### Prompt 12 — Commit and Push Phase 2

> ok, let's commit and push

**Artifacts**: Committed 12 files (1699 insertions) as `1bd409c` and pushed to `origin/main`.

### Prompt 13 — Confirm HISTORY.md Is Updated

> are you keeping history.md updated?

Confirmed HISTORY.md was current. User requested logging all interactions including minor ones.

### Prompt 14 — Log All Interactions

> yes please

Added retroactive entries for the commit/push and confirmation prompts.

### Prompt 15 — Push HISTORY.md Update

> let's push

**Artifacts**: Committed and pushed HISTORY.md update as `bedce3e`.

### Prompt 16 — Merge Duplicate HISTORY.md Files

> I see the issue. We have two history.md, one in paradigm/ and one in paradigm/.planning/ Could we merge the two files to paradigm/history.md ?

**Action**: Merged `.planning/HISTORY.md` into `HISTORY.md` (root), renumbered prompts sequentially, removed the duplicate.
