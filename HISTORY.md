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

### Prompt 17 — Commit and Push HISTORY.md Consolidation

> great! Let's commit and push

**Artifacts**: Committed and pushed as `1d5988c`.

### Prompt 18 — Plan Next Step

> Let's plan next step. Are we settled on what we need to do?

Reviewed roadmap. Phase 2 complete, Phase 3 (Docker sandbox) is next. Offered choice: move to Phase 3, do real e2e test first, or something else.

### Prompt 19 — Real End-to-End Test

> 2

User chose to do a real end-to-end test of Phase 2 with live Claude API calls before moving on.

---

## 2026-02-12

### Prompt 20 — Implement E2E Test Hardening Plan

> Implement the following plan: Real End-to-End Test of Phase 2

Implementing the plan from the planning session: add error handling around agent API calls and checkpoint creation, add progress output to CLI, add `--rounds` CLI option, log literature search failures, and update ROADMAP.md to mark Phase 2 complete.

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Error handling, progress output
- `src/paradigm/main.py` — `--rounds` CLI option
- `ROADMAP.md` — Phase 2 marked complete

### Prompt 21 — .env File for API Key

> could you check that it is now in configs/default.yaml? [...] Yes, let's use a .env file that is not tracked by git

Moved API key from `configs/default.yaml` to `.env` file, added `python-dotenv` dependency, added `.env` to `.gitignore`.

**Artifacts modified:** `.env` (new), `configs/default.yaml`, `.gitignore`, `pyproject.toml`, `src/paradigm/config.py`

### Prompt 22 — Fix data_dir Resolution

> yes, fix that so data_dir resolves relative to the project root

The `data_dir: "./data"` config was resolving relative to cwd, causing data to land in `configs/data/` when run from `configs/`. Fixed `load_config` to resolve relative paths against the project root (config file's parent directory).

**Artifacts modified:** `src/paradigm/config.py`

### Prompt 23 — Move to Phase 3: Computational Sandbox

> Let's move on to phase 3 and build the sandbox

Plan and implement Phase 3 — Docker-based code execution sandbox.

### Prompt 24 — Implement Phase 3: Computational Sandbox

> Implement the following plan: Phase 3: Computational Sandbox

Implementing the approved plan: models.py (Pydantic models), safety.py (AST-based code scanner), docker.py (Docker SDK wrapper), executor.py (high-level pipeline), Dockerfile.sandbox, and tests.

**Artifacts produced:**
- `src/paradigm/sandbox/models.py` — ExecutionRequest, ExecutionResult, ExecutionStatus, SafetyVerdict, OutputFile
- `src/paradigm/sandbox/safety.py` — SafetyScanner (AST + regex code scanning)
- `src/paradigm/sandbox/docker.py` — ContainerManager (async Docker SDK wrapper)
- `src/paradigm/sandbox/executor.py` — CodeExecutor (safety scan → Docker execute → log)
- `src/paradigm/sandbox/__init__.py` — Module exports
- `docker/Dockerfile.sandbox` — Python 3.12-slim sandbox image
- `tests/test_sandbox.py` — ~27 tests with mocked Docker

### Prompt 25 — Install Docker

> Let's install docker

Docker Desktop installed via `brew install --cask docker` (required manual terminal run for sudo). Image `paradigm-sandbox:latest` built and smoke-tested.

### Prompt 26 — End-to-End Sandbox Test

> let's test the full pipeline end to end

Run the full CodeExecutor pipeline with real Docker — safety scan → execute in container → collect results.

### Prompt 27 — Commit and Push Phase 3

> let's commit and push

Committed and pushed Phase 3 as `7b0aefa` (15 files, 1143 insertions).

### Prompt 28 — Move to Phase 4

> good catch. Just removed it. Let's move to the next phase

Plan and implement Phase 4 — Writing + Paper Generation.

### Prompt 29 — Implement Phase 4: Writing + Paper Generation

> Implement the following plan: Phase 4: Writing + Paper Generation

Implementing the approved plan: `journal/paper.py` (data models), phase transitions, scheduler priorities, config fields, engine writing/review phases, and tests.

**Artifacts produced/modified:**
- `src/paradigm/journal/paper.py` — PaperSection, SectionDraft, PaperDraft, ReviewFeedback, section assignment, parsing
- `src/paradigm/journal/__init__.py` — Module exports
- `src/paradigm/orchestrator/phases.py` — PLANNING → WRITING transition
- `src/paradigm/orchestrator/scheduler.py` — WRITING/INTERNAL_REVIEW priorities
- `src/paradigm/config.py` — enable_writing, max_review_iterations
- `configs/default.yaml` — Writing config section
- `src/paradigm/orchestrator/engine.py` — _run_writing_phase, _run_review_phase, updated team roles
- `tests/test_writing.py` — Paper model + engine integration tests

### Prompt 30 — What's Left To Do?

> Ok. What's left to do?

Reviewed ROADMAP.md. Phases 0-4 complete. Remaining: Phase 5 (Peer Review + Publication), Phase 6 (Multi-Cycle + Polish), plus future phases.

### Prompt 31 — End-to-End Live Test

> Can we test if what we have done so far works?

Run the full pipeline live (SEEDING → IDEATION → PLANNING → WRITING → INTERNAL_REVIEW) with real Claude API calls, 1 round per phase to minimize cost.

**Result:** Full cycle completed successfully. Paper generated: "Enhanced Convective Overshooting in Massive Stars" (17.5K chars, 380K tokens total). Thread `thread-9a80e2395c85`, paper `paper-cfda5f7cd61b`.

### Prompt 32 — Where Is the Paper Stored?

> where is the paper that was generated stored?

Paper is in the SQLite database (`data/paradigm.db`, `papers` table). Exported a copy to `data/paper-cfda5f7cd61b.md`.

### Prompt 33 — Wire Up Paper CLI Commands

> yes, I think that would be a useful tool to have

Implemented `paradigm papers` (list papers with status/title) and `paradigm paper <id>` (view paper, `--export` to save as markdown file).

**Artifacts modified:** `src/paradigm/main.py`

### Prompt 34 — Auto-Save Papers as Markdown Files

> In general it would be good to have a folder where all the papers are stored as md files (beside the vector_db container)

Added `data/papers/` directory for automatic markdown file storage. Papers are written to disk as `.md` files when created and when revised.

**Artifacts modified:**
- `src/paradigm/config.py` — Added `papers_dir` to `StorageConfig`
- `src/paradigm/orchestrator/engine.py` — Added `_save_paper_file()`, called on paper creation and revision

### Prompt 35 — Implement Phase 5: Peer Review + Publication

> Implement the following plan: Phase 5: Peer Review + Publication

Implementing the approved plan: peer review pipeline (SUBMITTED → PEER_REVIEW → PUBLISHED/REJECTED), structured review scoring, publication to corpus, graveyard for rejected papers.

**Artifacts produced:**
- `src/paradigm/journal/review.py` — PeerReview model, parse_peer_review(), synthesize_decision()
- `src/paradigm/journal/publication.py` — publish_paper(), reject_paper()
- `tests/test_peer_review.py` — Comprehensive tests for peer review pipeline

**Artifacts modified:**
- `src/paradigm/journal/__init__.py` — New exports
- `src/paradigm/orchestrator/scheduler.py` — PEER_REVIEW/REVISION priorities
- `src/paradigm/orchestrator/engine.py` — Submission, peer review, revision phases
- `src/paradigm/config.py` — enable_peer_review, num_reviewers, max_revision_rounds
- `configs/default.yaml` — Peer review config section
- `src/paradigm/agents/prompts/reviewer.yaml` — Structured scoring instructions
- `src/paradigm/literature/corpus.py` — ingest_internal_paper() method
- `src/paradigm/orchestrator/phases.py` — SUBMITTED → REJECTED transition for desk rejection

### Prompt 36 — Fix Truncated Paper Output

> Something I noticed is that the papers (.md) all seem to be truncated, and missing the last part

**Root cause:** Two issues causing truncation:
1. `max_tokens: 4096` on agents — papers need much more than 4096 output tokens
2. `current_body[:8000]` in revision prompts — the writer only saw the first 8000 chars when revising

**Fix:**
- Added `max_tokens` override parameter to `Agent.generate()` so callers can request more tokens per-call
- Engine now uses `_WRITING_MAX_TOKENS = 16384` for all writing/assembly/revision calls
- Increased paper context limit from 8000 chars to `_PAPER_CONTEXT_LIMIT = 50000` chars

**Artifacts modified:**
- `src/paradigm/agents/base.py` — Added `max_tokens` parameter to `generate()`
- `src/paradigm/orchestrator/engine.py` — Added `_WRITING_MAX_TOKENS`, `_PAPER_CONTEXT_LIMIT` constants; used throughout writing pipeline

### Prompt 37 — Implement Phase 6: Multi-Cycle + Polish

> Implement the following plan: Phase 6: Multi-Cycle + Polish
>
> 4 steps: (1) Fix multi-cycle discovery in corpus.py — internal paper IDs weren't matched due to `arxiv:` prefix bug, (2) Citation recording — extract_citations_from_text() + wire into publish_paper(), (3) Operating modes — MODE_TEAM_ROLES dict + mode-specific prompts, (4) Intervention hooks — InterventionHook callback type + --interactive CLI flag.

**Key decisions:**
- Fix the critical `arxiv:` prefix bug that prevented internal papers from being discovered in search
- Add `extract_citations_from_text()` as a standalone function in citations.py
- MODE_TEAM_ROLES dict maps mode names to team compositions
- InterventionHook is a simple callback type, not a class
- Same-process pause/abort only; full cross-process resume deferred

**Artifacts produced/modified:**
- `src/paradigm/literature/corpus.py` — Fixed search for internal papers, enhanced build_literature_context, improved ingest_internal_paper
- `src/paradigm/literature/citations.py` — Added `extract_citations_from_text()`
- `src/paradigm/journal/publication.py` — Wired citation extraction into publish_paper
- `src/paradigm/orchestrator/engine.py` — MODE_TEAM_ROLES, mode prompts, InterventionHook, _check_intervention
- `src/paradigm/main.py` — Added `--interactive` flag to run command
- `tests/test_corpus.py` — 3 new tests for internal paper discovery
- `tests/test_citations.py` — 4 new tests for citation extraction
- `tests/test_orchestrator.py` — ~7 new tests for modes + intervention hooks
- `ROADMAP.md` — Phase 5 marked complete, Phase 6 updated

### Prompt 38 — Operations Manual + README Update

> Implement the following plan: Paradigm Operations Manual + README Update
>
> Create `docs/MANUAL.md` (~700-900 lines) as a comprehensive operations manual aimed at a scientist-operator. 14 sections covering: Overview, Quick Start, CLI Reference, Operating Modes, Research Cycle, Agent Team, Interactive Mode, Multi-Cycle Research, Configuration Reference, Data and Storage, Cost Management, Docker Sandbox, Troubleshooting, Recipes. Update `README.md` status to reflect Phases 0-5 complete, Phase 6 in progress. Add link to manual. Remove stale annotations.

**Key decisions:** All documentation content derived from actual source code (main.py, config.py, engine.py, phases.py, factory.py, paper.py, default.yaml) to ensure accuracy.

**Artifacts produced/modified:**
- `docs/MANUAL.md` — New comprehensive operations manual
- `README.md` — Updated status, Quick Start, and links

### Prompt 39 — Corpus Status Filtering + Graveyard Integration

> Implement the following plan: Corpus Status Filtering + Graveyard Integration
>
> 1. Add `search_graveyard()` to Database (keyword + type filters, LIKE search)
> 2. Add status filter to `corpus.search()` — only return published/external papers
> 3. Inject graveyard context into seeding phase and agent prompts
> 4. Write tests for all changes, run full suite

**Key decisions:**
- Filter corpus search results at SQLite level after ChromaDB hits (status must be "published" or "external")
- Graveyard context injected on round 1 of IDEATION alongside literature context, clearly marked as "NOT citable"
- `search_graveyard()` uses SQL LIKE across content, failure_reason, lessons_learned fields

**Artifacts produced/modified:**
- `src/paradigm/storage/database.py` — Added `search_graveyard()` method
- `src/paradigm/literature/corpus.py` — Added status check in `search()`
- `src/paradigm/orchestrator/engine.py` — Graveyard fetch in seeding, injection in prompt builder
- `tests/test_database.py` — 5 graveyard read tests
- `tests/test_corpus.py` — 2 status filtering tests
- `tests/test_orchestrator.py` — 1 graveyard context test

### Prompt 40 — Documentation Update: Graveyard Integration + Corpus Status Filtering

> Implement the following plan: Documentation Update: Graveyard Integration + Corpus Status Filtering
>
> Update docs/MANUAL.md (6 targeted edits across sections 5, 8, 10, 13, 14) and README.md to document three recently implemented features: search_graveyard(), status filter in corpus.search(), and graveyard context injection in the seeding/ideation phases. Move Phase 6 from "In Progress" to "Completed" in README.

**Artifacts modified:**
- `docs/MANUAL.md` — 6 edits documenting graveyard integration, corpus status filtering, and failure learning
- `README.md` — Phase 6 moved to completed
- `HISTORY.md` — This prompt logged
