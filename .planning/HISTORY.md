# Paradigm Project History

## 2026-02-11

### Prompt 1: Debug CI Failure
> we just implemented CI, but I received a notification from github actions that something didn't work

**Key decisions:** Investigating and fixing CI failures in `.github/workflows/ci.yml`
**Artifacts modified:**
- `src/paradigm/agents/prompts/.gitkeep` — created (missing dir caused verify_setup.py to fail)
- `tests/test_database.py` — removed spurious f-string prefix (F541)
- `src/paradigm/agents/base.py` — migrated Pydantic v1 `class Config` to v2 `model_config`

### Prompt 2: CI Error Log Analysis
> (User shared CI error log showing `src/paradigm/agents/prompts` directory missing)

**Root cause:** The `prompts/` directory was empty and had no `.gitkeep`, so git didn't track it. The `verify_setup.py` script checks for it and exits with code 1.
**Fix:** Added `.gitkeep` to `src/paradigm/agents/prompts/`

### Prompt 3: Move to Phase 1
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

### Prompt 4: Integrate Scientific Skills from External Repo
> I would like to implement in the plan the ability (for the agents) to acquire scientific skills from https://github.com/K-Dense-AI/claude-scientific-skills. I think it would be good to have the ability to either load all the agents with all the skills, or only load them with one skill, or assign a set of different skills, to mimic a diverse population of scientific expertise. Can we adapt the plan accordingly?

**Key decisions:** Explore the external skills repo and design a flexible skill-loading system for agents.

### Prompt 5: Implement Scientific Skills Integration

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

### Prompt 6: History Logging & Roadmap Update

> It seems history.md has only prompts from phase 0. What about our recent prompts? Also did you adapt the roadmap to include that modification (addition of skills)?

**Key decisions:** Update ROADMAP.md to reflect completed phases and the new skills integration step.
**Artifacts modified:**
- `.planning/HISTORY.md` — added this prompt
- `ROADMAP.md` — marked Phase 0 and Phase 1 complete, added skills integration to Phase 0

### Prompt 7: Move to Phase 2

> Let's move to the next phase

**Key decisions:** Plan and implement Phase 2 — Orchestrator + Ideation Loop.

## 2026-02-12

### Prompt — Implement Phase 2: Orchestrator + Ideation Loop

> Implement the following plan: Phase 2: Orchestrator + Ideation Loop — Implementation Plan. Create phases.py (phase state machine), scheduler.py (agent turn-taking), checkpoints.py (checkpoint compression), engine.py (main orchestration loop). Update main.py CLI to wire to engine. Write tests for all new modules.

**Key decisions**: Follow the approved plan exactly. Implementation order: phases → scheduler → checkpoints → engine → main.py → tests → verification.

**Artifacts**: New files: `orchestrator/phases.py`, `orchestrator/scheduler.py`, `storage/checkpoints.py`, `orchestrator/engine.py`. Modified: `main.py`, `__init__.py` files. Tests: `test_phases.py`, `test_scheduler.py`, `test_checkpoints.py`, `test_orchestrator.py`.

### Prompt — Commit and Push Phase 2

> ok, let's commit and push

**Artifacts**: Committed 12 files (1699 insertions) as `1bd409c` and pushed to `origin/main`.

### Prompt — Confirm HISTORY.md Is Updated

> are you keeping history.md updated?

Confirmed HISTORY.md was current. User requested logging all interactions including minor ones.

### Prompt — Log All Interactions

> yes please

Added retroactive entries for the commit/push and confirmation prompts.
