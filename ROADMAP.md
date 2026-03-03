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

## Phase 3: Computational Sandbox (Week 4) ✓ COMPLETE

**Goal**: Agents can write and execute Python code in isolated Docker containers.

### Tasks

- [x] Create `docker/Dockerfile.sandbox`:
  - Python 3.12 base
  - Pre-install: numpy, scipy, matplotlib, pandas, scikit-learn, sympy, astropy
  - Non-root user
  - No network access at runtime
- [x] Implement `sandbox/docker.py` — Container lifecycle management:
  - Build image (one-time)
  - Create container with resource limits (CPU, memory, timeout)
  - --network=none
  - Mount volumes (shared data R/O, results R/W)
  - Clean up after execution
- [x] Implement `sandbox/executor.py` — Code execution pipeline:
  - Receive code string from agent
  - Log code before execution
  - Write to container, execute, capture stdout/stderr/files
  - Return structured result to agent
  - Handle timeouts gracefully
- [x] Implement `sandbox/safety.py` — Pre-execution checks:
  - Scan for obvious dangerous patterns (os.system, subprocess, network calls)
  - Reject code that tries to escape sandbox
  - File size limits on outputs
- [x] Integration test: agent proposes an experiment → generates code → code runs in container → results returned
- [x] Wire sandbox into orchestration engine (EXECUTION phase handler)
  - Code extraction from agent responses (```python blocks with `# EXPERIMENT: name`)
  - Retry logic on safety rejection or execution failure (max 2 retries)
  - Results formatted and injected into WRITING phase (RESULTS/METHODS sections)
  - Figure tracking and copying to paper directory
  - EXECUTION phase only runs for modes with experimentalist (experimental, replication)
  - 13 tests covering extraction, formatting, skipping, retry, context injection, figures

### Exit Criteria

- A Docker image is built with scientific Python packages
- Code executes in isolation with no network access
- Results (stdout, files) are captured and returned
- Resource limits are enforced
- EXECUTION phase runs automatically in experimental/replication modes
- Dangerous code patterns are caught

---

## Phase 4: Writing + Paper Generation (Week 5) ✓ COMPLETE

**Goal**: Agents can collaboratively write a paper in structured sections.

### Tasks

- [x] Define paper structure template:
  ```
  Title, Authors, Abstract, Introduction, Methods, Results, Discussion, Conclusion, References
  ```
- [x] Implement writing phase in orchestrator:
  - Assign sections to agents based on skill (writer does intro/conclusion, theorist does methods, analyst does results)
  - Each agent drafts their section with access to: research plan checkpoint, literature, experiment results
  - Writer agent assembles and edits for coherence
  - Editor agent does internal review before submission
- [x] Implement draft management:
  - Track paper versions
  - Store drafts in database
  - Diff between versions
- [x] Test: end-to-end from research plan → complete paper draft
- [x] LaTeX math enforcement: post-processing pass converts Unicode math to LaTeX notation

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

## Phase 6: Multi-Cycle + Polish (Week 7-8) ✓ COMPLETE

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
- [x] Rich terminal UI (DisplayManager with 3-column live layout, plain-text fallback)
- [x] Citation grounding pipeline (Perplexity sonar-reasoning-pro, arXiv reference insertion)
- [x] Seed discovery (Perplexity pre-seeds literature before IDEATION)
- [x] Novelty checking (Semantic Scholar iterative search + LLM assessment, optional FutureHouse mode)
- [x] Agent episodic memory with end-of-cycle reflections and recency-weighted retrieval
- [x] LaTeX math notation enforcement (Unicode-to-LaTeX post-processing)
- [x] Experiment retry with vacuous execution detection (up to 3 attempts)

### Exit Criteria

- System runs multiple cycles autonomously
- Internal corpus grows with interconnected papers
- Human can inspect, pause, and steer the system
- Output quality is evaluated by Matteo on astrophysics topics

---

## Phase 7: Knowledge Architecture ✓ COMPLETE

**Goal**: Structured knowledge representation, hypothesis competition, and evidence tracking.

### Tasks

- [x] World model (`knowledge/world_model.py`) — in-memory structured knowledge store:
  - CRUD for entities, relationships, hypotheses, evidence, open questions, research goals
  - JSON snapshot persistence, markdown summary generation for prompt injection
- [x] Hypothesis tournament (`knowledge/hypothesis_tournament.py`) — Elo-based ranking:
  - Round-robin matchup generation, K-factor configurable
  - Debate judge scoring, consensus selection by rating
  - Orchestrated by tournament handler during IDEATION phase
- [x] Evidence graph (`knowledge/evidence_graph.py`) — conflict detection + resolution:
  - Conflict types: direct contradiction, methodological, scope mismatch, quantitative disagreement
  - Assumption tracking (active / invalidated / superseded)
  - Provenance chains linking evidence to conclusions
- [x] Conflict detection (`knowledge/conflict_detection.py`) — deterministic (no LLM needed):
  - Flags new evidence contradicting supported hypotheses
  - Maintains evidence-hypothesis linkage graph
- [x] Pydantic models (`knowledge/models.py`) — entity types, relationships, evidence sources, hypothesis status, confidence levels
- [x] Structured debate mechanism in IDEATION:
  - `[CHALLENGE: agent-id: reason]` syntax, defender/challenger prompts
  - Resolution markers (`[RESOLVED]`, `[CONCEDE]`), debate judge scoring
- [x] Tests: world model, evidence graph, hypothesis tournament

### Exit Criteria

- Agents build a queryable world model during research
- Competing hypotheses are ranked by Elo tournament
- Conflicting evidence is detected and tracked
- Knowledge state is serializable and resumable

---

## Phase 8: Multi-Provider Literature ✓ COMPLETE

**Goal**: Search across multiple academic and domain-specific sources with intelligent routing.

### Tasks

- [x] Literature providers beyond arXiv:
  - PubMed, bioRxiv (biomedical)
  - NASA ADS (astronomy/astrophysics)
  - Google Scholar (general academic)
  - Semantic Scholar (citation graphs + full-text)
  - SSRN (finance/economics)
  - SEC EDGAR (financial filings)
  - FRED (Federal Reserve economic data)
- [x] Domain-aware provider routing (`literature/domain_router.py`):
  - Classify research topics into academic domains
  - Route queries to domain-relevant providers
  - Keyword taxonomy for astrophysics, biology, chemistry, physics, economics, finance, medicine
- [x] Citation chain handling (`literature/citation_chains.py`)
- [x] Unified search service (`literature/search_service.py`) with keyword + provider-targeted syntax

### Exit Criteria

- Literature search draws from 10+ sources
- Domain routing prevents off-topic results
- Citation chains can be traversed across providers

---

## Phase 9: Domain System + Finance ✓ COMPLETE

**Goal**: Plugin-based domain architecture with finance as the second domain.

### Tasks

- [x] Domain registry (`domains/registry.py`) — lazy-loading plugin system:
  - Get/list/register domains
  - Each domain defines: name, source providers, document template, role prompts, default roles per mode, search strategies, literature instructions
- [x] Science domain (`domains/science/`) — refactored existing roles into domain plugin
- [x] Finance domain (`domains/finance/`) — fully implemented:
  - Roles: economist, quant, strategist, risk_analyst, experimentalist, writer, editor, reviewer
  - Mode-specific teams: directed, explore, empirical, strategy, policy
  - Data sources: SSRN, SEC EDGAR, FRED, Semantic Scholar
  - Role-targeted search strategies and later-round reinforcements

### Exit Criteria

- Paradigm can run research cycles in both science and finance domains
- Adding a new domain requires only a new directory with config + prompts
- Domain-specific agent behavior is driven by config, not hardcoded logic

---

## Phase 10: Web Frontend ✓ COMPLETE

**Goal**: Production-grade React UI for monitoring and controlling research sessions.

### Tasks

- [x] React 19 + TypeScript + Vite + Tailwind app scaffolding
- [x] State management: Zustand stores + TanStack React Query
- [x] Pages: Dashboard, ResearchPage, PapersPage, SessionPage, AgentsPage
- [x] Session monitoring components:
  - PhaseTracker, AgentPanel, MessagesPanel (streaming markdown + LaTeX)
  - InteractionBar (pause/resume/abort), ApprovalDialog, EventLog
  - ConnectionIndicator, StatsBar
- [x] KnowledgePanel — real-time world model visualization:
  - Entities, hypotheses, evidence, tournament rankings, conflicts
  - WebSocket `KnowledgeUpdateMsg` sync
- [x] WebSocket client with exponential backoff reconnection
- [x] REST client with API key auth via localStorage
- [x] Demo runner (`backend/api/services/demo_runner.py`) — simulated full research cycle for UI testing

### Exit Criteria

- Researcher can start, monitor, and control research cycles from a browser
- Real-time streaming of agent output with markdown + math rendering
- Knowledge state visible and updated live

---

## Phase 11: Web API + Security ✓ COMPLETE

**Goal**: FastAPI backend with REST + WebSocket, hardened for production deployment.

### Tasks

- [x] FastAPI backend (`backend/api/`) with REST endpoints + WebSocket protocol
- [x] SessionManager — async session orchestration bridging engine to WebSocket
- [x] WebSocketDisplayAdapter — implements DisplayManager interface over WebSocket
- [x] Conceptual figure generation — auto-matplotlib diagrams for non-experimental papers
- [x] Paper reproducibility — save working code alongside published papers

#### Security hardening (Prompt 54)

- [x] CORS lockdown: configurable via `PARADIGM_CORS_ORIGINS` env var (was wildcard `*`)
- [x] WebSocket authentication: API key required via query param or header (was unauthenticated)
- [x] Timing-safe API key comparison: `secrets.compare_digest()` (was `==`)
- [x] SQL field-name validation: regex whitelist in `database.py` (was dynamic f-string)
- [x] Sandbox safety: block `os.system()`, `os.popen()`, `os.exec*()` (were unblocked)
- [x] Agent prompt: removed `os.system()` instruction, packages listed as pre-installed
- [x] Error message sanitization: generic messages to clients, details in server logs
- [x] Session/cycle ID entropy: `secrets.token_hex(16)` = 128-bit (was 48-bit)
- [x] Frontend: auto-detect `wss://` vs `ws://`, pass API key on WebSocket connect

### Exit Criteria

- No API keys exposed in source code or client responses
- WebSocket connections are authenticated
- CORS restricted to configured origins
- Sandbox blocks all shell execution primitives
- Session IDs are cryptographically strong

---

## Phase 12: Production Hardening — PLANNED

**Goal**: Multi-user support, rate limiting, and observability for real deployment.

### Tasks

- [ ] **Authentication upgrade**: JWT or OAuth2 replacing single shared API key
- [ ] **Multi-user isolation**: user context on all requests, per-resource ownership validation
- [ ] **Rate limiting**: `slowapi` or similar middleware on all endpoints
- [ ] **Session timeouts**: auto-cleanup of idle sessions
- [ ] **Audit logging**: structured, queryable trail of who accessed/modified what
- [ ] **API key rotation**: per-user tokens with expiration and revocation
- [ ] **Frontend auth**: move API key from localStorage to httpOnly cookie
- [ ] **Input validation**: content filtering and length limits on all user-facing fields
- [ ] **Request size limits**: prevent memory exhaustion via oversized payloads
- [ ] **CSP headers**: Content-Security-Policy on frontend responses
- [ ] **HTTPS enforcement**: TLS termination, HSTS headers
- [ ] **Monitoring**: health metrics, error rates, latency tracking (Prometheus/Grafana or similar)

### Exit Criteria

- Multiple users can run concurrent sessions without data leakage
- Abuse is mitigated by rate limiting and input validation
- Operators have visibility into system health and usage

---

## Future Phases (Post-MVP)

These are tracked but not scheduled:

- **Conference mode**: Synchronous multi-agent discussion events
- **Grant mechanism**: Scarce compute resources agents compete for
- **Retraction system**: Detect and retract flawed papers
- **Scaling**: Move from SQLite → Postgres, single-node → distributed
- **Pre-registration**: Agents register hypotheses before testing
- **Domain plugins**: More domains — MESA for stellar physics, bioinformatics, climate science
- **Human-in-the-loop mode**: Real scientists collaborate with agent teams
- **Replication challenge**: Limit literature to pre-2020, see if agents re-derive recent results
- **Continuous prompt tuning**: Systematic evaluation and improvement of agent prompts
