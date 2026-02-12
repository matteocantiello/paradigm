# Paradigm — Implementation Roadmap

## Principles

1. **Get the loop working first.** The core loop (ideate → research → write → review → publish) is more important than any individual component being polished.
2. **Vertical slice, then widen.** Build one complete path through the system before adding options.
3. **Test with real prompts early.** Don't wait for perfection — run a research cycle as soon as the skeleton works.
4. **Checkpoint everything.** If you can't resume from a saved state, you can't iterate.

---

## Phase 0: Foundation (Week 1) ✓ COMPLETE

**Goal**: Project skeleton, configuration, database schema, basic agent abstraction.

### Tasks

- [x] Initialize Python project with `pyproject.toml`, deps, dev tooling (ruff, pytest)
- [x] Implement `config.py` — load YAML config, validate, provide defaults
- [x] Implement `storage/database.py` — SQLite schema creation (papers, agents, threads, graveyard, events)
- [x] Implement `agents/base.py` — Base agent class:
  - Takes a system prompt + conversation context
  - Calls Claude API
  - Returns structured response
  - Tracks token usage
- [x] Implement `logging/events.py` — Structured JSON-lines event logger
- [x] Write initial agent system prompts (YAML templates) for: theorist, analyst, skeptic
- [x] Write default config YAML
- [x] Unit tests for database, config, base agent
- [x] GitHub Actions CI pipeline
- [x] Scientific skills integration:
  - Added `claude-scientific-skills` submodule (142 skills) under `vendor/`
  - `agents/skills.py` — SkillRegistry for discovering, indexing, and composing skills
  - `agents/factory.py` — AgentFactory for creating agents with role prompts + skills
  - 8 role prompt YAML templates (theorist, analyst, synthesizer, experimentalist, writer, skeptic, editor, reviewer)
  - Flexible skill_mode: "default", "all", "none", "custom"

### Exit Criteria

- Can instantiate an agent, send it a message, get a response
- Database creates all tables correctly
- Events are logged to file
- `python -m paradigm --help` shows CLI

---

## Phase 1: Literature Access (Week 2) ✓ COMPLETE

**Goal**: Agents can search arXiv and retrieve papers.

### Tasks

- [x] Implement `literature/arxiv.py` — arXiv API client:
  - Search by query (keyword, category, date range)
  - Parse Atom feed response
  - Return structured results (id, title, authors, abstract, categories, date)
  - Rate limiting (1 req / 3s)
  - Optional: fetch full PDF → text extraction via PyMuPDF
- [x] Implement `literature/embeddings.py` — ChromaDB wrapper:
  - Embed paper abstracts using a sentence-transformer or Claude embeddings
  - Store and retrieve by semantic similarity
  - Upsert for both arXiv and internal papers
- [x] Implement `literature/corpus.py` — unified search interface:
  - Search arXiv (live)
  - Search internal corpus (ChromaDB + SQLite)
  - Merge and rank results
  - Return to agent as formatted context
- [x] Implement `literature/citations.py` — basic citation tracking:
  - Record when a paper cites another
  - Query citation count
  - Simple citation graph traversal
- [ ] Integration test: agent asks a question → literature search → relevant papers returned

### Exit Criteria

- `arxiv.search("stellar pulsation")` returns structured results
- Papers can be embedded and retrieved by semantic search
- An agent can be given a topic and produce a literature summary with citations

---

## Phase 2: Orchestrator + Ideation Loop (Week 3) ✓ COMPLETE

**Goal**: Multiple agents can discuss a topic in structured rounds and produce a research plan.

### Tasks

- [x] Implement `orchestrator/phases.py` — Phase state machine (enum + transitions)
- [x] Implement `orchestrator/scheduler.py` — Turn-taking logic:
  - Round-robin with optional priority (reputation-weighted)
  - Phase-appropriate agent selection (e.g., skeptic speaks after proposals)
  - Configurable number of rounds per phase
- [x] Implement `orchestrator/engine.py` — Main orchestration loop:
  - Accept seed prompt
  - Initialize research thread
  - Run through SEEDING → IDEATION → PLANNING phases
  - Each phase: iterate agents, collect responses, update checkpoint
  - Produce structured research plan as output
- [x] Implement `storage/checkpoints.py` — Thread checkpoint management:
  - Create, update, load checkpoints
  - Compress conversation history into summary (use Claude to summarize)
  - Resume from checkpoint
- [x] Implement structured message format (the communication protocol from spec)
- [x] Test: 154 unit tests passing (mocked API calls)

### Exit Criteria

- A full ideation cycle runs to completion
- Research plan is saved as a checkpoint
- All messages are logged
- System can resume from checkpoint

---

## Phase 3: Computational Sandbox (Week 4)

**Goal**: Agents can write and execute Python code in isolated Docker containers.

### Tasks

- [ ] Create `docker/Dockerfile.sandbox`:
  - Python 3.12 base
  - Pre-install: numpy, scipy, matplotlib, pandas, scikit-learn, sympy, astropy
  - Non-root user
  - No network access at runtime
- [ ] Implement `sandbox/docker.py` — Container lifecycle management:
  - Build image (one-time)
  - Create container with resource limits (CPU, memory, timeout)
  - --network=none
  - Mount volumes (shared data R/O, results R/W)
  - Clean up after execution
- [ ] Implement `sandbox/executor.py` — Code execution pipeline:
  - Receive code string from agent
  - Log code before execution
  - Write to container, execute, capture stdout/stderr/files
  - Return structured result to agent
  - Handle timeouts gracefully
- [ ] Implement `sandbox/safety.py` — Pre-execution checks:
  - Scan for obvious dangerous patterns (os.system, subprocess, network calls)
  - Reject code that tries to escape sandbox
  - File size limits on outputs
- [ ] Integration test: agent proposes an experiment → generates code → code runs in container → results returned

### Exit Criteria

- A Docker image is built with scientific Python packages
- Code executes in isolation with no network access
- Results (stdout, files) are captured and returned
- Resource limits are enforced
- Dangerous code patterns are caught

---

## Phase 4: Writing + Paper Generation (Week 5)

**Goal**: Agents can collaboratively write a paper in structured sections.

### Tasks

- [ ] Define paper structure template:
  ```
  Title, Authors, Abstract, Introduction, Methods, Results, Discussion, Conclusion, References
  ```
- [ ] Implement writing phase in orchestrator:
  - Assign sections to agents based on skill (writer does intro/conclusion, theorist does methods, analyst does results)
  - Each agent drafts their section with access to: research plan checkpoint, literature, experiment results
  - Writer agent assembles and edits for coherence
  - Skeptic agent does internal review before submission
- [ ] Implement draft management:
  - Track paper versions
  - Store drafts in database
  - Diff between versions
- [ ] Test: end-to-end from research plan → complete paper draft

### Exit Criteria

- A complete paper (all sections) is generated from a research thread
- Paper has proper citations (internal + arXiv)
- Paper is stored in the database as a draft
- Internal review feedback is generated

---

## Phase 5: Peer Review + Publication (Week 6) ✓ COMPLETE

**Goal**: Complete the loop — papers are reviewed and published to the corpus.

### Tasks

- [x] Implement structured peer review (`journal/review.py`): PeerReview model, parse_peer_review(), synthesize_decision()
- [x] Implement publication pipeline (`journal/publication.py`): publish_paper(), reject_paper()
- [x] Engine integration: SUBMITTED → PEER_REVIEW → REVISION loop → PUBLISHED/REJECTED
- [x] Desk review gate: editor-in-chief desk_reject/send_to_review
- [x] Reputation updates on publication
- [x] Graveyard storage for rejected papers with lessons learned
- [x] Add to ChromaDB on publish for future discoverability

### Exit Criteria

- **The full loop works.** A seed prompt produces a published paper in the internal corpus.
- Published papers are searchable by future agents
- Rejected papers are stored with lessons learned
- Agent reputations update correctly

---

## Phase 6: Multi-Cycle + Polish (Week 7-8) — IN PROGRESS

**Goal**: Run multiple research cycles. Papers cite each other. System produces useful output.

### Tasks

- [x] Fix multi-cycle discovery: internal papers found by corpus.search() (was broken by `arxiv:` prefix bug)
- [x] Citation extraction from paper body text (arXiv + internal IDs)
- [x] Citation recording on publish (auto-populate citation graph)
- [x] Operating modes: MODE_TEAM_ROLES dict (directed, explore, hypothesis, experimental, replication)
- [x] Mode-specific IDEATION prompts (explore, hypothesis)
- [x] Intervention hooks (pause, abort, continue) with `--interactive` CLI flag
- [x] All CLI commands implemented (run, status, inspect, papers, paper)
- [ ] Tune agent prompts based on output quality
- [x] Documentation: README, operations manual (`docs/MANUAL.md`), configuration reference
- [ ] Live multi-cycle test: cycle 1 → publish → cycle 2 discovers cycle 1 paper

### Exit Criteria

- System runs multiple cycles autonomously
- Internal corpus grows with interconnected papers
- Human can inspect, pause, and steer the system
- Output quality is evaluated by Matteo on astrophysics topics

---

## Future Phases (Post-MVP)

These are tracked but not scheduled:

- **Web dashboard**: Real-time monitoring, citation graph visualization
- **Conference mode**: Synchronous multi-agent discussion events
- **Grant mechanism**: Scarce compute resources agents compete for
- **Retraction system**: Detect and retract flawed papers
- **Multi-model support**: Different LLMs for different agent roles
- **Scaling**: Move from SQLite → Postgres, single-node → distributed
- **Pre-registration**: Agents register hypotheses before testing
- **Domain plugins**: Domain-specific tools (MESA for stellar physics, etc.)
- **Human-in-the-loop mode**: Real scientists collaborate with agent teams
- **Replication challenge**: Limit literature to pre-2020, see if agents re-derive recent results
