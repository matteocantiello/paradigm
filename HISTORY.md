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

### Prompt — Refactor test_orchestrator.py for multi-provider LLM abstraction

> Refactor test_orchestrator.py to use multi-provider LLM abstraction: change _mock_checkpoint_response() to return (json_text, input_tokens, output_tokens) tuple, add mock provider to mock_config fixture, remove all `patch("paradigm.storage.checkpoints.Anthropic")` and `patch("paradigm.agents.memory.Anthropic")` wrappers, change Agent constructors from api_key to provider=MagicMock().

**Key decisions**: Only change mocking patterns, not test logic or assertions.

**Artifacts modified**: `tests/test_orchestrator.py`

### Prompt — Refactor test_peer_review.py for multi-provider LLM abstraction

> Update tests/test_peer_review.py: add mock provider to mock_config fixtures, add _build_checkpoint_response() helper returning (json_text, input_tokens, output_tokens) tuple, remove all `patch("paradigm.storage.checkpoints.Anthropic")` wrappers and associated mock_client setup, change Agent constructors from api_key to provider=MagicMock().

**Key decisions**: Only change mocking patterns, not test logic or assertions.

**Artifacts modified**: `tests/test_peer_review.py`

### Prompt — Refactor test_experimentation.py for multi-provider LLM abstraction

> Update tests/test_experimentation.py: change _mock_checkpoint_response() to return (json_text, input_tokens, output_tokens) tuple, add mock provider to mock_config and mock_config_no_sandbox fixtures, remove all `patch("paradigm.storage.checkpoints.Anthropic")` wrappers and associated mock_client setup, change Agent constructors from api_key to provider=MagicMock(). Keep combined `with` statements that patch other things besides checkpoints.Anthropic but remove only the checkpoints.Anthropic part.

**Key decisions**: Only change mocking patterns, not test logic or assertions.

**Artifacts modified**: `tests/test_experimentation.py`

### Prompt — Refactor test_writing.py for multi-provider LLM abstraction

> Refactor test_writing.py to use multi-provider LLM abstraction: add _build_checkpoint_response() returning (json_text, input_tokens, output_tokens) tuple, add mock provider to mock_config and mock_config_no_writing fixtures, remove all `patch("paradigm.storage.checkpoints.Anthropic")` wrappers and un-indent, change Agent constructors from api_key to provider=MagicMock().

**Key decisions**: Only change mocking patterns, not test logic or assertions.

**Artifacts modified**: `tests/test_writing.py`

### Prompt — Refactor test_debate.py for multi-provider LLM abstraction

> Update tests/test_debate.py: add _build_checkpoint_response() helper returning (json_text, input_tokens, output_tokens) tuple, add mock provider to mock_config fixture, remove `patch("paradigm.storage.checkpoints.Anthropic")` wrapper in _build_engine and un-indent, add mock provider to inline Config() usages, add `import json`.

**Key decisions**: Only change mocking patterns, not test logic or assertions.

**Artifacts modified**: `tests/test_debate.py`

### Prompt — Route frontier models to Anthropic, open models to Together.ai

> Theorist and skeptic should be the ones running frontier models (Opus or Sonnet). Everything else should be outsourced to together.ai / open models. The roles that have to do the heavy lifting in terms of thinking should be on Claude API (Opus 4.6 possibly). Other agents use open models to save tokens.

**Key decisions**: Flip default_provider to together, override theorist+skeptic to anthropic/opus, fix model resolution to use provider.default_model when no role override exists, update checkpoint/memory to use provider-appropriate models.

**Artifacts modified**: `src/paradigm/config.py`, `configs/default.yaml`, `src/paradigm/orchestrator/engine.py`

### Prompt — Fix Desk Review Decision Parsing Bug

> Implement the following plan: Fix Desk Review Decision Parsing Bug
>
> Paper paper-1d696305a77e was desk-rejected despite the editor explicitly deciding send_to_review. Root cause: the desk review decision parser checks if "desk_reject" or "desk reject" appears anywhere in the editor's full response text. The editor's reasoning naturally includes phrases like "rather than desk rejection", which contains the substring "desk reject" — triggering a false positive.
>
> Fix: Parse only the ## Decision section of the response (using existing parse_sections_from_markdown()), not the full text. Add regression test.

**Key decisions**: Use existing parse_sections_from_markdown(); fall back to full-text scan only if no ## Decision section found; single decision check for both logging and control flow.

**Artifacts modified**: `src/paradigm/orchestrator/engine.py`, `tests/test_peer_review.py`

### Prompt — Multi-Provider LLM Refactoring

> Implement the following plan: [Multi-Provider LLM Refactoring plan]

**Goal**: Introduce an LLM provider abstraction layer enabling multi-backend support (Anthropic, OpenAI-compatible APIs like Together.ai, Fireworks, DeepInfra) while maintaining backward compatibility.

**Key decisions**:
- LLMProvider Protocol with AnthropicProvider and OpenAICompatibleProvider implementations
- Config-driven provider registry with per-role overrides
- Provider + model resolved per agent role via Config helper methods
- openai package is an optional dependency
- Backward compatible: auto-creates anthropic provider if providers dict is empty

**Artifacts produced**:
- NEW: `src/paradigm/agents/providers.py` — LLMProvider Protocol, AnthropicProvider, OpenAICompatibleProvider, create_provider() factory
- NEW: `tests/test_providers.py` — 26 unit tests for providers, config integration

**Artifacts modified**:
- `src/paradigm/config.py` — Added ProviderConfigEntry, AgentOverrideConfig, provider registry, get_provider(), get_provider_and_model_for_role()
- `configs/default.yaml` — Added providers section
- `src/paradigm/agents/base.py` — Replaced api_key with LLMProvider
- `src/paradigm/agents/factory.py` — Uses get_provider_and_model_for_role()
- `src/paradigm/storage/checkpoints.py` — Replaced api_key with LLMProvider
- `src/paradigm/agents/memory.py` — Replaced api_key with LLMProvider
- `src/paradigm/orchestrator/engine.py` — Updated 2 call sites
- `pyproject.toml` — Added openai optional dependency
- All test files updated to use mock providers with object.__setattr__() for Pydantic v2 compatibility

**Final result**: 477 tests passing, lint clean, format clean

### Prompt 66 — Update README.md

> Let's also update the readme.md, which is what is shown on github and is the first description of paradigm. Let's make it informative, useful to get started, and exciting!

**Status**: In progress — planning README update to make it compelling for GitHub visitors and useful for getting started with Paradigm.

### Prompt: Configure Together.ai Provider

> What steps do we need to follow to configure https://www.together.ai/ ? I will create an API key and add it to the .env file (?). What else is needed?
> (followed by: yes — to apply the config changes)

**Key decisions:**
- Install `openai` optional dependency for OpenAI-compatible provider support
- Add Together.ai provider to default.yaml with DeepSeek-R1 as default model
- Route the skeptic agent through Together.ai/DeepSeek-R1 for epistemic diversity

**Artifacts modified:**
- `configs/default.yaml` — added Together provider + skeptic override
- `pyproject.toml` — openai dependency already present from previous commit

### Prompt — Fix Sandbox Execution Environment Issues

> Implement the following plan: Fix Sandbox Execution Environment Issues
>
> The EXECUTION phase has a ~75% failure rate across recent runs. Analysis of thread-19c335b0bbe8 (21 attempts, 11 failures) reveals four systematic issues:
> 1. Docker image is stale (missing requests, pypdf, h5py, seaborn)
> 2. CODE_FILE parent directories not added to PYTHONPATH (from read_mist_models.py fails)
> 3. Ingested PDFs not saved to sandbox (raw PDF bytes discarded after text extraction)
> 4. Execution prompt template needs clarifications about PDF/code file availability
>
> Fix: Make _fetch_pdf_bytes public in arxiv.py, add CODE_FILE dirs to PYTHONPATH, save raw PDFs to data/shared/papers/, update execution prompt, improve CODE_FILE import instructions in resources.py.

**Key decisions:**
- Make `_fetch_pdf_bytes` a public method on ArxivClient (already has httpx + curl fallback)
- Add CODE_FILE parent dirs to repo_paths (deduplicated) for PYTHONPATH injection
- Save raw PDF bytes to `data/shared/papers/` during SEEDING (non-fatal on failure)
- Add explicit import instructions for CODE_FILE entries in `build_code_context()`

**Artifacts modified:**
- `src/paradigm/literature/arxiv.py` — Made `_fetch_pdf_bytes` public
- `src/paradigm/orchestrator/engine.py` — PYTHONPATH for code files, PDF save helper, prompt template updates
- `src/paradigm/literature/resources.py` — Improved CODE_FILE import instructions in `build_code_context()`

### Prompt — Add default scientific packages to Docker container

> We should load the most used scientific packages as defaults in the docker container

**Key decisions:** Promote 10 frequently-used packages from the offline pip cache to the Dockerfile so they're always available without manual `pip install`.

**Packages added to Dockerfile:** emcee, corner, lmfit, uncertainties, statsmodels, tqdm, numba, xarray, pyyaml, joblib

**Artifacts modified:**
- `docker/Dockerfile.sandbox` — Added 10 packages to the default install
- `src/paradigm/orchestrator/engine.py` — Updated "Available libraries" list and shrank offline cache list in execution prompt

## 2026-03-03

### Prompt — Complete Demo Runner: Add Missing Phases + Paper Creation

> Implement the following plan:
> Complete Demo Runner: Add Missing Phases + Paper Creation
>
> The demo runner (`demo_runner.py`) simulates a research cycle when the Paradigm core can't import (Python 3.10).
> It currently stops at the "internal" (review) phase and never creates a paper. Users see the cycle complete at Review
> but the Submitted/Peer Review/Published phases never fire, and the Papers page is empty.
>
> Changes: (1) Add in-memory `_demo_papers` store to papers.py with fallbacks in list_papers/get_paper/list_outputs,
> (2) Add submitted/peer_review/published phases to demo_runner.py, create demo paper after writing phase,
> link paper_id to cycle via `_cycles`.

**Key decisions:**
- Module-level `_demo_papers` dict in papers.py (same pattern as `_cycles` in research.py)
- Demo runner imports `_cycles` from research.py to set `paper_id` on the cycle
- Three new phases: submitted, peer_review, published
- Paper created after writing phase using existing `DEMO_PAPER_BODY` constant

**Artifacts modified:**
- `backend/api/routes/papers.py` — Added `_demo_papers` fallback store
- `backend/api/services/demo_runner.py` — Added 3 phases, create demo paper, link to cycle

### Prompt — Reduce Token Usage Per Research Cycle

> Implement the plan to reduce token usage per research cycle (~530K → ~300K target, ~40% reduction). Changes: (1) Phase-appropriate context injection via `_PHASE_CONTEXT_NEEDS` dict gating `_build_agent_prompt()`, (2) Reduce `_SEARCH_ENABLED_PHASES` from 7 to 3, (3) Fuzzy query deduplication via Jaccard similarity, (4) Reduce limits: `_LITERATURE_CONTEXT_LIMIT` 15K→10K, `max_papers` 5→3, `max_searches_per_round` 10→5.

**Key decisions:**
- IDEATION gets literature+references+memory but NOT code/data
- PLANNING gets literature+code/data+memory but NOT references
- Unlisted phases get nothing injected (they build their own prompts)
- Search only enabled in IDEATION, PLANNING, EXECUTION
- Fuzzy dedup uses normalized keyword sets + Jaccard similarity (threshold=0.7)

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — `_PHASE_CONTEXT_NEEDS`, gated `_build_agent_prompt()`, shrunk `_SEARCH_ENABLED_PHASES`, fuzzy dedup helpers + state, `_LITERATURE_CONTEXT_LIMIT` 15K→10K
- `src/paradigm/literature/prompt_utils.py` — `max_papers` default 5→3
- `configs/default.yaml` — `max_searches_per_round` 10→5
- `tests/test_orchestrator.py` — Phase context + fuzzy dedup tests
- `tests/test_prompt_utils.py` — Updated for `max_papers=3` default

**Future work:** The reduced limits (`_LITERATURE_CONTEXT_LIMIT` 10K, `max_papers` 3, `max_searches_per_round` 5) are conservative defaults for cost-efficient development and testing. For production research runs, agents should have the ability to download and retain more literature when they need to. Consider making these limits configurable via `default.yaml` (or a separate `production.yaml` profile) so they can be raised without code changes — e.g. `literature_context_limit: 25000`, `max_papers_per_search: 10`, `max_searches_per_round: 15`.

### Prompt — Multi-Provider LLM Refactoring: Epistemic Diversity + Testing Mode

> Implement the following plan: Multi-Provider LLM Refactoring — Epistemic Diversity + Testing Mode
>
> 1. Update model assignments in default.yaml: Together default → Llama 3.3 70B Turbo, skeptic → Together/Qwen3, editor → Together/GLM 4.7, add testing_overrides section
> 2. Add testing_overrides field to Config, apply_testing_overrides() method, validation in _ensure_providers
> 3. Add --testing CLI flag to run command, apply overrides before agent creation
> 4. Add tests for testing_overrides parsing, apply, resolution, and validation

**Key decisions:**
- Epistemic diversity: 5 independent orgs (Anthropic, Meta, Alibaba, Zhipu, DeepSeek) with distinct training lineages
- `--testing` flag swaps theorist from Opus to DeepSeek V3.1 via Together.ai, removing all Anthropic API calls
- Config-driven `testing_overrides` section in YAML, applied at runtime via `apply_testing_overrides()`
- No changes needed to providers.py, factory.py, engine.py, or orchestrator — existing abstraction handles it

**Artifacts modified:**
- `configs/default.yaml` — New model assignments, testing_overrides section
- `src/paradigm/config.py` — testing_overrides field, apply_testing_overrides(), validation
- `src/paradigm/main.py` — --testing flag on run command
- `tests/test_providers.py` — Tests for testing_overrides

### Prompt — Literature Search: Graph Traversal, Not Keyword Slot Machines

> Read all files in `.planning/` and `CLAUDE.md`. Then read `src/paradigm/literature/arxiv.py`, `src/paradigm/literature/corpus.py`, `src/paradigm/literature/embeddings.py`, and `src/paradigm/orchestrator/engine.py`. Plan a complete overhaul of literature search from flat keyword guessing to citation-graph traversal.
>
> New action markers: `[FOLLOW: arxiv_id]` (reference chasing via Semantic Scholar), `[CITED_BY: arxiv_id]` (citation-forward search), `[READ: arxiv_id]` (deep reading with PDF extraction). New module: `semantic_scholar.py`. Per-action-type budget counters. Agent prompt changes to prefer graph traversal over keyword rephrasing after Round 1.

**Goal:** Plan the implementation across 4 phases: (1) CITED_BY via Semantic Scholar, (2) FOLLOW via references endpoint, (3) READ for deep reading, (4) agent prompt changes + stall detection hints.

### Prompt 67 — Implement Literature Search Graph Traversal via Semantic Scholar

> Implement the following plan: Literature Search — Graph Traversal via Semantic Scholar
>
> Adds three new action markers (`[FOLLOW:]`, `[CITED_BY:]`, `[READ:]`) alongside existing `[SEARCH:]`,
> backed by a Semantic Scholar API client for structured citation graph traversal and PDF-based deep reading.
>
> Implementation steps: (1) Semantic Scholar API client, (2) Action marker parsing, (3) Config updates,
> (4) Event types, (5) Deep reading helper, (6) Corpus integration, (7) Engine integration, (8) Agent prompt updates, (9) Tests.

**Key decisions:**
- Semantic Scholar for citation graph (free API, structured data, arXiv ID lookup)
- Per-action-type budgets (follow: 3, cited_by: 2, read: 2 per round)
- Stall detection hint when keyword search returns 0 new results
- Agent prompt updated to teach graph traversal strategy

**Artifacts produced/modified:**
- `src/paradigm/literature/semantic_scholar.py` (NEW)
- `src/paradigm/literature/prompt_utils.py` (MODIFY)
- `src/paradigm/literature/arxiv.py` (MODIFY)
- `src/paradigm/literature/corpus.py` (MODIFY)
- `src/paradigm/literature/__init__.py` (MODIFY)
- `src/paradigm/config.py` (MODIFY)
- `configs/default.yaml` (MODIFY)
- `src/paradigm/logging/events.py` (MODIFY)
- `src/paradigm/orchestrator/engine.py` (MODIFY)
- `tests/test_semantic_scholar.py` (NEW)
- `tests/test_prompt_utils.py` (MODIFY)
- `tests/test_corpus.py` (MODIFY)
- `tests/test_orchestrator.py` (MODIFY)

### Prompt — Fix Per-Agent Search Cap, 429 Backoff, and Circuit Breaker Minimum Sample

> Implement the following plan: Fix Remaining Literature Search + Execution Issues
>
> 1. Raise per-agent search cap from `max(1, max_searches//3)` to `max(2, max_searches*2//5)` — gives 2 searches instead of 1 with default budget of 5
> 2. Increase 429 backoff from `rate_limit * 2^(attempt+1)` (6s,12s,24s) to `10 * 2^attempt` (10s,20s,40s) — 70s total, enough for arXiv rate limits
> 3. Add minimum sample size to circuit breaker: `round_total >= 3` instead of `round_total > 0` — prevents 1/1 failure from triggering early stop
> 4. Update tests for new cap value and add circuit breaker minimum sample test

**Key decisions:**
- Per-agent cap formula changed to give the active searcher 2 slots while keeping round budget at 5
- Backoff uses fixed 10s base instead of rate_limit (3s), giving more headroom for arXiv 429s
- Circuit breaker requires at least 3 experiments before evaluating failure rate

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Per-agent cap formula, circuit breaker minimum sample
- `src/paradigm/literature/arxiv.py` — Increased 429 backoff
- `tests/test_orchestrator.py` — Updated per-agent cap test assertions
- `tests/test_experimentation.py` — New `test_circuit_breaker_minimum_sample` test

### Prompt 68 — Fix arXiv ID Validation for Graph Traversal Actions

> I'm seeing some issues: agents pass URLs (e.g., `https://www.aanda.org/...`) to `[READ:]` and
> literal placeholder text (`arxiv_id`) to `[FOLLOW:]`/`[CITED_BY:]`. These cause 400 errors
> from arXiv API and empty results from Semantic Scholar.

**Root cause:** `_normalize_arxiv_id()` didn't validate that the input looked like an arXiv ID —
it just stripped prefixes and returned whatever string it got.

**Fixes:**
- Added `_ARXIV_ID_RE` regex to validate arXiv ID format (YYMM.NNNNN or category/YYMMNNN)
- `_normalize_arxiv_id()` now returns empty string for URLs, placeholder text, and garbage
- Improved `_LITERATURE_INSTRUCTION` prompt to explicitly state arXiv IDs required (not URLs)
- Added 6 new tests for URL/garbage rejection across all three parsers

**Artifacts modified:**
- `src/paradigm/literature/prompt_utils.py` — validation regex + early URL rejection
- `src/paradigm/orchestrator/engine.py` — clearer prompt instruction
- `tests/test_prompt_utils.py` — 6 new validation tests

### Prompt 69 — Fix Execution Phase Network Access Failures

> Implement the following plan: Fix Execution Phase — Network Access Failures
>
> During live testing, agents in the EXECUTION phase repeatedly try to download data from the internet despite running in Docker with --network=none. This causes execution failures, retry loops waste tokens, and circuit breaker triggers early.
>
> Root causes: `requests` listed as available library, no-network constraint buried at end of prompt, retry prompt has no network reminder, safety scanner doesn't catch network calls.
>
> Fix: (1) Restructure execution prompt — remove requests, move no-network warning to top, add data strategy guidance, (2) Add network error detection to retry feedback, (3) Add network module detection to safety scanner (AST + regex), (4) Update analyze_results and retry_after_failure prompts with no-network reminders, (5) Tests for all changes.

**Key decisions:**
- Remove `requests` from available libraries list (contradictory signal with --network=none)
- Network constraint as bold warning block at top of execution prompt, not buried at end
- Network error pattern detection in `_execute_with_retry()` prepends clear guidance
- AST-based detection for `requests`, `httpx`, `aiohttp`, `ftplib` imports in safety scanner
- Regex-based detection for `urllib.request`, `http.client`, `socket` usage
- `urllib.parse` remains allowed (no network needed)

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Restructured execution prompt, network error detection in retry, updated analyze_results and retry_after_failure prompts
- `src/paradigm/sandbox/safety.py` — Added NETWORK_MODULES, _check_network_imports(), network regex patterns
- `tests/test_safety.py` — NEW: ~5 tests for network module detection
- `tests/test_orchestrator.py` — ~2 new tests for network error hints and library list

---

### Prompt 42 — Analyze Execution Phase of Latest Paradigm Run
**Date:** 2026-02-14

> Analyze the latest paradigm run's execution phase from data/events.jsonl. Find the most recent thread ID, extract all events for that thread, identify the research topic, count code execution successes/failures/rejections/timeouts, extract error messages, determine if errors are network-related, check for safety rejections, find phase transitions, check paper output directory, review the paper's search log and review log, and give a comprehensive summary.

**Key decisions:** Pure analysis task, no code changes.

**Artifacts examined:**
- `data/events.jsonl` — thread-28bbf68ba964 (60 events)
- `data/papers/paper-e4543cc41888/paper-e4543cc41888.md`
- `data/papers/paper-e4543cc41888/reviews.md`
- `data/papers/paper-e4543cc41888/literature_searches.md`
- `data/papers/paper-e4543cc41888/figures/` (3 PNG figures)

---

## 2026-02-14

### Prompt 30 — Fix File Path Hallucination & Hollow Papers

> Implement the following plan:
>
> # Plan: Fix File Path Hallucination & Hollow Papers
>
> ## Context
> Latest run (thread-28bbf68ba964) had 76.5% execution success rate but the paper was desk-rejected as a "template, not a manuscript" — just 35 lines with no quantitative results. Two root causes:
> 1. File path hallucination: execution prompt references nonexistent "Available Code Resources" / "Available Data Files" sections
> 2. Hollow papers: _MIN_PAPER_LENGTH = 500 too low, no section length guidance, passive experiment injection
>
> ## Changes
> 1. Add `_list_shared_files()` helper, inject actual file listing into execution prompt
> 2. Fix `propose_experiment` template to remove phantom section references
> 3. Raise `_MIN_PAPER_LENGTH` from 500 to 3000
> 4. Add section length guidance to `section_drafting` template
> 5. Strengthen experiment results injection wording
> 6. Add ~4 new tests

**Key decisions:**
- `_list_shared_files()` scans at execution time for ground truth
- 3000 chars minimum (~1000 words) for paper body
- Demand quantitative results in section drafting and experiment injection

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py`
- `tests/test_orchestrator.py`
- `HISTORY.md`

### Prompt 31 — Add Auto-Import Preamble for Pandas (and Common Libraries)

> We also need to add pandas (NameError: name 'pd' is not defined | Missing import (code bug))

**Key decisions:**
- Add a `_SCIENCE_PREAMBLE` auto-prepended to all experiment code in the executor
- Covers numpy, scipy, matplotlib, pandas, astropy with standard aliases
- Also add import reminder to the execution prompt template

**Artifacts modified:**
- `src/paradigm/sandbox/executor.py`
- `src/paradigm/orchestrator/engine.py`
- `tests/test_executor.py` (new test)
- `HISTORY.md`

### Prompt 32 — Fix Literature Search Pipeline Stalling

> Implement the following plan: Fix Literature Search Pipeline Stalling
>
> Agents are not finding new literature after the first batch. Logs show: theorist monopolizes the search budget (5/5 searches), repeats queries returning 0 new results, other agents never search. Root causes: shared per-round budget, no early termination on stale searches, no cross-round stall tracking, stall hint fires only once per round.
>
> Changes: (1) Early termination after 2 consecutive stale keyword searches, (2) Cross-round stale tracking with hard cap after 5 cumulative stale searches, (3) Unconditional stall hint (remove follow/cited_by count condition), (4) Per-agent keyword search cap.

**Key decisions:**
- `_total_stale_keyword_searches` persists across rounds (never reset per round)
- Per-agent cap: `max(1, max_searches_per_round // 3)`
- After 5 cumulative stale searches: hard-cap keyword budget to 1/round + inject persistent warning
- Stall hint always fires on 0-new results (not gated on follow/cited_by counts)

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Early termination, cross-round tracking, unconditional stall hint, per-agent cap
- `tests/test_orchestrator.py` — ~4 new tests
- `HISTORY.md` — This prompt logged

---

## 2026-02-15

### Prompt 24 — Refactor engine.py + Create tests/conftest.py

> Implement the following plan: Refactor engine.py (3,306 lines, 37 methods) into 5 focused modules (~900-line core + 4 handlers: constants.py, literature.py, debate.py, writing.py, review.py) and create tests/conftest.py to eliminate fixture duplication across 5 test files.

**Key decisions:**
- Handler classes receive back-reference to engine (`self._engine`)
- TYPE_CHECKING blocks to avoid circular imports
- Re-exports in engine.py preserve backward compatibility for tests
- conftest.py consolidates tmp_db, tmp_logger, build_checkpoint_response, make_mock_agent, mock_factory, mock_corpus

**Artifacts produced/modified:**
- `src/paradigm/orchestrator/constants.py` — NEW: all constants, prompt templates, pure functions
- `src/paradigm/orchestrator/literature.py` — NEW: LiteratureHandler class
- `src/paradigm/orchestrator/debate.py` — NEW: DebateHandler class
- `src/paradigm/orchestrator/writing.py` — NEW: WritingHandler class
- `src/paradigm/orchestrator/review.py` — NEW: ReviewHandler class
- `src/paradigm/orchestrator/engine.py` — Slimmed to ~900 lines, delegates to handlers
- `tests/conftest.py` — NEW: shared test fixtures
- `tests/test_*.py` — Updated to use conftest fixtures
- `HISTORY.md` — This prompt logged

### Prompt 25 — Remove old constants/functions from engine.py

> I need you to edit engine.py to remove the old module-level constants, prompt templates, and pure functions that have been moved to constants.py. The file currently has a dummy line `_PHASE_INSTRUCTIONS_COMPAT = {` at line ~91 that marks the start of the old block. Everything from that line through the `_format_execution_result` function (which ends with `return "\n\n".join(parts)`) and the two blank lines before `class OrchestrationEngine:` needs to be removed. Replace it with just two blank lines before `class OrchestrationEngine:`.

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Removed dead module-level constants/functions already in constants.py
- `HISTORY.md` — This prompt logged

### Prompt 26 — Refactor test_orchestrator.py to use shared conftest.py fixtures

> Edit tests/test_orchestrator.py to use shared fixtures from conftest.py: import build_checkpoint_response, make_mock_agent, LONG_RESPONSE, patch_config_provider; delete local tmp_db, tmp_logger, _LONG_RESPONSE, _make_mock_agent, mock_factory, mock_corpus, _build_checkpoint_response; simplify mock_config provider patching with patch_config_provider(); replace all _make_mock_agent/_ LONG_RESPONSE/_build_checkpoint_response references with conftest versions.

**Artifacts modified:**
- `tests/test_orchestrator.py` — Refactored to use shared conftest.py fixtures
- `HISTORY.md` — This prompt logged

### Prompt 27 — Refactor test_experimentation.py to use shared conftest.py fixtures

> Edit tests/test_experimentation.py to use shared fixtures from conftest.py: import build_checkpoint_response, make_mock_agent, patch_config_provider; delete local tmp_db, tmp_logger, _build_checkpoint_response, _make_mock_agent, mock_factory, mock_corpus; simplify mock_config and mock_config_no_sandbox provider patching with patch_config_provider(); replace all _make_mock_agent/_build_checkpoint_response references with conftest versions. Keep _make_experiment_agent and mock_factory_with_code since they are specific to experimentation tests.

**Artifacts modified:**
- `tests/test_experimentation.py` — Refactored to use shared conftest.py fixtures
- `HISTORY.md` — This prompt logged

### Prompt 28 — Refactor test_debate.py to use shared conftest.py fixtures

> Edit tests/test_debate.py to use shared fixtures from conftest.py: import build_checkpoint_response, make_mock_agent, patch_config_provider; delete local _build_checkpoint_response, _make_mock_agent, tmp_db, tmp_logger, mock_corpus; simplify both mock_config fixtures' provider patching with patch_config_provider(); replace all _make_mock_agent/_build_checkpoint_response references with conftest versions.

**Artifacts modified:**
- `tests/test_debate.py` — Refactored to use shared conftest.py fixtures
- `HISTORY.md` — This prompt logged

### Prompt 29 — Refactor test_peer_review.py to use shared conftest.py fixtures

> Edit tests/test_peer_review.py to use shared fixtures from conftest.py: import build_checkpoint_response, make_mock_agent, patch_config_provider; delete local tmp_db, tmp_logger, mock_corpus, _build_checkpoint_response, _make_mock_agent; simplify mock_config and mock_config_no_peer_review provider patching with patch_config_provider(); replace all _make_mock_agent/_build_checkpoint_response references with conftest versions. Keep _make_review_text and _make_writing_factory since they are specific to peer review tests.

**Artifacts modified:**
- `tests/test_peer_review.py` — Refactored to use shared conftest.py fixtures
- `HISTORY.md` — This prompt logged

### Prompt 30 — Refactor test_writing.py to use shared conftest.py fixtures

> Edit tests/test_writing.py to use shared fixtures from conftest.py: import build_checkpoint_response, make_mock_agent, patch_config_provider; delete local tmp_db, tmp_logger, _build_checkpoint_response, _make_mock_agent, mock_corpus; simplify mock_config and mock_config_no_writing provider patching with patch_config_provider(); replace all _make_mock_agent/_build_checkpoint_response references with conftest versions. Keep _make_writing_factory since it is specific to writing tests.

**Artifacts modified:**
- `tests/test_writing.py` — Refactored to use shared conftest.py fixtures
- `HISTORY.md` — This prompt logged

### Prompt 31 — Create orchestrator/debate.py (DebateHandler)

> Create the file /Users/mcantiello/astro/paradigm/src/paradigm/orchestrator/debate.py containing a `DebateHandler` class. Extract `_process_challenge_requests`, `_run_debate`, `_synthesize_debate`, and `_mechanical_debate_synthesis` from engine.py. Use `from __future__ import annotations` and `TYPE_CHECKING` to avoid circular imports. Translate all `self._foo` references to `self._engine._foo` and `self._debate_counts` to `self.debate_counts`.

**Artifacts produced:**
- `src/paradigm/orchestrator/debate.py` — NEW: DebateHandler class with 6 methods
- `HISTORY.md` — This prompt logged

### Prompt 32 — Create orchestrator/literature.py (LiteratureHandler)

> Create the file /Users/mcantiello/astro/paradigm/src/paradigm/orchestrator/literature.py containing a `LiteratureHandler` class that extracts the literature search methods from engine.py. The handler receives a back-reference to the engine (`self._engine`) in its constructor. It accesses engine state via `self._engine._config`, `self._engine._corpus`, etc. Use `from __future__ import annotations` and `TYPE_CHECKING` blocks to avoid circular imports. The class should contain `__init__`, `reset_round_counters`, `reset_cycle`, `process_search_requests`, and `process_literature_actions` methods, with method bodies copied from engine.py's `_process_search_requests` and `_process_literature_actions`, with attribute references updated to go through `self._engine` or `self` as appropriate.

**Artifacts produced:**
- `src/paradigm/orchestrator/literature.py` — NEW: LiteratureHandler class with 5 methods
- `HISTORY.md` — This prompt logged

### Prompt 33 — Create orchestrator/review.py (ReviewHandler)

> Create the file /Users/mcantiello/astro/paradigm/src/paradigm/orchestrator/review.py containing a `ReviewHandler` class. Extract `_run_review_phase`, `_run_revision`, `_run_submission_phase`, `_run_peer_review_phase`, and `_run_revision_phase` from engine.py. Use `from __future__ import annotations` and `TYPE_CHECKING` to avoid circular imports. Translate all `self._foo` references to `self._engine._foo`, `self._review_log` to `self.review_log`, `self._search_count_this_round` to `self._engine._literature.search_count_this_round`, `self._save_paper_file` to `self._engine._writing.save_paper_file`, and `self._run_revision` to `self.run_revision`.

**Artifacts produced:**
- `src/paradigm/orchestrator/review.py` — NEW: ReviewHandler class with 7 methods
- `HISTORY.md` — This prompt logged

### Prompt 34 — Create orchestrator/writing.py (WritingHandler)

> Create the file /Users/mcantiello/astro/paradigm/src/paradigm/orchestrator/writing.py containing a `WritingHandler` class. Extract writing-phase methods from engine.py (`_run_writing_phase`, `_run_section_drafting`, `_run_assembly`, `_embed_figures_inline`, `_save_paper_file`, `_copy_figures_to_paper_dir`, `_figure_dest_name`) into the new class, translating `self._*` references to `self._engine._*` as appropriate, and `self._search_count_this_round` to `self._engine._literature.search_count_this_round`, and `self._process_search_requests`/`self._process_literature_actions` to `self._engine._literature.*`.

**Artifacts produced:**
- `src/paradigm/orchestrator/writing.py` — NEW: WritingHandler class with 7 methods

### Prompt 35 — Rewrite engine.py to delegate to handler classes

> Rewrite /Users/mcantiello/astro/paradigm/src/paradigm/orchestrator/engine.py to delegate to the new handler classes instead of implementing everything inline. Update imports, create handler instances in __init__, delegate method calls in run_research_cycle and other methods, remove extracted methods, and update all references to handler-owned state.

**Key decisions:**
- Handler instances created in `__init__`: `self._literature`, `self._debate`, `self._writing`, `self._review`
- Per-cycle state (search/debate/review counters) now owned by handlers
- 18 methods removed from engine.py (now in handler classes)
- Remaining methods updated to reference handler state via `self._literature.*`, `self._debate.*`, `self._review.*`, `self._writing.*`

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Major rewrite: imports trimmed, handlers injected, methods removed, references updated
- `HISTORY.md` — This prompt logged

### Prompt 36 — Final cleanup and verification (continued session)

> Continue with the refactoring plan — final cleanup and verification after handler integration.

**Key decisions:**
- Fixed stale reference `engine._literature_context` → `engine._literature.literature_context` in test_debate.py
- Ran ruff format on 4 files (debate.py, literature.py, writing.py, test_debate.py)
- Removed unused import `build_checkpoint_response` from test_peer_review.py
- Fixed import sort order in conftest.py, helpers.py, test_peer_review.py, test_writing.py

**Final results:**
- 578/578 tests passing
- All ruff check + format passing
- engine.py: 3,306 → 1,262 lines (62% reduction)
- New modules: constants.py (641), literature.py (448), debate.py (393), writing.py (358), review.py (453)
- New test infrastructure: conftest.py + helpers.py (eliminated ~290 lines of fixture duplication)

**Artifacts modified:**
- `tests/test_debate.py` — Fixed `_literature_context` → `_literature.literature_context`
- `tests/test_peer_review.py` — Removed unused import
- `tests/conftest.py`, `tests/helpers.py`, `tests/test_writing.py` — Import sort fixes
- `src/paradigm/orchestrator/debate.py`, `literature.py`, `writing.py` — Formatting fixes
- `HISTORY.md` — This prompt logged

### Prompt 82 — Analyze Execution Phase Failures from Thread thread-17927ce63b27

> I need to analyze the execution phase failures from a Paradigm run. The thread ID is thread-17927ce63b27. There were 8 execution attempts across 3 rounds. For each execution directory, read script.py and check for output/stderr/result files. Also search events log for execution events from this thread. Provide detailed analysis of what each script was doing, what went wrong, and what changed between failing and succeeding attempts.

**Artifacts modified:**
- `HISTORY.md` — This prompt logged

### Prompt 83 — Fix Experiment Execution Failures (Vacuous Success + File Path Hallucination)

> Implement the following plan: Fix Experiment Execution Failures
>
> Two systemic problems: (1) Vacuous success — scripts that catch FileNotFoundError and exit 0 count as SUCCESS despite producing no scientific output. (2) File path hallucination on retry — retry feedback includes raw stderr but doesn't highlight what files exist, so agents keep fabricating filenames.
>
> Changes: Add `_is_vacuous_success()` + `_VACUOUS_STDOUT_PATTERNS` + `_FILE_NOT_FOUND_PATTERNS` to constants.py. In engine.py `_execute_with_retry`: detect vacuous success and reclassify as failure, add FileNotFoundError-specific retry guidance with file listing.

**Key decisions:**
- Vacuous success: no output_files AND (stdout < 20 chars OR stdout contains error-like patterns)
- File-not-found guidance: inject file listing directly next to the error, not buried in checkpoint context
- Check both stdout and stderr for file-not-found patterns (scripts may catch and print to stdout)

**Artifacts modified:**
- `src/paradigm/orchestrator/constants.py` — `_VACUOUS_STDOUT_PATTERNS`, `_FILE_NOT_FOUND_PATTERNS`, `_is_vacuous_success()`
- `src/paradigm/orchestrator/engine.py` — Vacuous success detection + file-not-found retry guidance
- `tests/test_experimentation.py` — Tests for vacuous success and file-not-found guidance
- `HISTORY.md` — This prompt logged

### Prompt 84 — Route Experimentalist to Opus 4.6

> I also (as a default) I think we need to use Opus 4.6 for the experimentalist, since the other models seem to hallucinate constantly and this agent needs to be precise and skilled

**Key decisions:** Experimentalist needs precision for code generation and file path handling — route to Anthropic/Opus alongside theorist.

**Artifacts modified:**
- `configs/default.yaml` — Added `experimentalist` override: `provider: anthropic, model: claude-opus-4-6`
- `HISTORY.md` — This prompt logged

### Prompt 85 — Fix Literature Search: Agents Don't Use Graph Traversal in Round 2+

> Implement the following plan: Fix Literature Search — Agents Don't Use Graph Traversal in Round 2+
>
> Agents in round 2+ keep doing keyword searches that return 0 new results instead of using [FOLLOW:] and [CITED_BY:] for citation graph traversal. Root cause: agents can't see the arXiv IDs of papers they found — literature context is truncated to 10K chars, and stall hints tell agents to use graph traversal but don't provide concrete paper IDs to follow.
>
> Changes: (1) Track discovered papers in compact index in LiteratureHandler, (2) Inject paper index into round 2+ prompts, (3) Make stall hints include concrete paper IDs, (4) Increase _LITERATURE_CONTEXT_LIMIT 10K→15K.

**Key decisions:**
- `discovered_papers: list[tuple[str, str, str]]` (arxiv_id, title, first_author) tracked on LiteratureHandler
- `build_paper_index()` renders compact reference list not subject to truncation
- Paper index prepended to checkpoint context for search-enabled phases at round 2+
- Stall hints include 3 concrete `[FOLLOW: arxiv_id]` examples from discovered papers

**Artifacts modified:**
- `src/paradigm/orchestrator/literature.py` — `discovered_papers`, `build_paper_index()`, track in search/follow/cited_by, concrete IDs in stall hints
- `src/paradigm/orchestrator/engine.py` — Inject paper index into round 2+ prompts
- `src/paradigm/orchestrator/constants.py` — `_LITERATURE_CONTEXT_LIMIT` 10000 → 15000
- `tests/test_orchestrator.py` — Tests for paper index building and injection
- `HISTORY.md` — This prompt logged

---

## 2026-02-15

### Prompt 33 — FOLLOW/CITED_BY Dedup + Filter Self-Papers + Increase Read Budget

> Implement the following plan: FOLLOW/CITED_BY Dedup + Filter Self-Papers + Increase Read Budget
>
> Three resource waste problems: (1) FOLLOW/CITED_BY have zero deduplication — same papers followed multiple times, (2) ChromaDB search returns Paradigm's own published papers — paper-* IDs waste search slots, (3) read_budget_per_round: 2 too low for 5 agents.
>
> Fix 1: Add followed_paper_ids and cited_by_paper_ids sets to LiteratureHandler, skip duplicates.
> Fix 2: Skip paper-* IDs in Corpus.search() local results.
> Fix 3: Increase read_budget_per_round from 2 to 5 in config.py and default.yaml.
> Also fix stale YAML max_review_iterations: 1 → 2.

**Key decisions:**
- Same dedup pattern as read_paper_ids (per-cycle sets, reset in reset_cycle)
- paper-* filtering at corpus level prevents self-citation pollution
- read_budget_per_round: 5 gives ~1 read per agent per round

**Artifacts modified:**
- `src/paradigm/orchestrator/literature.py` — `followed_paper_ids`, `cited_by_paper_ids` sets + dedup checks
- `src/paradigm/literature/corpus.py` — Skip `paper-*` IDs in `search()` local results
- `src/paradigm/config.py` — `read_budget_per_round: 2` → `5`
- `configs/default.yaml` — `read_budget_per_round: 2` → `5`, `max_review_iterations: 1` → `2`
- `tests/test_orchestrator.py` — 6 new tests
- `HISTORY.md` — This prompt logged

### Prompt 32 — Fix Internal Review Revision Flow + Add READ Deduplication

> Implement the following plan:
>
> Fix 1: Internal Review Revision Flow — Change `max_review_iterations` default from 1 to 2 in `config.py` so the editor review → writer revision loop actually runs.
>
> Fix 2: READ Deduplication — Add `read_paper_ids: set[str]` to `LiteratureHandler` that persists across rounds (reset per-cycle). When a `[READ:]` request comes in, skip if already in `read_paper_ids`. Log a message so it's visible.

**Key decisions:**
- `max_review_iterations` default changed from 1 → 2 (review → revise → review)
- `read_paper_ids` set added to `LiteratureHandler.__init__`, cleared in `reset_cycle()`
- Dedup check inserted before `corpus.read_paper()` call, after budget check

**Artifacts modified:**
- `src/paradigm/config.py` — `max_review_iterations: int = 1` → `2`
- `src/paradigm/orchestrator/literature.py` — `read_paper_ids` set, dedup check in READ processing, reset in `reset_cycle()`
- `tests/test_orchestrator.py` — Tests for READ dedup, dedup reset, config default
- `HISTORY.md` — This prompt logged

### Prompt 33 — Analyze Execution Phase of Most Recent Paradigm Run

> Analyze the execution phase of the most recent Paradigm paper run. I need to understand why experiments got stuck and couldn't make progress.
>
> Steps:
> 1. Find the most recent thread ID from `data/events.jsonl`
> 2. Extract ALL events for that thread — focus on PHASE_TRANSITION, CODE_EXECUTION, EXPERIMENT_* events
> 3. Find the paper ID from the thread and read the paper's search log and review log
> 4. Look in `data/` for execution directories
> 5. For each failed execution, read the `script.py` and `stderr`/`result.json` files
> 6. Check for patterns: network errors? Missing files? Import errors? Timeouts?
> 7. Read execution-related prompts in `src/paradigm/orchestrator/constants.py`
>
> Give me a comprehensive breakdown.

**Key decisions:** Pure analysis task, no code changes.
**Artifacts examined:** TBD

---

### Prompt 40 — Analyze Desk-Rejected Paper

> Analyze the latest Paradigm paper that was desk-rejected to understand what went wrong. The thread is thread-f035675480f5 and the paper is paper-be233212b32b.
>
> 1. Read the paper: `data/papers/paper-be233212b32b/paper-be233212b32b.md`
> 2. Read the review log: `data/papers/paper-be233212b32b/reviews.md`
> 3. Read the literature search log (first 100 lines)
> 4. Check how many figures are in the paper directory
> 5. Look at the desk review logic in `src/paradigm/orchestrator/review.py`
>
> Focus on paper substance, desk rejection reason, quantitative results from experiments, figure handling, and disconnect between experimental output and paper content.

**Key decisions:** Pure analysis task, no code changes.
**Artifacts examined:** TBD

---

### Prompt 41 — Fix Paper Quality: Stop Auto-Promote, Raise Min Length, More Review Iterations

> Implement the following plan:
>
> Fix Paper Quality — Stop Auto-Promote, Raise Min Length, More Review Iterations
>
> The latest Paradigm run produced a paper that was desk-rejected despite 36/36 successful experiments.
> Root cause: the paper was only 735 words (5,850 chars) — a skeleton with fabricated numbers. Three issues:
>
> 1. Auto-promote on max review iterations — `review.py` lines 131-134 mark paper as "reviewed" when exhausted
> 2. `_MIN_PAPER_LENGTH = 3000` is too low — needs ~10,000 chars
> 3. `max_review_iterations = 2` — only 2 rounds, bump to 3
>
> Fix 1: Don't auto-promote → set `writing_failed` instead of `reviewed`
> Fix 2: Raise `_MIN_PAPER_LENGTH` to 10000
> Fix 3: Increase `max_review_iterations` to 3
> Fix 4: Update tests and helpers

**Key decisions:**
- `writing_failed` status for exhausted review iterations (mirrors existing pattern)
- 10,000 char minimum (~1,250 words) — still lenient but catches skeletons
- 3 review iterations = 2 revision chances

**Artifacts modified:**
- `src/paradigm/orchestrator/review.py` — Stop auto-promoting on max iterations
- `src/paradigm/orchestrator/constants.py` — `_MIN_PAPER_LENGTH = 10000`
- `src/paradigm/config.py` — `max_review_iterations: int = 3`
- `configs/default.yaml` — `max_review_iterations: 3`
- `tests/helpers.py` — Pad `LONG_RESPONSE` to exceed 10,000 chars
- `tests/test_orchestrator.py` — Update assertions + add new test
- `HISTORY.md` — This prompt logged

---

### Prompt 42 — Document Literature Search Algorithm in Manual

> Great. Let's make sure this is documented in the manual

**Key decisions:**
- Added new section 9 "Literature Search System" to `docs/MANUAL.md`
- Updated outdated config values in the configuration reference
- Renumbered sections 9-14 → 10-15

**Artifacts modified:**
- `docs/MANUAL.md` — New literature search section + config updates
- `HISTORY.md` — This prompt logged

---

## 2026-02-16

### Prompt 43 — Fix Editor Review Parsing + Missing Token Summary

> Implement the following plan: Fix Editor Review Parsing + Missing Token Summary
>
> The latest Paradigm run (thread-f77c4ffcc059) hit `writing_failed` after 3 internal review iterations despite the editor having 0 required changes on iterations 2-3. Three compounding issues:
> 1. Max tokens truncation — Editor `generate()` uses default `max_tokens=4096`. The prompt puts Recommendation last, so it gets cut off. Iterations 2-3 both hit exactly 4096 tokens.
> 2. Header level mismatch — Editor used `### Recommendation` (h3) under a `## Scientific Editorial Review` wrapper. The parser only matches `##` headers.
> 3. Unsafe default — When recommendation section is missing (truncation or wrong header), `parse_review_feedback` defaults to "revise". Any parsing failure = revise.
>
> Additionally, the `writing_failed` early return from the previous commit skips `_print_token_summary()` and `_save_auxiliary_files()`.
>
> Fixes: (1) Add token summary to writing_failed early return, (2) Increase editor review max_tokens to 8192, (3) Make parse_review_feedback resilient to ### headers and truncation, (4) Strengthen editor review prompt, (5) Add tests.

**Key decisions:**
- `_REVIEW_MAX_TOKENS = 8192` — prevents truncation of Recommendation section
- `_parse_h3_sections()` local helper — fallback for ### headers without changing shared parser
- Full-text fallback — if no Recommendation section found, scan for "accept" vs "revise" in body
- Strip trailing colons from header keys in both parsers
- Prompt strengthened to require `## Recommendation` and `##` headers

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Add `_save_auxiliary_files` + `_print_token_summary` to writing_failed return
- `src/paradigm/orchestrator/constants.py` — Add `_REVIEW_MAX_TOKENS = 8192`, strengthen editor_review prompt
- `src/paradigm/orchestrator/review.py` — Pass `max_tokens=_REVIEW_MAX_TOKENS` to editor.generate()
- `src/paradigm/journal/paper.py` — Add `_parse_h3_sections`, enhance `parse_review_feedback` with fallbacks, strip colons from keys
- `tests/test_writing.py` — Add 3 tests for parse_review_feedback edge cases
- `HISTORY.md` — This prompt logged

### Prompt 44 — Update Model Assignments: Opus Default, Gemini for Skeptic/Editor

> Route analyst, synthesizer, writer to Opus 4.6 in default mode. Add Google Gemini provider with `gemini-3-pro-preview`. Route skeptic and editor to Gemini. Update testing overrides so `--testing` stays Anthropic/Google-free. Update documentation.

**Key decisions:**
- Default mode: 5 core roles on Anthropic/Opus 4.6, skeptic + editor on Google/Gemini 3 Pro
- Testing mode: all roles on Together.ai (DeepSeek-V3.1 + Qwen3 Thinking), zero Anthropic/Google calls
- Google provider via OpenAI-compatible endpoint at `generativelanguage.googleapis.com/v1beta/`
- MANUAL.md updated: prerequisites, providers section, model assignment tables, environment variables, error messages

**Artifacts modified:**
- `configs/default.yaml` — Add google provider, route analyst/synthesizer/writer to Opus, skeptic/editor to Gemini, update testing overrides
- `docs/MANUAL.md` — Add providers section, model assignment tables, multi-provider setup docs
- `HISTORY.md` — This prompt logged
---

## 2026-02-16

### Prompt — Rich Terminal UI Implementation

> Implement the following plan: Rich Terminal UI for Paradigm using the `rich` library. Replace all 155 `click.echo()` calls with a DisplayManager that supports both rich terminal output and plain text fallback. Implementation in 4 phases: Phase 0 (scaffolding + click.echo replacement), Phase 1 (phase bar + stats), Phase 2 (live layout), Phase 3 (polish).

**Artifacts:** `src/paradigm/display/` package (theme.py, manager.py, fallback.py, components.py, layout.py), modifications to engine.py, literature.py, debate.py, writing.py, review.py, main.py, tests.

### Prompt — Replace click.echo in Handler Files with DisplayManager Calls

> Replace ALL `click.echo` calls in these 4 handler files with `self._engine._display.method()` calls. Remove `import click` from each file: literature.py, debate.py, writing.py, review.py.

**Key decisions:**
- Each handler accesses display via `self._engine._display`
- Display methods already defined on DisplayManager (manager.py) with both Rich and plain-text fallback
- `import click` removed from all 4 handler files

**Artifacts modified:**
- `src/paradigm/orchestrator/literature.py` — 19 click.echo → display method calls
- `src/paradigm/orchestrator/debate.py` — 12 click.echo → display method calls
- `src/paradigm/orchestrator/writing.py` — 8 click.echo → display method calls
- `src/paradigm/orchestrator/review.py` — 21 click.echo → display method calls
- `HISTORY.md` — This prompt logged

### Prompt — Replace click.echo in engine.py with DisplayManager

> Replace ALL `click.echo` calls in engine.py with calls to `self._display` (a DisplayManager instance). Add `display: DisplayManager | None = None` parameter to `__init__()`, store as `self._display`, remove `import click`. Replace each click.echo with the appropriate DisplayManager method (phase_transition, phase_aborted, phase_paused, agent_response, agent_error, experiment_round, checkpoint_saved, token_summary, etc.).

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Replaced all 40+ click.echo calls with DisplayManager method calls, added display parameter to __init__, removed click import
- `HISTORY.md` — This prompt logged

## 2026-02-16

### Prompt 30 — Fix Rich UI final summary disappearing

> It works. One issue is that at the end of the execution the rich visualization disappears, and no information is provided to the user. There should be a static, final summary of the important information provided to the user, including where to find the paper.

**Key decisions:**
- Final summary panel is now printed **after** the Live display is torn down in `stop()`, so it persists on screen
- `token_summary()` in Rich mode saves data for later rather than printing mid-Live (where it would be overwritten)
- `DisplayState` extended with `thread_id`, `paper_id`, `paper_path`, and `outcome` fields
- `build_final_summary()` now includes outcome status, thread ID, paper file path, token usage, elapsed time, and stats
- Panel border color reflects outcome (green for success, red for failure)
- Paper path is passed from `WritingHandler.save_paper_file()` through to the display

**Artifacts modified:**
- `src/paradigm/display/manager.py` — Added state fields, saved token summary, print final panel in stop()
- `src/paradigm/display/components.py` — Extended build_final_summary() with outcome, thread, paper path
- `src/paradigm/orchestrator/writing.py` — Pass paper_path to display.paper_saved()
- `HISTORY.md` — This prompt logged

## 2026-02-16

### Prompt 40 — Adjust Token Budgets and Max Tokens

> Let's have a look at paradigm configuration file
> Are these values for max_tokens and token_budget reasonable?
> Let's adjust this. Let's increase max_tokens: 16384 for writers and 8192 as default. Let's raise token_budget_per_agent: 300,000 for heavy-use roles

**Key decisions:**
- Global `max_tokens` raised from 4096 → 8192
- Writer role gets `max_tokens: 16384` (papers need more output room)
- Heavy-use roles (theorist, experimentalist, analyst, synthesizer, writer) get `token_budget_per_agent: 300,000` (up from 100K global default)
- `AgentOverrideConfig` extended to support per-role `max_tokens` and `token_budget_per_agent`

**Artifacts modified:**
- `configs/default.yaml` — Updated token values and per-role overrides
- `src/paradigm/config.py` — Extended AgentOverrideConfig, updated default max_tokens
- `src/paradigm/agents/factory.py` — Resolve per-role max_tokens from overrides
- `src/paradigm/agents/base.py` — Updated default max_tokens parameter
- `tests/test_config.py` — Updated assertion for new default
- `HISTORY.md` — This prompt logged

### Prompt 41 — Fix Phase Display for Seeding, Internal, Submitted, Peer-Review, Published

> In display (where the rich visualization is implemented) we need to make sure that 'seeding' is shown at the beginning as active and then marked as executed (green) once done. Currently it doesn't show. Same for internal, submitted, peer-review and published (if it gets there)

**Key decisions:**
- Add `phase_transition("SEEDING")` call before seeding phase runs
- Add `phase_transition("PUBLISHED")` / `phase_transition("REJECTED")` in engine.py terminal states
- Update `paper_published()` / `paper_rejected()` to move current phase to completed

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — Added phase_transition calls for SEEDING, PUBLISHED, REJECTED
- `src/paradigm/display/manager.py` — Updated paper_published/paper_rejected to update phase state
- `HISTORY.md` — This prompt logged

### Prompt 31 — LaTeX math notation in paper output

> Ensure Paradigm's paper output uses LaTeX math notation instead of Unicode characters. Update writer and editor agent system prompts to require LaTeX math mode. Add a post-processing safety net that converts remaining Unicode math characters to LaTeX equivalents, being careful not to double-wrap characters already inside $...$ blocks.

**Key decisions:**
- Writer and editor system prompts updated with explicit LaTeX math rules
- Post-processing regex pass added after final paper markdown is assembled
- Unicode-to-LaTeX mapping covers Greek letters, sub/superscripts, math operators, astronomy symbols, script letters
- Replacement logic splits on $ delimiters to avoid double-wrapping

**Artifacts modified:**
- Writer agent system prompt
- Editor agent system prompt  
- Post-processing step in writing pipeline
- HISTORY.md — This prompt logged

### Prompt 32 — Agent Messages Panel in Rich Live Display

> Implement the following plan: Add a third panel to the Rich live display showing real-time agent output (role, model, and first ~500 chars of response). Expand DisplayState with agent_messages, update DisplayManager.agent_response() signature, create build_agent_messages_panel() component, change layout to 3-column, and forward role/model/content from engine.py.

**Key decisions:**
- agent_messages capped at 8 entries in DisplayState
- 3-column layout with ratios agents=1, messages=2, events=2
- New kwargs (role, model, content) are optional to preserve PlainTextFallback compatibility

**Artifacts modified:**
- `src/paradigm/display/manager.py` — agent_messages field + add_agent_message() + expand agent_response()
- `src/paradigm/display/components.py` — Add build_agent_messages_panel()
- `src/paradigm/display/layout.py` — Import + add messages panel as third column
- `src/paradigm/orchestrator/engine.py` — Pass role/model/content to agent_response() calls
- `tests/test_display.py` — Tests for agent_messages tracking + new panel
- `HISTORY.md` — This prompt logged

### Prompt 33 — Update Documentation to Reflect Recent Changes

> Implement the following plan: Update Documentation to Reflect Recent Changes. The project has accumulated many features over the past ~10 commits that aren't reflected in the documentation. Bring all docs up to date: MANUAL.md (add sections for Rich terminal UI, citation grounding/Perplexity, seed discovery, novelty checking, memory/reflection, experiment retry/vacuous detection, LaTeX math enforcement), ROADMAP.md (mark Phase 4 complete, update Phase 6, trim Future Phases), README.md (add display/ module, update test count), ARCHITECTURE.md (add seed discovery + citation grounding to data flow), CLAUDE.md (add display/ to project structure).

**Key decisions:**
- Add 4 new sections to MANUAL.md (sections 16-19)
- Update existing MANUAL.md sections 5, 10, and ToC
- Mark Phase 4 Writing as complete in ROADMAP.md
- Update test count from 477 to current count
- Remove "Multi-model support" from Future Phases (already implemented)

**Artifacts modified:**
- `docs/MANUAL.md` — Add sections 16-19, update sections 5/10/ToC
- `ROADMAP.md` — Mark Phase 4 complete, update Phase 6, trim Future Phases
- `README.md` — Add display/ to structure, update test count
- `ARCHITECTURE.md` — Add seed discovery + citation grounding to data flow
- `CLAUDE.md` — Add display/ to project structure
- `HISTORY.md` — This prompt logged

### Prompt 34 — Domain Profiles Design (Extending Beyond Academic Research)

> Let's discuss the possibility of extending paradigm to non-academic research. Let's say someone wanted to write a report about a specific phenomena, or for example a financial report on a company. How would you go about tailoring the current setup? [...] Let's think about a concrete design for the source provider abstraction. [...] Let's add this plan as an .md inside ./planning/

**Key decisions:**
- Domain profile abstraction instead of forking (70% of code is generic)
- SourceProvider ABC with unified SourceResult model
- Configurable DocumentTemplate replacing hardcoded PaperSection enum
- Domain-specific role prompts, review criteria, and postprocessors bundled as profiles
- `domain: science | research | financial` config key to switch modes

**Artifacts produced:**
- `.planning/DOMAIN-PROFILES.md` — Full design document for domain profiles system
- `HISTORY.md` — This prompt logged

### Prompt 35 — Add Conversation Transcript and Working Code to Paper Folders

> Implement the following plan: Add Conversation Transcript and Working Code to Paper Folders
>
> Paper folders (`data/papers/<paper-id>/`) currently contain the paper markdown, figures, `literature_searches.md`, and `reviews.md`. For transparency and reproducibility, each paper folder should be a self-contained research artifact that also includes a full conversation transcript and the working experiment code that produced the results.
>
> Changes: (1) Add `_save_transcript(paper_id)` method to engine.py that reads all events for the thread and renders organized markdown by phase, (2) Add `successful_code` field to `ExperimentationResult` and track working code in retry loop, (3) Add `_save_experiment_code(paper_id)` to write experiments/ directory with working code files, (4) Wire into `_save_auxiliary_files()`, (5) Update docs/MANUAL.md section 11.

**Key decisions:**
- Transcript organized by phase with headers, agent messages shown with timestamps
- Only non-vacuous successful experiment code is saved
- Each experiment saved as sanitized `.py` file with `README.md` index

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py` — `_save_transcript()`, `_save_experiment_code()`, `_successful_code` field, wired into `_save_auxiliary_files()`
- `src/paradigm/orchestrator/experimentation.py` — `successful_code` field on `ExperimentationResult`, tracking in retry loop
- `docs/MANUAL.md` — Updated directory layout in section 11
- `HISTORY.md` — This prompt logged

## 2026-02-17

### Prompt — Analyze PLANNING Phase of paper-b219da65e779 Transcript

> Read and analyze the PLANNING phase from the transcript at /Users/mcantiello/astro/paradigm/data/papers/paper-b219da65e779/transcript.md. The file is large (~293K), so focus on the PLANNING section (between the ## PLANNING and ## EXECUTION headers).
>
> For the PLANNING phase, analyze:
> 1. How many rounds of discussion happened? How many agents participated?
> 2. Did the plan become more concrete and actionable across rounds?
> 3. Was there unnecessary repetition of ideas already settled in IDEATION?
> 4. Did agents productively refine the research plan or just restate it?
> 5. Were literature searches in this phase productive or redundant with IDEATION?
> 6. Was the final plan clear enough for the experimentalist to act on?
> 7. What was discussed that could have been skipped?
> 8. What should have been discussed but wasn't?
>
> Quote specific examples of productive vs. wasteful exchanges. Be thorough and critical.

**Key decisions:** Pure analysis task, no code changes.
**Artifacts examined:** `data/papers/paper-b219da65e779/transcript.md` (PLANNING phase)

### Prompt — Analyze IDEATION Phase of paper-b219da65e779 Transcript

> Read and analyze the IDEATION phase from the transcript at /Users/mcantiello/astro/paradigm/data/papers/paper-b219da65e779/transcript.md. The file is large (~293K), so focus on the IDEATION section (between the ## IDEATION and ## PLANNING headers).
>
> For the IDEATION phase, analyze:
> 1. What was the seed prompt / research topic?
> 2. How many rounds of discussion happened? How many agents participated?
> 3. Did agents build on each other's ideas or just repeat themselves?
> 4. Were there genuine disagreements or challenges?
> 5. Did the discussion converge on specific hypotheses by the end?
> 6. Was there redundancy -- agents saying the same thing in different words?
> 7. Were literature searches productive? Did agents find genuinely useful papers?
> 8. What insights emerged vs. what was just generic filler?
>
> Quote specific examples of both productive and wasteful exchanges. Be thorough and critical.

**Key decisions:** Pure analysis task, no code changes.
**Artifacts examined:** `data/papers/paper-b219da65e779/transcript.md` (IDEATION phase, lines 17-1471)

### Prompt — Analyze WRITING, INTERNAL_REVIEW, and Subsequent Phases

> Read and analyze the WRITING, INTERNAL_REVIEW, and subsequent phases from the transcript at /Users/mcantiello/astro/paradigm/data/papers/paper-b219da65e779/transcript.md. Focus on everything after ## WRITING.
>
> Also read:
> - The reviews file: /Users/mcantiello/astro/paradigm/data/papers/paper-b219da65e779/reviews.md
> - The first 100 lines of the paper: /Users/mcantiello/astro/paradigm/data/papers/paper-b219da65e779/paper-b219da65e779.md (just first 100 lines to understand the topic)
>
> For these phases, analyze:
> 1. WRITING: Did the paper incorporate the experimental results well? Was the writing phase productive?
> 2. Did section drafts reflect the discussion from IDEATION/PLANNING or were they disconnected?
> 3. INTERNAL_REVIEW: What feedback did the editor give? Was it substantive or superficial?
> 4. Did the revision improve the paper materially?
> 5. PEER_REVIEW: What did reviewers say? Were their critiques valid?
> 6. Was there a gap between what the experiments showed and what the paper claims?
> 7. What's the overall quality of the pipeline output?
> 8. What's the biggest disconnect between phases?

**Key decisions:** Pure analysis task, no code changes.
**Artifacts examined:** `data/papers/paper-b219da65e779/transcript.md` (WRITING through PEER_REVIEW), `reviews.md`, `paper-b219da65e779.md`

### Prompt — Post-Execution Discussion Phase + Caveats Propagation

> Implement the following plan:
>
> # Plan: Post-Execution Discussion Phase + Caveats Propagation
>
> Transcript analysis of `paper-b219da65e779` revealed that experimental results go directly to the WRITING phase with no team discussion. The experimentalist's warnings (e.g., "this is synthetic data", "PDF extraction failed") are lost, and writing agents treat all results as authoritative. This produces papers that present synthetic placeholder data as if it were real observational results.
>
> Two changes address this:
> 1. **POST_EXECUTION phase** — The research team reconvenes after experiments to interpret results, flag limitations, and agree on what the evidence supports before writing begins.
> 2. **Caveats propagation** — Structured warnings from the execution phase (synthetic data, network errors, high failure rates, vacuous successes) are collected and injected into both the POST_EXECUTION discussion and WRITING prompts.

**Key decisions:** Add POST_EXECUTION phase enum between EXECUTION and WRITING; collect structured caveats during experimentation; propagate caveats into POST_EXECUTION and WRITING prompts; add `enable_post_execution_discussion` config flag.
**Artifacts modified:** `phases.py`, `experimentation.py`, `constants.py`, `engine.py`, `writing.py`, `config.py`, `docs/MANUAL.md`

### Prompt 138 — Premature Convergence Detection

> Implement premature convergence detection for discussion phases (IDEATION, PLANNING, POST_EXECUTION). After each round, use a cheap LLM call to assess whether agents have converged (80%+ overlap in core proposals). If yes, skip remaining rounds. This addresses the problem where all agents independently produce nearly identical proposals in Round 1, and Round 2 has 80%+ overlap with no new substance, wasting ~60-70% of discussion-phase tokens.

**Key decisions:** LLM-based detection (not keyword Jaccard) for semantic understanding; check after every round (cheap ~300 tokens); skip all remaining rounds on convergence (no ceremonial "one more" round); enabled by default with 0.85 confidence threshold; implemented as private method in engine.py (no new module).
**Artifacts modified:** `config.py`, `constants.py`, `engine.py`, `display/fallback.py`, `display/manager.py`, `docs/MANUAL.md`

### Prompt 139 — Fix Skeptic Too Agreeable

> Fix the skeptic agent becoming too passive in rounds 2+. The problem: all agents receive identical phase prompts with consensus-building language ("build on promising hypotheses", "respond to your colleagues"), which overrides the skeptic's adversarial system prompt. Solution: add role-specific later-round reinforcements that inject adversarial instructions for the skeptic after the phase template in rounds 2+. Also sharpen the skeptic's system prompt to remove hedging language.

**Key decisions:** `_ROLE_LATER_ROUND_REINFORCEMENTS` dict in constants.py mapping role names to reinforcement paragraphs; injected in `_build_agent_prompt()` after template formatting for rounds 2+; only skeptic gets an entry (extensible to other roles); skeptic system prompt sharpened to remove "Acknowledge strong evidence while still probing weaknesses" and add "Never agree with the group just to move forward".
**Artifacts modified:** `orchestrator/constants.py`, `orchestrator/engine.py`, `agents/prompts/skeptic.yaml`

### Prompt 140 — Tighter Search Deduplication

> Implement tighter search deduplication. In a real run: 31 keyword searches with heavy overlap, only ~12 unique papers from 28 READ requests. Graph traversal (FOLLOW/CITED_BY) severely underused. Root causes: (1) Jaccard threshold 0.7 too lenient — reworded queries slip through, (2) all agents get identical search instructions so they independently search the same obvious terms, (3) per-agent cap of 2 lets each agent burn multiple keyword searches instead of using graph traversal.
>
> Changes: (1) Lower Jaccard threshold 0.7→0.5, (2) expand stop words with ~20 scientific filler words, (3) lower per-agent keyword cap 2→1, (4) add role-specific search strategy reinforcements (`_ROLE_SEARCH_STRATEGIES`), (5) inject role search strategies in `_build_agent_prompt()` after `_LITERATURE_INSTRUCTION`, (6) add tests.

**Key decisions:** Jaccard 0.5 threshold; scientific filler stop words; per-agent cap 1 forces graph traversal; role-specific search strategies differentiate agent search behavior.
**Artifacts modified:** `orchestrator/constants.py`, `orchestrator/engine.py`, `tests/test_literature_helpers.py`

### Prompt 141 — Deeper Peer Review (Inject Execution Metadata)

> Fix shallow peer review. Both reviewers gave 8-9/10 and missed synthetic data, sample size inflation, and contradictory chi-squared results. Inject execution metadata (sample sizes, data sources, known caveats) into peer review prompts. Require reviewers to verify specific quantitative claims against the data.

**Key decisions:** Add `{execution_metadata}` to peer review template; build metadata from caveats + truncated execution context; add mandatory claim verification checklist to review instructions; inject in `run_peer_review_phase()`.
**Artifacts modified:** `orchestrator/constants.py`, `orchestrator/review.py`, `tests/test_peer_review.py`

### Prompt 142 — Discussion: Sandbox Data Access Options

> Let's talk about the last issue: Sandbox can't access real data. What options do we have to make this more permissive?

**Key decisions:** Discussion only, no code changes.

### Prompt 143 — Implement Data Pre-staging (`[DATA:]`) + Configurable Network Mode

> Implement the following plan: Data Pre-staging (`[DATA:]`) + Configurable Network Mode. Two complementary changes: (1) Pre-staging — Agents can request data URLs during IDEATION/PLANNING via `[DATA: url]`. The orchestrator downloads them outside the sandbox and mounts them before EXECUTION. (2) Configurable network mode — Users can opt into `--network-access` at the CLI, which sets `network_mode="bridge"`, skips network-import safety checks, and adjusts agent prompts.

**Key decisions:** `[DATA:]` uses existing `classify_resource()`/`resolve_resource()` pipeline; budget cap at 3 per round; `--network-access` flag overrides `config.sandbox.network_mode`; `SafetyConfig` gains `network_enabled` field; hardcoded "NO network access" strings replaced with `{network_caveat}` placeholder.
**Artifacts modified:** `literature/prompt_utils.py`, `orchestrator/literature.py`, `orchestrator/constants.py`, `orchestrator/engine.py`, `orchestrator/experimentation.py`, `sandbox/safety.py`, `sandbox/executor.py`, `main.py`, `display/manager.py`, `display/fallback.py`, `tests/test_literature_helpers.py`, `tests/test_sandbox.py`, `tests/test_orchestrator.py`

### Prompt 144 — Update documentation and manual

> Let's update documentation and manual with the appropriate changes

This prompt requests updating docs/MANUAL.md and other documentation files to cover the new `[DATA:]` pre-staging feature and `--network-access` CLI flag.

### Prompt 145 — Update testing mode model assignments + Add `extra_body` support

> In testing mode, we should have theorist and experimentalist use Qwen/Qwen3.5-397B-A17B, rest could be DeepSeek. Also use DeepSeek-V3.1 in thinking mode for the skeptic https://www.together.ai/models
>
> Implement plan: Update `testing_overrides` models and thread `extra_body` parameter through config → factory → agent → provider chain for Together.ai thinking mode support.

**Key decisions:**
- `extra_body: dict[str, Any] | None` added to `AgentOverrideConfig` for provider-specific params
- `get_provider_and_model_for_role()` returns 3-tuple: `(provider, model, extra_body)`
- `extra_body` passed through Agent → LLMProvider.complete()/complete_streaming()
- AnthropicProvider accepts but ignores `extra_body`; OpenAICompatibleProvider passes to SDK
- Skeptic gets `reasoning: {enabled: true}` via extra_body for Together.ai thinking mode

**Artifacts modified:**
- `src/paradigm/config.py` — `extra_body` on AgentOverrideConfig, 3-tuple return
- `src/paradigm/agents/providers.py` — `extra_body` on protocol + both implementations
- `src/paradigm/agents/base.py` — `extra_body` on Agent, passed to provider calls
- `src/paradigm/agents/factory.py` — Unpack 3-tuple, pass `extra_body` to Agent
- `configs/default.yaml` — Updated testing_overrides with new models + thinking mode
- `HISTORY.md` — This prompt logged

### Prompt 146 — Comprehensive Analysis of paper-b94ddf5e98bf Run

> Let's analyze the log and transcript from latest paradigm run (paper-b94ddf5e98bf). In light of the latest changes to the code base, were some of the issues solved? And are there lingering issues we should tackle?

**Analysis scope**: Paper, reviews, literature searches, experiments, event log (238 events), transcript (8,667 lines). Thread: thread-ea4511620a12. Final outcome: `writing_failed` after 5 internal review iterations.

**Key findings**: See detailed analysis below in conversation. Identified 10 systemic issues, categorized by what's fixed vs. what's lingering.

## 2026-02-17

### Prompt 147 — Review Domain Profiles Design

> Look at .planning/DOMAIN-PROFILES.md

Reviewed the domain profiles design document. Summarized the architecture, migration path, and open questions.

### Prompt 148 — Start Domain Profiles Implementation

> I want to start with implementing this. But I think it would be better to create a new branch when we commit. Thoughts?

**Key decisions:**
- Create a `feature/domain-profiles` branch for this refactor
- Keep `main` stable while iterating on the domain abstraction

### Prompt 149 — Implement Domain Profiles Plan (Steps 1-2)

> Implement the following plan: [Domain Profiles Implementation Plan - 8 commits]

Full implementation of domain profiles abstraction: define interfaces, create science domain, wire profile through config/factory/engine/writing/review. 8 commits covering base interfaces, registry, science profile, config wiring, factory wiring, constants migration, template wiring, and cleanup.

### Prompt 150 — Discuss 5 Open Questions from Domain Profiles Design

> You said 5 open questions remain around role mapping, sandbox packages, corpus isolation, skill libraries, and citation grounding across domains. Let's discuss

**Decisions made:**
1. Role mapping — Shared modes, domain-specific role mappings. Add `phase_active_roles` to DomainProfile
2. Sandbox — Add `SandboxProfile` with preamble, available_libraries, docker_image to DomainProfile
3. Corpus isolation — Prefix ChromaDB collection with domain name. Add `corpus_namespace` to DomainProfile
4. Skill libraries — Add `skills_dir` to DomainProfile. Make skill header configurable
5. Citation grounding — Use postprocessor registry with `ReferenceFormatter` ABC

**Priority order:** Sandbox preamble > Corpus isolation > Citation grounding > Skills wiring > Phase active roles

### Prompt 151 — Update Design Doc with Resolved Decisions

> Update the design doc with these decisions

**Action:** Updated `.planning/DOMAIN-PROFILES.md` to replace Open Questions with Resolved Decisions, add Phase 2 plan

## 2026-02-17

### Prompt 152 — Fix ruff CI lint failures

> Some github actions test didn't pass: Run ruff check src/ tests/ — 8 errors (I001 import sorting, F401 unused imports)

**Action:** Ran `ruff check --fix src/ tests/` to auto-fix all 8 errors:
- Fixed import sorting (I001) in `base.py`, `engine.py`, `test_orchestrator.py`
- Removed unused `Path` import (F401) from `test_domain_integration.py` and `test_domain_science.py`
- Removed unused `list_domains` import (F401) from `test_domain_science.py`

### Prompt 153 — Fix ruff format CI failures

> still some linting issues Run ruff format --check src/ tests/ — 8 files would be reformatted

**Action:** Ran `ruff format src/ tests/` to auto-format 8 files: `base.py`, `registry.py`, `review.py`, `engine.py`, `writing.py`, `test_domain_integration.py`, `test_domain_science.py`, `test_factory.py`

## 2026-02-17

### Prompt 154 — Analyze Literature Search Log for paper-8b1c0a378ab0

> Read and analyze the literature search log at:
> /Users/mcantiello/astro/paradigm/data/papers/paper-8b1c0a378ab0/literature_searches.md
>
> This file records all literature searches made during a multi-agent AI research discussion. Analyze:
> 1. Search patterns: How many searches were made? What queries were used? Are they well-targeted or too broad/narrow?
> 2. Temporal distribution: When in the discussion (which phase/round) do most searches happen? Is there a good pattern of early exploration followed by targeted follow-up, or is it random?
> 3. Redundancy: Are there duplicate or near-duplicate searches? Do agents search for things that were already found?
> 4. Reference utilization: Are the papers found actually used in the discussion? Or are searches performed but results ignored?
> 5. Missing searches: Based on the topics discussed, are there obvious searches that should have been done but weren't?
> 6. Follow/cited-by patterns: How are [FOLLOW:] and [CITED_BY:] actions used? Are they chasing relevant citation chains?
>
> Provide a detailed analysis with specific examples.

**Action:** Full analysis of literature search log provided below.

## 2026-02-17

### Prompt — Implement Source Provider Adapter Layer

> Implement the following plan: Source Provider Adapter Layer — Implementation Plan
> Full migration: Refactor Corpus to delegate to SourceProvider instances and return SourceResult instead of ArxivPaper/SemanticPaper. Update format functions and LiteratureHandler to work with SourceResult. Create concrete adapter classes that wrap existing clients.

**Key decisions**: Full migration approach (not dual-mode). 9 implementation steps covering conversion helpers, provider adapters, factory, Corpus refactor, format function updates, LiteratureHandler updates, main.py wiring, exports, and tests.

**Artifacts**: domains/base.py (modified), literature/providers.py (new), literature/provider_factory.py (new), literature/corpus.py (modified), literature/prompt_utils.py (modified), orchestrator/literature.py (modified), main.py (modified), literature/__init__.py (modified), tests/test_source_providers.py (new), tests/test_orchestrator.py (modified), tests/test_corpus.py (modified), tests/test_prompt_utils.py (modified)

**Verification**: All 838 tests pass. Ruff lint and format checks pass. Fixed 4 remaining SemanticPaper → SourceResult mock conversions in test_orchestrator.py (follow/cited_by tests in both TestLiteratureGraphTraversal and TestLiteratureDedup classes).

### Prompt — Analyze transcript 8b1c0a378ab0

> Let's analyze the transcript in 8b1c0a378ab0. It would be good to understand if the current implementation of phases of discussion works, or if it leads to redundant discussions or misses important insights. Are the logs revealing obvious shortcoming of the current approach and/or ways to improve?

**Key decisions**: Research/analysis task — no code changes expected.

### Prompt — Analyze paper and reviews from 8b1c0a378ab0

> Read and analyze these two files from the paper-8b1c0a378ab0 research run:
>
> 1. /Users/mcantiello/astro/paradigm/data/papers/paper-8b1c0a378ab0/paper-8b1c0a378ab0.md (the final paper)
> 2. /Users/mcantiello/astro/paradigm/data/papers/paper-8b1c0a378ab0/reviews.md (peer reviews)
>
> For the paper: What is the topic? What's the overall quality and novelty? Does it feel like a coherent paper or a patchwork of different agents' contributions? Are there gaps, contradictions, or weak sections?
>
> For the reviews: What do reviewers identify as strengths and weaknesses? Are reviewer criticisms fair and substantive, or formulaic? Do the reviews reveal problems with the multi-agent discussion process?

**Key decisions**: Research/analysis task — no code changes expected.

### Prompt — Summarize phase orchestration design

> Read and summarize the phase orchestration design from these files in /Users/mcantiello/astro/paradigm/src/paradigm/:
>
> 1. orchestrator/phases.py - What phases exist, what are the transitions?
> 2. orchestrator/engine.py - How does the engine run phases and rounds? How are agents scheduled? What context do they receive?
> 3. orchestrator/constants.py - What phase-specific configuration exists (active roles per phase, context needs, instructions)?
> 4. orchestrator/literature.py - How are literature actions processed during phases?
> 5. agents/prompts/ - Look at any system prompt templates that show how agents are instructed about phases
>
> I need to understand:
> - What each phase is supposed to accomplish
> - How many rounds each phase gets
> - Which agents are active in each phase
> - What instructions/context agents receive per phase
> - How phase-specific behavior is enforced (or not)

**Key decisions**: Research/analysis task — no code changes expected.

### Prompt 25 — Structural Analysis of Red Noise Research Transcript

> Read and analyze the transcript at data/papers/paper-8b1c0a378ab0/transcript.md. This is a ~2.2MB transcript of an AI multi-agent research discussion. Provide a detailed structural analysis covering: phase progression, redundancy analysis, phase transitions, agent differentiation, literature integration, missed opportunities, and conversation dynamics.

**Key decisions**: Transcript analysis — no code changes expected.

### Prompt 26 — Implement 6 Architectural Fixes from Transcript Analysis

> Let's implement all these fixes

Referring to 6 prioritized architectural recommendations from the transcript analysis:
1. Execution circuit breaker + multi-agent advisory
2. Cross-phase consensus carry-forward
3. Execution-aware writing (prevent confabulation)
4. Search result quality filtering
5. Plan → execution coupling
6. Editor escalation path

**Status**: Plan mode — exploring codebase and writing implementation plan.

### Prompt 31 — Implement 6 Architectural Fixes

> Implement the following plan: [6 Architectural Fixes for Orchestrator — Implementation Plan]

Full implementation of 6 targeted fixes identified from transcript analysis:
- Fix 6: Editor escalation path (explicit rejection)
- Fix 4: Search result quality filtering
- Fix 2: Cross-phase consensus carry-forward
- Fix 3: Execution-aware writing (prevent confabulation)
- Fix 1: Execution circuit breaker + multi-agent advisory
- Fix 5: Plan → execution coupling

**Artifacts modified**: Multiple files across orchestrator, journal, display, config, and tests.

**Implementation completed** (continued session):
- All 6 fixes implemented and verified
- Cross-round circuit breaker added (Fix 1 completion)
- `_extract_planning_actions()` method added to engine.py (Fix 5 completion)
- 30+ new tests added across 4 test files
- 2 existing tests updated for relevance filter compatibility (Fix 4 side-effect)
- All 868 tests passing, ruff clean

### Prompt 32 — Plan Finance Domain

> Let's make a plan for creating a new domain on economy / financial research. Need to decide resource access and repository access, name of agents, what else?

Planning a new "finance" domain for the platform. User decisions via Q&A:
- Domain name: "finance"
- Output format: Research report
- Data sources: SSRN + SEC EDGAR + FRED + Semantic Scholar
- Experiments: Both econometrics + quant finance

**Status**: Plan written and awaiting user approval.

### Prompt 33 — Continue Session (Context Recovery)

> Continue from where we left off (context window continuation).

Finalizing the finance domain plan and presenting for approval.

### Prompt 34 — Implement Finance Domain

> Implement the following plan: Finance Domain Implementation Plan
>
> Add a new "finance" domain to Paradigm for economy/financial research. This follows the same pattern as the existing "science" domain but with finance-specific agent roles, document template, review criteria, research modes, and data source providers. Includes: 8 agent YAML prompts, constants.py, template.py, __init__.py, modifications to base.py/engine.py/paper.py, 3 new source providers (SSRN, SEC EDGAR, FRED), finance.yaml config, Dockerfile.finance, and tests.

**Key decisions:**
- 8 agent roles: economist, quant, strategist, risk_analyst, experimentalist, writer, editor, reviewer
- 5 research modes: directed, explore, empirical, strategy, policy
- Document template: "research_report" with 8 sections (executive_summary through recommendations)
- 5 review criteria: rigor, novelty, relevance, actionability, risk_awareness
- Phase-active roles: ideation/planning/post_execution use economist, quant, strategist, risk_analyst only
- Added `phase_active_roles` field to DomainProfile (base.py) — engine uses domain profile first, falls back to hardcoded constants
- Made peer review scoring dynamic — review prompt and score parsing use domain criteria
- 3 new source providers: SSRN (HTML scraping), SEC EDGAR (EFTS API), FRED (series search API)

**Artifacts created:**
- `src/paradigm/domains/finance/__init__.py` — Domain registration
- `src/paradigm/domains/finance/constants.py` — Team roles, search strategies, reinforcements
- `src/paradigm/domains/finance/template.py` — Research report template + review criteria
- `src/paradigm/domains/finance/prompts/` — 8 YAML agent prompt files
- `configs/finance.yaml` — Finance domain config
- `docker/Dockerfile.finance` — Finance sandbox with econometrics/quant packages
- `tests/test_finance_domain.py` — 14 domain tests
- `tests/test_finance_providers.py` — 16 provider tests

**Artifacts modified:**
- `src/paradigm/domains/base.py` — Added `phase_active_roles` field to DomainProfile
- `src/paradigm/orchestrator/engine.py` — Added `_get_phase_active_roles()` helper, replaced 5 direct references
- `src/paradigm/orchestrator/debate.py` — Use engine's `_get_phase_active_roles()` instead of direct constant
- `src/paradigm/orchestrator/review.py` — Dynamic score format, domain-aware `parse_peer_review` call
- `src/paradigm/journal/review.py` — Added optional `categories` param to `parse_peer_review`
- `src/paradigm/literature/providers.py` — Added SSRNSourceProvider, SECEdgarSourceProvider, FREDSourceProvider
- `src/paradigm/literature/provider_factory.py` — Registered 3 new providers

**Verification:** 898 tests passing (868 existing + 30 new), ruff clean.

### Prompt 35 — Domain Documentation

> Can we add a document where we describe the different domain implementations? docs/DOMAINS.md And also add some basic information about the existence of domains (and how to switch) in docs/MANUAL.md

**Artifacts created:**
- `docs/DOMAINS.md` — Detailed reference for all domain implementations

**Artifacts modified:**
- `docs/MANUAL.md` — Added domains section with switching instructions

### Prompt 36 — Analyze Discussion Phase Effectiveness in paper-031da0db1190

> Let's analyze the logs of paper-031da0db1190. It would be good to understand if the current implementation of phases of discussion works, or if it leads to redundant discussions or misses important insights. Are the logs revealing obvious shortcoming of the current approach and/or ways to improve?

**Key decisions**: Research/analysis task — no code changes expected.

### Prompt 37 — Analyze Paper and Reviews for paper-031da0db1190

> Read and analyze these two files from a Paradigm AI multi-agent research run:
> 1. paper-031da0db1190.md (the final paper)
> 2. reviews.md (peer reviews)
>
> For the paper: What is the topic? What's the overall quality and novelty? Does it feel like a coherent paper or a patchwork? Are there gaps, contradictions, or weak sections? Are caveats and limitations well-handled? Are figures referenced? Do they seem legitimate?
>
> For the reviews: What do reviewers identify as strengths and weaknesses? Are reviewer criticisms fair and substantive, or formulaic? Do the reviews reveal problems with the multi-agent discussion process? Do reviewers catch fabricated data or unsupported claims?

**Key decisions**: Analysis task — no code changes expected.

### Prompt 38 — Analyze IDEATION Phase Effectiveness in paper-031da0db1190 Transcript

> Read the first ~4000 lines of the transcript.md for paper-031da0db1190. Focus on the IDEATION phase. Analyze: phase identification (start/end, rounds), agent differentiation, redundancy within/across rounds, quality of ideas, anti-repetition effectiveness, convergence, and literature integration. Return detailed analysis with specific quoted examples.

**Key decisions**: Analysis task — no code changes expected.

### Prompt 39 — Analyze PLANNING Phase Effectiveness in paper-031da0db1190 Transcript

> Read /Users/mcantiello/astro/paradigm/data/papers/paper-031da0db1190/transcript.md from approximately lines 4000-8000 (adjust based on phase headers you find). Look for the PLANNING phase.
>
> The transcript has phase headers like "## Phase: PLANNING" or similar markers. Analyze:
>
> 1. **Phase identification**: Where does PLANNING start and end? How many rounds?
> 2. **Connection to IDEATION**: Does the plan build on what was discussed in ideation, or does it seem disconnected?
> 3. **Specificity**: Are the planned experiments specific enough to be implemented? Or vague?
> 4. **Agent roles**: Do agents contribute differently to planning? Does the experimentalist propose experiments while the analyst plans analysis?
> 5. **Redundancy across rounds**: Do later planning rounds add new value or repeat?
> 6. **Completeness**: Are there gaps in the plan (missing experiments, unaddressed questions)?
> 7. **Consensus carry-forward**: Is there evidence of consensus summaries being used from ideation?
>
> Return a detailed analysis with specific examples.

**Key decisions**: Analysis task — no code changes expected.

### Prompt 40 — Analyze WRITING, INTERNAL_REVIEW, and POST_EXECUTION Phases in paper-031da0db1190 Transcript

> Read the transcript from approximately line 15000 to end. Analyze the WRITING, INTERNAL_REVIEW, and any PEER_REVIEW phases.
>
> Analyze:
> 1. Phase identification: Where does each phase start? How many internal review rounds?
> 2. Caveat propagation: Do the writers acknowledge execution caveats and limitations? Or do they confabulate results that weren't achieved?
> 3. Figure references: Do writers reference figures? Are the figure references accurate?
> 4. Internal review quality: Does the editor catch real issues, or is it formulaic?
> 5. Convergence: Does the editor eventually approve, or does it loop?
> 6. Writing quality: Is the prose coherent? Does it read like one author or a patchwork?
> 7. POST_EXECUTION summary: Is there evidence of the post-execution team assessment being used in writing?
>
> Return a detailed analysis with specific examples.

**Key decisions**: Analysis task — no code changes expected.

### Prompt 41 — Implement 7 Orchestration Pipeline Improvements

> Implement the following plan:
>
> # Plan: 7 Orchestration Pipeline Improvements
>
> Analysis of paper-031da0db1190 revealed systemic issues in multi-agent discussion phases: writers fabricating results for failed experiments, execution retries losing state, numerical inconsistencies across sections, phases ending without synthesized conclusions, empty agent contributions wasting context, review pipeline terminating early, and no literature searches during execution errors.
>
> Implementation order: Fix 2 (incremental retry), Fix 5 (suppress empty contributions), Fix 1 (anti-confabulation fact sheet), Fix 7 (literature search on errors), Fix 6 (multi-round review enforcement), Fix 3 (cross-section number harmonization), Fix 4 (structured convergence artifacts).

**Key decisions**: Implementing all 7 fixes across constants.py, experimentation.py, writing.py, review.py, and engine.py.

**Artifacts modified:**
- `src/paradigm/orchestrator/constants.py` — Updated retry template, anti-confab templates, synthesis closing templates, review enforcement
- `src/paradigm/orchestrator/experimentation.py` — Failed code in retry, enriched metadata, auto-search on errors
- `src/paradigm/orchestrator/writing.py` — Execution fact sheet, numerical discrepancy detection
- `src/paradigm/orchestrator/review.py` — Fact sheet injection, mandatory check failure counting, auto-reject
- `src/paradigm/orchestrator/engine.py` — Empty contribution suppression, synthesis rounds + state + injection

### Prompt 42 — Analyze paper-a39fa8281c11 Transcript for Pipeline Improvement Assessment

> Let's analyze the logs of paper-a39fa8281c11. It would be good to understand if the updates we made have improved the flow of discussion and the outcome. Do we still have redundant discussions? Are we missing important insights? Are the logs revealing obvious shortcomings of the current approach and/or ways to improve?

**Key decisions**: Analysis task — no code changes expected.

### Prompt 43 — Analyze Literature Searches Log for paper-a39fa8281c11

> Read the literature searches log at /Users/mcantiello/astro/paradigm/data/papers/paper-a39fa8281c11/literature_searches.md (224 lines). Analyze: 1) Search diversity, 2) Phase distribution, 3) Result quality, 4) Agent differentiation, 5) Redundancy.

**Key decisions**: Analysis task — no code changes expected.

### Prompt 44 — Deep Analysis of paper-a39fa8281c11 SEEDING/IDEATION/PLANNING Phases

> Read the transcript of paper-a39fa8281c11 at /Users/mcantiello/astro/paradigm/data/papers/paper-a39fa8281c11/transcript.md. The file is ~15,700 lines. Read the first ~3000 lines covering SEEDING, IDEATION, and PLANNING phases (including any synthesis rounds). Analyze: 1. Redundancy, 2. Synthesis rounds, 3. Empty contribution suppression, 4. Phase transitions, 5. Literature search quality, 6. Agent differentiation, 7. Convergence.

**Key decisions**: Deep diagnostic analysis of early pipeline phases — no code changes expected.

### Prompt 45 — Deep Analysis of paper-a39fa8281c11 POST_EXECUTION through PEER_REVIEW

> Read the transcript of paper-a39fa8281c11 at /Users/mcantiello/astro/paradigm/data/papers/paper-a39fa8281c11/transcript.md. Read approximately lines 10000-15736 covering POST_EXECUTION, WRITING, INTERNAL_REVIEW, and any PEER_REVIEW phases. Also read reviews.md and the final paper. Analyze: 1. POST_EXECUTION synthesis, 2. Anti-confabulation (Fix 1), 3. Numerical consistency (Fix 3), 4. Writing quality, 5. Review enforcement (Fix 6), 6. Caveat propagation, 7. Review iterations.

**Key decisions**: Deep diagnostic analysis of late pipeline phases — no code changes expected.

### Prompt 46 — Deep Analysis of paper-a39fa8281c11 EXECUTION Phase (lines 3000-10000)

> Read the transcript of paper-a39fa8281c11 at /Users/mcantiello/astro/paradigm/data/papers/paper-a39fa8281c11/transcript.md. Read approximately lines 3000-10000 which should cover the EXECUTION phase (experiments, retries, results). Analyze: 1. Retry behavior (Fix 2), 2. Experiment success rate, 3. Auto literature search (Fix 7), 4. Code quality, 5. Strategy redirects, 6. Experiment metadata, 7. Planning action items.

**Key decisions**: Deep diagnostic analysis of EXECUTION phase — no code changes expected.

### Prompt 47 — Implement P0 fixes from paper-a39fa8281c11 analysis

> (Continued from previous session) Implement the P0 fixes identified from paper-a39fa8281c11 analysis:
> 1. Internal review "REVISE" doesn't trigger revision loop before submission
> 2. POST_EXECUTION synthesis confabulates — fact sheet not injected into synthesis prompt

**Key decisions**:
- Fix A: `parse_review_feedback()` in `paper.py` had priority bug — "accept" checked before "revise" in section-based parsing. Added regex guard for co-occurrence of "accept" + "revise/revision/revisions" → now classified as "revise".
- Fix B: `_run_synthesis_round()` in `engine.py` now injects execution fact sheet into POST_EXECUTION synthesis prompt so synthesizer is grounded in actual experiment outputs.

**Artifacts modified**: `src/paradigm/journal/paper.py`, `src/paradigm/orchestrator/engine.py`, `tests/test_writing.py`

### Prompt 48 — Analyze paper-8255adb41353 logs for pipeline assessment

> Let's analyze the logs of paper-8255adb41353 (thread-aa4101952c58). It would be good to understand if the updates we made have improved the flow of discussion and the outcome. Do we still have redundant discussions? Are we missing important insights? Are the logs revealing obvious shortcoming of the current approach and/or ways to improve?

**Key decisions**: Analysis task — no code changes expected.

### Prompt 49 — Implement 7 Pipeline Fixes from paper-8255adb41353 Analysis

> Implement the following plan: 7 Pipeline Fixes from paper-8255adb41353 Analysis
> Fix 1: Convergence detection too conservative (threshold 0.85→0.70, two-round lookback, JSON error handling)
> Fix 2: Debate deduplication (resolved_topics tracking, _is_duplicate_challenge)
> Fix 3: Auto-search query construction (replace garbled seed_prompt[:80])
> Fix 4: Refine _DATA_ERROR_PATTERNS (remove pure coding errors)
> Fix 5: Number harmonization in section drafting (_extract_reference_values)
> Fix 6: Synthesis injection location (move from end to checkpoint_context)
> Fix 7: Workspace manifest for experiments

**Key decisions**: Implementing all 7 fixes in priority order per the plan.

**Artifacts modified**: `src/paradigm/config.py`, `src/paradigm/orchestrator/constants.py`, `src/paradigm/orchestrator/engine.py`, `src/paradigm/orchestrator/debate.py`, `src/paradigm/orchestrator/experimentation.py`, `src/paradigm/orchestrator/writing.py`

### Prompt 50 — Analyze paper-ea24bcb33c20 logs for pipeline assessment

> Let's analyze the logs of paper-ea24bcb33c20 (thread-658a131f203f). It would be good to understand if the updates we made have improved the flow of discussion and the outcome. Do we still have redundant discussions? Are we missing important insights? Are the logs revealing obvious shortcoming of the current approach and/or ways to improve?

**Key decisions**: Analysis task — no code changes expected.

### Prompt 51 — Deep analysis of EXECUTION phase in paper-ea24bcb33c20 transcript

> Read and analyze the EXECUTION phase of the research transcript. Focus on: experiment round count, success/failure rate, repeated errors, strategy redirects, auto-search queries, workspace file tracking, network access attempts, MIST model download handling, cascading failures, circuit breaker firing, and overall code quality.

**Key decisions**: Analysis task — no code changes expected.

### Prompt 52 — Deep analysis of IDEATION and PLANNING phases in paper-ea24bcb33c20 transcript

> Read and analyze the IDEATION through PLANNING phases of the research transcript at /Users/mcantiello/astro/paradigm/data/papers/paper-ea24bcb33c20/transcript.md (lines 1-800). Focus on: convergence detection, redundant discussion, anti-repetition rules, debates, round counts, whether PLANNING built on IDEATION synthesis, literature search quality, and agent filler vs substantive contributions.

**Key decisions**: Analysis task — no code changes expected.

### Prompt 53 — Deep analysis of POST_EXECUTION, WRITING, and INTERNAL_REVIEW phases

> Read and analyze the POST_EXECUTION, WRITING, and INTERNAL_REVIEW phases of the research transcript at /Users/mcantiello/astro/paradigm/data/papers/paper-ea24bcb33c20/transcript.md. These phases are likely in the latter half of the file (lines 7000+). Also read the paper itself at /Users/mcantiello/astro/paradigm/data/papers/paper-ea24bcb33c20/paper-ea24bcb33c20.md and the reviews at /Users/mcantiello/astro/paradigm/data/papers/paper-ea24bcb33c20/reviews.md. Focus on: POST_EXECUTION critical evaluation, WRITING fact sheet adherence, numerical inconsistencies, paper quality, internal review accuracy, rejection reasons, synthesis injection effectiveness, and token budget efficiency.

**Key decisions**: Analysis task — no code changes expected.

### Prompt 54 — Investigate literature search/arXiv API failures

> Last run seems to have issues downloading references. Maybe they banned our arXiv API?

**Key decisions**: Investigation task — diagnose why 20/21 literature searches failed or returned irrelevant results in paper-ea24bcb33c20.

### Prompt 55 — Fix literature search failures (3 fixes)

> Implement the plan to fix literature search failures from paper-ea24bcb33c20 analysis.

After testing, chose **coverage + title+abstract at 0.15** over title-only (tested empirically: 35/36 relevant papers pass vs 30/36 with title-only, zero irrelevant leakage in both cases).

**Key decisions**:
- Fix 1: Jaccard → query coverage metric, kept title+abstract matching (not title-only)
- Fix 2: arXiv OR → AND query matching with 6-term cap
- Fix 3: Semantic Scholar retry with exponential backoff on 429

**Artifacts modified**:
- `src/paradigm/orchestrator/constants.py` — `_filter_relevant_papers()`
- `src/paradigm/literature/arxiv.py` — `_build_query()`
- `src/paradigm/literature/semantic_scholar.py` — `_get_json()`

### Prompt 186 — Analyze paper-b436ee48eb27 Logs for Pipeline Improvements

> Let's analyze the logs of paper-b436ee48eb27 (thread-570c3ca5fde8). It would be good to understand if the updates we made have improved the flow of discussion and the outcome. Do we still have redundant discussions? Are we missing important insights? Are the logs revealing obvious shortcomings of the current approach and/or ways to improve?

**Key objective**: Post-mortem analysis of a recent paper run to evaluate pipeline improvements and identify remaining issues.

**Key findings from paper-b436ee48eb27 post-mortem**:
1. ~65% token waste from agent redundancy and execution retries
2. Discussion phases ~80% redundant (parallel monologues)
3. EXECUTION 87% of transcript, achieved 1 of 7 planned experiments
4. Data parsing consumed 85% of experiment effort (44 scripts for a 2-3 script task)
5. Key science missing: wind variability, partial correlations, MIST tracks, key citations
6. MIST track confabulation survived editorial review
7. Skeptic is the highest-value agent by far

**Artifacts produced**: Post-mortem analysis documented in conversation

### Prompt 187 — Implement P0 Fixes from paper-b436ee48eb27 Post-Mortem

> Yes, except 3) (network was available within the container, as we ran with --network-access). So that's another issue and we need to deal with it separately.

**Key clarification**: Docker sandbox had `--network-access`, so VizieR/MIST download failures were due to bad agent strategy, not network restrictions. This is a separate issue.

**Approved fixes (3 of 4 P0 items)**:
1. Sequential differentiation in IDEATION/PLANNING
2. Execution retry limits + environment memory
3. Pre-WRITING scope gate (prevent confabulations)

### Prompt 188 — Implement Three Pipeline Fixes from paper-b436ee48eb27 Post-Mortem

> Implement the following plan: [Three Pipeline Fixes from paper-b436ee48eb27 Post-Mortem]

**Key changes**:
1. **Fix 1 — Sequential Differentiation**: Add `{recent_messages}` to IDEATION, PLANNING, POST_EXECUTION round_1 templates with strong differentiation instructions; add header logic in `_build_agent_prompt()` for round_1 recent messages
2. **Fix 2 — Execution Environment Memory**: Add `_learned_constraints` list to `ExperimentationHandler`; extract constraints from ModuleNotFoundError, file-not-found, and network errors; inject into experiment and retry prompts; add experiment count cap
3. **Fix 3 — Pre-WRITING Scope Gate**: Enhance POST_EXECUTION synthesis with FORBIDDEN claims section; add `_extract_forbidden_claims()`, `_build_forbidden_claims_block()`, `_check_forbidden_claims_violations()` to WritingHandler; inject into section drafting, assembly, and editor review

**Files modified**: `constants.py`, `experimentation.py`, `writing.py`, `engine.py`, `manager.py`, `fallback.py`

### Prompt 189 — Deep Analysis of Execution Round Architecture

> I want to understand better how to improve the execution round. Let's focus on that

**Key objective**: Analyze the current execution phase architecture, identify bottlenecks and failure modes, and discuss improvement strategies.

### Prompt 190 — Implement Experiment Dependency Graph + Multi-Agent Pre-Execution Review

> Implement the following plan: [Feature C: Experiment Dependency Graph + Feature E: Pre-Execution Code Review]

**Key changes:**
- `CodeBlock` dataclass + `_EXPERIMENT_DEPENDS_RE` regex for parsing `# DEPENDS:` directives
- `_topological_sort()` and `_get_downstream_dependents()` for dependency ordering
- Dependency-aware execution loop with cascade skip logic
- `experiment_skipped()` display method
- `# DEPENDS:` instruction added to prompt templates
- Config fields: `enable_pre_execution_review`, `pre_execution_review_role`
- `pre_execution_review` and `fix_after_review` prompt templates
- `_pre_execution_review()` and `_apply_review_fixes()` methods
- Review display methods: `experiment_review_requested/passed/issues`

**Artifacts modified:**
- `src/paradigm/orchestrator/constants.py`
- `src/paradigm/orchestrator/experimentation.py`
- `src/paradigm/config.py`
- `src/paradigm/display/manager.py`
- `src/paradigm/display/fallback.py`
- `tests/test_experimentation.py`

### Prompt 191 — Analyze paper-d18c7e87f628 Logs

> Let's analyze the logs of paper-d18c7e87f628 (thread-c9ca4624a973). It would be good to understand if the updates we made have improved the execution, the flow of discussion and the outcome. Do we still have redundant discussions? Are we missing important insights? Are the logs revealing obvious shortcomings of the current approach and/or ways to improve? One thing to note is that last run was done in --testing mode

**Key objective**: Post-mortem analysis of latest run to assess impact of recent pipeline improvements.

### Prompt 192 — Analyze Paper and Reviews for paper-d18c7e87f628

> Read and analyze these two files from a Paradigm research run (paper-d18c7e87f628):
> 1. The final paper (`paper-d18c7e87f628.md`)
> 2. The peer reviews (`reviews.md`)
>
> Provide a detailed analysis covering: what the paper is about, quality assessment, figure presence, conclusion support, reviewer feedback, acceptance status, weaknesses, and word count.

**Key objective**: Content-level analysis of the paper and its peer review, as opposed to the pipeline log analysis in Prompt 191.

### Prompt 193 — Deep Analysis of SEEDING, IDEATION, and PLANNING Phases from paper-d18c7e87f628

> Read and analyze the SEEDING, IDEATION, and PLANNING phases from the transcript at `/Users/mcantiello/astro/paradigm/data/papers/paper-d18c7e87f628/transcript.md`. These are in the first ~2000-3000 lines.
>
> For each phase, analyze:
> 1. **Redundancy**: Are agents repeating each other's points? How much unique content does each agent contribute?
> 2. **Quality of discussion**: Are there genuine disagreements or is it all agreement? Is the skeptic adding value?
> 3. **Convergence**: Does the planning phase produce concrete, actionable experiment plans?
> 4. **Missing insights**: Are there obvious questions or angles the agents failed to consider?
> 5. **Phase transitions**: Do phases end at the right time or go on too long?
>
> Also note: this run was in --testing mode so models may be smaller/cheaper.
>
> This is a RESEARCH task -- do NOT write any code or edit any files.

**Key objective**: Detailed qualitative analysis of agent collaboration quality in the early pipeline phases.

### Prompt 194 — Analyze Literature Search Log for paper-d18c7e87f628

> Read and analyze the literature search log at `/Users/mcantiello/astro/paradigm/data/papers/paper-d18c7e87f628/literature_searches.md`.
>
> Analyze:
> 1. **Search quality**: Are the search queries well-formed? Do they target the right concepts?
> 2. **Result relevance**: Are the returned papers relevant to the research question?
> 3. **Coverage**: Does the literature search adequately cover the topic?
> 4. **Redundancy**: Are there duplicate or near-duplicate searches?
> 5. **Graph traversal**: Were FOLLOW/CITED_BY actions used effectively?
> 6. **Phase distribution**: Which phases triggered searches? Is the distribution appropriate?
> 7. **Total searches**: How many total searches? Is this appropriate?
>
> This is a RESEARCH task — do NOT write any code or edit any files.

**Key objective**: Assess the quality, coverage, redundancy, and effectiveness of the literature search pipeline for the red noise paper.

---

### Prompt 55 — Analyze EXECUTION Phase from Red Noise Paper Transcript

> Read and analyze the EXECUTION phase from the transcript at `/Users/mcantiello/astro/paradigm/data/papers/paper-d18c7e87f628/transcript.md`. The execution phase typically starts after PLANNING (search for "Phase: EXECUTION" or similar markers). It may span lines ~3000-9000 approximately — search for the right section.
>
> Focus your analysis on:
> 1. **Experiment success/failure rates**: How many experiments succeeded vs failed? What types of failures?
> 2. **Cascade failures**: Were there experiments that failed because they depended on prior failed experiments?
> 3. **Retry effectiveness**: When experiments failed and were retried, did the retries succeed?
> 4. **Experiment quality**: Were the experiments well-designed? Did they produce meaningful results?
> 5. **Redundant experiments**: Were any experiments essentially duplicates of each other?
> 6. **File path issues**: Did experiments try to read files that don't exist?
> 7. **Figure generation**: Were figures produced? Were they meaningful?
> 8. **Dependency patterns**: Could experiments have benefited from explicit `# DEPENDS:` declarations? Identify specific cases.
> 9. **Round structure**: How many rounds? Did the agent effectively iterate?
>
> Also note: this was run in --testing mode. Note whether the new dependency graph feature was actually used (look for `# DEPENDS:` in experiment code or "skipped" messages).
>
> This is a RESEARCH task — do NOT write any code or edit any files.

**Key objective**: Comprehensive analysis of the execution phase of the red noise paper, focusing on experiment success rates, cascade failures, dependency patterns, and whether the dependency graph feature was utilized.

---

## 2026-02-18

### Prompt 195 — Implement Post-Mortem Fixes from paper-d18c7e87f628 Analysis

> (Continuation session) Implement the prioritized fixes identified from the post-mortem analysis:
> 1. Add `workspace = Path('/data/workspace')` to auto-import preamble (84% of failures)
> 2. Synthetic data detection guardrail
> 3. Writing anti-repetition instruction + figure reference check
> 4. POST_EXECUTION redundancy reduction
> 5. Skeptic critique propagation

**Artifacts modified**: `src/paradigm/sandbox/executor.py`, `src/paradigm/orchestrator/constants.py`, `src/paradigm/orchestrator/experimentation.py`

### Prompt 196 — Post-Mortem Analysis of paper-13fd1ece63ac (thread-9795f2b87899)

> Run has finished. Let's look at thread-9795f2b87899 and paper-13fd1ece63ac logs

**Key objective**: Analyze the new run to assess impact of the 4 fixes (workspace preamble, synthetic data guardrail, figure references, POST_EXECUTION anti-redundancy) implemented in Prompt 195.

### Prompt 197 — Post-Mortem Analysis of paper-856ebaabb7dd

> Run just ended. Can you look at the logs?

**Key objective**: Analyze the latest run (paper-856ebaabb7dd) — especially whether the figure pipeline fix (workspace scanning) worked, and overall pipeline quality. Only 4 experiment scripts and no figures/ directory present.

### Prompt 198 — Post-Mortem Analysis of paper-3904517dea66

> Let's analyze the logs of paper-3904517dea66. It would be good to understand if the updates we made have improved the execution, the flow of discussion and the outcome. Do we still have redundant discussions? Are we missing important insights? Are the logs revealing obvious shortcomings of the current approach and/or ways to improve?

**Key objective**: Comprehensive post-mortem of the latest run. 22 figures in figures/ dir (rglob fix worked!), 24K line transcript, 20 experiment scripts. Full assessment of all pipeline improvements.

### Prompt 199 — Implement Execution Sprints (Collaborative Experiment Design + Checkpoint)

> Implement the following plan: [Execution Sprints plan — restructure EXECUTION phase into collaborative sprints where the team participates in experiment design and result assessment]

**Key objective**: Restructure the EXECUTION phase into collaborative sprints with three sub-phases: (1) Design Review — experimentalist proposes plan, team reviews; (2) Code + Execute — existing round loop; (3) Results Checkpoint — all agents assess results, majority "EXPERIMENTS SUFFICIENT" triggers early stop. Feature is off by default (`enable_execution_sprints: false`) for backward compatibility.

**Files modified**: `config.py`, `constants.py`, `fallback.py`, `manager.py`, `experimentation.py`, `default.yaml`, `test_experimentation.py`

### Prompt 200 — Post-Mortem Analysis of paper-dfa2eae4cb3f (with execution sprints, --testing)

> Let's analyze the logs of paper-dfa2eae4cb3f (note I ran with --testing). It would be good to understand if the updates we made have improved the execution and the outcome. Are the logs revealing obvious shortcomings of the current approach and/or ways to improve?

**Key objective**: Analyze first run with execution sprints enabled (using --testing open-weight models). Assess whether sprints improved execution quality, whether design reviews caught issues before code was written, and whether checkpoints added value. Identify remaining shortcomings.

## 2026-02-19

### Prompt 201 — Deep Code Review of paper-dfa2eae4cb3f Experiments

> Read all the experiment scripts in data/papers/paper-dfa2eae4cb3f/experiments/ (there are 10 .py files). Analyze: (1) Code Quality, (2) Dependencies, (3) Scientific Rigor, (4) Failure Points (exp07/exp08 "fix" experiments, exp20 workspace audit), (5) Gaps (missing exp06, exp11-exp19), (6) Figure Generation.

**Key objective**: Comprehensive code review of all 10 experiment scripts to assess quality, dependency chains, scientific merit, failure modes, and figure output.

### Prompt 202 — Deep Transcript Analysis of paper-dfa2eae4cb3f

> Read the transcript at data/papers/paper-dfa2eae4cb3f/transcript.md (~22K lines). Analyze 8 aspects: (1) Sprint Structure, (2) Design Review Quality, (3) Results Checkpoint Value, (4) Experiment Flow, (5) Redundancy, (6) Phase Transitions, (7) Token Usage, (8) Testing Mode quality differences.

**Key objective**: Comprehensive transcript analysis of the full research cycle to evaluate the execution sprint system, agent interactions, experiment success/failure rates, and open-weight vs Anthropic model quality.

### Prompt 203 — Implement All 6 Post-Mortem Fixes (Plan)

> Let's implement the fixes you suggested

**Key objective**: Plan implementation of all 6 improvement suggestions from the paper-dfa2eae4cb3f post-mortem analysis. Entered plan mode, designed detailed implementation plan for all 6 fixes.

### Prompt 204 — Implement All 6 Post-Mortem Fixes (Execute)

> Implement the following plan: 6 Post-Mortem Fixes from paper-dfa2eae4cb3f Analysis

**Key objective**: Execute the detailed plan for all 6 fixes: (1) Schema registry to prevent data schema amnesia, (2) STOP AND PIVOT early stopping, (3) Workspace state in design reviews, (4) Advisory prompt context, (5) Reduce IDEATION/PLANNING redundancy, (6) Writer should not include failed experiments.

**Files modified**: `experimentation.py`, `constants.py`, `engine.py`, `writing.py`, `display/fallback.py`, `display/manager.py`, `tests/test_experimentation.py`, `tests/test_writing.py`

**Artifacts produced**:
- Fix 1: `_peek_json_schema()` helper + JSON schema in workspace manifest
- Fix 2: `SprintStopReason` enum, STOP AND PIVOT detection in checkpoints, `sprint_pivot_stop()` display methods
- Fix 3: `{workspace_manifest}` in design proposal/review templates
- Fix 4: `_ADVISORY_PROMPT_TEMPLATE` with seed_prompt, recent_failures, network_caveat, reviewer_role
- Fix 5: Strengthened `_GENERAL_LATER_ROUND_REINFORCEMENT`, `_build_established_points()` in engine.py
- Fix 6: Partitioned fact sheet (success/failed), `_filter_successful_execution_context()`, filtered context injection
- Tests: 945 passed (75 experimentation, 67 writing, full suite green)

### Prompt 205 — Analyze paper-98e5f2add2a9 Logs (Post-Fix Evaluation)

> Let's analyze the logs of paper-98e5f2add2a9.md (note I ran with --testing). It would be good to understand if the updates we made have improved the execution and the outcome. Are the logs revealing obvious shortcoming of the current approach and/or ways to improve?

**Key objective**: Evaluate whether the 6 post-mortem fixes improved execution quality by analyzing the first run after implementation.

**Analysis completed** (4 parallel subagents):
- Experiment quality: 75% meaningful (up from 36%), zero dict-vs-list errors
- Fix evaluation: Fix 1 (partial — no JSON files), Fix 2 (worked), Fix 3 (worked), Fix 4 (not triggered), Fix 5 (partial), Fix 6 (worked)
- Paper desk-rejected: internal inconsistency, unicode formatting, synthetic data framed as real
- Internal review crashed (API connection error — incomplete chunked read)
- 26/39 code executions succeeded; ALL 13 failures were trivial Python bugs (NameError, syntax, imports)
- Token efficiency: ~25-30% duplicated content (code retries, echoed outputs, redundant summaries)
- New shortcomings identified for next round of fixes (see Prompt 205 analysis below)

### Prompt 206 — Implement 7 Post-Mortem Fixes from paper-98e5f2add2a9

> Implement the following plan: 7 Post-Mortem Fixes from paper-98e5f2add2a9 Analysis
>
> After analysis of the second execution-sprints run (paper-98e5f2add2a9, --testing mode), seven new failure modes were identified:
> 1. Pre-execution AST syntax check (34% code execution failures were trivial Python bugs)
> 2. Internal review retry with exponential backoff (API connection error crashed review)
> 3. Apply Unicode→LaTeX before internal review (sanitize_unicode_math only ran on disk save)
> 4. LaTeX formatting directive in writing templates (agents generate Unicode instead of LaTeX)
> 5. Data origin statement for writers (synthetic data framed as real observations)
> 6. Truncate code in retry prompts (25-30% token waste from full code re-sends)
> 7. Reference quality gate (106 bare-URL references, no validation)

**Key decisions:**
- All 7 fixes are independent and can be implemented in parallel
- AST check runs before Docker container startup (Step 0b)
- Internal review retries 2 times with exponential backoff (1s, 2s)
- Unicode sanitization applied right after paper assembly, before review
- Data origin statement injected into both section drafting and assembly prompts
- Code truncation shows ±10 lines around error, preserves short code (<40 lines)
- Reference quality check warns on >50% bare URLs and >80 total references

**Artifacts modified:**
- `src/paradigm/sandbox/executor.py` — AST syntax pre-check before Docker execution
- `src/paradigm/orchestrator/review.py` — Internal review retry with exponential backoff, reference quality injection
- `src/paradigm/orchestrator/writing.py` — Unicode sanitization before review, data origin statement, reference quality check
- `src/paradigm/orchestrator/constants.py` — LaTeX directives in templates, truncated code label, reference formatting directive
- `src/paradigm/orchestrator/experimentation.py` — `_truncate_code_for_retry()`, error line extraction, truncated code in retry
- `src/paradigm/display/fallback.py` — `review_editor_retry()` display method
- `src/paradigm/display/manager.py` — `review_editor_retry()` display method
- Tests: 945 passed (75 experimentation, 67 writing, full suite green)

### Prompt 207 — Analyze paper-c26c233833a8 Logs (Post-Fix Evaluation #2)

> Let's analyze the logs of paper-c26c233833a8.md (note I ran with --testing). It would be good to understand if the updates we made have improved the execution and the outcome. Are the logs revealing obvious shortcoming of the current approach and/or ways to improve?

**Key objective**: Evaluate whether the 7 post-mortem fixes (Prompt 206) improved execution quality by analyzing the first run after implementation.

### Prompt 208 — Deep Analysis of paper-c26c233833a8

> Read and analyze the paper at /Users/mcantiello/astro/paradigm/data/papers/paper-c26c233833a8/paper-c26c233833a8.md
>
> Evaluate:
> 1. Overall quality: Is this a coherent, well-structured research paper? Rate 1-10.
> 2. Unicode vs LaTeX: Does the paper use proper LaTeX math mode ($...$) or are there still Unicode math symbols?
> 3. Data origin honesty: Does the paper clearly state data is synthetic/simulated?
> 4. Section redundancy: Are the same numbers/findings repeated verbatim across sections?
> 5. Reference quality: How many references? Are they bare URLs or proper citations?
> 6. Figure references: Does the paper reference figures that exist?
> 7. Internal consistency: Do numbers in the abstract match numbers in the body?
> 8. Paper outcome: Was the paper accepted, rejected, or desk-rejected?
>
> Read the reviews.md file as well.

**Key objective**: Detailed quality audit of the paper produced after post-mortem fixes.

---

## 2026-02-19

### Prompt — Literature Search Log Analysis (paper-c26c233833a8)

> Read and analyze the literature search log at /Users/mcantiello/astro/paradigm/data/papers/paper-c26c233833a8/literature_searches.md
>
> Evaluate:
> 1. Total searches: How many literature searches were performed?
> 2. Unique vs duplicate: How many were unique? Were there duplicate or near-duplicate queries?
> 3. Phase distribution: Which phases had the most searches?
> 4. Search quality: Were the search queries specific and relevant, or vague/generic?
> 5. Results yield: How many total papers were found? How many were "new" vs already in corpus?
> 6. Agent distribution: Which agents performed the most searches?
> 7. Wasted searches: Were there searches that returned 0 results or clearly irrelevant results?

**Key objective**: Evaluate efficiency and quality of the literature search pipeline for this paper run.

### Prompt 210 — Post-Fix Effectiveness Analysis (paper-c26c233833a8)

> Analyze the JSONL events log at data/events.jsonl to evaluate the effectiveness of 7 recent fixes in the Paradigm research system. The paper being analyzed is paper-c26c233833a8 (thread-282863bad52c). Look for evidence of: Fix 1 (AST syntax pre-check), Fix 2 (internal review retry), Fix 3 (unicode sanitization), Fix 5 (data origin), Fix 6 (code truncation), Fix 7 (reference quality). Also provide total token usage, phase-by-phase breakdown, API calls, and error events.

**Key objective**: Determine whether the 7 post-mortem fixes from Prompt 206 are demonstrably effective in this first post-fix run.

### Prompt 211 — Analyze paper-bfc2caed84a9 Logs (Post-Fix Evaluation #3)

> Let's analyze the logs of paper-bfc2caed84a9.md (note I ran with --testing). It would be good to understand if the updates we made have improved the execution and the outcome. Are the logs revealing obvious shortcoming of the current approach and/or ways to improve?

**Key objective**: Third post-fix evaluation to assess consistency of improvements and identify remaining failure patterns.

### Prompt 212 — Deep Transcript Analysis of paper-bfc2caed84a9 Execution Phase

> Analyze the transcript of a Paradigm research cycle run at /Users/mcantiello/astro/paradigm/data/papers/paper-bfc2caed84a9/transcript.md. This is a large file (~1.3MB). Focus specifically on the EXECUTION phase experiments. Evaluate: success/failure rate, failure categories, AST pre-check (Fix 1), retry effectiveness, code truncation (Fix 6), sprint design review, internal review (Fix 2), cascading dependency failures, token waste, timeout issues. Also check the experiments directory and count figures produced.

**Key objective**: Deep dive into transcript to evaluate post-fix effectiveness with specific evidence from the execution phase.

### Prompt 213 — Detailed Paper Quality Evaluation (paper-bfc2caed84a9)

> Read and analyze the paper at data/papers/paper-bfc2caed84a9/paper-bfc2caed84a9.md. Also read the reviews at data/papers/paper-bfc2caed84a9/reviews.md. Also list the figures directory. Evaluate: (1) overall quality, (2) Unicode vs LaTeX, (3) data origin honesty, (4) section redundancy, (5) reference quality, (6) figure references, (7) internal consistency, (8) paper outcome, (9) revision artifacts, (10) results in methods.

**Key objective**: Comprehensive 10-point quality audit of the final paper output to assess scientific writing quality, formatting compliance, and content integrity.

### Prompt 214 — JSONL Events Log Analysis for paper-bfc2caed84a9

> Analyze the JSONL events log at /Users/mcantiello/astro/paradigm/data/events.jsonl to evaluate the latest Paradigm run that produced paper-bfc2caed84a9. Find the thread ID, filter to that thread, and provide: (1) Thread ID, (2) Total token usage, (3) Total elapsed time, (4) Number of API calls, (5) Number of code executions and success/failure breakdown, (6) Phase durations, (7) Error events, (8) Fix effectiveness evidence for AST pre-check, review retry, synthetic data awareness, reference quality, (9) Anomalies.

**Key objective**: Quantitative post-mortem analysis of the events log to evaluate run efficiency, error patterns, and fix effectiveness with specific numbers.

### Prompt 215 — Literature Search Log Analysis for paper-bfc2caed84a9

> Read and analyze the literature search log at /Users/mcantiello/astro/paradigm/data/papers/paper-bfc2caed84a9/literature_searches.md. Evaluate: (1) Total searches, (2) Unique vs duplicate queries, (3) Phase distribution, (4) Search quality, (5) Results yield and new vs already-in-corpus, (6) Agent distribution, (7) Wasted searches, (8) Off-topic contamination.

**Key objective**: Quantitative evaluation of literature search efficiency, redundancy, and quality.

### Prompt 216 — Post-Mortem Analysis of paper-cdddc9232c19

> Let's analyze the logs of paper-cdddc9232c19.md. It would be good to understand if the updates we made have improved the execution and the outcome. Are the logs revealing obvious shortcoming of the current approach and/or ways to improve?

**Key objective**: Comprehensive post-mortem of the fourth run after implementing 7 fixes. Evaluate fix effectiveness, paper quality, experiment success rate, and identify remaining failure modes.

### Prompt 218 — Implement 7 Post-Mortem Fixes from paper-cdddc9232c19

> Implement the following plan:
> 
> # Plan: 7 Post-Mortem Fixes from paper-cdddc9232c19 Analysis
> 
> Post-mortem analysis of paper-cdddc9232c19 ("Entropy, Prediction, and the Physics of Musical Experience") — the fourth run after implementing 13 prior fixes. Key fixes: 1) Schema contract for experiments (CSV peeking), 2) Writing assembly timeout handling, 3) Figure existence validation, 4) Search topic-relevance boosting, 5) Citation grounding fallback, 6) Thread ID on all API events, 7) Convergence log clarification.

**Key decisions**: Implementing 7 targeted fixes to address schema mismatches, writing timeouts, phantom figures, astrophysics search bias, silent citation failures, missing thread_id on events, and confusing convergence logs.

**Artifacts modified**: experimentation.py, constants.py, writing.py, review.py, literature.py, bibliography.py, events.py, engine.py, fallback.py, manager.py, test_experimentation.py, test_writing.py

## 2026-02-25

### Prompt: Multi-Source Academic Literature Search Integration

> Implement the following plan: Multi-Source Academic Literature Search Integration
> 
> Add PubMed, bioRxiv/medRxiv, NASA ADS, and Google Scholar as additional literature sources,
> plus enhanced citation chain traversal. Implement as native Python wrappers fitting the existing
> SourceProvider architecture. Also enhance SemanticScholarClient with new methods, create a
> unified LiteratureSearchService, and add citation chain BFS traversal.

**Key decisions**: Native Python wrappers (no MCP), follow existing SourceProvider pattern
**Artifacts**: 5 new files created, 7 files modified, 5 test files created

## Prompt 5 — Domain-Aware Source Selection Fix (2026-02-25)

> Given the recent upgrade for literature search using mcp engines, can we fix 1?

(Continued from context recovery - implementing recommendation #1 from paper-489a566e6225 analysis: Domain-Aware Source Selection to route queries to appropriate literature providers based on research topic.)

## Prompt 6 — Fresh-Start Internal Corpus Option (2026-02-25)

> Let's also deal with Internal Corpus domain isolation. Let's just add a Fresh-start option: Allow a run to start with empty internal corpus

**Context:** Addressing concerns about domain isolation in the internal corpus. The solution is to add a simple fresh-start option that allows a research run to begin with an empty internal corpus, ensuring domain-specific papers don't pollute unrelated research threads.

**Key decisions:**
- Add `--fresh-corpus` CLI flag to `paradigm run` command
- When enabled, initialize a new isolated corpus for the thread
- Default behavior (no flag) maintains existing corpus behavior
- Simple and low-risk implementation approach

**Artifacts to create/modify:**
- Update `src/paradigm/main.py` — Add CLI flag
- Update `src/paradigm/config.py` — Add config option
- Update `src/paradigm/storage/corpus.py` — Add fresh-start logic
- Update tests if needed


## 2026-02-25

### Prompt — Implement Literature Review Mode (`--mode review`)

> Implement the following plan: [Full plan for Literature Review Mode]

- Adds `--mode review` for pure literature survey work
- Review-specific prompts, team composition, document template
- No engine flow changes needed (execution already skips without experimentalist)
- 9 files modified, 1 new test file

### Prompt — Update Manual and Description for Review Mode

> Can we update the manual and overall description of paradigm given the latest changes?

- Update README.md, docs/MANUAL.md, SPEC.md, docs/DOMAINS.md with review mode
- Ensure pyproject.toml description reflects latest capabilities

### Prompt — Provider-Targeted Search (`[SEARCH:provider: query]`)

> Implement the following plan:
>
> # Plan: Provider-Targeted Search (`[SEARCH:provider: query]`)
>
> Add an optional provider hint to agent search markers: `[SEARCH:pubmed: query]`.
> When specified, only that provider is queried. When omitted, existing domain-aware
> routing applies unchanged.
>
> Changes: prompt_utils.py (regex + return type), orchestrator/literature.py (unpack
> provider), corpus.py (provider param), constants.py (instruction update), tests.

- Updated regex to capture optional provider prefix
- Changed `parse_search_requests()` return type to `list[tuple[str, str | None]]`
- Added `provider` parameter to `corpus.search()` and `_search_via_providers()`
- Updated `LITERATURE_INSTRUCTION` with provider-targeted syntax
- Added `tests/test_targeted_search.py`

### Prompt — Document --fresh-corpus in Manual

> is this option documented in the manual? ... yes, add it

- Added `--fresh-corpus` to CLI reference table in MANUAL.md
- Added usage example in examples section
- Added "Fresh corpus mode" note in Multi-Cycle Research section

### Prompt — Document --fresh-corpus in README

> also update the readme

- Added `--fresh-corpus` usage example to Quick Start section in README.md
- Synced .github/README.md

---

## 2026-02-26

### Prompt — Implement Conceptual Figure Generation for Non-Experimental Papers

> Implement the following plan:
>
> # Plan: Conceptual Figure Generation for Non-Experimental Papers
>
> When Paradigm runs in `--mode review` (or any mode where EXECUTION is skipped), no figures are generated. The writer agent is told "NO FIGURES AVAILABLE" but sometimes still references figures — and for review/synthesis papers, conceptual diagrams would genuinely improve the paper. The editor refuses papers with broken figure references, creating a deadlock.
>
> Solution: After paper assembly, generate matplotlib-based conceptual figures for any `Figure N` references in the text using the existing sandbox infrastructure.
>
> Changes: config.py (new fields), constants.py (prompt template + mode overrides), writing.py (core methods + wiring), display manager/fallback (progress methods), tests.

**Key decisions:**
- Post-assembly step within WRITING phase, not a new phase
- Uses writer agent for code generation
- One LLM call per figure, strip orphan refs on total failure
- Default on, configurable off

**Artifacts produced or modified:**
- `src/paradigm/config.py`
- `src/paradigm/orchestrator/constants.py`
- `src/paradigm/orchestrator/writing.py`
- `src/paradigm/display/manager.py`
- `src/paradigm/display/fallback.py`
- `tests/test_conceptual_figures.py` (new)

### Prompt 219 — Publish Working Code Alongside Papers for Reproducibility

> Implement the following plan:
>
> # Plan: Publish Working Code Alongside Papers for Reproducibility
>
> Rename `experiments/` → `code/` in paper output, save conceptual figure scripts
> alongside experiment code, add display method for code saving feedback.

**Key decisions:**
- Rename `experiments/` → `code/` directory in paper artifacts
- Conceptual figure code flows through existing `_successful_code` pipeline
- Add `code_saved()` display method for UI feedback

**Artifacts modified:**
- `src/paradigm/orchestrator/engine.py`
- `src/paradigm/orchestrator/writing.py`
- `src/paradigm/display/manager.py`
- `src/paradigm/display/fallback.py`
- `tests/test_conceptual_figures.py`

## 2026-02-26

### Prompt — Extract ResearchState from OrchestrationEngine

> Implement the following plan:
> 
> # Plan: Extract `ResearchState` from `OrchestrationEngine`
> 
> Create a `ResearchState` dataclass holding all per-cycle mutable state. Engine keeps infrastructure and handlers on itself, exposes state via `self.state`. Handlers access `self._engine.state.xxx` instead of `self._engine._xxx`. Pure mechanical refactor — no logic changes.
> 
> Total: 1 new file, 17 modified files, ~590 mechanical attribute replacements.

**Artifacts:** `src/paradigm/orchestrator/state.py` (new), modifications to engine.py, 7 handler files, 9 test files

## 2026-02-26

### Prompt: Replace engine._xxx with engine.state.xxx in test_experimentation.py

> In the file tests/test_experimentation.py, replace all occurrences of `engine._xxx` to `engine.state.xxx` for specific state variables only (thread_id, seed_prompt, agents, messages, checkpoint (not _checkpoint_mgr), execution_context, execution_caveats, execution_figures, successful_code, experiment_metadata, planning_action_items, resolved_resources, code_context, data_context). Use sed with word-boundary-aware patterns.

- **Artifacts modified**: `tests/test_experimentation.py`

### Prompt — Replace state variable patterns in test_experimentation_handler.py

> In the file tests/test_experimentation_handler.py, replace all occurrences of these state variable patterns:
> - engine._thread_id -> engine.state.thread_id
> - engine._seed_prompt -> engine.state.seed_prompt
> - engine._agents -> engine.state.agents
> - engine._resolved_resources -> engine.state.resolved_resources
> - engine._code_context -> engine.state.code_context
> - engine._data_context -> engine.state.data_context
> - engine._checkpoint (NOT engine._checkpoint_mgr) -> engine.state.checkpoint
>
> Use sed with word boundary pattern to avoid matching engine._checkpoint_mgr.


### Prompt — Replace state variable patterns in test_debate.py

> In the file tests/test_debate.py, replace all occurrences of engine._agents -> engine.state.agents, engine._thread_id -> engine.state.thread_id, engine._seed_prompt -> engine.state.seed_prompt, engine._messages -> engine.state.messages, engine._checkpoint -> engine.state.checkpoint (NOT engine._checkpoint_mgr), engine._graveyard_context -> engine.state.graveyard_context, engine._code_context -> engine.state.code_context, engine._data_context -> engine.state.data_context, engine._reference_context -> engine.state.reference_context, engine._mode -> engine.state.mode. Use sed with word boundary patterns to avoid matching checkpoint_mgr.

**Artifacts modified:**
- `tests/test_debate.py`

### Prompt 52 — Replace private attributes with state object in 6 test files

> Make these replacements in 6 test files:
> 1. tests/test_orchestrator.py: engine._agents -> engine.state.agents, engine._thread_id -> engine.state.thread_id, engine._seed_prompt -> engine.state.seed_prompt, engine._messages -> engine.state.messages, engine._checkpoint (NOT _checkpoint_mgr) -> engine.state.checkpoint, engine._consensus_summary -> engine.state.consensus_summary, engine._mode -> engine.state.mode, engine._resolved_resources -> engine.state.resolved_resources
> 2. tests/test_writing.py: engine._experiment_metadata -> engine.state.experiment_metadata, engine._execution_context -> engine.state.execution_context, engine._execution_figures -> engine.state.execution_figures
> 3. tests/test_peer_review.py: engine._execution_caveats -> engine.state.execution_caveats, engine._execution_context -> engine.state.execution_context
> 4. tests/test_conceptual_figures.py: engine._execution_figures -> engine.state.execution_figures, engine._thread_id -> engine.state.thread_id, engine._successful_code -> engine.state.successful_code
> 5. tests/test_memory_handler.py: engine._thread_id -> engine.state.thread_id, engine._seed_prompt -> engine.state.seed_prompt, engine._agents -> engine.state.agents
> 6. tests/test_citation_handler.py: engine._thread_id -> engine.state.thread_id

**Artifacts modified:**
- `tests/test_orchestrator.py`
- `tests/test_writing.py`
- `tests/test_peer_review.py`
- `tests/test_conceptual_figures.py`
- `tests/test_memory_handler.py`
- `tests/test_citation_handler.py`

---

## 2026-03-03

### Prompt — Knowledge Architecture Upgrade: World Model, Hypothesis Tournaments, and Evidence Graphs

> Three-stage upgrade to Paradigm's knowledge infrastructure:
> - **Stage 1:** Structured World Model — persistent, queryable knowledge store with entities, relationships, evidence, hypotheses, open questions, and research goals. Agents write to and read from it throughout a research cycle.
> - **Stage 2:** Knowledge Graph for Conflicting Evidence — epistemic structure with conflict edges, assumption tracking, evidence weighting, provenance chains. Turns flat evidence store into proper knowledge graph.
> - **Stage 3:** Evolutionary Hypothesis Selection — population-based hypothesis generation with Elo-rated tournaments, evolutionary refinement, and selection of winners for testing.
>
> Inspired by Kosmos (structured world model), Google AI Co-Scientist (tournament-based Elo ranking), and Microsoft Discovery (graph-based knowledge engine).
>
> Each stage builds on the previous. Do not start Stage 2 until Stage 1 is complete and tested. Do not start Stage 3 until Stage 2 is complete and tested.

**Key decisions:** TBD (entering plan mode)

**Artifacts to produce:**
- `src/paradigm/knowledge/__init__.py` (new)
- `src/paradigm/knowledge/world_model.py` (new, Stage 1)
- `src/paradigm/knowledge/evidence_graph.py` (new, Stage 2)
- `src/paradigm/knowledge/conflict_detection.py` (new, Stage 2)
- `src/paradigm/knowledge/hypothesis_tournament.py` (new, Stage 3)
- `src/paradigm/agents/prompts/debate_judge.yaml` (new, Stage 3)
- Modifications to engine.py, phases.py, base.py, database.py, config.py, default.yaml, and agent prompts
- `tests/test_world_model.py`, `tests/test_evidence_graph.py`, `tests/test_hypothesis_tournament.py`

---

## 2026-02-26

### Prompt 53 — Implement Web Frontend Backend (FastAPI) + Frontend Architecture Plan

> Implement the following plan:
>
> # Paradigm Web Frontend — Implementation Plan
>
> Build a FastAPI backend with REST endpoints, WebSocket support, Pydantic v2 models,
> SessionManager service, WebSocketDisplayAdapter (bridging DisplayManager interface to WS),
> and all route handlers. Also write frontend-plan.md for the React/Vite frontend architecture.
>
> Key deliverables:
> 1. Working FastAPI application (backend/api/) with all REST + WS endpoints
> 2. frontend-plan.md — comprehensive frontend architecture document
> 3. Auto-exported OpenAPI spec
> 4. Updated pyproject.toml with [api] extra
> 5. backend/README.md with setup instructions

**Key decisions:**
- Backend lives in `backend/api/` directory, cleanly separated from core
- FastAPI wraps existing Paradigm internals via bridge adapters
- WebSocket protocol uses discriminated unions for type safety
- SessionManager manages async research cycle tasks
- WebSocketDisplayAdapter implements DisplayManager interface for WS broadcasting
- Config shared via FastAPI dependency injection

**Artifacts produced:**
- `backend/api/` — Full API package
- `backend/README.md` — Setup documentation
- `frontend-plan.md` — Frontend architecture plan
- `pyproject.toml` — Updated with [api] extra

---

### Prompt 54 — Update Documentation for Web API

> let's update the manual and readme, and any documentation that is touched by these changes. Maybe add an API document? After that let's commit and push

**Key decisions:**
- Add Web API section to README.md
- Add section 21 (Web API) to MANUAL.md
- Create `docs/API.md` as a dedicated API reference document
- Update INSTALL.md with API dependencies
- Update ROADMAP.md to reflect Web API milestone
- Update project structure and documentation table in README.md

**Artifacts produced/modified:**
- `README.md` — Added Web API section, updated project structure and docs table
- `docs/MANUAL.md` — Added section 21 for Web API
- `docs/API.md` — New comprehensive API reference document
- `INSTALL.md` — Added API dependencies section
- `ROADMAP.md` — Added Web API to Phase 6 tasks

### Prompt 55 — Implement React/TypeScript Frontend

> Implement the following plan:
>
> Paradigm Frontend — full React 18 + TypeScript implementation with Vite 6, Tailwind CSS 4, shadcn/ui, Zustand 5, TanStack Query v5.
> Phases 0-7: Project scaffold, API client + app shell, WebSocket + session store, session cockpit, research cycles + dashboard, paper viewer, agent config, polish.

**Artifacts produced:**
- `frontend/` — Complete React/TypeScript frontend application

## 2026-03-03

### Prompt 56 — Knowledge Architecture Upgrade: World Model, Evidence Graphs, Hypothesis Tournaments

> Implement the following plan:
>
> Knowledge Architecture Upgrade: World Model, Evidence Graphs, Hypothesis Tournaments
>
> Three-stage upgrade adding: (1) structured world model (queryable knowledge store with entities, hypotheses, evidence), (2) evidence graph (conflict tracking, assumption management, provenance chains), and (3) evolutionary hypothesis tournament (population-based selection via Elo-rated debates).

**Key decisions:**
- World model as in-memory dicts with snapshot-based JSON persistence
- Evidence graph wraps world model, adds conflict detection and assumption cascade
- Tournament runs as internal steps within IDEATION phase (no new phases)
- All features behind KnowledgeConfig toggles (world model on by default, others off)
- Handler pattern matches existing ExperimentationHandler, DebateHandler

**Artifacts produced/modified:**
- `src/paradigm/knowledge/__init__.py` — Package init
- `src/paradigm/knowledge/models.py` — Pydantic models
- `src/paradigm/knowledge/world_model.py` — WorldModel class
- `src/paradigm/knowledge/world_model_handler.py` — Handler
- `src/paradigm/knowledge/evidence_graph.py` — EvidenceGraph + ConflictDetector
- `src/paradigm/knowledge/conflict_detection.py` — ConflictDetector
- `src/paradigm/knowledge/hypothesis_tournament.py` — Elo logic
- `src/paradigm/knowledge/tournament_handler.py` — Tournament handler
- `src/paradigm/config.py` — KnowledgeConfig added
- `src/paradigm/storage/database.py` — world_model_snapshots table
- `src/paradigm/orchestrator/state.py` — world_model + evidence_graph fields
- `src/paradigm/orchestrator/constants.py` — context needs + tournament prompts
- `src/paradigm/orchestrator/engine.py` — handler integration
- `src/paradigm/domains/science/prompts/debate_judge.yaml` — New agent role
- `src/paradigm/domains/science/prompts/skeptic.yaml` — Evidence graph awareness
- `src/paradigm/domains/science/prompts/synthesizer.yaml` — Evidence landscape awareness
- `configs/default.yaml` — knowledge section
- `tests/test_world_model.py` — World model tests
- `tests/test_evidence_graph.py` — Evidence graph tests
- `tests/test_hypothesis_tournament.py` — Tournament tests

---

## 2026-03-03

### Prompt 54 — Security Audit for Web Deployment

> Can you make sure that no API keys are publicly exposed, and that there are no security risks for Paradigm when deploying as a web app?

**Scope**: Full security review of the codebase — API key handling, authentication, input validation, WebSocket security, Docker sandbox safety, and general OWASP concerns for web deployment.

## Prompt 54 — Knowledge Architecture UI Integration (2026-03-03)

> Implement the following plan: Knowledge Architecture UI Integration. Full snapshots via WebSocket, tabbed right panel (Events/Knowledge), REST fallback, demo runner updates. 18-step implementation across backend models, display adapter, session manager, engine, tournament handler, routes, demo runner, and full frontend (types, stores, hooks, components, pages, constants, REST client).

**Artifacts**: backend/api/models/messages.py, backend/api/services/session_manager.py, backend/api/services/ws_display.py, src/paradigm/display/manager.py, src/paradigm/knowledge/tournament_handler.py, src/paradigm/orchestrator/engine.py, backend/api/routes/sessions.py, backend/api/services/demo_runner.py, frontend/src/api/ws-types.ts, frontend/src/stores/sessionStore.ts, frontend/src/stores/uiStore.ts, frontend/src/hooks/useResearchSession.ts, frontend/src/lib/constants.ts, frontend/src/components/session/KnowledgePanel.tsx, frontend/src/components/session/RightPanel.tsx, frontend/src/components/session/SessionView.tsx, frontend/src/pages/SessionPage.tsx, frontend/src/api/client.ts

### Prompt 55 — Update ROADMAP.md with Security Recommendations

> Can we add these recommendations to ROADMAP.md? Roadmap likely needs an update as well, given recent development

**Scope**: Refresh ROADMAP.md to reflect what's been built (frontend, knowledge architecture, security hardening) and add security recommendations as a tracked phase.

### Prompt 56 — Fix Stats Bar, Phase Tracker, and Elapsed Time Not Updating in Web UI

> A few issues (see the image of the frontend): time, tokens, searches, papers are not updated. Also the current phase of the research is not shown. Maybe the recent changes have broken that workflow?

**Root cause**: Pre-existing bugs, not caused by knowledge UI changes. (1) Stats never broadcast after update — `agent_response()`, `search_result()`, etc. call `update_session_state()` but never `_broadcast_state()`. (2) Phase names sent UPPERCASE from engine but frontend expects lowercase. (3) `from_phase` never included in `PhaseTransitionMsg`, so `completedPhases` never populated.

**Artifacts**: backend/api/services/ws_display.py

### Prompt 57 — Implement Testing/Production Mode Toggle in Frontend

> Implement the following plan:
>
> # Testing/Production Mode Toggle in Frontend
>
> Add a toggle in the web UI to switch between production (frontier Claude/Gemini models) and testing (together.ai open models) at runtime. Backend: add mode tracking to Config class, new GET/PUT /api/v1/config/mode endpoints. Frontend: REST client functions, TanStack Query hooks, header toggle switch.
>
> Implementation order: config.py → backend route → main.py registration → client.ts → hook → Header.tsx

**Key decisions:**
- Store production overrides backup in Config class-level dict (not Pydantic field)
- Toggle invalidates both config-mode and agents query caches
- Toggle only shown when testing_available is true

**Artifacts modified:**
- `src/paradigm/config.py` — mode tracking + restore method
- `backend/api/routes/config.py` — NEW: GET/PUT mode endpoints
- `backend/api/main.py` — register config router
- `frontend/src/api/client.ts` — config mode API functions
- `frontend/src/hooks/useConfigMode.ts` — NEW: query + mutation hooks
- `frontend/src/components/layout/Header.tsx` — toggle switch

---

### Prompt 58 — Fix Research Cycle Card: Delete + Click-to-Open

> Implement the following plan:
>
> Fix two bugs in the Research Cycles UI: (1) DELETE endpoint only sets status=ABORTED but never removes the cycle from the in-memory `_cycles` dict — fix by adding `del _cycles[cycle_id]`. (2) The cycle card isn't clickable — make the entire card navigate to `/session/{thread_id}` when a thread_id exists, add cursor-pointer/hover styling, stopPropagation on trash button, and remove the separate ExternalLink icon button.

**Artifacts modified:**
- `backend/api/routes/research.py` — actually remove cycle from `_cycles` on DELETE
- `frontend/src/components/research/CycleCard.tsx` — make card clickable, remove ExternalLink button

### Prompt 59 — Fix Stale State Between Cycles + Show Mode Badge

> Implement the following plan:
>
> Fix three issues: (1) Starting a new research cycle doesn't clear old events/messages/knowledge from the previous session — reset all session state in `connect()`. (2) The Testing/Production mode badge no longer appears in the header when config is unavailable — always show mode badge, with "Demo" variant. (3) Return `mode="demo"` from backend config endpoint when config is None.

**Artifacts modified:**
- `frontend/src/stores/sessionStore.ts` — reset all session state in `connect()`
- `frontend/src/components/layout/Header.tsx` — always show mode badge, handle "demo" mode
- `backend/api/routes/config.py` — return `mode="demo"` when config unavailable

### Prompt 60 — Frontend Audit: Fix & Improve (12 issues)

> Implement the following plan:
>
> Comprehensive audit of the frontend revealed functional bugs, dead code, type mismatches with the backend, and code quality issues. This plan addresses 12 issues across 14 files:
> 1. Abort button sends "pause" instead of "abort"
> 2. Paper TOC scroll is broken (no id attrs on headings)
> 3. Wrong height calculation in SessionPage
> 4. WebSocket reconnect backoff has no max delay cap
> 5. Remove dead code (eventLogVisible, EVIDENCE_SOURCE_LABELS, cssVar)
> 6. Fix type mismatches with backend (completed_phases, extra_body, modifications)
> 7. Consolidate duplicate imports in Dashboard
> 8. Add radix to parseInt calls
> 9. Remove redundant type casts in sessionStore
> 10. Fix React.ReactNode without React import
> 11. Add 404 catch-all route
> 12. Batch error handler set() calls in sessionStore

### Prompt 61 — Documentation Update (6 files)

> Implement the documentation update plan: replace frontend/README.md Vite boilerplate with project-specific docs, update backend/README.md with missing endpoints and WS types, update docs/API.md with config mode / knowledge / abort / knowledge_update sections, append Web UI subsection to docs/MANUAL.md section 21, prepend deviation note to frontend-plan.md, and add frontend/README.md to root README.md documentation table.

**Artifacts modified:**
- `frontend/README.md` — full rewrite
- `backend/README.md` — add endpoints, WS types, architecture entries
- `docs/API.md` — add sections + fix existing entries
- `docs/MANUAL.md` — append Web UI subsection
- `frontend-plan.md` — prepend deviation note
- `README.md` — add doc table row

## Prompt 54: Backend Config Loading Without Paradigm Import
Date: 2026-03-03

Understand how to make backend load config without importing from `paradigm` (which requires Python 3.11+, but runtime is 3.10).

Tasks:
1. Read src/paradigm/config.py fully
2. Read backend/api/main.py — _load_paradigm_config function
3. Search for app.state.config usage across backend/api/
4. Check backend/api/routes/agents.py config usage
5. Check backend/api/services/session_manager.py config usage
6. Report which Config attributes/methods are actually used by backend

Goal: Identify minimal config data structure needed for backend independence.

### Prompt 62 — Fix Backend Config Loading on Python 3.10

> Implement the following plan:
>
> Create a lightweight config loader in the backend (`backend/api/config.py`) that reads the YAML config file directly and constructs simple Pydantic models — no import from `paradigm` needed. This mirrors the minimal subset of `Config` that the backend routes actually use. The full `paradigm.Config` object is still needed for `SessionManager._run_cycle()`, but that already works in demo mode when core isn't available.
>
> Changes:
> 1. Create `backend/api/config.py` — lightweight config models + loader
> 2. Update `backend/api/main.py` — use new loader as fallback
> 3. Update `backend/api/routes/agents.py` — switch AgentOverrideConfig import

**Artifacts produced/modified:**
- `backend/api/config.py` — new lightweight config models + loader
- `backend/api/main.py` — fallback to backend config loader
- `backend/api/routes/agents.py` — import from backend config

### Prompt 68 — Implement Dedicated Settings Page

> Implement a dedicated Settings page: backend GET/PUT endpoints for 6 config sections (orchestrator, sandbox, literature, knowledge, memory, citation), frontend Settings page with left tab strip, per-section save/reset, toggle/number/select field components, TanStack Query hooks, sidebar nav item.

**Key decisions:**
- Backend: `GET /api/v1/settings` returns all sections, `PUT /api/v1/settings/{section}` updates one at a time
- Frontend: VS Code / GitHub style left tab strip + scrollable content area
- Per-section Save/Reset buttons with dirty state tracking
- Config compatibility: `hasattr(config, section)` checks for both full and lightweight config

**Artifacts produced:**
- `backend/api/models/settings.py` (NEW)
- `backend/api/routes/settings.py` (NEW)
- `frontend/src/hooks/useSettings.ts` (NEW)
- `frontend/src/components/settings/SettingsField.tsx` (NEW)
- `frontend/src/components/settings/SettingsSection.tsx` (NEW)
- `frontend/src/pages/SettingsPage.tsx` (NEW)

**Artifacts modified:**
- `backend/api/main.py` — Register settings router
- `frontend/src/api/client.ts` — Add settings interfaces + functions
- `frontend/src/App.tsx` — Add settings route
- `frontend/src/components/layout/Sidebar.tsx` — Add settings nav item

---

## 2026-03-03

### Prompt 69 — Literature References Panel & Research Folder Browser

> Implement the following plan:
>
> 1. **Clickable literature count** — StatsBar papers count opens a panel showing actual papers found, with arXiv/PDF links
> 2. **Research folder browser** — Tabbed viewer on the Papers page exposing all artifacts: paper, literature, reviews, transcript, code, figures
> 3. **Visual polish** — Consistent styling, empty states, hover effects on interactive elements
>
> Backend: Add papers_dir to config, artifact models, artifact_parser.py, 6 REST endpoints (artifacts, literature, reviews, transcript, experiments, figures), demo literature/reviews data.
> Frontend: API client interfaces + hooks, LiteraturePanel slide-over, clickable StatsBar, ArtifactTabs with 6 tab types, PapersPage update.

**Artifacts produced:**
- `backend/api/services/artifact_parser.py` (NEW)
- `frontend/src/components/session/LiteraturePanel.tsx` (NEW)
- `frontend/src/components/papers/ArtifactTabs.tsx` (NEW)
- `frontend/src/components/papers/LiteratureTab.tsx` (NEW)
- `frontend/src/components/papers/ReviewsTab.tsx` (NEW)
- `frontend/src/components/papers/TranscriptTab.tsx` (NEW)
- `frontend/src/components/papers/CodeTab.tsx` (NEW)
- `frontend/src/components/papers/FiguresTab.tsx` (NEW)

**Artifacts modified:**
- `backend/api/config.py` — Add papers_dir property
- `backend/api/models/papers.py` — Add 5 artifact models
- `backend/api/routes/papers.py` — Add 6 artifact endpoints
- `backend/api/services/demo_runner.py` — Add demo literature/reviews data
- `frontend/src/api/client.ts` — Add artifact interfaces + functions
- `frontend/src/hooks/usePapers.ts` — Add 4 artifact hooks
- `frontend/src/components/session/StatsBar.tsx` — Clickable papers count
- `frontend/src/components/session/SessionView.tsx` — Wire literature panel
- `frontend/src/pages/PapersPage.tsx` — Tabbed artifact viewer

### Prompt 63 — Live Literature Panel and Broken arXiv Link Fix

> When I click on a paper it eventually loads but it is very slow. And opening literature, review etc it also takes a long time (several tens of seconds). Why is that? Can we fix this? Also the links to abstract and pdf are all broken (e.g. https://arxiv.org/pdf/bbff2f80d2855bf6e4e94aeb3ef542936dbd82cd). Also: when I look at the papers (clicking on the papers counter) it says "Not yet available" even when the counter has a large number of papers. Can we expose the literature during the research cycle?

**Root cause (live literature):** `LiteraturePanel` required a `paperId` which only exists after cycle completion. During the cycle, papers_found counter was live but clicking it showed "Not yet available".

**Root cause (broken links):** Synthetic IDs like `ext-f1a306c75ff5` (SHA256 hashes of external URLs) were treated as arXiv IDs, generating invalid URLs like `https://arxiv.org/pdf/ext-f1a306c75ff5`.

**Fix — Live literature streaming:**
1. Added `LiteratureUpdateMsg` WS message type with search log and unique papers
2. `WebSocketDisplayAdapter` accumulates paper data during searches and broadcasts via WebSocket
3. Extended `search_result()` interface with optional `papers` kwarg to pass paper details through
4. Frontend `sessionStore` handles new `literature_update` message, stores in `LiveLiterature` state
5. `LiteraturePanel` uses live WebSocket data when no `paperId` available, shows "LIVE" badge

**Fix — Broken arXiv links:**
1. Backend `artifact_parser.py`: skip `arxiv_url` construction for `ext-` prefixed IDs
2. Frontend `LiteraturePanel`: added `isValidArxivId()` guard — filters out `ext-` and hex-hash IDs
3. Frontend `LiteratureTab` (papers page): same `isValidArxivId()` guard for Abstract/PDF links

**Artifacts modified:**
- `backend/api/models/messages.py` — Add LiteratureUpdateMsg, LiteraturePaperMsg, LiteratureSearchMsg
- `backend/api/services/ws_display.py` — Accumulate and broadcast literature data
- `backend/api/services/artifact_parser.py` — Fix arxiv_url for ext- IDs
- `src/paradigm/display/manager.py` — Add optional papers/phase kwargs to search_result
- `src/paradigm/orchestrator/literature.py` — Pass paper dicts through search_result
- `frontend/src/api/ws-types.ts` — Add LiteratureUpdateMsg types
- `frontend/src/stores/sessionStore.ts` — Handle literature_update, add LiveLiterature state
- `frontend/src/hooks/useResearchSession.ts` — Expose literature from store
- `frontend/src/components/session/SessionView.tsx` — Pass liveLiterature to LiteraturePanel
- `frontend/src/components/session/LiteraturePanel.tsx` — Full rewrite: support live + API data, fix links
- `frontend/src/components/papers/LiteratureTab.tsx` — Fix broken arXiv links with isValidArxivId

### Prompt — Fix Knowledge Feature Activation + Figure Validation

> Implement the following plan: Fix Knowledge Feature Activation + Figure Validation
>
> Two issues from paper-891269b98270:
> 1. Knowledge features (world model) produced empty output — agents never emit [ENTITY:], [HYPOTHESIS:], [EVIDENCE:] tags because no prompt instructs them to.
> 2. Figure duplication/mismatch — writer references more figures than exist; embed_figures_inline() force-appends unreferenced figures and can duplicate on multiple calls.
>
> Fixes: (1) Add _KNOWLEDGE_TAG_INSTRUCTION constant and inject it in _build_agent_prompt() for world-model-enabled phases. (2) Add figure count caps in section drafting + assembly prompts, strip orphan image tags in embed_figures_inline(), remove force-append fallback.

**Key decisions:**
- Knowledge tag instructions injected at same point as literature/debate instructions (end of `_build_agent_prompt()`)
- Only target phases with `world_model` in `_PHASE_CONTEXT_NEEDS` (IDEATION, PLANNING, POST_EXECUTION)
- Figure orphan cleanup uses regex to strip image tags referencing figures beyond actual count

**Artifacts modified:**
- `src/paradigm/orchestrator/constants.py` — Add `_KNOWLEDGE_TAG_INSTRUCTION` constant
- `src/paradigm/orchestrator/engine.py` — Inject knowledge tags in `_build_agent_prompt()`
- `src/paradigm/orchestrator/writing.py` — Figure count caps + orphan tag cleanup in `embed_figures_inline()`


---

## Prompt 63 — Per-Cycle ChromaDB Collection Isolation

**Date:** 2026-03-04

> Implement the following plan: Per-Cycle ChromaDB Collection Isolation.
> Literature search results from previous research cycles leak into new ones because all cycles share a single persistent ChromaDB collection named "paradigm_papers". Thread a collection_name through the Corpus/provider initialization chain so each cycle gets its own ChromaDB collection.

**Key decisions:**
- Use `session_id` (backend) or generated short UUID (CLI) as collection suffix
- Collection name format: `paradigm_papers_{id}`
- Thread `collection_name` through Corpus and provider_factory constructors

**Artifacts modified:**
- `src/paradigm/literature/corpus.py` — Add `collection_name` param, forward to EmbeddingStore
- `src/paradigm/literature/provider_factory.py` — Add `collection_name` param, forward to EmbeddingStore
- `src/paradigm/main.py` — Generate cycle_id, pass collection_name to Corpus + providers
- `backend/api/services/session_manager.py` — Pass session_id-based collection_name to Corpus

---

## Prompt 64 — Polish Paradigm Frontend Design

**Date:** 2026-03-04

> Let's polish Paradigm frontend look. Let's make it more slick and functional.

**Key decisions:**
- TBD — Frontend design overhaul for visual polish and improved UX

**Artifacts modified:**
- TBD

---

## 2026-03-04

### Prompt 63 — Frontend Polish: Observatory Control Room Theme

> Implement the full frontend polish plan: Observatory Control Room theme with deep navy/charcoal darks, teal/cyan accents, Outfit + JetBrains Mono fonts, glassmorphism cards, animated phase tracker, observatory-inspired loading spinner, and atmospheric styling across all 17 component files.

**Key decisions:**
- Direction: Observatory Control Room — deep navy, teal accents, scientific precision
- Fonts: Outfit (display/body) + JetBrains Mono (monospace)
- 17 files modified across layout, dashboard, session, shared components, and constants

**Artifacts modified:**
- `frontend/index.html` — Google Fonts
- `frontend/src/index.css` — Color system, scrollbar, glow utilities, noise texture
- `frontend/src/components/layout/Sidebar.tsx` — Logo, gradient bg, version tag
- `frontend/src/components/layout/Header.tsx` — Pulse indicators, taller, glow border
- `frontend/src/components/layout/AppShell.tsx` — Radial gradient content area
- `frontend/src/pages/Dashboard.tsx` — Gradient heading, styled sections
- `frontend/src/components/research/CycleCard.tsx` — Glassmorphism, hover glow
- `frontend/src/components/papers/PaperCard.tsx` — Glassmorphism, hover glow
- `frontend/src/components/shared/StatusBadge.tsx` — Animated running dot
- `frontend/src/components/shared/EmptyState.tsx` — Atmospheric styling
- `frontend/src/components/shared/LoadingSpinner.tsx` — Observatory spinner
- `frontend/src/components/session/PhaseTracker.tsx` — Connected pipeline nodes
- `frontend/src/components/session/StatsBar.tsx` — Instrument cards
- `frontend/src/components/session/AgentPanel.tsx` — Agent glow borders
- `frontend/src/components/session/MessagesPanel.tsx` — Message animations
- `frontend/src/components/session/RightPanel.tsx` — Pill tabs
- `frontend/src/components/session/EventLog.tsx` — JetBrains Mono styling
- `frontend/src/components/session/InteractionBar.tsx` — Themed input bar
- `frontend/src/components/research/SetupWizard.tsx` — Glass modal
- `frontend/src/lib/constants.ts` — Adjusted agent colors

### Prompt 64 — Setup Wizard Textarea Size + Settings Auto-Save

> A few things: the window where to include the Research Prompt should be larger (hard to read the final prompt otherwise). Also the save button in the settings seems superfluous: one should just be able to change the preferences with the buttons. The only extra button required is the 'reset to default'

**Key decisions:**
- Make SetupWizard prompt textarea and modal larger
- Settings: auto-save on change, remove Save button, keep only Reset to Defaults

**Artifacts modified:**
- `frontend/src/components/research/SetupWizard.tsx`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/components/settings/SettingsSection.tsx`

### Prompt 65 — WebSocket Keepalive, Reconnect, and Message Buffer

> WebSocket connections drop during long research cycles (overnight runs). Implement: (1) server-side ping/pong keepalive, (2) frontend heartbeat + unlimited reconnect, (3) message buffer so events aren't lost during brief disconnects.

**Artifacts:** `backend/api/routes/ws.py`, `frontend/src/api/websocket.ts`, `backend/api/services/session_manager.py`

---

## 2026-06-03

### Prompt 66 — Resume Work on Paradigm

> Let's get back to working on paradigm

**Key decisions:**
- Removed a stray "in-app music player" history entry that had leaked in from a different project sharing this folder (Paradigm is the agentic science platform).
- Produced a full project status report. Findings: Phases 0–11 complete (~25k LOC core, 1219 tests, clean ruff); real usage in DB shows 14 published / 24 rejected / **24 writing_failed** / 189 external papers. Frontier is reliability + output quality, not features.

### Prompt 67 — Diagnose & Fix Failed Runs, Then Eval Harness & Efficiency

> Let's start with 1 and then move to 2 and 3

Where (1), (2), (3) refer to the recommended next steps from the status report:
1. **Reliability** — diagnose and fix the 24 `writing_failed` runs (38% of research attempts never produced a paper).
2. **Evaluation harness** — repeatable scorer over fixed seed prompts to measure quality systematically.
3. **Orchestration efficiency** — reduce the ~65% token waste, tighten convergence, cap execution sprawl.

**Key decisions:**
- Starting with (1): root-cause the `writing_failed` runs from events.jsonl + transcripts before proposing fixes.

**Diagnosis (step 1):** All 24 `writing_failed` papers had substantial bodies (10k–65k chars) — none were crashes. Every one was killed by the *internal editor* at INTERNAL_REVIEW, before peer review. Two buckets: (A) editor correctly rejected papers built on failed/synthetic experiments, forbidden claims, non-existent figures, bare-URL refs; (B) revise loop ran all 5 iterations as "Revise" and never reached "accept". Also found 2 live code bugs: `tournament_handler` called `provider.complete(system_prompt=, user_prompt=)` against a `(system=, messages=)` signature (tournament silently broken, 188 errors), and `SourceResult.id` rejected None ids from S2/bioRxiv/PubMed/ADS (144 errors → lost lit → bare-URL citations).

**Fixes implemented (all 5, in order); 1226 tests pass, ruff clean, tsc clean:**
1. Tournament `complete()` signature fixed; tests had encoded the buggy signature — updated to the real Protocol.
2. `SourceResult` gained a `model_validator` that synthesizes a stable `src-<sha1>` id from url/title when the upstream id is falsy.
3. Post-EXECUTION go/no-go gate: `abort_on_execution_failure` (default True) stops the cycle with status `execution_failed` when no experiment produced usable output (`successful_code` empty) — saves ~1M tokens on doomed papers.
4. Revise-loop convergence: re-sanitize Unicode math on every revision; stall early-exit after 2 non-decreasing required-change counts.
5. Split `writing_failed` into honest statuses: `writing_incomplete`, `review_rejected`, `revision_exhausted` (+`execution_failed`); updated engine, display (×3), terminal colors, frontend StatusBadge.

**Artifacts modified:** `src/paradigm/knowledge/tournament_handler.py`, `src/paradigm/domains/base.py`, `src/paradigm/config.py`, `src/paradigm/orchestrator/{engine,review,writing}.py`, `src/paradigm/display/{manager,fallback,components}.py`, `backend/api/services/ws_display.py`, `frontend/src/components/shared/StatusBadge.tsx`, tests (`test_hypothesis_tournament`, `test_domain_base`, `test_orchestrator`, `test_peer_review`), `tasks/todo.md`.

**Step 2 — Evaluation harness (Phase A, offline) DONE.** User chose: offline-now/live-opt-in, deterministic + LLM judge blended. New `src/paradigm/eval/` package: `models.py` (DeterministicMetrics/JudgeScores/PaperScore/EvalReport + OUTCOME_SCORES), `metrics.py` (domain-agnostic: outcome→score, sections, references + bare-URL ratio, figure present/referenced, citations), `judge.py` (optional, resilient LLM taste judge), `harness.py` (collect → `score_paper` → blend → render/CSV/JSON; `score_paper` reused by future live mode). Added DB `get_thread_id_for_paper` (token attribution) and CLI `paradigm eval` (`--judge/--no-judge`, `--limit`, `--include-external`, `--live` stub). 9 new tests; full suite **1235 passed**, ruff clean. Baseline over real `data/papers`: 63 generated papers, **mean quality 61.0/100**; harness auto-surfaced non-existent figures (paper-37146874e965: 0/32) and bare-URL citations (paper-98e5f2add2a9: 104/106). Phase B (`--live` engine wiring) deferred. Artifacts: `src/paradigm/eval/*`, `src/paradigm/storage/database.py`, `src/paradigm/main.py`, `tests/test_eval.py`, `tasks/todo-eval.md`.

**Step 3 — Orchestration efficiency: DIAGNOSED, then PAUSED (no edits).** User chose diagnose-first + quality-first. Token by role (85.6M total): experimentalist 27.6%, synthesizer 18.8%, theorist 15.4%, analyst 12.9%, skeptic 8.8%, writer 8.5%, editor 6.8%. Initial headline numbers were corrected for honesty: the "64% duplicate searches" is mostly legitimate *cross-cycle* re-search (within-run dedup verified working at `literature.py:292-299`), and "76% zero-result" swept in events lacking a result-count field. **Clean finding:** agents issue `id:<arxiv-id>` lookups through the keyword-search interface, which always returns 0 — **471 zero-result `id:` queries** (e.g. `id:2509.12411` ×15). Proposals drafted (not implemented): P1 route id:/arXiv-ID queries to a real paper lookup; P2 normalize over-long queries to keywords; P3 stamp experiment names on `code_execution` events so retry waste becomes measurable. **Decision: pause and resume later.** User's steer: do paper lookups via **MCP or a dedicated fetch-by-ID path**, not a keyword-search reroute. See `tasks/todo-step3.md`.

> NOTE: Step 1 + Step 2 code changes are complete and verified but **uncommitted** in the working tree.

---

### Prompt 68 — Literature Review & Strategic Synthesis from External Sources

> Please have a look at this repo. Then look into the literature folder. After that I would like for you to lookup these links, downloads relevant articles if needed, and read through. Syntesize all important findings relevant to paradigm in a new md file inside /literature. At the end you should describe carefully and in a detailed way development directions for paradigm that are informed by what you read
>
> [16 links provided: Auto-claude-code adversarial research in sleep; Anthropic Operon; Sakana AI Scientist (Nature); OpenGauss (Lean/Math); AlphaXiv MCP (Pento); "AI Can learn scientific taste" (alphaXiv); Self-evolving Agent skills (arXiv 2605.23904); "Why AI Cannot do good science without humans" (Nature); Claude 101 for academia (X/Mushtaq Bilal); "Accelerating scientific research with Gemini" (arXiv 2602.03837); The AI Scientist (arXiv 2408.06292); "What will be scarce?" (Alex Imas substack); Paperclip scientific literature MCP; gxl.ai paperclip CLI; "A new consciousness of mathematics" (substack)]

**Key decisions:**
- Read existing literature folder (Paradigm Agentic Science research dossier + Competitive Landscape Analysis).
- Fan out to fetch/read all 16 external sources; synthesize into a new `/literature` md file with Paradigm-relevant findings + detailed development directions.

**Artifacts produced:**
- `literature/2026-06_Research-Synthesis_and_Development-Directions.md` — synthesis of all 15 external sources (read via 6 parallel research subagents) + 12 prioritized development directions (D1–D12) tied to specific modules, a 4-phase roadmap, and strategic-positioning guidance.

**Key findings (for quick reference):**
- Master theme: build a **verification kernel** (re-execution + sympy/unit checks + claim-DAG with `sorry`-gates) since empirical science has no Lean kernel — attacks the 38% no-paper rate, quality variability, and credibility at once.
- Replace the linear execution loop with **tree-search + Experiment Progress Manager** (AI Scientist v2) to fix `writing_failed`.
- Wire a **held-out eval harness** (prereq for everything) + calibrate the reviewer against the real 14-published/24-rejected DB.
- **Cross-model adversarial review** ("a loop cannot acquit") + `/kill-argument` phase; **trained taste judge** as the tournament adjudicator (Elo + win-rate, tiered debate cost); **gated skill optimization** (SkillOpt) to make reflection reproducible.
- Interop: **expose Paradigm as an MCP server** + consume alphaXiv/Paperclip MCP + **paper→repo reproduction**.
- Strategic: don't optimize for paper *throughput* (Imas: AI output is non-scarce); keep **mandatory human gates** (Nature) at problem-selection/prioritization/verification/ethics; provenance + git threads + verification kernel = the moat.
- Provenance correction: arXiv 2602.03837 is the Gemini *case-studies* paper, **not** the Co-Scientist tournament paper (that's 2502.18864).

> Note: a research subagent spawned during this prompt auto-appended a spurious "Prompt 69" entry here (subagents inherited the CLAUDE.md logging rule); it was an internal research dispatch, not a human prompt, and has been removed.

---

### Prompt 69 — Commit Prompt-67 Work to a Branch

> Yes, let's commit to a branch

**Action:** Created branch `prompt67-reliability-eval` and committed the (previously uncommitted) Step 1 reliability fixes and Step 2 evaluation harness as two logical commits. Pre-existing untracked files (`PROMPT-*.md`, `literature/`, `paper-*.pdf`) were intentionally left out.

### Prompt 70 — Push and Open a PR

> yes push and open a PR

**Action:** Pushed `prompt67-reliability-eval` to `origin`. The `gh` CLI is not installed in this environment, so the PR is opened via the GitHub compare URL (title/body prepared by Claude) rather than programmatically.

---

### Prompt 71 — Analyze Denario Architecture, Compare to Paradigm, then Roadmap

> Before moving to plan mode, I would like to have a look at the architecture of another platform -- Denarion (in /Users/mcantiello/astro/Denario ). Do a thorough analysis of its inner working and compare to Paradigm. We want to learn as much as possible in terms of different choices adopted there and what we could use to improve paradimg. After that we can create a roadmap including all the learnings we gathered so far from the readings and this new exercise

**Key decisions:**
- Two-step request: (1) deep architectural analysis of Denario (`/Users/mcantiello/astro/Denario`) + Paradigm comparison → write findings to a literature/analysis doc; (2) THEN build a roadmap folding in both the Prompt-68 external-source synthesis and the Denario learnings.
- Denario = open-source multi-agent research platform (AstroPilot-AI / Flatiron), AG2/LangGraph + cmbagent backend — Paradigm's most direct competitor per the Competitive Landscape doc.

**Artifacts produced:**
- `literature/2026-06_Denario-vs-Paradigm-Architecture-Analysis.md` — code-level analysis of Denario (read `denario.py` + 3 read-only sub-analyses of `langgraph_agents/`, `paper_agents/`, cmbagent stages) + head-to-head comparison + ranked adopt-list (5 leaf-level wins + strategic build-vs-buy) + convergence map to D1–D12.

**Key findings:**
- Denario = ~5k LOC thin layer over **LangGraph + AG2/cmbagent** + FutureHouse PaperQA + Perplexity; **human-driven stepwise** (edit Markdown artifacts between stages); ships **journal-ready LaTeX** and has **published papers** (AI-authors conf, LSST DESC; cmbagent won NeurIPS Fair Universe).
- Paradigm is ahead on: autonomy loop, hypothesis tournaments/debate, real editor+2-reviewer+decision journal, episodic memory, reputation, git threads, sandbox safety, token budgets. (Verified: Paradigm already does per-role model heterogeneity + per-thread/agent budgets — those are NOT gaps.)
- **Adopt from Denario (leaf-level, philosophy-compatible):** (1) journal-ready LaTeX + LLM compile-repair loop; (2) **multimodal/figure-aware reviewer** (= D8, confirmed in production); (3) **`restart_at_step`** experiment resume (= granular D2); (4) **resolve-or-drop citation grounding** (= D1 anti-fabrication); (5) **console-as-data-bus** engineer→researcher contract. Plus effort/mode toggle, controlled-vocab keywords.
- **Strategic (decide, not default):** optionally consume FutureHouse PaperQA (D10); do NOT adopt cmbagent as executor (conflicts with own-sandbox/no-AutoGen) — borrow its ideas instead.
- Biggest gap is **output polish + validation**, not capability: closing the 5 adopt-items + producing one real validated paper flips Paradigm's position.

**Next step (per user):** create a unified roadmap fusing the Prompt-68 external synthesis (D1–D12) + these Denario learnings — to be done in plan mode.

---

### Prompt 72 — Approve Unified Roadmap & Begin Phase-1 Implementation

> Yes please → (plan mode) → retry → **plan approved**

**Flow:** Entered plan mode; explored current state (confirmed Prompt-67 reliability + eval harness already done; everything else greenfield with pinned hook points); asked 3 scoping questions → answers: **(1) first focus = Harden correctness, (2) posture = Hybrid + provenance, (3) interop = Consume external agents**. Drafted the unified roadmap, pressure-tested Phase-1 with a Plan agent, presented via ExitPlanMode. A remote Ultraplan refinement attempt failed (`error_during_execution`); on retry the user approved the local plan directly.

**Plan approved** (`~/.claude/plans/squishy-crafting-dahl.md`). Phase 1 = **Correctness Kernel**, build order **1A→1C→1B→1E→1D** + a fetch-by-ID interop slice. Each feature default-off, test-gated, plain-Python.

**Artifacts produced:**
- `literature/2026-06_Unified-Roadmap.md` — the approved roadmap (copied into the repo).
- `tasks/todo.md` — seeded with Phase-1 checkable items (overwrites the completed Prompt-67 todo, which is preserved in git history + HISTORY Prompt 67).
- Implementation in progress (working tree, branch `prompt67-reliability-eval`; new branch/commits held for user's go-ahead).

**1A — Falsifiability / Pre-registration: COMPLETE & verified** (full suite 1265 passed, ruff clean). Default-off (`knowledge.enable_preregistration`). Files: `knowledge/models.py` (PredictionRule/PredictionVerdict/PredictionDirection + Hypothesis fields), `orchestrator/preregistration.py` (new handler), `phases.py` (PRE_REGISTRATION sub-phase), `state.py`, `config.py`, `engine.py` (freeze + evaluate wiring), `experimentation.py` (rule injection), `writing.py` (verdicts → Fact Sheet/FORBIDDEN), `display/theme.py`, `constants.py`; tests `test_preregistration.py` (24) + `test_phases.py`. DB persistence of verdicts deferred to 1D.

> On user instruction ("commit first, then 1C"): created branch **`phase1-correctness-kernel`** off `prompt67-reliability-eval` (keeps the reliability/eval PR clean); committed docs/roadmap then the 1A implementation as two logical commits. Proceeding to 1C next.

**1C — Tree-search / step-restart: COMPLETE & verified** (full suite 1275 passed, ruff clean). Default-off (`orchestrator.enable_best_first_nodes` / `enable_step_restart`). `constants.py` (`CodeBlock.restart_at_step` + `# RESTART_AT:` parsing; `_best_first_order` dependency-respecting non-buggy-preferring Kahn traversal); `experimentation.py` (best-first ordering + `_buggy_experiments` tracking + step-restart retry guidance); `config.py`; tests `test_tree_search.py` (10). Committed as its own logical commit.

**Interop slice — fetch-by-id lookup: COMPLETE & verified** (full suite 1343 passed, ruff clean). `orchestrator/literature.py`: `_extract_arxiv_id_query` (anchored regex; keyword queries excluded) + `_resolve_id_query` routes `id:<arxiv-id>` SEARCH requests to `corpus.read_paper` (fetch-by-id) instead of keyword search — eliminates the 471 guaranteed-zero `id:` queries; counts against the search budget but not the keyword-stale throttle. Tests `test_literature_id_lookup.py` (17, incl. routing proof). External MCP/PaperQA consumption deferred to Phase 5.

> **✅ PHASE 1 COMPLETE (6/6):** 1A pre-registration · 1C tree-search/restart · 1B verification kernel · 1E human-gate+provenance · 1D eval selection-gate · interop fetch-by-id. All default-off / backward-compatible; six logical commits on branch `phase1-correctness-kernel`; full suite 1343 passed, ruff clean.

**1D — Eval extension (selection gate): COMPLETE & verified** (full suite 1326 passed, ruff clean; offline `paradigm eval` backward-compatible). `eval/seeds.py` (`SeedPrompt`, hash-fixed `split_seeds` — no test leakage); `eval/calibration.py` (pure `fit_threshold` balanced-accuracy sweep + `calibrate_from_db` + persist); `eval/metrics.py`+`models.py` (`reproduction_pass_rate`/`prereg_verdict` reported-only + new `OUTCOME_SCORES`); `harness.py` (`run_live_eval`/`score_thread_paper`); `main.py` (`_run_research`→thread_id; `paradigm eval --live N --split ...`); **SQLite persistence** of verification/prereg/provenance (idempotent `papers` columns + `_record_provenance` write — fold-in from 1A/1B/1E); tests `test_eval_selection.py` (20). Deferred: a `--calibrate` CLI wrapper.

**1E — Hybrid human-gate + provenance: COMPLETE & verified** (full suite 1306 passed, ruff clean). Default-off (`orchestrator.human_gate_mode="off"`). `orchestrator/human_gate.py` (pure `decide_human_gate` off/advisory/blocking + no-hook deadlock guard; `build_provenance`); `engine.py` (`_human_gate`/`_handle_gate_decision` at problem_selection/pre_registration/final_verification + `_record_provenance`); `knowledge/models.py` `ProvenanceRecord`; `state.py` (`gate_decisions`, `provenance`); `config.py`; tests `test_human_gate.py` (12). Provenance SQLite persistence deferred to 1D.

**1B — Verification Kernel: COMPLETE & verified** (full suite 1294 passed, ruff clean). Default-off (`orchestrator.enable_verification`). `orchestrator/verification.py` (re-execute `successful_code` in a fresh seeded `--network=none` `verify/<thread>` workspace; compare `RESULT[...]` tokens within tolerance → accepted/rejected/nondeterministic; `apply_gate` demotes non-accepted); `knowledge/models.py` `VerificationRecord`; `state.py`; `phases.py` `VERIFICATION` sub-phase; `engine.py` block+gate (abort `verification_failed` if none reproduce); `experimentation.py` `RESULT[]` console contract; `writing.py` Verification Ledger (resolve-or-drop at source via demotion→FORBIDDEN); `config.py`; tests `test_verification.py` (19). Checker battery + SQLite persistence deferred to follow-up/1D.

---

### Prompt 73 — Push Phase-1 Branch + Open PR, then Validate Live

> 1 and then validate live

(Where "1" = the offered "push the branch + open a PR for the Phase-1 series" option.)

**Action:** Push `phase1-correctness-kernel` to `origin` and open a PR (via `gh` if available, else the GitHub compare URL with prepared title/body). Then validate the kernel live — enable the default-off flags and run a real cycle + `paradigm eval --live`.

**Done:** PR #12 opened (`phase1-correctness-kernel` → `main`, comprehensive); PR #11 closed as superseded. Created `configs/validate.yaml` (lean, isolated `data_validate`, all Phase-1 flags on, `--network=none`). User started Docker + built `paradigm-sandbox:latest`. Launched live validation cycle (`--testing`, self-contained 1/√n prompt) in background.

---

### Prompt 74 — Keep Testing/Refining, Then Continue the Development Plan

> Keep testing and refining if needed. After that continue with the development plan

**Action:** Complete the live validation (inspect run artifacts: prereg freeze/verdict, verification ledger, provenance, fetch-by-id); fix any integration bugs surfaced; re-run if needed. Then proceed to **Phase 2 — Output quality & credibility** (journal-ready LaTeX + compile-repair, figure-aware multimodal review, resolve-or-drop citation finalize).

**Refine — model choice:** First run exposed that `testing_overrides` used `deepseek-ai/DeepSeek-V3.1` (no longer serverless on Together → 400s for analyst/synthesizer/skeptic/editor). User specified the models to use instead: **`deepseek-ai/DeepSeek-V4-Pro`, `moonshotai/Kimi-K2.6`, `zai-org/GLM-5.1`**. Updated `configs/validate.yaml` overrides — makers (theorist/experimentalist)→DeepSeek-V4-Pro, analyst/synthesizer/editor→Kimi-K2.6, writer/skeptic→GLM-5.1 (skeptic on a different family = cross-model adversarial diversity). Will mirror into `configs/default.yaml` testing_overrides once validated.

**LIVE VALIDATION RESULT (✅ kernel works end-to-end).** Full `--testing` cycle on the 1/√n prompt (thread-1dd581744a51, paper-a2f64ebeb18f; 853K tokens, ~1h41m):
- **1B verification kernel ✓✓** — re-executed all 3 experiments in a fresh `--network=none` sandbox and reproduced **13 `RESULT[]` metrics with max rel error 0.00e+00**; `final_verification` gate "3/3 reproduced"; `reproduction_pass_rate=1.0` persisted + read by eval.
- **1E gates + provenance ✓** — all 3 advisory gates fired; provenance persisted (`verified_by=kernel`, `verification_summary={accepted:3,total:3}`, gate decisions recorded).
- **Console-as-data-bus ✓** (experimentalist emitted `RESULT[...]`); **1D eval ✓** (read persisted records, scored 65/100).
- **1A ran but froze 0 rules** — the reject gate correctly dropped 2 non-falsifiable tournament hypotheses; the theorist didn't emit well-formed `PredictionRule` JSON → no prereg.
- **Only blocker to publication:** editor recommended "revise (0 required changes)" twice → `revision_exhausted` (no accept).

**Refines applied (full suite 1349 passed, ruff clean):**
1. `orchestrator/review.py` — extracted `_resolve_internal_recommendation`: "revise" with **0 required changes → accept** (lets the loop converge); "revise" + ≥4 failed checks → reject (unchanged). +6 unit tests.
2. `orchestrator/constants.py` — added a concrete worked example to `_PREREGISTRATION_PROMPT` to elicit well-formed rules (addresses 1A's 0-rules outcome).
3. `configs/default.yaml` — fixed `testing_overrides` (dead DeepSeek-V3.1 → DeepSeek-V4-Pro/Kimi-K2.6/GLM-5.1); added `configs/validate.yaml`.
- Noted (non-fatal): occasional checkpoint-JSON parse fallback; a `SyntaxWarning '\s'` in agent-written code.

**PHASE 2 STARTED — Output quality & credibility.** Tasks: P2-LaTeX (journal-ready LaTeX + compile-repair), P2-VLM (figure-aware multimodal review, D8), P2-cite (resolve-or-drop citations).
- **P2-cite COMPLETE & verified** (full suite 1355 passed, ruff clean). Default-off (`citation.drop_unresolved_citations`). `literature/bibliography.py`: `drop_unresolved_references` (drop refs with no resolved metadata + renumber, return index remap) + `remap_citation_markers` (rewrite/remove in-text `[N]` so dropped citations don't dangle); wired into `orchestrator/citation_handler.py`; `config.py` flag; tests `test_citation_drop.py` (6). Completes 1B's resolve-or-drop discipline at the bibliography stage (attacks the bare-URL references that drove `writing_failed`).

**Branch split (user chose "New Phase-2 branch/PR"):** `phase1-correctness-kernel` (= origin, PR #12) reset to the validation-refines commit (Phase 1 + validation only); new `phase2-output-quality` branch (pushed) carries P2-cite onward; Phase-2 PR deferred until the phase is further along.

---

### Prompt 75 — Implementation Summary (Rationale + Technical Solution)

> Let's pause. I would like to make a summary of all the changes we implemented. The rationale/motivation and the technical solution

**Artifact:** `docs/correctness-kernel-implementation.md` — comprehensive summary of everything built across Phase 1 + live validation + refines + Phase-2 P2-cite: per-feature motivation + technical solution, a new-files/models/phases reference, a config-flag table, and branch/PR state.

---

### Prompt 76 — Phase 2: P2-LaTeX (toggleable LaTeX/PDF output)

> Let's continue with Phase 2. The latex/pdf output should be something one can toggle on/off

**Key decisions:**
- New `journal/latex.py`: deterministic markdown→LaTeX (no LLM, no external Python deps; math-preserving escaping) + journal presets + best-effort PDF compile (shells out to tectonic/xelatex/pdflatex only if installed).
- Explicit on/off toggles per user: `journal.enable_latex_output` (emit `.tex`) and `journal.compile_pdf` (also build PDF). Default off; hooked into `WritingHandler.save_paper_file` (non-fatal). Tests in `test_latex_output.py`.
- On the `phase2-output-quality` branch.

**P2-LaTeX COMPLETE & verified** (full suite 1374 passed, ruff clean). `journal/latex.py`: `markdown_to_latex` (deterministic, math-preserving escaping, headings/abstract/figures/lists/bold-italic/references), `JOURNAL_PRESETS` (none/arxiv/neurips, base-TeX-only packages), `find_latex_engine`/`compile_pdf` (best-effort: tectonic/xelatex/pdflatex; graceful no-engine path), `write_paper_latex` orchestrator; `JournalConfig` (`enable_latex_output`/`latex_journal`/`compile_pdf`, default off); writing hook. Tests `test_latex_output.py` (19, incl. a real xelatex compile). **Demonstrated live:** the 23 KB validation paper rendered to `.tex` and compiled to a 312 KB PDF via xelatex. Refine from the demo: dropped `authblk` from the arxiv preset (not in minimal TeX installs) → base-package-only presets.

**P2-VLM COMPLETE & verified** (full suite 1386 passed, ruff clean). Default-off (`orchestrator.enable_multimodal_review`). `agents/providers.py`: `build_image_message` on both providers (Anthropic image blocks / OpenAI `image_url` data-URLs) + Protocol method. `journal/review.py`: `encode_figures_for_review` (read PNG/JPG/GIF/WEBP figures → bytes, cap count/size, skip PDFs/missing). `orchestrator/review.py`: `_run_figure_review` (resolves the editor's provider, sends the actual figure images via `build_image_message`+`complete`, returns concrete findings; graceful "" on disable/no-figures/non-vision-model/error) — findings injected into the editor's review prompt. `constants.py` `_FIGURE_REVIEW_PROMPT`; `config.py` flags (`enable_multimodal_review`/`multimodal_review_role`/`max_review_figures`). Tests `test_multimodal_review.py` (14). 

> **✅ PHASE 2 COMPLETE (3/3):** P2-cite · P2-LaTeX · P2-VLM. All default-off / backward-compatible; full suite 1386 passed, ruff clean. Branch `phase2-output-quality`.

---

### Prompt 77 — Open Phase-2 PR + mark Phase 2 done in docs

> yes

**Action:** Updated `docs/correctness-kernel-implementation.md` to mark Phase 2 complete (P2-LaTeX/P2-VLM technical solutions + new flags in the table + status). Opened the Phase-2 PR **stacked on `phase1-correctness-kernel`** (base = the Phase-1 branch) so it shows only the 4 Phase-2 commits and PR #12 stays focused; can retarget to `main` once #12 merges.

---

### Prompt 78 — Integrate new features into docs + add GUI controls

> Next can we document and integrate all the new improvements in the documentation? Also it would be good to implement controls for the new features in the graphical UI

**Plan:** (1) Weave the Phase-1/2 features + config flags into the main docs (README, ARCHITECTURE, docs/MANUAL + API/DOMAINS as needed). (2) Add frontend (DenarioApp-style React) controls for the new toggles (pre-registration, verification, step-restart/best-first, human-gate, LaTeX/PDF output, multimodal review, drop-unresolved-citations), plumbed through the backend API → engine config. New branch stacked on `phase2-output-quality` (has all the flags).

**Done (branch `docs-and-ui-controls`).**
- **GUI controls (end-to-end):** backend `settings.py` models gained the new fields (Orchestrator: verification/best-first/step-restart/human-gate/multimodal; Knowledge: pre-registration; new Journal section; Citation: drop-unresolved) + the `journal` section registered in the route dispatch — GET/PUT `/api/v1/settings` now expose+update them (verified by a Config round-trip). Frontend `client.ts` interfaces mirrored; `SettingsPage.tsx` gained the controls in the Orchestrator/Knowledge/Citation sections + a new **Journal** tab, reusing Toggle/Select/Number fields + auto-save. Fixed a pre-existing `PaperViewer.tsx` TS2604 + removed dead `shallowEqual` so `tsc -b` is green. (One pre-existing eslint `set-state-in-effect` in the untouched `useSectionForm` hook left as-is.)
- **Docs:** `configs/default.yaml` now inline-documents all new flags (correct names/defaults) under `orchestrator`/`knowledge`/`citation` + a new `journal` section; README gained the 2 kernel phases in the loop diagram, a Correctness-Kernel + Output-Quality feature group, and `paradigm eval` in the CLI table; ARCHITECTURE gained a "Correctness Kernel (optional sub-phases)" section; docs/MANUAL gained section 22 "Correctness Kernel & Output Formats" (flag tables + `paradigm eval`) + TOC entry. Corrected the explore agents' invented details (no `--calibrate-judges` CLI, no `enable_fetch_by_id` flag, no fake top-level YAML sections).
- Verified: settings GET/PUT round-trip; `tsc -b` exit 0; `test_config.py` + ruff(src,backend) green. Each part committed separately on `docs-and-ui-controls`.

---

### Prompt 79 — Run a local instance for manual testing

> I want to test the platform and GUI works. Can you run an instance so I can test?

**Action:** Launch the platform via `./dev.sh` (backend uvicorn :8000 + frontend vite :3000; auth disabled in dev — no `PARADIGM_API_KEY`) on the `docs-and-ui-controls` branch (has the new GUI controls). Verify both services are up and hand the user the URLs. (Fixed a `dev.sh` bug: `conda run --no-banner` → `--no-capture-output`.)

---

### Prompt 80 — Phase 3 scope ("what do we have in phase 3?")

> Let's move to the next phase. What do we have in phase 3?

**Action:** Summarized Phase 3 (Smarter selection & adversarial review) from the roadmap — taste judge, Elo tiered-debate + stabilization stopping, diversity/proximity step, cross-model adversarial review + /kill-argument — with motivation, code hook points (extends existing `hypothesis_tournament`/`tournament_handler`/`debate`/`review`), dependencies (1D selection gate), and a proposed build order.

---

### Prompt 81 — Diagnose "extremely slow" GUI test run

> So I am running the test, but everything is moving extremely slowly. What is the bottleneck?

**Diagnosis (from `data/events.jsonl` + `~/.paradigm/backend.log`):** Not $ cost — **wall-clock latency of the big open-weight testing models**. The GUI ran in testing mode, whose `testing_overrides` point at DeepSeek-V4-Pro / Kimi-K2.6 / GLM-5.1 (huge MoE models, cheap but very slow + verbose on Together). Measured per-call: **one Kimi-K2.6 call took ~11.5 min**, DeepSeek-V4-Pro ~2 min. Multiplied by 7 agents × `max_rounds_per_phase` (default **10**) × many phases → hours; the run was still stuck in IDEATION after ~15 min. Levers: switch to a fast model (Llama-3.3-70B-Turbo / Haiku), drop max_rounds_per_phase to 1–2, disable Perplexity extras (citation grounding, seed discovery) + debates/sprints/verification for a smoke test.

---

### Prompt 82 — Add a FAST mode config

> YEs, let's come up with a FAST mode where we use claude-haiku-4-5 and meta-llama/Llama-3.3-70B-Instruct-Turbo, 2 max_rounds_per_phase, and turn off slow extras

**Action:** Created `configs/fast.yaml` — a self-contained fast-iteration config. Models: `claude-haiku-4-5` for the core science roles (theorist/experimentalist/analyst/synthesizer/writer) and `meta-llama/Llama-3.3-70B-Instruct-Turbo` for skeptic/editor + default/utility calls (cross-model diversity, both fast). `max_rounds_per_phase: 2`. Slow extras off: debates, execution sprints, Perplexity citation grounding + seed discovery; review loop trimmed (1 reviewer, 1 revision round, 2 review iterations); smaller tournament. Correctness-kernel + multimodal + LaTeX features left off (default). Relaunched the dev instance with `PARADIGM_CONFIG=configs/fast.yaml`.

---

### Prompt 83 — Brainstorm: responsiveness & richer intermediate progress

> In general the platform is very unresponsive. It would be helpful for it to be more responsive and provide more intermediate milestones about the progress, or at least provide more information about what's going on. This would be important for a number of reasons. First as an educational tool: user will learn something as it looks at the research progress and intermediate steps. It also exposes more the trajectory, allowing to make more interventions if needed. Moreover it will make the platform more interactive and fun to use. Can we brainstorm a bit about this and come up with an improvement plan?

**Action:** Brainstorm + improvement plan (no code yet). Grounded the discussion by auditing the progress pipeline (orchestrator → DisplayManager → WebSocketDisplayAdapter → WS → frontend) and whether agent calls stream.

---

## 2026-06-05

### Prompt 84 — Testing: "a bunch of 'search failed' messages"

> Sounds good — pausing here so you can test. [...] I am testing and seeing a bunch of 'search failed' messages

**Diagnosis (from `data/events.jsonl` + live `curl`):** The live cycle's failures are **arXiv IP rate-limiting (`429 "Rate exceeded"`) + `ReadTimeout`**, surfaced to the GUI as red `Search failed:` / `Read failed:` / `Follow failed:` / `Cited-by failed:` events. A fresh single `curl` to `export.arxiv.org` returns 429 immediately → the machine has tripped arXiv's persistent IP throttle. Contributing root causes: (1) **two+ independent `ArxivClient` instances** (one in `provider_factory.py`, one in `corpus.py`) each with its own 3s rate-limit clock → effective rate > 1 req / 3s; (2) `ReadTimeout` / transient network errors are **never retried**; (3) 429 backoff ignores the `Retry-After` header; (4) expected, recoverable external-source failures render as loud red `error` events instead of a calm, deduped notice. (The `system_prompt` TypeErrors + `SourceResult` ValidationErrors in older threads are stale, not from this cycle.)

**Fix (branch `responsive-live-progress`) — user chose "Robust + calm UI":**
- **`literature/arxiv.py`** — root-cause robustness: a **process-global rate limiter** (`_arxiv_rate_gate()` + module-level last-request clock) so *all* `ArxivClient` instances (corpus + provider factory) share ONE cadence instead of each pacing itself (the double-client bug that tripped the 429). `_rate_limited_get` now **retries transient errors** (timeouts, connect/protocol drops) with jittered backoff and **honors `Retry-After`** on 429 (capped 60s). Base URL switched `http`→`https` to drop the 301 redirect round-trip.
- **`orchestrator/literature.py`** — `_is_transient_source_error()` classifier + `_handle_source_failure()`: best-effort source failures (rate-limit/timeout) now log to the structured stream for forensics but surface **ONE calm, deduped notice per source per cycle** (`degraded_sources`) instead of a red error per request; genuine/unexpected errors still surface loudly. Wired into all 5 search/read/follow/cited_by except blocks.
- **Display (`manager.py` / `fallback.py` / `ws_display.py`)** — new `source_degraded(source)` rendering a calm `warning`-level "{source} rate-limited — using cached corpus + other sources" (replaces the red `error` spam).
- **Tests:** +25 (`test_arxiv_resilience.py`, `test_literature_degradation.py`) covering 429/transient retry, Retry-After (+cap), global-gate sharing, classifier, dedup, reset, display parity. **Full suite 1441 passed**, ruff clean. Live timing test: 6 requests across two independent clients paced at exactly 0.5s globally (was interleaved before).
- **Note:** arXiv was still IP-throttling this machine at fix time (fresh `curl` → 429 then 12s timeout) — a persistent server-side penalty that clears on its own. The fix makes the platform *resilient + quiet* under it, not immune; changes are live via uvicorn `--reload` on the fast.yaml instance.

---

### Prompt 85 — Thorough platform audit + refactor + bug-fix pass

> I want you to do a very thorough audit of the platform. Take all the time you need. Once you have done with that, proceed with any necessary/useful refactoring, and fix any bugs or issues you have identified. Stop only when you think the platform is in great shape from a development perspective, since there's a lot of development ahead and I want things to be ready.

**Plan:** Multi-dimensional audit (architecture, correctness/bugs, async/concurrency, error handling, provider interfaces, data models, tests, backend API, dead code, type safety) using parallel read-only subagents, then synthesize → prioritize → refactor + fix → verify (full suite + ruff). Investigate the real runtime error signatures seen during Prompt 84 (e.g. `OpenAICompatibleProvider.complete() got unexpected kwarg 'system_prompt'` ×182, `ResearchState has no attribute 'current_phase'`, `SourceResult.id` ValidationError ×94).

**Audit method:** 4 parallel read-only subagents (orchestrator core; agents/providers/literature; backend API + frontend; storage/logging/sandbox/config/tests). Findings synthesized + each verified against the code before fixing.

**Verdict on historical runtime errors (all STALE / already-fixed — confirmed):** `OpenAICompatibleProvider.complete() ... 'system_prompt'` (fixed by multi-provider abstraction; all callers use `system=`), `SourceResult.id` ValidationError (fixed by the `_ensure_id` validator), `ResearchState.current_phase` (fixed: stream sink now reads `phase_manager.current_phase`).

**Bugs fixed (live):**
1. **`literature/novelty.py`** called `provider.generate()` — which `LLMProvider` doesn't have → `AttributeError` every call, swallowed → the Semantic-Scholar novelty check was a **silent no-op** (always `is_novel=True`). Switched to `await asyncio.to_thread(provider.complete, ...)`, fixed result unpacking; updated 3 tests.
2. **`agents/providers.py`** — `AnthropicProvider.complete()/complete_streaming()` silently **dropped `extra_body`** (per-role overrides, e.g. extended thinking). Now forwarded, mirroring the OpenAI path. +2 tests.
3. **Security:** `configs/default.yaml` + `fast.yaml` set sandbox `network_mode: "bridge"`, overriding the safe `"none"` default → agent code ran **with network** and the safety scanner's network guard was disabled (SPEC `--network=none` violation). Set both to `"none"`.
4. **`ws_display._broadcast_state`** omitted `completed_phases` → the frontend phase tracker was **wiped on every event** in the real engine path. Now echoes `state.completed_phases`.
5. **Resource leaks:** generic `SourceProvider.close()` added (closes httpx `aclose()` / wrapped `close()`); `Corpus.close()` now tears down all providers; `session_manager._run_cycle` closes the corpus in `finally` (was leaking a connection pool per cycle); `verification.py` re-execution executor now cleaned up in `finally` (Docker container leak); `cleanup_session()` added + wired into the delete-cycle route (frees state + drops the per-cycle ChromaDB collection). +4 tests.
6. **WS robustness:** malformed client messages now reply with an error frame instead of tearing down the socket; `_fire_and_forget` tracks tasks + logs failures (no more lost/unretrieved broadcasts); frontend stops the reconnect storm on terminal close codes (1000/4001/4004).
7. **Noise/robustness:** convergence-check now brace-extracts JSON from prose and logs unparsed replies as `STATE_CHANGE` not `ERROR` (the ~21× `JSONDecodeError`-shaped ERROR source); `engine.py` convergence `except` now logs instead of silent `pass`.
8. **Config/DB hardening:** `checkpoint_interval`/`max_rounds_per_phase` now `Field(gt=0)` (the div-by-zero guard); SQLite opens with `journal_mode=WAL` + `busy_timeout=5000` (concurrent-session safety).

**Verification:** full suite **1447 passed** (+6 net new tests), `ruff check src/ backend/ tests/` clean, frontend `tsc -b` + `npm run build` green.

**Deferred (documented for focused follow-ups — higher-risk refactors / lower-value cleanups, not done to avoid destabilizing):** extract `engine.py` (2082 lines) into `artifacts.py` + `prompt_builder.py` + a shared fence-tolerant `_json_llm_call`; per-session SQLite connections + wrap the 32 sync DB writes in `to_thread`; **real pause/resume** (currently cosmetic — the engine never consults session status; tie into Phase C GUI intervention); `extra="forbid"` on config models (blocked on `finance.yaml`'s top-level `mode` key); `executions/` dir TTL pruning (disk growth); dead code (`reflection_model`, the unused `events` table + indices, `safety._get_call_name`, `ExecutionResult.started_at`); `datetime.utcnow()` → `datetime.now(UTC)`; rename `literature/providers.py` to avoid the collision with `agents/providers.py`.

---

### Prompt 86 — Commit

> commit

**Action:** Commit the uncommitted work on `responsive-live-progress` as logical commits (Prompt 84 arXiv resilience; Prompt 85 audit fixes/hardening), excluding scratch artifacts (PROMPT-*.md, data_validate/, paper-*.pdf).

---

### Prompt 87 — Continue development: start Phase C (hypothesis board + tournament bracket)

> Let's continue with development. What is the next phase we had planned?

**Decision:** We're on Phase C (Depth — live artifacts + GUI intervention). User chose to start with the **hypothesis board + tournament bracket** (frontend on existing `KnowledgeUpdateMsg`; lowest-risk visible win). Build order after: live draft, then experiment panel + GUI intervention (the latter also fixes the audit-flagged cosmetic pause/resume).

---

### Prompt 88 — Build out Phase C (#3 draft, #2 experiment, #4 intervention, #5 profile) + full test + GUI polish

> Continue with phase #3 then phase #2, phase #4 and phase #5. Do intermediate commits as needed. When you are done with all that do a test and make sure all works properly. After that use /frontend-design:frontend-design to improve the GUI to make the platform as engaging and interactive as possible. Iterate as much as needed until the look and feel of the platform is ready for prime time

**Plan:** Phase C remaining slices in order: (#3) live draft / PaperViewer via new DraftUpdateMsg; (#2) experiment panel via ExperimentUpdateMsg; (#4) GUI intervention + REAL pause (engine asyncio.Event gate + human-gate payload threading; fixes the audit-flagged cosmetic pause/resume); (#5) interactive profile enabling stream_tokens + human_gate_mode. Intermediate commits per slice; full test pass (pytest + ruff + tsc + build); then /frontend-design GUI polish, iterating to prime-time.

**Phase C complete + tested (all 5 slices committed):** tournament board, live draft, experiment panel, real pause/resume, interactive profile. Live end-to-end test on `configs/interactive.yaml` surfaced + fixed a hard deadlock (sync intervention/human-gate hook called inline on the event loop) — engine now offloads the hook via `to_thread` (async `_check_intervention`/`_human_gate`) and `_make_intervention_hook` captures the loop at creation. Verified live: health responsive 8/8 during the run, token streaming + 7 hypotheses flowing, and the `problem_selection` approval gate fires → client responds → cycle proceeds (no freeze). Full suite **1447 passed**, ruff + tsc + build green. Next: `/frontend-design` GUI polish to prime-time.

### Prompt 88 (cont.) — GUI polish via /frontend-design

**Done — "Observatory" design system.** Elevated the GUI to a distinctive, prime-time look: a nocturnal scientific-instrument identity. Deep indigo-ink void with a faint nebula glow + film grain; a warm **starlight-gold** signature accent against a cool **cyan** "live data" accent; type system = **Fraunces** (scholarly serif, for brand/headings — it writes papers), **Hanken Grotesk** (UI), **JetBrains Mono** (live data). Reworked `index.css` design tokens (cascades to every component), `index.html` fonts, the Sidebar/Dashboard brand identity (Fraunces wordmark + "Observatory" + observatory mark with an orbiting cyan star), and a gold streaming caret. Live-verified via headless-Chrome screenshots (dashboard, session view, knowledge/tournament tab) — instrument-grade phase tracker, live streaming agent output (markdown+LaTeX), activity timeline with narration, and the Phase-C tabs all cohesive. tsc + eslint + build green.

---

### Prompt 89 — "running a cycle but it seems stuck"

> running a cycle but it seems stuck

**Investigating:** prime suspect is the new interactive-profile blocking approval gate (cycle waiting for GUI approval), or a stall. Checking config, backend health, pending approvals, session status, and recent events/log.

**Diagnosis + fix:** Not a crash — the cycle was blocked at the interactive profile's blocking human-gate, which fired at `problem_selection` *immediately* after seeding (before any visible work), with confusing "problem_selection → problem_selection" wording. Backend was healthy (deadlock fix holds); confirmed a pending `ApprovalRequestMsg`. Fixed `configs/interactive.yaml` → `human_gate_points: []` so blocking mode now gates only at the 4 meaningful PHASE transitions (ideation→planning, …), never immediately. Restarted on fast.yaml (hands-off) to clear the stuck cycle; the running backend baked the old config so a restart was required to load the fix.

---

### Prompt 90 — "Is it stuck again? Can you check?"

> Is it stuck again? Can you check?

**Investigating:** on fast.yaml now (no gates), so a different cause if stuck. Checking health responsiveness, running session progress (event growth over a window), pending approvals, and recent activity/log.

**Root cause + fix:** Not a gate — the cycle was CRAWLING on arXiv. arXiv is hard-throttling this IP (429/timeouts, from heavy session testing; live `curl` → HTTP 000 after 8s). The Prompt-84 retry/backoff was too patient — each literature call took 1–2 min before degrading, so the cycle inched forward (~2 min/event). Added a **circuit breaker** to `arxiv.py`: after 2 fully-failed calls the circuit opens for 120s and subsequent calls fail INSTANTLY (no network/retry/backoff) → the cycle proceeds fast on cached corpus + other sources; a success closes it. Also snappier detection (timeout 30s→15s, per-call retries 3→2). +2 tests; full suite 1449 green.

---

### Prompt 91 — Plan: alternative literature-injection methods (MCP server, less PDF)

> We also need to think about different ways to inject literature. For example via a MCP server. We did a bit of reading about this in the past, wondering if we have something in our literature survey. Anyway, we should do some planning about this as it could help speeding up and reducing tokens (downloading and reading PDFs is clunky)

**Task:** Planning (no impl yet). Survey what we already have (literature synthesis + MCP paper-lookup notes), audit the current PDF-heavy literature flow, and propose token/speed-efficient literature-injection options (MCP literature server, structured-API/abstract/TLDR-first, summarize+cache, fetch-by-id) with tradeoffs + a recommended plan.

---

### Prompt 92 — Explore available literature MCP servers (D10 groundwork)

> Let's do 2. Let's first explore what MCP servers for literature are available

**Task:** Web-research the current landscape of literature/research-paper MCP servers (arXiv, Semantic Scholar, PubMed, alphaXiv, Paperclip, PaperQA/FutureHouse, etc.) — transport (stdio vs hosted HTTP), coverage, content shape (raw PDF vs pre-digested), auth, license/offline-ability — and assess fit for the orchestrator-as-MCP-client SourceProvider (offline-additive). No code yet.

---

### Prompt 93 — Prototype alphaXiv as an MCP-client SourceProvider

> Let's start with alphaXiv (and keep nanyang12138/Academic-MCP-Server as a future option) and prototype as an MCP-client SourceProvider

**Plan:** Build `literature/mcp_provider.py` — orchestrator-as-MCP-client (deterministic), wrapping the alphaXiv hosted MCP server as a `SourceProvider` behind the existing abstraction (offline-additive, flag-gated). search()→alphaXiv search tool; fetch()→get_paper_content (structured breakdown, not raw PDF). Config block in LiteratureConfig + provider_factory wiring. Deterministic unit tests with a fake MCP ClientSession. Keep Academic-MCP-Server (PubMed/bioRxiv/etc.) as a future provider. First confirm alphaXiv connection (URL/transport/auth/tool names) + `mcp` SDK availability.

**Done — MCP-client SourceProvider prototype.** New `literature/mcp_provider.py` (`MCPSourceProvider`): orchestrator-as-MCP-client over streamable HTTP, **discovers tools at runtime** (`list_tools()`) and matches them by heuristic (search vs embedding vs get_paper_content) with config overrides, parses results defensively (structuredContent → text-JSON), normalizes to `SourceResult`/`SourceDocument` (prefers alphaXiv's pre-digested breakdown/tldr over raw abstract). Optional/additive: `LiteratureConfig.mcp` (default OFF; alphaXiv `https://api.alphaxiv.org/mcp/v1`, `ALPHAXIV_API_KEY` Bearer); wired in `provider_factory` only when enabled; `mcp` is an optional pyproject extra (lazy-imported). **Finding:** alphaXiv MCP requires auth (bare connect → 401), so live use needs an alphaXiv API key. Deterministic offline tests (+10, fake ClientSession); full suite 1459 green; ruff clean. Next: set ALPHAXIV_API_KEY + enable to smoke-test live, then tune the normalizer against real alphaXiv responses. Academic-MCP-Server (PubMed/bioRxiv) kept as a future provider behind the same class.

---

### Prompt 94 — alphaXiv MCP API key: can't find how to create one

> Can't seem to find a way to create an API key. Here's their doc page, any hints? https://www.alphaxiv.org/docs/mcp

**Task:** Read alphaXiv's MCP doc page; determine the real auth mechanism (likely OAuth 2.1 browser flow, not a manually-created static API key) and how a deterministic Python MCP client should obtain/use the token.

**Done — alphaXiv OAuth wired.** Probed the 401: alphaXiv MCP is **Clerk OAuth 2.1, no static API key** (`authorization_uri=clerk.alphaxiv.org`, scope `email profile`); Clerk advertises a `registration_endpoint` (dynamic client registration works) + `refresh_token`/`offline_access`. New `literature/mcp_auth.py`: `FileTokenStorage` (caches token+client-reg under `~/.paradigm/mcp/<name>/`, 0600), `build_oauth_provider` (headless = never opens a browser → degrades; interactive = browser + one-shot localhost callback server), `interactive_login`. `MCPSourceProvider` gains `auth_mode` (oauth|bearer|none); oauth builds the OAuthClientProvider with the cached token (headless auto-refresh). Config: `MCPLiteratureConfig.auth_mode` + `oauth_scope="openid profile email offline_access"` (offline_access → refresh token for headless). New CLI: **`paradigm mcp-login`** (one-time browser login). +6 tests; ruff + full suite **1465** green. User runs `paradigm mcp-login` once → headless thereafter.

---

### Prompt 95 — "not to have to log in for every session?"

> Is there a way to not to have to log in for every session?

**Answer:** Already one-time — not per session. `mcp-login` caches the token + refresh token + client registration to `~/.paradigm/mcp/<name>/` (0600); the orchestrator loads it on every connect and the MCP OAuthClientProvider auto-refreshes via the refresh token (offline_access scope) with no browser, across cycles and process restarts. Re-login only if the refresh token expires/is revoked or the cache is deleted. alphaXiv/Clerk supports only authorization_code + refresh_token (no client_credentials machine-token), so the single interactive bootstrap is unavoidable — but for a headless server you can log in once on any machine and copy `~/.paradigm/mcp/alphaxiv/` over. (No code change needed.)

---

### Prompt 96 — "Done. Can we try if it works?"

> Done. Can we try if it works?

User completed `paradigm mcp-login` (after activating the conda env). Running a live smoke test of `MCPSourceProvider` against alphaXiv: list_tools → search → fetch, capturing real response shapes to tune `_to_source_result`/`_to_source_document`.

**Outcome — alphaXiv MCP live & tuned.** Login worked (token cached, `0600`). Live probe revealed the real API: search tool is `discover_papers` (required args `keywords: array`, `question: string`, `difficulty: number 1-10`) returning a **plain-text** numbered listing (`N. [ID=<arxiv_id>] **title**. Published <date> [by <affils>]: <abstract>`), and `get_paper_content` takes a `url`. Tuned `MCPSourceProvider` (still generic): (1) schema-driven search-arg builder (`_build_search_args` fills args by role+type — keywords/question/difficulty/limit), (2) numbered-listing text parser (`_parse_text_listing`) as a third fallback after structuredContent/JSON, (3) url-aware id coercion in `fetch` (bare arXiv id → abs URL), plus control-char scrubbing and the "by" clause kept as **affiliations** (not mislabeled as authors). Added `search_difficulty` config (default 3). Verified end-to-end live: `search()`→4 clean `SourceResult`s (incl. old-style `astro-ph/…` ids), `fetch()`→46 KB document. +9 tests; full suite **1474 passed**, ruff clean.

---

### Prompt 97 — "enable the mcp and run the platform"

> can you enable the mcp and run the platform. Then I'll try an experiment

Enabling `literature.mcp.enabled: true` in the interactive config and launching the platform (backend + frontend) for a live experiment.

---

### Prompt 98 — "stuck, arXiv rate-limited — maybe drop arxiv?"

> It seems stuck. It says arXiv rate-limited. Maybe we don't want arxiv anymore?

Investigating: is the cycle actually blocked on arXiv or fast-failing via the circuit breaker? Considering routing interactive-config literature through alphaXiv MCP (which serves the same arXiv content, pre-digested) to avoid the rate-limited IP.

**Root cause — NOT arXiv itself.** The backend's `Corpus` (`session_manager.py`) was built with **no `source_providers`**, so the GUI literature pipeline always hit `Corpus._search_legacy` (direct `ArxivClient`) and silently ignored every configured provider — including the alphaXiv MCP I'd just enabled. The CLI (`main.py`) wires providers via `create_source_providers`; the backend never did. So: (a) alphaXiv could never participate in the GUI, and (b) the "arXiv rate-limited" error FLOOD came from the legacy path letting `ArxivUnavailable` propagate to `orchestrator/literature.py:log_error` (the provider path swallows a failing provider at `corpus.py:251`). Fix: wire `create_source_providers(...)` into `session_manager._run_cycle` (load domain profile first; pass `source_providers` + `topic=seed_prompt`). Verified: provider build → 8 providers incl. `alphaxiv` (MCPSourceProvider); `corpus.search(provider="alphaxiv")` → 4 `[alphaxiv]` results. 249 relevant tests pass; backend restarted on interactive config. The wiring fixes BOTH symptoms (alphaXiv now feeds literature; arXiv fails fast+silent via the breaker, no flood).

---

### Prompt 99 — agent refuses to do work + platform unresponsive / unclear state

> It says **I will not propose placeholder experiments or fabricate citations.** Would you like me to instead help structure an experimental workflow once you have access to the actual data and literature? - But I don't know how to steer. In general one issue with the platform is that it's very unresponsive and it's not obvious when something is happening, when nothing is happening, and when a human input is needed / possible.

Two issues: (1) an agent punted to the human (likely literature-starved — now fixed — and/or over-cautious prompt); (2) core UX gap: no clear system-state signal (working / idle / awaiting-human). Investigating current interaction model + status UI before proposing a plan. No restarts.

**Outcome — responsiveness + real steering (both in one pass).** Root finding while diagnosing: free-text steering was a no-op — `ws.py` dropped `user_message`/`user_intervention` on TODOs; and the "live" dot pinged regardless of actual activity. Fix, Part B (steering): per-session guidance inbox (`SessionManager._guidance` + `queue_user_guidance` + `_make_guidance_provider`), engine `guidance_provider` drained at each round boundary (`_drain_guidance`) and injected as a top-priority "HUMAN GUIDANCE" block into agent prompts (cleared after the round), `EventType.USER_GUIDANCE` + `display.info` narration, immediate "received — applies next round" ack; no-op for the CLI. Part A (visibility): store `lastActivityAt` on every message; `useSystemState` hook derives working/thinking/awaiting/paused/stalled/done/… on a 1s heartbeat (stalled = >35s idle while running); new `StatusPill` (color+label+hint) in the session header; `NowPlaying` pings only when truly live; InteractionBar placeholder signals steering applies next round. +4 tests; full suite 1478 pass; ruff clean; frontend tsc + vite build clean. Backend auto-reloaded (uvicorn --reload), frontend HMR — no manual restart.

---

### Prompt 100 — raise stalled threshold to 120s

> Let's change stalled to be no activity for more than 120s

Bumping `STALL_MS` 35s → 120s in `useSystemState.ts` (thinking band widens to 12–120s). Long model calls / literature searches no longer flagged as stalled.

---

### Prompt 101 — make agent messages readable (markdown/typography like Claude)

> The formatting of the messages is really hard for a reader to parse. Is there a way to make it more intelligible / easy to digest? For example using the same strategy that claude does when providing a description of the workflow in CLI or even on the web interface (fonts, colors, formatting, even md)?

Agents emit markdown (+ LaTeX math per SPEC). Investigating current MessagesPanel rendering → add proper markdown + math rendering with readable typography/role-coloring.

**Outcome — messages now render as rich markdown.** Root cause: live `MessagesPanel` rendered raw `out.content` in a `<p>` (whitespace-pre-wrap), so markdown showed as literal `**`/`##`/`$…$`. (Deps react-markdown/remark-gfm/remark-math/rehype-katex/katex were already installed + KaTeX CSS imported, just unused in the message stream; no @tailwindcss/typography, so `prose` is a no-op.) Added `components/shared/Markdown.tsx` — reusable, memoized (re-parses only when source changes → streaming stays cheap), remark-gfm + remark-math + rehype-katex (`throwOnError:false` for partial-stream safety), with an explicit Observatory-themed element map (serif H1, sized headings, bulleted/numbered lists, inline + fenced code, blockquotes, tables, cyan links, KaTeX math). Wired into MessagesPanel (body 12.5px, brighter `foreground/85`). tsc + vite build clean.

---

### Prompt 102 — loop stuck silently during review

> Somehow the research loop got stuck during review silently. Can you check what happened?

Investigating read-only (NO restart — live session must not be killed): backend.log + events.jsonl tail, focus on review/peer-review phase, look for swallowed exceptions / awaited gate.

**Diagnosis — it wasn't stuck; it completed silently.** events.jsonl: writing → assembly → `internal` (editor review → writer revision → editor review) → `state_change cycle_complete` (elapsed 1334s, 237k tokens) at 17:49:46. A paper (paper-56ec183fd171) was produced and is viewable. Root cause of the "stuck during review" perception: `_run_cycle`'s terminal branches set `state.status` (COMPLETED/ABORTED/FAILED) and sent only a NotificationMsg — they never broadcast a `SessionStateMsg`, so the frontend `status` never left "running"; with the new StatusPill that reads as Working → (120s) Stalled, sitting on the last review message = looks like a silent hang. Fix: broadcast the terminal status from the `finally` block (covers all 3 terminal states; structural msg → buffered, so reconnects see it too). +4 regression tests; full suite 1482 pass; ruff clean. (Secondary, not yet fixed: a long *non-streamed* review generation emits nothing until done, so a >120s turn can briefly show "Stalled" — would need a backend "agent working" heartbeat.)

---

### Prompt 103 — terminal GUI action + resumable/continuable cycles

> When the process finishes (regardless of the reason) there should be a clear action on the GUI. Either show the final product (paper) or give a summary of what happened and why the process didn't converge. In the latter case, there should always be a way to continue the research process from an unfinished point (for example if the internet connection dropped, we should be able later on to restart from the unfinished experiment which should be logged somewhere as such -- eg in the research tab. We should also be able to restart with some comments and user steering)

Big feature. Part A: clear terminal action (view paper | failure/non-convergence summary). Part B: resumable cycles — mark interrupted runs, surface in research tab, continue from checkpoint with optional steering. Investigating current checkpoint/resume/status architecture before planning. Read-only.

**Plan + decision (Phase 1 first).** Confirmed gaps: no terminal/completion screen; `_cycles` is in-memory (research tab wiped on restart); engine always starts fresh (no resume anywhere); checkpoints are summary-level. Proposed 3 phases (1: terminal action/summary; 2: persist cycles + auto-mark interrupted; 3: checkpoint-resume + steering). User chose **"Terminal screen first"** — building the end-of-run screen (View Paper on success | non-convergence summary + a Resume affordance for Phase 3), deferring the resume foundation+engine.

**Outcome — Phase 1 (terminal screen) done.** Backend `_enrich_cycle` backfills live status + thread_id + paper_id onto the in-memory cycle (it was only written at start → research tab showed every cycle "running" forever and never learned its paper); wired into list + get (+4 tests). New `TerminalScreen` (frontend): on terminal status shows outcome (complete / finished-no-paper / failed / stopped) + one-line summary + stats (phase reached, rounds, elapsed, tokens, papers) + actions — **View paper** (converged), **Resume** (disabled "soon" → Phase 3), **Back to research**; mounted in SessionView above the panels. `PapersPage` gains `?paper=<id>` deep-linking. Full suite 1486 pass; ruff + tsc + vite build clean. Phases 2 (persist cycles + mark interrupted) and 3 (checkpoint-resume + steering) tracked in tasks/todo.md.

---

### Prompt 104 — Phase 2: persist cycles + mark interrupted

> Yes, let's move into phase 2

Persist research cycles to the DB (survive restart), add list/reconstruct, and on startup mark orphaned running/paused cycles as `interrupted` so unfinished runs are visible + labeled in the research tab. Capture thread_id for Phase-3 resume.

**Outcome — Phase 2 (persist cycles + mark interrupted) done.** New DB `cycles` table + CRUD + `mark_running_cycles_interrupted()` (flips only running/paused → interrupted, leaving pending/completed). `CycleStore` service (DB-backed; in-memory fallback shares research._cycles so demo paths keep working), wired into the lifespan which calls `mark_interrupted_on_startup()`. Migrated research.py + sessions.py to the store; session_manager now persists the terminal cycle row (status + thread_id read from `engine.state` so it survives a mid-run drop, not just clean completion, + paper_id from the thread) in the finally. `CycleStatus.INTERRUPTED` + amber StatusBadge + CycleCard shows the phase reached. Net effect: the research tab survives restart, and a cut-off run shows as **Interrupted** (resumable in Phase 3) instead of perpetually "running". +6 tests; full suite 1492; ruff + tsc + vite build clean.

---

### Prompt 105 — Phase 3: checkpoint-resume + steering

> Yes [proceed into Phase 3]

Resume an interrupted/terminal cycle from its last checkpoint, continuing from that phase, with optional steering. Investigating engine phase sequence to find the resume hook, then wiring engine resume param + POST /resume endpoint + Resume button.

**Outcome — Phase 3 (resume + steering) done.** Decided AGAINST mid-phase engine re-entry (phases have hard state deps: world_model, selected_hypotheses, draft — unsafe with summary-level checkpoints). Instead resume reuses the Phase-99 guidance inbox: `POST /api/v1/research/{cycle_id}/resume` (optional `comment`) builds a continuation note from the prior thread's checkpoint (hypothesis/findings/open-questions/next-steps/summary) + the operator's steering, creates a fresh linked continuation cycle (`resumed_from` — new DB column + model + store passthrough), starts it, and queues the note as first-round guidance so the team continues the established direction. Works for interrupted/failed/aborted AND completed ("extend further"); falls back to a bare continuation when no checkpoint/thread_id. Frontend: `resumeCycle()` client; TerminalScreen Resume button + inline steering textarea (navigates to the new run); CycleCard quick-Resume for resumable statuses + "continues an earlier run" lineage; cycleId threaded SessionPage→SessionView→TerminalScreen. +5 tests; full suite 1497; ruff + tsc + vite build clean. Resume route live in OpenAPI. Checkpoint-granularity (re-derives forward with prior context), not exact mid-experiment replay — set with user up front.

---

### Prompt 106 — start a new run

> let's start a new run

Platform already running (no restart). Checking auth + interactive gate config to decide how to kick off + what to expect.

---

### Prompt 107 — "Clearly something went wrong"

> Clearly something went wrong

Investigating read-only: backend.log tail + recent events for errors/tracebacks after a run start.

**Diagnosis + fix — empty team = zero agents.** The new run (cycle-87df0bcf, seed = an LRD review prompt) finished in 3.6s with 0 tokens because it ran with `team_roles: []` → `create_team([])` → ZERO agents → every phase produced nothing → writing died with ValueError "insufficient content (0 chars < 10000)". Two bugs: (1) engine `run_research_cycle` only defaulted the team on `team_roles is None`, so an empty list bypassed the fallback — fixed to `if not team_roles:` (empty OR None → default/profile roles). (2) SetupWizard sent `[]` when ALL roles were deselected (`roles.length === ALL_ROLES.length ? null : roles`) — fixed to also send null when `roles.length === 0`. +2 regression tests (team=[] and None → non-empty team). Full suite 1499; ruff + tsc clean.

---

### Prompt 108 — plan: make the platform accessible from the web

> Before we do that, I would like to make a plan on how to make the platform accessible from the web

Planning task (no code yet). Taking stock of deployment-relevant state (CORS, auth, frontend serving, Docker, secrets, sandbox), then clarifying audience/scale + security + hosting to produce a phased deployment plan.

---

### Prompt 109 — "let's go" (begin Phase 1 of web deployment)

> let's go

Wrote the plan to .planning/WEB-DEPLOYMENT.md. Starting Phase 1 (make-it-deployable) with the recommended defaults: single VM + Caddy + on-host systemd backend; production.yaml with non-blocking gates + experiments enabled (hardened sandbox); host/domain left as deploy-time placeholders. Phase-1 code: max_concurrent_sessions cap + sandbox hardening (pids_limit/cap_drop), plus Caddyfile, systemd unit, .env template, production.yaml, deploy runbook.

**Outcome — Phase 1 (make-it-deployable) done.** Code: (1) concurrency cap — `SessionManager.max_concurrent_sessions` + `at_capacity()`/`active_session_count()`; both run entry points (start_session route + resume endpoint) return HTTP 429 when full; overridable via `PARADIGM_MAX_CONCURRENT_SESSIONS` (wired in main.py lifespan). (2) sandbox hardening — `SandboxConfig` gains `pids_limit`/`drop_capabilities`/`no_new_privileges`/`read_only_rootfs`, applied in `sandbox/docker.py` create (cap_drop=ALL, no-new-privileges, pids_limit). Ops artifacts: `configs/production.yaml` (non-blocking gates, streaming, mcp on, experiments-on-hardened + disable toggle), `deploy/Caddyfile` (auto-TLS + basic_auth + serve dist + proxy /api/WS), `deploy/paradigm-backend.service` (single-proc systemd, on-host to avoid the sandbox sibling-container path gotcha), `deploy/.env.production.example`, `deploy/DEPLOY.md` runbook, `.gitignore` (.env.production + .paradigm/). +3 guardrail tests; full suite 1502; ruff + tsc clean. Frontend served same-origin → no API/WS URL env needed. Phases 2 (provision/deploy) + 3 (operate) are in DEPLOY.md, executed on the VM.

---

### Prompt 110 — production models (Claude + OpenAI/Gemini, FAST), hide orchestrator bar, GUI cleanup

> As we prepare for deployment ... revert production to Claude and OpenAI or gemini (check API keys are all there) ... most important thing I need right now is speed ... ideas on which models to use for the different agents ... hide for now the orchestrator bar ... showing the automatic part and getting to a final paper is more important. Do also a thorough cleanup of the GUI so that it looks great

Multi-part: (1) production.yaml → Claude + OpenAI/Gemini (drop Together/Llama), speed-optimized per-agent models; verify keys. (2) Hide the InteractionBar for the demo. (3) Thorough GUI polish.

**Outcome — demo prep.** (1) Models: verified GEMINI key works live (gemini-2.5-flash ~1.0s, gemini-2.5-flash-lite ~0.37s; 2.0-flash is 404/removed). production.yaml now Claude + Gemini (Together/Llama dropped): bulk roles (theorist/analyst/experimentalist/skeptic) on gemini-2.5-flash-lite, synthesizer/editor on gemini-2.5-flash, writer on claude-haiku-4-5 (paper quality). Set max_rounds_per_phase 2→1 for speed; noted experiments as the main remaining time/risk lever. (2) Hid the InteractionBar in SessionView behind SHOW_INTERACTION_BAR=false (reversible) — foregrounds the autonomous flow for the demo. (3) GUI: session header now shows the research topic (truncated, via cycle.seed_prompt through SessionPage→SessionView). Chrome (Header/Sidebar/Observatory system) is already cohesive — left it, inviting the user to point at specific rough surfaces rather than sweeping a good design blind. tsc + vite build clean; suite 1502.

---

### Prompt 111 — "yes please restart"

> yes please restart

Restarting the local backend+frontend onto configs/production.yaml (fast Claude+Gemini, 1 round, hidden bar). Verifying keys load + health, no run kicked off.

---

### Prompt 112 — irrelevant papers in literature results

> a lot of the papers returned are not relevant for the research project. Can we look into why is the case?

Diagnosing literature relevance: which providers get queried (domain router), whether results are relevance-filtered/ranked at all, and the empirical papers from recent runs. Suspect: off-topic providers (pubmed/biorxiv on an astro topic) and/or no per-result relevance threshold.

**Diagnosis + fix — irrelevant literature.** Root cause: the domain router ranks/skips PROVIDERS by topic (pubmed/biorxiv correctly skipped for astro), but there was NO per-RESULT relevance filtering — each provider's top-N (esp. broad google_scholar/semantic_scholar keyword matches) was aggregated and injected into agent context as-is, query ordering trusted. Fix: `Corpus._rerank_by_relevance` semantically re-ranks the aggregated pool by cosine similarity of each result's title+summary to the query (Chroma default MiniLM embedder, lazy+cached) and drops results below `literature.relevance_threshold` (default 0.25), with `relevance_min_keep` (default 3) as a starve-guard; fails open if embeddings unavailable. Wired into `_search_via_providers`; logs `candidates`/`relevance_dropped`. Validated empirically: relevant titles 0.58–0.74 cosine, loosely-related <0.10, off-topic ≤0.05 — clean separation at 0.25. Domain-agnostic. +3 tests; full suite 1505; ruff clean. Backend auto-reloaded → applies to the next run.

---

### Prompt 113 — agent icons in the agents/token area + Theorist = lightbulb

> In the agents area (where token usage is shown) ... have the icons showing which agent is what. Overall the icons should be always used next to the text/thing an agent is doing. The Theorist Icon should be the light bulb, not the telescope.

GUI: ensure per-agent icons (from AGENT_THEMES) appear in the agents/token panel + everywhere an agent is referenced; change theorist icon telescope→Lightbulb.

**Outcome — agent icons.** Theorist icon Telescope→Lightbulb in AGENT_THEMES (flows to every agent reference). Session "Agents" panel now shows each agent's cumulative token usage (Coins icon + formatTokens, summed per agentId from agentOutputs) next to its role icon. Added role icons where agents were referenced as bare text: NowPlaying (active-agent label), DraftPanel (section author), and per-message token counts in MessagesPanel (next to the model). tsc + vite build clean.

---

### Prompt 114 — push all new changes to main

> Can we push all the new changes to the main branch of paradigm? ... before we set it as a cloud service

Consolidating the work branch into main before deployment. Assessing branch/commits/remote + handling pre-existing uncommitted changes and the user's local artifacts (PROMPT-*, data_validate/, pdf) which must NOT be committed.

---

### Prompt 115 — how to start the platform on Hetzner; crontab?

> I got the Hetzner service and deployed there. How do I get the platform started? Do I need to add something to the crontab?

Answer: no crontab — use systemd (paradigm-backend.service: enable --now = start now + on boot; Restart=always = auto-restart) + Caddy as a service. crontab only useful for the optional nightly data-dir backup. Provided start + verify commands + the common gotchas (docker group, conda-vs-venv ExecStart, .env.production, prereq build steps).

---

### Prompt 116 — Caddy default "congrats" page; make Paradigm serve

> If I go to paradigm.stellarphysics.org there's a caddy congrats page. So the web server is working. Just need to have paradigm work there

Caddy is running on its DEFAULT config (welcome page), not the Paradigm Caddyfile. Need: backend up on :8000 + frontend/dist built, then install the Paradigm Caddyfile (domain paradigm.stellarphysics.org, basic_auth, serve dist, proxy /api) at /etc/caddy/Caddyfile + reload. Provided concrete filled-in Caddyfile + prereq checks + troubleshooting (502=backend down, blank=dist missing).

---

### Prompt 117 — how do I start paradigm (on the VM)

> Ok. I need to start paradigm. How do I do that?

Found a critical DEPLOY.md bug: install said ".[mcp]" but the backend's fastapi/uvicorn are the `api` extra and Gemini needs `openai` → fixed to ".[api,mcp,openai]". Gave: correct install, a manual foreground uvicorn run to see errors, then systemd enable --now for permanence.

---

### Prompt 118 — "API offline" in the deployed GUI

> the platform shows up. I am trying to run a cycle but it says API offline

The frontend health-checks /health (root), but the Caddyfile only proxied /api/* → /health hit the static server → "API offline". Fixed deploy/Caddyfile matcher to `@api path /api/* /health`. (Actual /api/v1 calls were already proxied.)

---

### Prompt 119 — deployed GUI still "API offline"

> API still offline

Two deploy bugs found: (1) frontend WS URL hardcoded :8000 in its fallback (`window.location.hostname}:8000`) → unreachable behind the proxy; fixed to same-origin `window.location.host` (|| so empty env falls through). Dev still uses VITE_WS_BASE_URL override. (2) The "API offline" indicator = /health proxy — gave curl diagnostic to isolate Caddy reload vs browser cache. WS fix needs a frontend rebuild on the VM.

---

### Prompt 120 — detailed deployment guide

> Can you make a detailed md file with the deployment instructions? So that we can easily redo it ... and/or fix issues

Deployment succeeded (Hetzner/Ubuntu 24.04 + Caddy + systemd). Rewrote deploy/DEPLOY.md as the battle-tested guide: full ordered steps + a "gotchas we actually hit" table (python3.12-venv, .[api,mcp,openai] extras, .env.production, User=root, Caddy /api/* AND /health, the WS :8000→same-origin rebuild, npm from frontend/, the lib gitignore fix) + operating/backup/hardening sections.

---

### Prompt 121 — cycles aborting right after start (deployed)

> I am getting a lot of aborted cycles right after starting on the platform

ABORTED = session task cancelled. Tracing what cancels it: backend abort/cleanup paths + WS-disconnect handling, and frontend abort triggers (on unmount / WS failure). Suspect the WS can't connect through Caddy basic_auth → reconnect/unmount churn → abort, or a disconnect-triggered cleanup.

**Diagnosis (in progress).** Screenshot confirms a REAL cycle (gemini-2.5-flash-lite, user's CRISPR prompt, 1.1k real tokens, real [SEARCH:] request) that gets ABORTED ~12s into ideation, right after the theorist's first step. The "Demo" badge is cosmetic: config/mode sets testing_available = (len(testing_overrides)>0); production.yaml has none → Header hard-coded "Demo". FIXED Header to show "Live" when mode=production ("Demo" only when config is None). ABORTED = task cancelled; callers are shutdown() (SIGTERM/restart), delete_research_cycle, ws client abort. Need the VM journal to see which — suspect backend restart (OOM?) during the first literature search (chromadb/embedding model load). Awaiting journalctl.

**ROOT CAUSE of the aborts (from VM journal): the alphaXiv MCP provider.** No OAuth token on the VM → on the theorist's first [SEARCH], the MCP client's OAuth raised "needs interactive login", and its anyio teardown threw `RuntimeError: Attempted to exit cancel scope in a different task` wrapped in a `BaseExceptionGroup`. `BaseExceptionGroup` is NOT an `Exception`, so it escaped the corpus's `except Exception` provider guard and cancelled the whole cycle → ABORTED ~12s into ideation, every time. (Backend stable 2h/210MB — NOT memory/restart. The WS 403 flood = frontend retrying a deleted session, separate noise.) Fix: (1) `configs/production.yaml` literature.mcp.enabled → false (no token on the VM anyway). (2) Hardened BOTH corpus provider-search guards: `except asyncio.CancelledError: raise` then `except BaseException: log+skip` — a flaky provider can never abort a cycle again. +2 regression tests; full suite 1507. Also fixed the misleading "Demo" header label (commit prior). User applies on VM: `git pull && systemctl restart paradigm-backend` (no frontend rebuild needed for the abort fix; rebuild only for the Header "Live" cosmetic).

---

### Prompt 122 — make alphaXiv MCP work on the VM

> wait, I want alphaxiv mcp to work. So how do I make it work on the VM?

Re-enabled mcp in production.yaml. Robustness: MCPSourceProvider._ensure_session now pre-checks storage.has_tokens() in oauth mode and fails cleanly + fast (no streamablehttp connection → no anyio BaseExceptionGroup) when no token. systemd unit sets Environment=HOME=/root so $HOME/.paradigm/mcp/ resolves for the root service. User steps: run mcp-login on a browser machine, scp ~/.paradigm/mcp/ to /root/.paradigm/ on the VM, git pull, re-cp the unit (HOME), daemon-reload, restart.

---

### Prompt 123 — experiments halt: paradigm-sandbox:latest image not found

> the execution halts after the experiments ... the paradigm-sandbox:latest Docker image was not found

Missed deploy step (Step 4): the sandbox image was never built on the VM, so experiments skip (graceful — the platform reported it cleanly, didn't crash). Fix: build it. Updated DEPLOY.md to use `docker/` as the build context (Dockerfile has no COPY → avoids sending the whole repo) + marked it REQUIRED. User runs: `docker build -t paradigm-sandbox:latest -f docker/Dockerfile.sandbox docker/`, no restart needed.

---

### Prompt 124 — agents shown as bare numbers; add icons/names + calls + tokens

> add the agents icons and names when showing their total number of calls and tokens used ... don't understand the number succession next to Ideation

ROOT CAUSE: agent ids are `${role}-${index}` ("theorist-0") but getAgentRole returned parts[LAST] = the index ("0") → numeric labels, generic icons everywhere (AgentPanel, NowPlaying "number succession", Messages, Draft). Fixed getAgentRole to strip the trailing numeric index → return the role. Reworked AgentPanel: role icon + role name + "N calls · M tokens" (calls = per-agent message count; tokens = summed), dropped the confusing/inconsistent activity subtitle. The NowPlaying agent labels now resolve to role names+icons too (fixes the "number succession"). tsc + build clean. Frontend change → needs `npm run build` on the VM.

---

### Prompt 125 — literature: 70 "read" but 0 in the found bar; XAI papers contaminating an LRD run

> More importantly, in the latest run I am seeing issues with the literature search. I do see 70 papers should have been read, but I see zero in the literature found bar. I am wondering if this is because I toggled a bunch of features (see snapshot). [+ a long agent log from a JWST "Little Red Dots" run + a Settings screenshot]

ROOT CAUSE (from the agent log, not the toggles): a feedback trap. The agents issue over-constrained boolean queries (`"JWST LRDs" AND "thermal emission" AND "5000 K" AND "dense gas"`) that return **0** results. When keyword search returns nothing, `literature.py` injected a **"You MUST use [FOLLOW: arxiv_id]/[CITED_BY:] — do NOT [SEARCH:]"** warning — but the discovered-papers list was empty, so the agents **invented** arXiv IDs (`"Let's assume 2303.11111"`). Those hallucinated IDs resolve to **real-but-unrelated papers (eXplainable-AI / XAI)** whose references then poisoned the shared literature context. "0 in the found bar" = genuine searches found nothing (the bar counts search/follow/cited-by hits); "70 read" = the volume of FOLLOW/READ attempts on made-up IDs.

The toggles are mostly a red herring for this. But note: `production.yaml` has citation grounding / novelty / seed-discovery OFF (speed); the screenshot shows them ON (GUI override). All three need PERPLEXITY_API_KEY — without it on the VM they no-op (seed discovery logs "PERPLEXITY_API_KEY not set" and ingests 0, and it doesn't even increment the found bar). They add latency + failure surface; recommend OFF for the demo unless the key is set.

FIX (src/paradigm/orchestrator/literature.py): (1) Never force [FOLLOW:] when nothing's been discovered — `_build_stall_hint` + new `_build_exhaustion_warning` branch: with real discovered IDs → "use [FOLLOW:] from the list, don't invent IDs"; with none → "broaden ONE [SEARCH:], do NOT invent IDs, note the gap." (2) New gate `_is_discovered_id` + `_note_rejected_id`: [FOLLOW:]/[CITED_BY:]/[READ:] now reject any arXiv ID not in `seen_paper_ids` (i.e. never returned by a real search/traversal) and leave the agent a rejection note. This blocks the hallucination→contamination loop at the source; legit graph traversal is unaffected (every ID in the "Discovered Papers" list is in `seen_paper_ids`). Tests: updated 6 mechanism/dedup tests to stub the discovery precondition; added `test_follow_rejects_undiscovered_id`. Full suite 1508 green, ruff clean. Backend change → `git pull && systemctl restart paradigm-backend` on the VM. Separately: the real fix for "0 papers" is making genuine searches return astro results — check the VM's provider availability (arXiv rate-limit/circuit-breaker, NASA_ADS_API_KEY, alphaXiv) and prefer simpler 1–2 term queries.

---

### Prompt 126 — tighten agent prompts to discourage over-constrained boolean searches

> Yes [tighten the agent prompts to discourage 4-term boolean AND queries that trigger empty searches]

Follow-up to 125: the empty searches that trigger the forced-FOLLOW trap come from agents writing 4–5 term `AND` queries. Updating the [SEARCH:] guidance the agents see to prefer 2–3 plain keywords, no boolean operators, broaden on empty.

---

### Prompt 127 — experiments still failing (NameError 'u', PermissionError on /data/workspace, dust_extinction missing)

> Other issue: we are still having problems with the experiments -- see this log [long EXECUTION-phase log: repeated `NameError: name 'u' is not defined`, `PermissionError` writing to /data/workspace/*.csv, dust_extinction not available → hand-rolled CCM89 spiral, agents giving up and proposing theoretical/synthetic fallbacks]

Three distinct EXECUTION failures to investigate: (1) code executes without its imports — agents treat experiments as a persistent notebook kernel but each runs fresh; (2) /data/workspace not actually writable despite the prompt claiming it is; (3) dust_extinction/extinction not in the sandbox image.

**FIXES (commit pending):**
1. **NameError `u`/`const`** — the auto-import preamble (`executor.py:_SCIENCE_PREAMBLE`) imported np/scipy/plt/pd but NOT astropy. Added `import astropy.units as u` + `astropy.constants as const` (try/except). Updated the EXECUTION prompt to say u/const are auto-imported (don't re-import) + each experiment is a FRESH process (not a notebook — variables don't persist; use /data/workspace files).
2. **PermissionError on /data/workspace** — `/data/workspace` + `/data/results` are bind-mounted from host dirs created by the backend (root on the VM); the container runs as non-root `sandbox`, so root-owned 0755 dirs → PermissionError. Added `_make_sandbox_writable()` (chmod 0o777) on both dirs after mkdir. The image's `chown sandbox /data` is overridden by the bind mount — this is the real fix.
3. **dust_extinction missing** — the prompt PROMISED photutils/specutils/dust_extinction/galpy/healpy/plotly/bokeh/tables/netCDF4/pyarrow but the Dockerfile installed NONE → agents hand-rolled a broken CCM89 and spiralled (14.4k tok). Added the reliable-wheel subset to Dockerfile.sandbox (photutils, specutils, dust_extinction, plotly, bokeh, tables, netCDF4, pyarrow; dropped galpy/healpy to keep the slim build compiler-free) and synced the prompt list to match + told agents to use dust_extinction's CCM89 instead of hand-rolling.

Tests: +2 (preamble astropy aliases, _make_sandbox_writable mode); full suite green. Apply on VM: `git pull && systemctl restart paradigm-backend` (fixes 1+2) AND **rebuild the sandbox image** for fix 3: `docker build -t paradigm-sandbox:latest -f docker/Dockerfile.sandbox docker/`.

---

### Prompt 128 — git pull blocked by local edits to deploy/paradigm-backend.service (VM)

> [git pull error: local changes to deploy/paradigm-backend.service would be overwritten]

Guidance only (VM ops). The repo file is a TEMPLATE; the running unit is the installed copy at /etc/systemd/system/. Safe sequence: diff + back up the file, `git stash push deploy/paradigm-backend.service`, `git pull` (fast-forwards), do NOT re-cp the template (installed unit already has root + conda ExecStart + HOME=/root). Optional: `git update-index --skip-worktree` to stop future conflicts.

---

### Prompt 129 — agent icons/numbers still old on the VM

> I am still seeing the old issue with the agent icons and numbers on the VM

Guidance only. Frontend change (commit 15f43dd) → needs `cd /opt/paradigm/frontend && npm run build` (Caddy serves the prebuilt dist/; a backend restart doesn't touch it) + hard-refresh. `npm ci` first if build errors.

---

### Prompt 130 — experiment failures round 2 (astropy API misuse + hallucinated module + unit spirals)

> Ok. I am still seeing experiment failures: [log: AttributeError const.k (should be k_B), astropy.modeling.models.Planck1D doesn't exist, `from spectral_fitting_tools import greybody_fit` hallucinated module, 540-line/12k-token unit-conversion spirals]

Basic bugs from 127 are GONE (rebuild worked). Remaining failures are gemini-2.5-flash-lite writing fragile scientific code: const.k vs const.k_B, non-existent Planck1D/BlackBody1D (it's BlackBody), inventing a spectral_fitting_tools module, and drowning in astropy.units B_nu<->B_lambda conversions. Fix: add astropy-gotchas + keep-it-simple + no-invented-imports guidance to the EXECUTION prompt; ALSO recommend bumping the experiment-writing role off flash-lite (the real bottleneck).

---

### Prompt 131 — assign a flagship Claude model to the experimentalist

> Maybe we assign a better model to the experimentalist. Like a flagship Claude model?

The flash-lite experimentalist is the root of the experiment failures. Bumping experimentalist (the code-writing role) to Claude Sonnet 4.6 in production.yaml (flagship-tier code quality at ~half Opus cost, faster — good for the retry loop). Opus 4.8 is a one-line swap if max reliability is wanted.

---

### Prompt 132 — CI failing on `ruff format --check` (28 files)

> CI is failing [ruff format --check would reformat 28 files]

CI runs `ruff format --check` (formatter, separate from the `ruff check` linter I'd been running). 28 files drifted — mostly pre-existing in files not touched this session; CI installs ruff UNPINNED (latest 0.15.16) while local was 0.15.4. Fix: match CI's ruff version, `ruff format src/ tests/`, and PIN ruff==0.15.16 (pyproject [dev] + lint.yml) so the unpinned-latest drift can't recur.

**Follow-up (Test Python 3.11/3.12 failing):** once the format check passed, the test step ran and exposed a PRE-EXISTING collection error: `ModuleNotFoundError: No module named 'fastapi'` in tests/test_cycle_enrichment.py + tests/test_resume_cycle.py (they import the backend). CI installed only `.[dev]`. Fix: CI now installs `.[dev,api]` so fastapi is present and the backend tests actually run. (The "Node.js 20 actions are deprecated" lines are a non-blocking GitHub warning — actions/checkout@v4 + setup-python@v5 are already latest; auto-migrates to Node24 by Sept 2026. No action needed.)

---

### Prompt 133 — rejected paper leaves the run stuck; need a terminal action (show paper/reason)

> Interestingly the paper was rejected. But the research ends up being stuck -- I think we need an action once rejected (like still show the final paper) [screenshot: editor desk_reject at Submitted, phase tracker stuck on "Submitted", "Stalled — No activity for 773s"]

Editor desk_rejected (LaTeX math-notation violations) at the Submitted gate, but the cycle didn't finalize → UI stalls in Submitted for 13min instead of a terminal screen. Need: (1) backend finalizes/broadcasts terminal status on reject; (2) frontend terminal action shows the final paper + rejection reason (+ resume/revise).

**FIXES (commit pending):**
1. **The stall (root cause):** after desk-reject the engine still runs `run_memory_generation()` (one LLM reflection per agent) with NO timeout — a stuck call left `run_research_cycle` never returning, so the session never finalized and the UI stalled forever (status stuck "running" → "Stalled"). Bounded reflection with `asyncio.wait_for(_REFLECTION_TIMEOUT_S=120)`; on timeout it's a non-fatal memory_error and the cycle finalizes. (Also protects the success path.)
2. **Desk-reject was invisible to the UI:** review.py transitioned state→REJECTED but never called `_display.phase_transition(REJECTED)`, and engine.py's desk-reject branch never called `_display.paper_rejected()` (unlike the peer-review path). Added both → tracker advances to Rejected + a "Paper REJECTED" notification.
3. **Terminal screen now handles rejection:** TerminalScreen treats `currentPhase==="rejected"` as a distinct terminal state ("Paper was not accepted" + View paper + "Revise & resubmit"), not a convergence. SessionPage refetches cycles on terminal status so `paper_id` (enriched from the thread) is present → "View paper" works for rejected papers.

Tests: +1 (hanging-reflection timeout guard); full suite 1510 green; frontend builds. Apply: `git pull && systemctl restart paradigm-backend` + `cd frontend && npm run build`.

---

### Prompt 134 — fix the LaTeX-notation desk rejection (writer enforce math mode + relax editor)

> yes [tighten the writer/editor prompt to enforce LaTeX math mode + relax the editor's desk-reject threshold]

Editor desk-rejected purely for Unicode math (α vs $\alpha$, × vs $\times$, log subscripts). Two fixes: (1) writer prompt — require LaTeX math mode, never Unicode math symbols; (2) editor desk_review — desk_reject only for FUNDAMENTAL issues, never fixable formatting/notation.

---

### Prompt 135 — reviewer icons + paper stuck in Peer Review (stalled)

> We need icons for the reviewers. Maybe a magnifying glass? Also not sure why the paper got stuck in review (it says stalled) [screenshot: 2 peer-reviewer agents with generic person icons; review gave major_revision; "Stalled 6282s" in Peer Review]

(1) peer-reviewer role has no AGENT_THEMES entry → generic icon; add a magnifier-on-document icon (distinct from skeptic's plain Search). (2) Stalled ~105min in Peer Review = same LLM-hang disease as the memory-gen stall (Prompt 133) but in the review/revision pipeline → need a per-call LLM timeout so NO single call can hang the cycle.

---

### Prompt 136 — broken figure links in paper, PDF never exposed, literature papers polluting the Papers tab

> Moreover, the figures in the md paper are not visualized (broken links). Also the pdf of the paper (when produced like in this case it should) is never exposed (there should be at least a link). Finally why are some papers from the literature ending up in the published papers tab (external)? [screenshots: paper viewer with broken Figure 6/9 images; Papers tab showing A&A 621/640/668/692 as "External" alongside the platform's own papers] Let's fix all these issues

Three issues: (1) paper md figures render as broken image links (figure files not served / paths not rewritten); (2) no PDF download link exposed even when a PDF is produced; (3) external literature citations (A&A IGW refs) appear in the Papers tab as "External" — should be excluded from the platform's own papers list.

**FIXES (commit pending):**
1. **External literature in Papers tab:** corpus stores ingested refs as papers with status="external" (for citation/dedup). The Papers "All" list now excludes them (papers.py list_papers, both demo + db paths) + fixes total/pagination. They never had a tab, so they should never show.
2. **Broken figure links:** paper md embeds `![Figure N](figures/<name>)` (relative). PaperViewer now renders a custom `img` that rewrites `figures/<name>` → paperFigureUrl(paperId, name) (the existing authed /papers/{id}/figures/{file} endpoint that FiguresTab already uses).
3. **PDF never exposed:** added `GET /papers/{id}/pdf` (serves a pre-built PDF, else compiles on-demand via journal.latex.write_paper_latex in a thread; 503 with a clear message if no LaTeX engine). Added has_pdf to artifacts. Frontend: "Download PDF" link in PaperExport (always shown; on-demand). production.yaml journal.enable_latex_output+compile_pdf → true (best-effort; .tex always written, PDF when a LaTeX engine is on PATH). VM needs `tectonic` (one static binary) for actual PDFs.

Tests +2 (artifact has_pdf/figures). Full suite 1516 green; frontend builds. Apply: git pull + restart backend + rebuild frontend; `apt install -y tectonic` (or cargo/binary) on the VM for PDFs.

---

### Prompt 137 — PDF link overlaps text; pre-compile PDF at cycle end (not on click)

> The link to the pdf needs to be placed in a better way -- currently overlapping with text. Also it took several seconds for the pdf to be produced, I wonder if the compilation could happen when the cycle ends, not when the user click on the pdf link (so it's ready)

(1) PaperExport's 3-button row (Copy/Download .md/Download PDF) overflows the 200px TOC sidebar → stack vertically. (2) Pre-compile the PDF at cycle end so the link is instant; the on-demand endpoint stays as a fallback for pre-existing papers.

---

### Prompt 138 — cycle fails immediately: Unknown role 'peer-reviewer' (+ alphaXiv token expired)

> I tried a cycle and it failed immediately [journal: ValueError: Unknown role 'peer-reviewer' in create_team; also alphaXiv MCP OAuth "needs interactive login" + anyio BaseExceptionGroup]. What I did was removing the experimentalist and using Explore instead of Directed. If I keep those things it works... There are a bunch of issues -- let's tackle

REGRESSION (mine): adding "peer-reviewer" to AGENT_THEMES (for the reviewer icon) made the team picker offer it as a selectable role, but "peer-reviewer" is a runtime agent_id, not a factory role → create_team raises. Fix: team picker must only offer composable roles (exclude reviewer/peer-reviewer/debate_judge); keep the theme map for display. Bug 2: alphaXiv OAuth token expired → re-login needed; cycle survives via the corpus BaseException guard but logs noise.

---

### Prompt 139 — disable alphaXiv; make Perplexity + arXiv work

> Let's flip alphaxiv, then also make sure perplexity and arxiv work

(1) production.yaml literature.mcp.enabled → false. (2) Perplexity: needs PERPLEXITY_API_KEY + the citation features (seed discovery / grounding / novelty) that use it — verify env var + enable. (3) arXiv: default provider, no key but rate-limited — verify it's on + working.

---

### Prompt 140 — keep alphaXiv (faster) with arXiv fallback; audit literature-graph features

> I would like to keep alphaxiv mcp if possible -- I think it's faster. Maybe we use arxiv as a fallback option? In the meantime I'll add the perplexity key. I know we had it -- including some fancier ways to look into literature graphs etc. Can you check?

Re-enable alphaXiv but make an expired/invalid token degrade cleanly to the other providers (arXiv etc.) without noise. Audit + report the literature-graph capabilities ([FOLLOW:]/[CITED_BY:]/[READ:]/[CHAIN:] + alphaXiv MCP tools).

---

### Prompt 141 — `paradigm mcp-login` fails: No module named 'mcp'

> [mcp-login] Login failed: No module named 'mcp'

The conda `paradigm` env HAS mcp; the user's `paradigm` CLI resolves to a different env without the extra. mcp_auth imports `mcp` lazily so the helpful ImportError handler is skipped → generic "Login failed". Fix: catch ModuleNotFoundError in mcp_login and print an actionable message (install paradigm[mcp] in THIS interpreter / use the conda env). Immediate fix for the user: run from the conda env.

---

### Prompt 142 — re-enable the CHAIN feature (multi-hop citation-graph traversal)

> I'll test while you re-enable the chain feature

[CHAIN: id depth=N direction=refs|cites|both] is fully dormant: parser + process_chain_requests + follow_citation_chain exist but process_chain_requests is never invoked + not documented. Wire it into the agent response loop, gate the seed id to discovered ids (no hallucinated seed amplified by depth), bound depth, document it, test.

---

### Prompt 143 — flood of WebSocket 403s in the journal

> can we check why we're getting all these 403 [journal: session-0481… WS 403 every ~30s for 10+ min; a real session connects fine; also Perplexity 401 + "Failed to parse checkpoint JSON"]

The 403s = a stale browser tab reconnecting forever to a session that no longer exists on the backend (deleted / lost on restart) → WS handshake 403 → frontend retry loop never gives up. Cosmetic noise, not a functional break (real runs connect). Fix: frontend should stop reconnecting once the session is gone. (Also visible: Perplexity 401 = bad/placeholder key; "Failed to parse checkpoint JSON" = resume fallback.)

---

### Prompt 144 — new Perplexity API key

> Ok I generated a new perplexity API key: [REDACTED]

No code change. Key goes in the VM's gitignored deploy/.env.production (overwrite the bad value that caused the 401), then restart. Secret NOT stored in repo; advised the user to rotate it since it was shared in chat.

---

### Prompt 145 — note GPT-5.4-mini for future + agents-tab model dropdown (future); update DEPLOY + user manual

> GPT-5.4 mini could be a good option ... let's leave it for the future. A future implementation should also show possible models in the agents tab in a drop-down menu (frontend change). Finally ... update the deployment instructions, and also the user manual.

Record 2 future items (GPT-5.4-mini option; per-agent model dropdown in the agents tab). Now: update deploy/DEPLOY.md for all the recent VM/config changes (GEMINI required + PERPLEXITY keys, tectonic for PDF, alphaXiv re-login, sandbox image, config defaults) and the user manual.

---

### Prompt 146 — Perplexity still 401 with a brand-new key

> still seeing issues with perplexity, even if I just created a new API key [journal: 401 Unauthorized on api.perplexity.ai/chat/completions, attempts 1+2]

401 with a new key (after restart, new PID 28291) → either the process isn't seeing the new value (env not reloaded / malformed line / duplicate), the key value is malformed (quotes/whitespace/CR from vi), or the Perplexity account lacks credits/billing. Investigate the client (key read, headers, model, base_url) + give VM debug steps (file check, /proc/<pid>/environ check, direct curl) + surface the 401 response body.

### Prompt 147 — Perplexity key was malformed (resolved by user). 

### Prompt 148 — internal-review rejection stalls (no terminal screen)

> still seeing an issue when the research process terminates (accepted or not). It stalls instead of giving a message about the outcome and showing the paper. [screenshot: "Internal review rejected the paper", then Stalled 522s, in "internal review"]

The desk_reject terminal fix (prompt 133) didn't cover the INTERNAL_REVIEW reject path. Need: every terminal outcome (publish / desk-reject / peer-reject / internal-reject / revision-exhausted / no-paper) must finalize → set REJECTED/PUBLISHED phase + broadcast + return, so the frontend TerminalScreen shows the outcome + paper. Investigate the engine internal-review branch + whether it hangs or just doesn't broadcast terminal.

### Prompt 149 — Perplexity works now; arXiv 429s during seed-discovery ingestion

> [journal: Seed discovery found IDs via Perplexity, but "failed to ingest <id>: 429" then "arXiv unavailable — circuit breaker open (rate-limited)" for the rest]

Perplexity fixed (returns IDs). New issue: run_seed_discovery fetches each discovered ID from arXiv in a tight loop (~10 rapid get_paper calls) → 429 → circuit breaker opens → arXiv disabled for the whole cycle (incl. agents' later searches). Fix: don't burst — rate-limit or batch the seed fetches (arXiv id_list takes comma-separated IDs → one request), so it doesn't trip the breaker.

### Prompt 150 — how to change default settings on the VM; are GUI choices sticky?

> how do I change the default settings of paradigm on the VM? Are choices sticky (remembered next round) or always fallback to defaults?

Explain the config layers: production.yaml (static defaults, edit+restart) vs the GUI Settings panel (persistence? sticky?) vs per-run wizard choices. Investigate settings.py persistence + how a new cycle applies settings.

### Prompt 151 — some literature papers show '(?)' instead of authors

> some show '?' instead of their list of authors [Literature Found panel; papers WITH arXiv IDs but no authors → "(?)"]

Some SourceResults reach the live literature panel with empty authors → rendered "(?)". Likely a provider whose parsing drops author names (alphaXiv text-listing extracts affiliations not authors? Semantic Scholar refs?). Find the renderer + the broadcast + the provider that drops authors; fix author extraction.

Done (commit e9f8111): alphaXiv listings carry a published date but expose affiliations, not author NAMES → `_parse_date` populates the year; frontend `formatByline()` degrades gracefully (Authors (Year) / Authors / (Year) / nothing) — never a bare "(?)". Wired into all 4 render sites. 1526 tests pass, frontend builds.

### Prompt 152 — how do I see how many people visit the VM, and from which IP?

> I would like to know how many people visit the platform on the VM, and ideally from which IP. How do I achieve that? Is that already logged somewhere?

Informational. Visitor IPs are NOT currently captured: the repo/VM Caddyfile has no `log` directive (Caddy is the edge that sees real client IPs, but logs only runtime/error events without it), and uvicorn sits behind Caddy on 127.0.0.1 with no `--proxy-headers`, so its access log shows only 127.0.0.1. Answer: enable Caddy access logging (JSON log block) → analyze with jq / goaccess. Offered to bake the `log` block into deploy/Caddyfile + DEPLOY.md.

### Prompt 153 — stalled again at end (Peer Review); 'Review' stage not lit green in the phase bar

> I think it stalled again at the end. Also trying to understand why the 'Review' stage button is not light up green in the sequence bar [screenshot: phase bar Seeding✓ Ideation✓ Planning✓ Execution✓ Discussion✓ Writing✓ Review(grey,no check) Submitted✓ PeerReview(●current) Published(grey); "Stalled — No activity for 146s" in Peer Review, 10m37s in phase; 3 Reviewer agents produced reviews]

Two issues: (1) terminal stall AGAIN — Peer Review produced reviews (3 reviewers) but then no activity for 146s → the editor decision / transition to Published|Rejected after peer review hangs (LLM call without timeout, or missing terminal broadcast). (2) Phase-bar display bug: "Review" (internal review) shows grey/unchecked while the LATER "Submitted" shows ✓ — the tracker isn't marking an earlier phase complete once a later one is reached. Investigate phases.py order + frontend PhaseTracker completion logic + the peer-review→terminal path in engine/review.

Done (commit 7613da6): fixed (1) "Review" pip (engine emitted "INTERNAL_REVIEW"→"internal_review"; now passes the enum→"internal"); (2) publish_paper offloaded ChromaDB ingest via to_thread; (3) terminal phase_transition(PUBLISHED|REJECTED) broadcast on peer-review accept/reject paths. Regression tests added. 1526 pass.

### Prompt 154 — STILL stalls at the end (rejected); "Review" pip now green though

> Might still be broken... [screenshot: phase bar now Review✓ Submitted✓ PeerReview✓ Published(grey); "● Rejected", "Stalled — No activity for 679s", 11m20s in phase] + caddy/journal log (process alive, health checks every 30s, "Failed to parse checkpoint JSON, using fallback" lines, NO traceback)

Fix #1 (Review pip) CONFIRMED working — bar fully green through Peer Review and current=rejected. Fix #2 partially worked: REJECTED phase_transition reached the UI. BUT session status never became terminal → frontend still "running" → watchdog shows "Stalled" for 679s. Root: the post-cycle TAIL after the REJECTED broadcast (engine ~657-669: _save_auxiliary_files [PDF compile?] + run_memory_generation) runs/hangs for 11+ min with zero activity broadcasts, so run_research_cycle never returns → session_manager never marks COMPLETED. Need: (a) bound/offload the tail so the session finalizes promptly, and/or (b) frontend: once a terminal phase (published/rejected) is reached, stop showing "Stalled" and render the terminal screen regardless of session status. Investigate memory-gen timeout (per-agent vs total) + _save_auxiliary_files PDF compile.

Done (commit ccedf22): reflections now run concurrently (asyncio.gather) so the post-cycle tail no longer hangs finalization (the wait_for(120) was defeated by uncancellable to_thread); frontend now finalizes on a terminal PHASE (published/rejected) regardless of session status — no false "Stalled", terminal screen + View-paper render immediately. Tests added. 1528 pass.

### Prompt 155 — colored topic badges (arXiv large categories) on papers + cycles; cross-pollination

> Can we also add a colored tag to papers and cycles in dashboard and research according to the topic? A little badge with different color for eg astro cs bio med physics eco stat... Use the arxiv subdivision (just large categories, no sub-subdivisions). Topics assigned by an agent (the theorist who reads the prompt first). Checked again at end of cycle in case the paper drifted. Multiple badges possible — eg an economics paper using astro techniques gets both badges. Cross pollination should be a feature of Paradigm.

Feature: topic taxonomy (arXiv top-level groups + astro split out + med): astro/physics/cs/math/stat/bio/med/econ/eess (+ other). (1) Theorist classifies the seed prompt at the start → initial topics on the thread → broadcast. (2) Re-classify the PAPER at cycle end (drift check + cross-pollination) → final topics (can be multiple) on thread + paper. (3) Colored TopicBadge pills on Dashboard + Research cycle cards + Papers tab. Store topics on thread + paper (DB), surface via cycle + paper API responses, shared taxonomy constants (backend + frontend). Plan + implement with tests.

Done: topic-badge feature implemented. Backend — new `agents/topics.py` (taxonomy astro/physics/cs/math/stat/bio/med/econ/eess/other + LLM `classify_topics`, robust parse, ["other"] fallback); `topics` JSON column on papers + threads (idempotent); engine classifies the seed prompt after seeding (theorist's brain) and re-classifies the finished paper at cycle end (drift + cross-pollination, multiple tags), best-effort/bounded; `topics_assigned` on DisplayManager + fallback + ws_display (broadcasts TopicsUpdateMsg + state); cycle/paper API responses carry `topics`. Frontend — TOPIC_LABELS/TOPIC_COLORS, `TopicBadges` pill component, rendered on Dashboard+Research cycle cards, Papers tab cards, paper viewer, and the live session header; store handles topics_update/session_state. Tests: tests/test_topics.py (parse/classify/DB round-trip). Full suite 1539 pass; frontend tsc+build clean.

### Prompt 156 — retroactively apply topic badges to existing papers/cycles

> Can we retroactively apply the badges to existing papers / research cycles?

Existing papers/threads predate the feature → topics column NULL. Add a one-off backfill: a `paradigm` CLI command that opens the DB, classifies each paper (title+abstract+body) → paper.topics + owning thread.topics, and each remaining thread (seed/title/hypothesis) → thread.topics, skipping ones already tagged (--force to redo, --dry-run to preview). Reuses agents/topics.classify_topics with the config provider. No backend restart needed (API reads topics fresh; GUI refresh shows them).

Done (backfill): added `paradigm backfill-topics` CLI command (--dry-run/--force/--limit) + `agents/topics.backfill_topics(database, ...)` core + `Database.list_threads()`. Tags existing papers from content (and their owning thread, so cycle badge matches) and remaining cycles from the seed prompt; idempotent, skips external literature. No backend restart needed — API reads topics fresh; refresh the UI. Tests in tests/test_topics.py (backfill incl. idempotency, dry-run, external-skip). 1542 pass.

### Prompt 157 — per-agent model selector dropdown in agents config (Anthropic / Gemini / TogetherAI)

> it would be great to be able to select models for the agents using a dropdown selector in agents config. Select what is available via anthropic API, gemini API, and togetherAI

Feature: a GUI dropdown per agent/role to choose its model from Anthropic, Gemini, and TogetherAI. Needs: (1) a model catalog the backend exposes (which models per provider, gated by which API keys are set) — decide live-API-listing vs curated; (2) per-role model+provider override applied to the next cycle (mirror the in-memory Settings-panel pattern); (3) TogetherAI provider wiring (OpenAI-compatible base_url + TOGETHER_API_KEY); (4) frontend agents-config UI with grouped dropdowns. Plan + build with tests. (Was flagged as a future item in ROADMAP: per-agent model picker + OpenAI/Together provider.)

Done (commit pending): per-agent model picker (hybrid). Backend — `agents/model_catalog.py` (curated shortlist per family anthropic/gemini/together + live fetch from each provider's API, cached 1h, filtered; family derived from type+base_url); `GET /api/v1/models?refresh=` endpoint (key-gated, curated default, live on refresh, falls back to curated on error, injects each provider's configured default); provider validation on the agents PUT; TogetherAI wired into production.yaml (TOGETHER_API_KEY, hidden if unset). Frontend — AgentConfig dropdown grouped by provider (selecting a model sets provider too), "Refresh from API" button, "hidden (no key)" hint, Advanced disclosure for custom model/provider; client types + useModelCatalog hook. Per-role overrides already persist in-memory + apply next cycle (existing). Tests: tests/test_model_catalog.py (12). 1554 pass; frontend builds.

### Prompt 158 — research session crashed on alphaXiv MCP "needs interactive login"

> THe research session stopped. journalctl: RuntimeError: MCP server 'alphaxiv' needs a one-time interactive login. Run: paradigm mcp-login

alphaXiv MCP raised a fatal RuntimeError ("needs a one-time interactive login") that propagated up and STOPPED the research cycle, instead of degrading cleanly (arXiv + other providers should carry the run, per the prompt-140/142 clean-fallback design). Find where this RuntimeError is raised + why it's not caught at the search/provider level; make alphaXiv failures non-fatal. Immediate unblock for the user: disable literature.mcp.enabled or re-run paradigm mcp-login.

Done (commit pending): made alphaXiv MCP failures truly non-fatal. Root cause: a [READ] action → corpus read loop → provider.fetch → session.call_tool could raise an anyio BaseExceptionGroup (the raw "needs interactive login" RuntimeError) when the cached OAuth token EXPIRED mid-session; corpus.py:475 caught only `except Exception` (misses BaseExceptionGroup) → it escaped → crashed the cycle. Fix: MCPSourceProvider.search/fetch now wrap their whole body (incl. call_tool) — re-raise CancelledError, catch BaseException → degrade to []/None (so NO caller path can be crashed); corpus read loop guard hardened to BaseException too. Tests: test_mcp_provider degradation cases (BaseExceptionGroup, raw login RuntimeError, prior connect-failed, CancelledError propagates). 1558 pass.

### Prompt 159 — pause a research cycle so it can be restarted later

> I would like to introduce the ability to pause a research cycle, so that it can re restarted later on

Add a Pause capability for a running cycle that lets it be resumed later. Existing pieces to assess: session_manager.pause_session/resume_session (in-memory PAUSED + intervention hook blocks engine at round boundaries), the InterventionHook, checkpoint saving, the durable resume-from-checkpoint flow (resumeCycle creates a new cycle from the prior checkpoint), and the frontend InteractionBar (currently hidden, SHOW_INTERACTION_BAR=false). Decide: live pause (same process, ephemeral) vs durable pause (graceful stop + checkpoint, resumable after restart). Plan + build.

Done (pause): surfaced an always-visible Pause/Resume control in the session header (new SessionControls.tsx → existing WS session_control pause/resume → session_manager pause_session/resume_session, which toggles the engine's round-boundary pause gate). For durable "resume later": engine now checkpoints at the pause point (new is_paused predicate from session_manager → engine saves a checkpoint before blocking on the gate), unified the 3 checkpoint blocks into _save_checkpoint(). A paused cycle is clickable in the research list → reopen → Resume; after a restart it becomes "interrupted" → existing checkpoint-resume. Tests: pause-checkpoint persist/noop + round-loop consults is_paused. 1561 pass; frontend builds.

Done (preflight): model health check before each run. New agents/preflight.py pings each distinct (provider, model) the team uses with a 1-token completion (concurrent, ~10s cap each, best-effort) and returns per-role swaps for any that don't respond, preferring the config default as the healthy fallback. engine runs it before create_team (gated by orchestrator.model_preflight, default True) and passes role_overrides to AgentFactory.create_team (create_agent already honors provider+model kwargs → per-run swap, no shared-config mutation). New display.model_preflight(checked, swaps) on DisplayManager + fallback + ws_display (a warning notification + activity event on swap). configs unchanged (default True). Tests: test_preflight (healthy/swap/no-fallback/never-raises) + factory role_overrides. 1566 pass; no frontend change (uses existing notifications).

### Prompt 161 — latest produced paper got no topic badge

> Also the latest paper I produced wasn't given a badge. not sure why

A produced paper shows no topic badge → paper.topics empty. Likely the FINAL classification (_assign_final_topics → _assign_topics) failed/timed-out (caught + logged "topics_final", topics not written) — plausibly the theorist's model was flaky (recent Together/503). Robustness fix: if final classification fails, the paper should INHERIT the cycle's initial topics (so it always gets a badge), and classification should fall back to a reliable provider. Investigate _assign_topics/_assign_final_topics + make the paper always get topics.

Done (badge robustness): a produced paper now ALWAYS gets a topic badge. _assign_topics refactored: new _classify() tries the theorist's brain then the config DEFAULT provider (reliable fallback), each bounded to 45s; if the final classification still fails, the paper INHERITS the cycle's initial topics (or ["other"]) so it never ends up badge-less. Existing badge-less papers: fix retroactively with `paradigm backfill-topics`. Tests: inherit-initial + other-fallback. 1568 pass.

### Prompt 162 — add a favicon (browser-tab icon) for paradigm.stellarphysics.org

> What if I want to add a little icon that appears on the browser tab when I load paradigm.stellarphysics.org ?

Add a favicon. Replace the Vite default with an on-brand SVG (Observatory theme: gold/indigo). Wire it in frontend/index.html + frontend/public/, rebuild. Explain how to swap for a custom image.

Done: added frontend/public/favicon.svg (Observatory mark — starlight-gold star on the deep-indigo void + a cyan orbit/agent dot, theme-matched) and wired <link rel="icon" type="image/svg+xml"> + <meta theme-color="#16131f"> into frontend/index.html. Vite copies it to dist/ → served at /favicon.svg by Caddy. Frontend-only; rebuild on the VM to deploy.

Update (favicon): user shared the app's existing Observatory logo (concentric gold aperture rings + central gold sun + small cyan orbiting star, top-right, on a dark navy tile — the Sidebar.tsx CSS-div mark). Redrew favicon.svg to match it exactly (gold #e8c069 rings/sun + cyan #5cd0dd star on #0e1322, with a faint gold center glow), replacing the earlier star design. Rebuilt.

### Prompt 163 — Claude models failing to load (preflight swaps opus-4-7 → gemini)

> I am having problems loading claude models... Model check: swapped unreachable model(s) — theorist: claude-opus-4-7 → gemini-2.5-flash-lite; experimentalist: claude-opus-4-7 → gemini; editor: Qwen/Qwen2.5-72B-Instruct-Turbo → gemini

Root cause: AnthropicProvider.complete/complete_streaming always sent `temperature`, but Claude Opus 4.7/4.8 REMOVED sampling params (temperature/top_p/top_k → 400). So the preflight ping (and every agent turn) 400'd → opus-4-7 looked "unreachable" → swapped to gemini. Fix: `_accepts_temperature(model)` — omit temperature for claude-opus-4-7/4-8 prefixes (keep it for 4.6/sonnet/haiku). The editor/Qwen swap is separate (Together transient/availability). Tests: opus-4-7/4-8 omit temperature; 4.6/sonnet/haiku keep it.

### Prompt 164 — enable OpenAI models in the picker (reasoning-param shim + catalog)

> Can we also enable OpenAI models with this change? ... worried about the temperature as well. I already have the OpenAI API key set on the VM. Add a few top OpenAI models.

Done. (1) OpenAICompatibleProvider shim: `_token_sampling_kwargs` — OpenAI reasoning models (o-series, gpt-5*) use `max_completion_tokens` (not `max_tokens`) and OMIT `temperature` (default-only → a 0.0 ping 400s); non-reasoning (gpt-4o/4.1) keep max_tokens+temperature. (2) Catalog: `provider_family` maps api.openai.com → "openai" (+ "openai_compatible" generic fallback); curated OpenAI shortlist (gpt-5/-mini, gpt-4.1/-mini, gpt-4o/-mini, o4-mini); live filter keeps gpt-/o* chat models, drops embeddings/audio/image/realtime/etc.; FAMILY_LABELS openai="OpenAI". (3) production.yaml: openai provider (OPENAI_API_KEY, base_url api.openai.com/v1, default gpt-4o-mini; hidden if no key). (4) .env example + DEPLOY note OPENAI_API_KEY. Tests: reasoning shim (max_completion_tokens/no-temp) + non-reasoning; openai family + curated + live filter. 1574 pass.

### Prompt 165 — could Claude operate an autonomous use→find-bug→fix→deploy→retest loop on the live VM?

> Do you have access to paradigm.stellarphysics.org if I give you credentials? Would you be able to operate a loop where you use the platform, identify bugs or improvements, change the code, push to VM, then test again in a loop?

Capability/process question (no code change). Answer: I can drive the REST/WS API (with creds, if the session shell has network) but NOT the React/WebSocket UI like a human; I won't store credentials. I should NOT run an unsupervised code→push-to-prod→restart loop on the live VM (outward-facing, hard to reverse). Recommended instead: a LOCAL end-to-end loop (run backend + real cycles via CLI/`paradigm eval`, read logs/events, fix, test, push to branches) with the human doing the prod deploy; or a staging instance; or supervised VM ops with per-action confirmation + env-var/`!`-prefixed creds so secrets stay out of the transcript.

### Prompt 166 — preflight swapped skeptic gpt-5 → gemini; surface WHY

> first checking in that Model check: swapped unreachable model(s) — skeptic: gpt-5 → gemini-2.5-flash-lite

Two likely causes: (a) the reasoning-shim commit (2b8a3a0) not deployed yet → gpt-5 400s on temperature/max_tokens; or (b) `gpt-5` is the wrong id for the user's key (404 — they referenced "GPT-5.4 mini", so real ids are versioned). The preflight didn't say which. Fix: surface the failure REASON. _ping now returns the error string (404/400/timeout) instead of a bool; PreflightResult.swaps is (role, old, new, REASON); preflight logs each unreachable pair (metadata_key=model_preflight) + the display methods (DisplayManager/fallback/ws_display) include the reason in the notice. So the UI/log now says e.g. "skeptic: gpt-5 → gemini (Error code: 404 - the model gpt-5 does not exist)". Tests updated for 4-tuples. 1574 pass.

Update: user's OPENAI key list goes to GPT-5.5 (gpt-5 IS available → the earlier swap was just the un-deployed shim, not a 404). Refreshed the curated OpenAI shortlist to real top models: gpt-5.5, gpt-5.5-pro, gpt-5.4, gpt-5.4-mini, gpt-5.4-nano, gpt-5.1, gpt-4.1, gpt-4.1-mini, o4-mini (dropped stale gpt-5/gpt-4o guesses). Shim handles all gpt-5*/o* (startswith match).

### Prompt 167 — set a sensible diverse default team across providers

> keep model diversity ... top OpenAI for theorist, top anthropic for analyst/skeptic, best for experimentalist (gpt-5.5 or Opus 4.8), a good careful model for the writer, Gemini for reviewers/editor. Set a sensible default given these + your thoughts.

New production.yaml default lineup (all 3 providers): theorist=openai/gpt-5.4 (max_tokens 12288), analyst+skeptic=anthropic/claude-sonnet-4-6 (top-practical; Opus too slow/costly for every-phase roles, reserve it for the writer), experimentalist=openai/gpt-5.5 (best; writes code; 16384), writer=anthropic/claude-opus-4-8 (best careful long-form; 16384), synthesizer+editor+reviewer=gemini/gemini-2.5-flash. openai default_model gpt-4o-mini→gpt-4.1-mini (confirmed in user's key list). Config validates; all override providers in registry. NOTE: this is a production.yaml change → user does the stash/pop dance.

### Prompt 168 — build the local self-test loop

> Ok. now let's work on the local self-test loop

Build a local, fast, cheap harness that runs real research cycles + auto-triages the result (errors / stalls / empty output), so the loop is run → triage → fix → re-run without touching prod. First assess local env (keys, network from the sandboxed shell, Docker, deps); design a selftest config (cheapest models, 1 round, experiments off) + a runner/triage script; then run + iterate.

Done (self-test loop v1): added configs/selftest.yaml (cheapest end-to-end: all Gemini Flash-Lite, 1 round/phase, experiments OFF, lean peer review, no LaTeX/Perplexity) + scripts/selftest.py — drives the real `paradigm run` CLI in an isolated temp data dir, then triages the event log + SQLite DB + process output for CRASH / STALL / INCOMPLETE / THIN_PAPER / NO_BADGE / real ERROR events; transient external errors (429 / rate limit / 503 / semantic_scholar / arxiv) are downgraded to notes, not failures. Exits non-zero on real issues (smoke gate). Validated: 2 real cycles ran clean end-to-end (~170–220s, ~30K-char papers, terminal status revision_exhausted) — only a transient Semantic Scholar 429, no real bugs. Platform is healthy end-to-end.

### Prompt 169 — ran the hunting batch (option 1); triaged + fixed

> Let's do 1)

Batch: 3 directed (astro/bio/cs varied domains) + 1 explore + 1 experiments-on (Docker). Result: 4/5 cycles PASS clean (terminal status, ~20–38K-char papers; only transient Semantic Scholar 429/404 — non-fatal). The experiments-on cycle exposed: when experiments yield no usable output the engine hits abort_on_execution_failure → status=execution_failed and returns, but (like the reject paths before 148/153) did NOT broadcast a terminal phase_transition → live phase bar stuck on Execution (not a hard stall — session still completes into a terminal screen via the prompt-154 path — but inconsistent). Fixes: (a) engine broadcasts phase_transition(REJECTED) on the execution_failed + verification_failed abort paths; (b) frontend TerminalScreen: a "rejected" terminal WITHOUT a paperId now reads "Finished without a paper — experiments didn't yield usable results" (+ Resume, not "Revise & resubmit") instead of "Paper was not accepted"; (c) harness: execution_failed/verification_failed added to the terminal-status set (was a triage false-positive). Re-run of the experiments cycle then PASSED end-to-end (Flash-Lite wrote working code → 20K paper). 1574 tests pass; frontend builds.

### Prompt 170 — sweep every config toggle (on/off) to expose bugs (Flash-Lite)

> Still flash lite. Next I would like to test all the setting option (toggle on/off) to expose and fix possible bugs

Build scripts/toggle_sweep.py (reuses selftest.py _run_cycle + triage): from the selftest baseline, flip ONE toggle/group per variant and run a cheap Flash-Lite cycle, triage, report per-toggle PASS/issues. Variants cover orchestrator (writing/peer_review/checkpointing/preflight/convergence/debates/sprints/verification/multimodal/human_gate), knowledge (world_model/evidence_graph/tournament/prereg), citation (grounding/novelty/seed_discovery — Perplexity), journal (latex/pdf), experiments (Docker). Experiment-dependent toggles base on selftest-exp.yaml. Run in background; triage + fix failures.

Toggle sweep findings (round 1): 9/11 variants that ran were clean (writing_off→planning_complete, peer_review_off→reviewed, preflight_off, convergence_off, debates_on, gate_advisory, world_model_off, evidence_graph_off all PASS). REAL BUG: checkpointing_off (coincidental, data-dependent) → CRASH "Invalid IPv6 URL" + thread stuck 'active' — root cause: the engine round loop calls process_search_requests/process_literature_actions/process_data_requests with NO try/except (only agent.generate was guarded), so a malformed paper URL (httpx InvalidURL from a [CHAIN/FOLLOW/READ]) crashes the whole cycle. Fix: wrap those 3 literature calls in try/except (re-raise CancelledError, else log+continue) — literature is best-effort, never fatal. Also harness bugs: _run_cycle mishandled bytes stdout on timeout (TypeError crashed the sweep at variant 12 → variants 12-20 didn't run); triage didn't classify "incomplete chunked read"/"peer closed connection" (tournament_on/prereg_on transient Gemini stream drops) as transient. Fixed both. Re-running variants 12-20 + checkpointing_off.

Toggle sweep findings (round 2): checkpointing_off now PASS (literature-guard fix confirmed). novelty_on PASS (slow ~400s). seed_discovery_on PASS. REAL BUG: citation_grounding_on → STALL (>600s, thread stuck 'active') — root cause: run_citation_grounding grounds sections SEQUENTIALLY, each cite_section grounds paragraphs SEQUENTIALLY, each cite_paragraph up to perplexity_timeout(120s)×retries; summed → many minutes, no activity → GUI watchdog reads it as a stall. Fix: cite_section now grounds paragraphs CONCURRENTLY (asyncio.gather, return_exceptions); run_citation_grounding grounds sections CONCURRENTLY under a 240s overall budget (asyncio.wait_for) → on overrun, leave the paper ungrounded (best-effort) instead of stalling. 1574 pass. (Remaining sweep variants latex/pdf/experiments/sprints/verification/multimodal still running.)
