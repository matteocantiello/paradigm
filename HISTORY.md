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

### Prompt 41 — Live Multi-Cycle Test

> What's left to do? What's next in the roadmap?
> → User chose option 1: Run the live multi-cycle test (cycle 1 publishes → cycle 2 discovers and cites it)

**Goal:** Validate cross-cycle discovery, graveyard learning, and corpus status filtering with real API calls.

### Prompt 42 — Execute Live Multi-Cycle Test

> Implement the following plan: Live Multi-Cycle Test
>
> Steps: (1) Fix _WRITING_MAX_TOKENS 16384→32768, (2) Pre-flight verification, (3) Run Cycle 1 (convective overshooting topic), (4) Verify Cycle 1 published, (5) Run Cycle 2 (asteroseismology topic), (6) Verify cross-cycle discovery and citation, (7) Update ROADMAP.md.

**Goal:** Execute the live multi-cycle test with real API calls. Cycle 2 must discover and cite Cycle 1's paper.

**First attempt result:** Failed — API credit balance ran out mid-PLANNING phase. Also hit "streaming required" error for 32768-token writes. Both issues fixed (streaming auto-enabled for max_tokens >= 8192).

### Prompt 43 — Resume Multi-Cycle Test

> Can you resume?

Resuming Cycle 1 after API credits replenished.

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — `_WRITING_MAX_TOKENS` 16384 → 32768
- `src/paradigm/agents/base.py` — Added streaming support for large `max_tokens` calls (avoids Anthropic 10-min timeout)
- `ROADMAP.md` — Marked live multi-cycle test complete

**Cycle 1 result:**
- Paper `paper-173de3e7f52f`: "The Role of Convective Overshooting in Determining the Main-Sequence Width of Intermediate-Mass Stars"
- **PUBLISHED** — 1069 lines, full Conclusions section, no truncation
- Peer review: two major_revision recommendations (avg scores 7.2 and 7.0), decision: accept
- Paper ingested into ChromaDB for future discoverability
- Total tokens: ~390K across all agents/phases
- Thread: `thread-20c7e60617fb`

**Cycle 2 result:**
- Paper `paper-13367558d434`: "Asteroseismic Constraints on Interior Mixing Processes in Intermediate-Mass Stars"
- **DESK-REJECTED** — 322 lines, complete paper, but editor recommended "revise" during internal review (82 changes), then desk review rejected
- Thread: `thread-312e59f9a24e`

**Cross-cycle discovery verification:**
- Cycle 2 literature search: `local_results=6` (vs Cycle 1's `local_results=5`) — the extra result is Cycle 1's published paper from ChromaDB
- Cycle 2 paper extensively discusses "helium stratification feedback" — a key concept from Cycle 1's paper, confirming knowledge transfer
- Corpus status filtering works: rejected papers did NOT appear in search results (only published/external returned)
- Graveyard entries present (4 total) but keyword-based LIKE search too strict for multi-word prompts — known limitation for future improvement

**Verification checklist:**
- [x] Cycle 1 paper published (not truncated, passed peer review)
- [x] Cycle 2 literature search finds Cycle 1's paper (`local_results` = 6 vs 5)
- [x] Cycle 2 paper influenced by Cycle 1 (helium stratification feedback concept)
- [ ] Cycle 2 paper explicitly cites Cycle 1 by paper ID (agents don't cite by internal IDs — needs prompt improvement)
- [x] Rejected papers do NOT appear in corpus search results (status filter works)
- [~] Graveyard context loaded (mechanism works, keyword search too strict for discovery)

### Prompt 44 — Sandbox Integration Planning

> Are the agents using the docker for running calculations and producing figures?
> → No, the sandbox is built (Phase 3) but not wired into the orchestration engine.
> → User asked to plan the integration.

**Goal:** Plan integration of Docker sandbox into the research cycle so agents can run code, produce figures, and include computational results in papers.

### Prompt 45 — Implement Sandbox Integration Plan

> Implement the following plan: [Integrate Docker Sandbox into Orchestration Engine]
> Full plan provided with 11 implementation steps covering config, scheduler, engine
> changes (EXECUTION phase handler, code extraction, retry logic, results formatting,
> figure copying), and 13 tests.

**Goal:** Wire the Docker sandbox into the orchestration engine so `experimental` and `replication` modes run code and produce figures during the EXECUTION phase.

### Prompt 46 — Test Docker Functionality

> Can we test the docker functionality?

**Goal:** Live test the EXECUTION phase with Docker running to verify agents can propose code, execute it in the sandbox, and produce results/figures.

### Prompt 47 — Fix CI Formatting Failures

> Fix ruff format failures in CI for base.py, engine.py, database.py, test_experimentation.py

**Goal:** Run `ruff format` on the 4 files that CI flagged.

### Prompt 48 — Add Prompt File Support

> Next we should add the ability to pass a prompt to paradigm via the file prompt.md (I already created one in the repo)

**Goal:** Add `--prompt-file` CLI option to read research prompts from a markdown file.

**Changes:**
- `src/paradigm/main.py`: Added `--prompt-file` option (mutually exclusive with `--prompt`, validates file not empty)

### Prompt 49 — Update Manual and History

> Let's update the manual and history

**Goal:** Update `docs/MANUAL.md` to document the `--prompt-file` feature and EXECUTION phase; update `HISTORY.md`.

**Changes:**
- `docs/MANUAL.md`: Added `--prompt-file` to CLI reference, added prompt file examples, added Prompt Files subsection, added EXECUTION phase details section, updated phase flow diagram, added experimentation config to orchestrator table, updated data directory layout for figures, updated cost estimates, updated interactive mode intervention points, added Recipe 8 for experimental mode with prompt file
- `HISTORY.md`: Logged prompts 48-49

### Prompt 50 — Implement Smart Prompt Preprocessing for Literature Search

> Implement the following plan: Smart Prompt Preprocessing for Literature Search - adding prompt preprocessing to extract clean search keywords and fetch referenced PDFs from user prompts. New module prompt_utils.py, updates to arxiv.py, corpus.py, engine.py, and new tests.

**Artifacts:** `src/paradigm/literature/prompt_utils.py` (new), `src/paradigm/literature/arxiv.py`, `src/paradigm/literature/corpus.py`, `src/paradigm/orchestrator/engine.py`, `tests/test_prompt_utils.py` (new)

### Prompt 51 — Implement Agent-Driven Literature Search

> Implement the following plan: Agent-Driven Literature Search
>
> Replace the one-shot prompt→arXiv pipeline with an agent-driven, ongoing search capability using the `[SEARCH: query]` text-parsing pattern. Agents drive search by writing `[SEARCH: query]` in their responses. The orchestrator parses these markers, executes searches, and feeds results back as accumulated literature context.

**Key decisions:**
- Prompt is context for agents, NOT a search query — agents decide what to search for
- Text parsing pattern (`[SEARCH: query]`) consistent with code execution via fenced blocks
- Search enabled in all deliberation phases (IDEATION through REVISION)
- Accumulated context grows throughout the cycle, available to all subsequent agents
- Configurable budget: `max_searches_per_round` prevents runaway costs

**Artifacts modified:**
- `src/paradigm/config.py` — Added `max_searches_per_round` to OrchestratorConfig
- `configs/default.yaml` — Added `max_searches_per_round: 3`
- `src/paradigm/literature/prompt_utils.py` — Added `parse_search_requests()`, `format_search_results()`
- `src/paradigm/orchestrator/engine.py` — Removed arXiv call from seeding, added `_process_search_requests()`, integrated search into all phases, updated prompt building
- `tests/test_prompt_utils.py` — Tests for new functions
- `tests/test_orchestrator.py` — Updated mock_corpus, added search integration test

### Prompt 52 — Fix External PDF Fetching (403 Forbidden)

> We're still having issues with link extractions — A&A URLs returning "Could not extract PDF"

**Root cause:** The httpx client had no `User-Agent` header. Journal sites like A&A (aanda.org) block requests with the default httpx user agent, returning 403 Forbidden.

**Fix:** Added a descriptive `User-Agent` header to the `ArxivClient` httpx client.

**Artifacts modified:**
- `src/paradigm/literature/arxiv.py` — Added User-Agent header to httpx.AsyncClient

### Prompt 53 — Fix PDF Fetching for IOP Science (TLS Fingerprint Detection)

> Let's also test a couple more journals: IOP Science and Nature

**Testing results:**
- A&A (aanda.org): Works with User-Agent fix from prompt 52
- Nature `.pdf` URL: Works
- Nature article URL (HTML): Correctly rejected — not a PDF
- IOP Science: Blocked by Radware Bot Manager captcha — TLS fingerprint detection

**Root cause:** IOP Science uses Radware Bot Manager, which fingerprints the TLS handshake. Python's httpx library has a distinctive TLS fingerprint that gets blocked, while `curl` has a different fingerprint that passes.

**Fix:** Refactored `fetch_pdf_from_url()` into two layers:
1. `_fetch_pdf_bytes()` — tries httpx first, validates response is PDF via content-type
2. If httpx gets blocked (HTML/captcha response), falls back to `curl` subprocess
3. Validates `%PDF-` magic bytes before returning

**Tested against:** A&A, IOP/ApJ, IOP/ApJS, Nature PDF, Nature HTML — all behave correctly.

**Artifacts modified:**
- `src/paradigm/literature/arxiv.py` — Added `_fetch_pdf_bytes()` with curl fallback, content-type validation, `%PDF-` magic bytes check
- `docs/MANUAL.md` — Updated SEEDING phase docs, added agent-driven search docs, added `max_searches_per_round` config, added PDF troubleshooting

### Prompt 54 — Fix arXiv Rate Limiting and Duplicate Searches

> I'm running a full cycle, and I'm seeing a number of fails at retrieving from the arxiv. Wondering if this is a timeout issue with their API or something else

**Root cause:** Two issues:
1. arXiv returns 429 (rate limit) when too many searches fire in rapid succession — the 3s per-request rate limit isn't enough when agents request dozens of searches per round
2. Agents repeat identical queries across rounds (e.g., "subsurface convection zones intermediate mass stars" appears in round 1, 2, 3...), wasting budget and API calls

**Fix:**
1. Added retry with exponential backoff on 429 in `_rate_limited_get()` (backoff: 6s, 12s, 24s)
2. Added global query dedup (`_searched_queries` set) in `_process_search_requests()` — queries already executed in the cycle are silently skipped

**Artifacts modified:**
- `src/paradigm/literature/arxiv.py` — Retry with exponential backoff on 429 in `_rate_limited_get()`
- `src/paradigm/orchestrator/engine.py` — Added `_searched_queries` set for global dedup, reset at cycle start

### Prompt 55 — Implement Paper Artifact Files (Search Log + Review Report)

> Implement the following plan: Paper Artifact Files (Search Log + Review Report)
>
> After a research cycle, save two human-readable files alongside each paper:
> 1. `literature_searches.md` — All search queries, which agent made them, which phase, and the papers returned
> 2. `reviews.md` — Full peer review text, scores, internal review, and final decision
>
> Both files live in `papers/{paper_id}/`. Always use subdirectory layout. Accumulate search and review data in engine state, write at end of cycle.

**Key decisions:**
- Always use subdirectory layout for papers (not conditional on figures)
- Accumulate `_search_log` and `_review_log` as lists of dicts in engine state
- Write files at end of cycle in a common exit path
- Search log captures query, agent_id, phase, and paper metadata
- Review log captures all review types: internal, desk, peer, decision, revision

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Added `_search_log` + `_review_log` state, accumulation, save methods, subdirectory layout
- `tests/test_orchestrator.py` — Tests for search log, review log, and file writing

### Prompt 56 — Plan Resource-Aware Prompt Preprocessing

> I want to be able to provide not just pdf to read in the prompt, but also links to tools and datasets. For example I might suggest paradigm to look for a python routine to make plots, or a repository of stellar models. The agents should be able to resolve these links, look into them, and extract any useful data or tools which can be then used during the next phases. So prompt.md should be a very generic container. Do you think this is possible? Or should we have different starting files for prompt, links to literature, data, code etc? Let's plan!

**Goal:** Plan how to make the prompt a generic container that can reference literature PDFs, code repositories, datasets, and tools — all resolved during SEEDING and made available to agents in later phases.

### Prompt 57 — Implement Resource-Aware Prompt Preprocessing

> Implement the following plan: Resource-Aware Prompt Preprocessing
>
> New module `resources.py` with URL classification (paper/code_repo/code_file/data/reference),
> type-specific async handlers (git clone for repos, httpx download for files, HTML scraping for references),
> context builders for agent prompts. Update `engine.py` to classify+resolve URLs during SEEDING,
> inject code/data/reference contexts into agent prompts, pass repo paths as PYTHONPATH to sandbox.
> Update `docker.py` and `executor.py` to accept environment variables. New tests for all.

**Key decisions:**
- Resolve all resources during SEEDING only (no mid-cycle fetching)
- GitHub repos: shallow clone into `data/shared/repos/`
- PYTHONPATH injection via `environment` dict on container create (avoids DENIED_MODULES for sys)
- `prompt.md` stays a single generic container file

**Artifacts produced/modified:**
- `src/paradigm/literature/resources.py` — NEW: ResourceType, ResolvedResource, classify_resource(), resolve_resource(), context builders
- `src/paradigm/orchestrator/engine.py` — Resource state, seeding classification+resolution, context injection in prompts, PYTHONPATH for sandbox
- `src/paradigm/sandbox/docker.py` — `environment` parameter on execute()
- `src/paradigm/sandbox/executor.py` — `repo_paths` parameter, PYTHONPATH building
- `tests/test_resources.py` — NEW: ~15+ tests
- `tests/test_orchestrator.py` — Tests for resource-aware seeding and context injection

### Prompt 58 — Phase-Appropriate Agent Filtering

> Implement the following plan: Phase-Appropriate Agent Filtering
>
> Currently all agents speak during every round of IDEATION and PLANNING — including the editor and writer, who consume ~50-55K tokens each per round without adding phase-appropriate value. Exclude editor from IDEATION and PLANNING (only participates from INTERNAL_REVIEW onward), exclude writer from IDEATION and PLANNING (only participates from WRITING onward). Use a data-driven filtering approach via a _PHASE_ACTIVE_ROLES dict.

**Key decisions:**
- Editor excluded from IDEATION and PLANNING — only participates from INTERNAL_REVIEW onward
- Writer excluded from IDEATION and PLANNING — only participates from WRITING onward
- Data-driven filtering via `_PHASE_ACTIVE_ROLES` dict (not hardcoded per-phase logic)
- ~33% fewer API calls in deliberation phases (~1M tokens saved per cycle)

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Added `_PHASE_ACTIVE_ROLES` constant, filter in `_run_round()`, updated CLI phase output
- `src/paradigm/orchestrator/scheduler.py` — Removed `"writer"` from IDEATION and PLANNING in `_PHASE_PRIORITIES`
- `tests/test_orchestrator.py` — Tests for editor/writer exclusion from IDEATION/PLANNING

### Prompt 59 — Fix Three Critical Bugs from Live Test

> Implement the following plan: Fix Three Critical Bugs from Live Test
>
> A live research cycle on red noise in massive stars revealed three bugs:
> 1. Searches return same ~7 papers — 71 searches executed, zero arXiv results. Local ChromaDB papers fill all result slots before arXiv papers are added.
> 2. No Docker execution — "directed" mode team has no experimentalist, so EXECUTION phase is skipped entirely.
> 3. Empty paper saved and submitted — ConnectionErrors during WRITING phase caused all agents to fail silently. An empty paper (0 bytes) was saved, then sent through review/peer-review, wasting API calls.

**Key decisions:**
- Bug 1: Rewrite corpus.search() to build local/arXiv lists independently then merge; increase max_results 5→10; add _seen_paper_ids for cross-query dedup; add _LITERATURE_CONTEXT_LIMIT=15000
- Bug 2: Add experimentalist to directed/explore/hypothesis mode teams
- Bug 3: Add _MIN_PAPER_LENGTH=500 guard in writing phase; skip review/submission if paper is empty

**Artifacts modified:**
- `src/paradigm/literature/corpus.py` — Rewrite search() to separate local/arXiv lists then merge
- `src/paradigm/orchestrator/engine.py` — All three bug fixes
- `tests/test_orchestrator.py` — Updated call counts, new tests
- `tests/test_corpus.py` — New test for interleaved results

### Prompt 60 — Display Total Token Usage at End of Run

> Can we also display the total number of tokens utilized by paradigm at the end of the run. And maybe store it in the paper log

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Token summary at end of cycle + stored in paper metadata
- `tests/test_orchestrator.py` — Test for token summary

### Prompt 61 — Relax Safety Scanner for Docker Sandbox
> Why is the safety scanner blocking all these modules (modules: pathlib, io, requests, http, urllib, glob, fnmatch, shutil, tempfile, plus builtins like open, getattr, locals, vars, etc.)? I think these should be allowed to be run inside the docker

- **Decision**: Remove overly restrictive module/builtin blocks from safety scanner since Docker container with --network=none is the real security boundary
- **Artifacts**: `src/paradigm/sandbox/safety.py`, experimentalist prompt, safety tests

### Prompt 62 — Add Execution Phase Circuit Breaker
> Still let's add a failure-rate circuit breaker — if >70% of executions fail in a round, declare experiments sufficient and move on

- **Decision**: Add per-round failure rate check; if >70% of executions in a round fail, break out of execution loop
- **Artifacts**: `src/paradigm/orchestrator/engine.py`, `tests/test_experimentation.py`

### Prompt 63 — Analyze Execution Events for Thread a6013bedc956
> Analyze the execution events for thread-a6013bedc956 in data/events.jsonl. Count code_execution events, successes vs failures vs rejections, error events, and check execution directories for experimentalist-2 outputs (PNGs) in the execution phase window (Feb 14 04:24–06:00 UTC).

- **Decision**: Diagnostic analysis only, no code changes
- **Artifacts**: None (analysis output)

### Prompt 64 — Fix Docker Sandbox Environment Issues
> Ok, let's try to tackle the issues still present. Let's start with 1

Issue 1: 9 execution failures were environmental — 4× ModuleNotFoundError: requests, 3× FileNotFoundError (CSV from prior execution not available), 2× ModuleNotFoundError: PyPDF2. Docker image needs more packages and cross-execution file persistence needs work.

- **Artifacts**: `docker/Dockerfile`, `src/paradigm/sandbox/docker.py`, `src/paradigm/orchestrator/engine.py`

### Prompt 64 — Offline Pip Cache for Docker Sandbox
> Is it possible to allow agents to install packages in docker as they need? Would this be too much of a safety threat?
> Let's start with 2. But let's make a note in history.md that down the road we might want to do 4

- **Decision**: Implement option 2 — offline pip cache. Pre-download wheels for common scientific packages, mount them read-only in the container. Agents can `pip install --no-index --find-links /data/packages/ <pkg>`.
- **Future**: Down the road, consider option 4 — orchestrator-mediated installs where the agent declares `# REQUIRES: package1, package2`, the orchestrator validates against an allowlist, and builds/extends the Docker image before execution. This would be fully dynamic but requires more engineering.
- **Artifacts**: `docker/requirements-cache.txt`, `docker/cache_packages.sh`, `src/paradigm/sandbox/executor.py`, `src/paradigm/sandbox/docker.py`, `src/paradigm/orchestrator/engine.py`

### Prompt 65 — Strip Agent Scaffolding from Paper Body
> Let's now fix 2. (Paper body starts with meta-text (lines 1-54): The revision agent included planning notes, XML function calls, and tool invocation text before the actual paper starts at line 57. The assembly/revision step leaked agent scaffolding into the paper.)

- **Decision**: Add post-processing to strip agent meta-text from paper body before saving
- **Artifacts**: `src/paradigm/orchestrator/engine.py` or `src/paradigm/journal/paper.py`

### Prompt 66 — Embed Figures Inline in Paper Markdown
> Now let's fix 3. (Figures not embedded inline: The paper references "Figure 1", "Figure 2", etc. in text but never uses ![Figure](figures/...) markdown syntax to actually embed them)

- **Decision**: Add post-processing after paper finalization to ensure figure image tags are present in the paper body
- **Artifacts**: `src/paradigm/orchestrator/engine.py`

## 2026-02-14

### Prompt — Implement Agent Episodic Memory System

> Implement the following plan: [Agent Episodic Memory System plan - config, core memory module with ChromaDB, engine integration, CLI commands, event logging, tests]

**Key decisions**: ChromaDB for semantic search, per-agent memories, recency × similarity scoring, non-fatal reflection, bounded context injection.

**Artifacts**: `src/paradigm/agents/memory.py` (new), `tests/test_agent_memory.py` (new), edits to `config.py`, `default.yaml`, `events.py`, `engine.py`, `main.py`

### Prompt — Update spec and planning docs for memory system

> We should also update spec.md given all the changes. And any other .md file that doesn't reflect the current architecture and choices

**Key decisions**: Update SPEC.md, ROADMAP.md, DECISIONS.md, and any other planning docs to reflect the new agent episodic memory system.

### Prompt — Update spec and planning docs for memory system

> We should also update spec.md given all the changes. And any other .md file that doesn't reflect the current architecture and choices

**Key decisions**: Update SPEC.md, ROADMAP.md, DECISIONS.md, and any other planning docs to reflect the new agent episodic memory system.

### Prompt — Focused Debate Sub-routine

> Looking at how the orchestrator runs rounds: each agent speaks in sequence, seeing the accumulated messages. But agents don't really argue. The theorist proposes, the skeptic responds, and then the cycle moves on. There's no mechanism for the theorist to defend its position against the skeptic's critique, refine the argument through back-and-forth, and arrive at something neither would have produced alone. The scheduler gives each agent one turn per round, and the number of rounds is fixed. Real intellectual progress happens in sustained, focused exchanges between two people who disagree.
> You could address this with a focused debate sub-routine: when two agents disagree during IDEATION or PLANNING, the orchestrator spawns a structured debate (alternating turns, limited to the two agents, with an explicit resolution condition) before resuming the normal round.

**Key decisions**: Explicit `[CHALLENGE: agent-id: reason]` tags (deterministic, like `[SEARCH:]`), defender speaks first, synthesizer generates outcome summary, one debate per agent response, max 3 exchanges × max 2 debates per phase, inline execution within `_run_round`.

**Artifacts**: `src/paradigm/config.py`, `configs/default.yaml`, `src/paradigm/logging/events.py`, `src/paradigm/literature/prompt_utils.py`, `src/paradigm/orchestrator/engine.py`, `tests/test_debate.py` (new)

### Prompt — Implement Focused Debate Sub-routine

> Implement the following plan: [Focused Debate Sub-routine plan — config fields, DEBATE_TRIGGERED event, ChallengeRequest parsing, engine debate constants/state/methods, _run_debate, _synthesize_debate, _process_challenge_requests, _run_round and _build_agent_prompt wiring, tests]

### Prompt — Fix SyntaxWarning from LaTeX escape sequences in sandbox

> I am running a paradigm loop with the version with the new docker settings, and it looks like is encountering some errors: [SyntaxWarning: invalid escape sequence '\o' from `<unknown>` source during EXECUTION phase, causing retries and failures across multiple experiments]

**Key decisions**: Suppress SyntaxWarning during ast.parse() in safety scanner; add raw-string hint to EXECUTION prompt.

**Artifacts**: `src/paradigm/sandbox/safety.py`, `src/paradigm/orchestrator/engine.py`

### Prompt — Add total execution time to session output

> Together with the total number of tokens, it would be great to print and log the total execution time for a paradigm session
