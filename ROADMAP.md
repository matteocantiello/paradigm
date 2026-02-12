# Paradigm — Implementation Roadmap

## Principles

1. **Get the loop working first.** The core loop (ideate → research → write → review → publish) is more important than any individual component being polished.
2. **Vertical slice, then widen.** Build one complete path through the system before adding options.
3. **Test with real prompts early.** Don't wait for perfection — run a research cycle as soon as the skeleton works.
4. **Checkpoint everything.** If you can't resume from a saved state, you can't iterate.

---

## Phase 0: Foundation (Week 1)

**Goal**: Project skeleton, configuration, database schema, basic agent abstraction.

### Tasks

- [ ] Initialize Python project with `pyproject.toml`, deps, dev tooling (ruff, pytest)
- [ ] Implement `config.py` — load YAML config, validate, provide defaults
- [ ] Implement `storage/database.py` — SQLite schema creation (papers, agents, threads, graveyard, events)
- [ ] Implement `agents/base.py` — Base agent class:
  - Takes a system prompt + conversation context
  - Calls Claude API
  - Returns structured response
  - Tracks token usage
- [ ] Implement `logging/events.py` — Structured JSON-lines event logger
- [ ] Write initial agent system prompts (YAML templates) for: theorist, analyst, skeptic
- [ ] Write default config YAML
- [ ] Unit tests for database, config, base agent

### Exit Criteria

- Can instantiate an agent, send it a message, get a response
- Database creates all tables correctly
- Events are logged to file
- `python -m paradigm --help` shows CLI

---

## Phase 1: Literature Access (Week 2)

**Goal**: Agents can search arXiv and retrieve papers.

### Tasks

- [ ] Implement `literature/arxiv.py` — arXiv API client:
  - Search by query (keyword, category, date range)
  - Parse Atom feed response
  - Return structured results (id, title, authors, abstract, categories, date)
  - Rate limiting (1 req / 3s)
  - Optional: fetch full PDF → text extraction via PyMuPDF
- [ ] Implement `literature/embeddings.py` — ChromaDB wrapper:
  - Embed paper abstracts using a sentence-transformer or Claude embeddings
  - Store and retrieve by semantic similarity
  - Upsert for both arXiv and internal papers
- [ ] Implement `literature/corpus.py` — unified search interface:
  - Search arXiv (live)
  - Search internal corpus (ChromaDB + SQLite)
  - Merge and rank results
  - Return to agent as formatted context
- [ ] Implement `literature/citations.py` — basic citation tracking:
  - Record when a paper cites another
  - Query citation count
  - Simple citation graph traversal
- [ ] Integration test: agent asks a question → literature search → relevant papers returned

### Exit Criteria

- `arxiv.search("stellar pulsation")` returns structured results
- Papers can be embedded and retrieved by semantic search
- An agent can be given a topic and produce a literature summary with citations

---

## Phase 2: Orchestrator + Ideation Loop (Week 3)

**Goal**: Multiple agents can discuss a topic in structured rounds and produce a research plan.

### Tasks

- [ ] Implement `orchestrator/phases.py` — Phase state machine (enum + transitions)
- [ ] Implement `orchestrator/scheduler.py` — Turn-taking logic:
  - Round-robin with optional priority (reputation-weighted)
  - Phase-appropriate agent selection (e.g., skeptic speaks after proposals)
  - Configurable number of rounds per phase
- [ ] Implement `orchestrator/engine.py` — Main orchestration loop:
  - Accept seed prompt
  - Initialize research thread
  - Run through SEEDING → IDEATION → PLANNING phases
  - Each phase: iterate agents, collect responses, update checkpoint
  - Produce structured research plan as output
- [ ] Implement `storage/checkpoints.py` — Thread checkpoint management:
  - Create, update, load checkpoints
  - Compress conversation history into summary (use Claude to summarize)
  - Resume from checkpoint
- [ ] Implement structured message format (the communication protocol from spec)
- [ ] Test: 3 agents (theorist, analyst, skeptic) discuss "open problems in stellar variability" for 3 rounds, produce a research plan

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

## Phase 5: Peer Review + Publication (Week 6)

**Goal**: Complete the loop — papers are reviewed and published to the corpus.

### Tasks

- [ ] Implement `agents/journal.py`:
  - Editor agent: desk review, assign reviewers, make decisions
  - Reviewer agents: structured review with scores + feedback
  - Different reviewer personalities via system prompts
- [ ] Implement `journal/submission.py`:
  - Submit paper → change status to submitted
  - Editor desk review
  - Reviewer assignment (exclude team members, match by keyword)
- [ ] Implement `journal/review.py`:
  - Collect reviews
  - Editor synthesizes decision
  - Handle revision cycles (max 2 rounds)
- [ ] Implement `journal/publication.py`:
  - On acceptance: status → published, add to ChromaDB, update citation graph
  - Generate paper metadata (summary, keywords) for discoverability
  - On rejection: add to graveyard with feedback and lessons
- [ ] Implement reputation updates:
  - Update author reputation on publication
  - Update citation counts when new papers cite existing ones
- [ ] End-to-end test: seed prompt → ideation → literature → experiment → paper → review → publication

### Exit Criteria

- **The full loop works.** A seed prompt produces a published paper in the internal corpus.
- Published papers are searchable by future agents
- Rejected papers are stored with lessons learned
- Agent reputations update correctly

---

## Phase 6: Multi-Cycle + Polish (Week 7-8)

**Goal**: Run multiple research cycles. Papers cite each other. System produces useful output.

### Tasks

- [ ] Run a second research cycle that builds on the first published paper
- [ ] Verify citation graph grows correctly
- [ ] Implement the operating modes (directed, exploratory, hypothesis generator, etc.)
- [ ] Add CLI commands:
  - `paradigm run --mode directed --prompt "..."`
  - `paradigm run --mode explore --topic "..."`
  - `paradigm status` — show active threads, published papers, agent stats
  - `paradigm inspect --thread <id>` — view thread checkpoint
  - `paradigm papers` — list published papers
  - `paradigm paper <id>` — view a published paper
- [ ] Tune agent prompts based on output quality
- [ ] Add intervention hooks (pause, inspect, override)
- [ ] Documentation: README, setup guide, configuration reference

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
