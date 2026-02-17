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
