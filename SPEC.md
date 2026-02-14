# Paradigm — Agentic Science Platform

## 1. Vision

Paradigm is a sandboxed environment where multiple AI agents with differentiated skills collaborate and compete to advance scientific knowledge. Agents generate hypotheses, search literature, run computational experiments, write papers, and submit them to an agent-managed peer review journal. Published papers enter a growing internal corpus that future agents build upon.

The architecture is domain-agnostic and designed for eventual extension beyond science (policy simulation, creative content, medicine, management strategy).

The name references Thomas Kuhn — paradigm shifts emerge from communities of researchers, not individuals.

## 2. Core Loop

```
┌─────────────────────────────────────────────────────────┐
│                    RESEARCH CYCLE                        │
│                                                         │
│  Prompt/Seed ──► Ideation ──► Literature Search          │
│       │              │              │                    │
│       │              ▼              ▼                    │
│       │         Research Plan ◄── Gap Analysis           │
│       │              │                                   │
│       │              ▼                                   │
│       │    Task Division (agent teams)                   │
│       │         │         │         │                    │
│       │    Compute    Analysis   Writing                 │
│       │         │         │         │                    │
│       │         └─────────┴─────────┘                    │
│       │                   │                              │
│       │              Draft Paper                         │
│       │                   │                              │
│       │              Submission                          │
│       │                   │                              │
│       │         ┌─────────┴─────────┐                    │
│       │     Editor Agent      Reviewer Agents            │
│       │         │                   │                    │
│       │         ▼                   ▼                    │
│       │    Accept/Reject     Structured Review           │
│       │         │                                        │
│       │    ┌────┴────┐                                   │
│       │  Accept    Revise ──► Revision Cycle             │
│       │    │                                             │
│       │    ▼                                             │
│       │  PUBLISH ──► Internal Corpus ──► Next Cycle      │
│       └─────────────────────────────────────────────────┘
```

## 3. Operating Modes

| Mode | Description | Trigger |
|------|-------------|---------|
| **Directed** | User provides a specific research question or problem | `"Develop a model to explain LRD"` |
| **Exploratory** | Agents freely discuss what's interesting, identify open problems | `"Explore open problems in turbulence"` |
| **Hypothesis Generator** | Produce testable hypotheses for real scientists to vet | `"Generate hypotheses about stellar variability"` |
| **Experimental Design** | Propose real-world experiments (to be vetted by humans) | `"Design experiments to test X"` |
| **Replication** | Attempt to re-derive or replicate existing results | `"Re-derive the period-luminosity relation"` |

## 4. Agent Architecture

### 4.1 Research Agents

Each research agent is a Claude API call with a differentiated system prompt. Differentiation is achieved through:

- **Skill profile**: Defines what the agent is good at (see taxonomy below)
- **Personality traits**: Risk tolerance, rigor preference, collaboration style
- **Publication record**: Accumulated over time, affects reputation score
- **Memory state**: Compressed checkpoints of ongoing research threads

#### Skill Taxonomy (MVP)

| Skill | Description | System Prompt Focus |
|-------|-------------|-------------------|
| **Theorist** | Mathematical modeling, derivations, analytical reasoning | Prioritize formal arguments, equations, proofs |
| **Data Analyst** | Statistical analysis, pattern finding, data interpretation | Prioritize empirical evidence, statistical rigor |
| **Literature Synthesizer** | Finding connections across papers, identifying gaps | Prioritize breadth of reading, cross-referencing |
| **Experimentalist** | Designing and running computational experiments | Prioritize reproducibility, methodology |
| **Writer** | Scientific communication, paper structuring | Prioritize clarity, narrative, proper formatting |
| **Skeptic** | Challenging assumptions, finding flaws, adversarial review | Prioritize logical consistency, edge cases |

### 4.2 Journal Agents

| Role | Count | Behavior |
|------|-------|----------|
| **Editor-in-Chief** | 1 | Desk reject/accept for review, assign reviewers, final decision |
| **Reviewer** | 2-3 per paper | Evaluate novelty, rigor, clarity, significance. Different personalities (harsh, generous, methods-focused, impact-focused) |

### 4.3 Agent State Schema

```json
{
  "agent_id": "theorist-01",
  "skill_profile": "theorist",
  "personality": {
    "risk_tolerance": 0.7,
    "rigor_preference": 0.9,
    "collaboration_tendency": 0.5
  },
  "reputation": {
    "h_index": 0,
    "total_citations": 0,
    "papers_published": 0,
    "reviews_completed": 0,
    "collaboration_score": 0.0
  },
  "active_threads": ["thread_uuid_1"],
  "memory_checkpoints": {}
}
```

### 4.4 Agent Episodic Memory

Agents accumulate **episodic memories** — persistent lessons that survive across research cycles. At the end of each cycle, a reflection call extracts 3-5 memories per agent, categorized as:

| Type | Description |
|------|-------------|
| **insight** | A factual discovery or key finding |
| **mistake** | An approach that failed or was unproductive |
| **strategy** | A methodological approach that worked well |
| **collaboration** | A lesson about working with other agents |

Memories are stored in ChromaDB (separate collection from paper embeddings) and retrieved via **semantic search with recency decay** at the start of each cycle. Each agent sees only their own memories, injected at the top of their prompt context.

**Recency scoring**: `combined_score = similarity × 0.5^(age_days / half_life_days)`. Default half-life is 30 days, so memories naturally fade unless they remain topically relevant.

**Bounded injection**: At most `max_memories_per_prompt` (default 5) memories are injected, capped at `max_memory_chars` (default 2000) to avoid crowding out literature and checkpoint context.

```
End of cycle:   engine → generate_reflections() → AgentMemoryStore.add_memories()
                                ↓ Claude reflection call (per agent, Sonnet, temp=0.3)
Start of cycle: engine._build_agent_prompt() → AgentMemoryStore.search() → recency rank → inject
```

## 5. Literature & Knowledge Infrastructure

### 5.1 External Literature Access

- **Primary source**: arXiv API (https://arxiv.org/help/api)
  - Search by keyword, author, category, date range
  - Retrieve abstracts, metadata, PDF links
  - Rate limited: 1 request per 3 seconds
- **Retrieval pipeline**:
  1. Agent formulates search query
  2. Orchestrator calls arXiv API
  3. Results returned as structured metadata + abstracts
  4. Agent can request full paper fetch (PDF → text extraction)
  5. Relevant passages embedded and cached locally

### 5.2 Internal Corpus (Published Papers)

- **Storage**: SQLite for metadata + ChromaDB for semantic search
- **Schema**:
  ```sql
  CREATE TABLE papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    authors TEXT NOT NULL,        -- JSON array of agent_ids
    body TEXT NOT NULL,            -- Full paper text (markdown)
    keywords TEXT,                 -- JSON array
    citations TEXT,                -- JSON array of paper_ids
    submitted_at DATETIME,
    published_at DATETIME,
    status TEXT,                   -- draft/submitted/in_review/accepted/rejected/published
    review_scores TEXT,            -- JSON: {novelty, rigor, clarity, significance}
    citation_count INTEGER DEFAULT 0
  );
  ```
- **Embeddings**: Abstract + section summaries embedded in ChromaDB (`paradigm_papers` collection) for semantic retrieval
- **Agent memories**: Episodic memories stored in a separate ChromaDB collection (`agent_memories`) — see §4.4
- **Citation graph**: Stored in SQLite, queryable for influence metrics

### 5.3 Research Thread Checkpoints

To prevent context window exhaustion, each research thread maintains a compressed state:

```json
{
  "thread_id": "uuid",
  "title": "Modeling LRD in stellar variability",
  "status": "active",
  "created_at": "2026-02-11T...",
  "updated_at": "2026-02-11T...",
  "participants": ["theorist-01", "data-analyst-01"],
  "hypothesis": "LRD in massive stars arises from subsurface convective zones...",
  "key_findings": ["Finding 1...", "Finding 2..."],
  "literature_reviewed": [{"arxiv_id": "...", "relevance": "...", "key_point": "..."}],
  "experiments_run": [{"description": "...", "result": "...", "code_path": "..."}],
  "open_questions": ["Question 1..."],
  "next_steps": ["Step 1..."],
  "full_conversation_summary": "Compressed narrative of all agent interactions...",
  "current_draft": null
}
```

This checkpoint is what agents receive when resuming work, not the full conversation history.

## 6. Computational Experiment Sandbox

### 6.1 Architecture

Each agent's code execution happens in an isolated Docker container:

```
┌──────────────────────────────────────┐
│          Orchestrator (Host)          │
│                                       │
│   ┌─────────┐  ┌─────────┐          │
│   │ Agent 1  │  │ Agent 2  │  ...    │
│   │ Container│  │ Container│          │
│   │ - Python │  │ - Python │          │
│   │ - numpy  │  │ - numpy  │          │
│   │ - scipy  │  │ - scipy  │          │
│   │ - etc.   │  │ - etc.   │          │
│   │ NO NET   │  │ NO NET   │          │
│   └────┬─────┘  └────┬─────┘          │
│        │              │               │
│        ▼              ▼               │
│   ┌─────────────────────────┐         │
│   │   Shared Volume (R/O)   │         │
│   │   - datasets            │         │
│   │   - published papers    │         │
│   └─────────────────────────┘         │
│                                       │
│   ┌─────────────────────────┐         │
│   │   Results Volume (R/W)  │         │
│   │   - per-agent output    │         │
│   └─────────────────────────┘         │
└──────────────────────────────────────┘
```

### 6.2 Constraints

- **No network access** from containers (--network=none)
- **CPU/memory limits** per container (configurable)
- **Execution timeout**: 5 minutes default, configurable
- **Pre-installed packages**: numpy, scipy, matplotlib, pandas, scikit-learn, sympy, astropy
- **Output**: stdout/stderr captured, files written to results volume
- **Audit**: All code submitted for execution is logged before running

### 6.3 Safety Protocol

1. Agent generates Python code as a string
2. Orchestrator logs the code with agent_id and timestamp
3. Code is written to a temp file in the container
4. Container executes with resource limits
5. stdout, stderr, and output files are captured
6. Results returned to agent as structured data
7. Human operator can pause/inspect at any step via intervention hooks

## 7. Orchestrator Design

The orchestrator is the central coordinator. It is a Python process (not an agent) that:

1. **Manages turn-taking**: Decides which agent speaks next based on phase and context
2. **Routes messages**: Agents never communicate directly; all messages go through the orchestrator
3. **Manages state**: Creates/updates research thread checkpoints
4. **Calls APIs**: arXiv, Claude, Docker
5. **Enforces rules**: Token budgets, timeouts, sandbox constraints
6. **Logs everything**: All agent inputs/outputs, decisions, API calls

### 7.1 Phase Machine

The research cycle is a state machine:

```python
class ResearchPhase(Enum):
    SEEDING = "seeding"           # Initial prompt processed
    IDEATION = "ideation"         # Agents brainstorm, propose hypotheses
    PLANNING = "planning"         # Research plan formalized
    LITERATURE = "literature"     # Literature search and review
    EXECUTION = "execution"       # Experiments, analysis, derivations
    WRITING = "writing"           # Paper drafting
    INTERNAL_REVIEW = "internal"  # Team self-review before submission
    SUBMITTED = "submitted"       # Submitted to journal
    PEER_REVIEW = "peer_review"   # Under review
    REVISION = "revision"         # Revise and resubmit
    PUBLISHED = "published"       # Accepted and published
    REJECTED = "rejected"         # Rejected (with feedback stored)
```

### 7.2 Communication Protocol

All agent interactions are structured messages:

```json
{
  "from": "theorist-01",
  "to": "team" | "agent_id" | "editor",
  "thread_id": "uuid",
  "phase": "ideation",
  "type": "proposal" | "critique" | "question" | "result" | "draft_section" | "review",
  "content": "...",
  "references": [{"type": "arxiv", "id": "..."}, {"type": "internal", "id": "..."}],
  "metadata": {}
}
```

## 8. Peer Review System

### 8.1 Submission Pipeline

1. Research team finalizes paper (markdown with structured sections)
2. Paper submitted to Editor-in-Chief agent
3. Editor does desk review:
   - Scope check: Is this science? Is it novel enough to review?
   - Quality floor: Is it coherent and properly formatted?
   - If desk reject: feedback stored, agents learn from it
4. Editor assigns 2 reviewer agents (matched by keyword overlap with their skill profile, excluding team members)
5. Each reviewer produces structured review:
   ```json
   {
     "novelty": 1-10,
     "rigor": 1-10,
     "clarity": 1-10,
     "significance": 1-10,
     "recommendation": "accept" | "minor_revision" | "major_revision" | "reject",
     "summary": "...",
     "strengths": ["..."],
     "weaknesses": ["..."],
     "questions": ["..."],
     "suggestions": ["..."]
   }
   ```
6. Editor makes final decision based on reviews
7. If revision requested: feedback sent to research team, revision cycle begins
8. On acceptance: paper published to internal corpus

### 8.2 Anti-Gaming Measures

- Reviews are **single-blind** (reviewers know authors, authors don't know reviewers)
- Editor cannot assign reviewers from the same research team
- Reviewer agents have varied personalities (some strict, some lenient) to simulate real review variance
- Papers that only self-cite excessively are flagged
- Editor is incentivized by downstream citation rates of accepted papers

## 9. Incentive System

### 9.1 Research Agent Metrics

| Metric | Description | Weight |
|--------|-------------|--------|
| Papers published | Count of accepted papers | 0.3 |
| Citation impact | Citations received by published papers | 0.3 |
| Collaboration score | Successful co-authorships | 0.15 |
| Review contribution | Quality of reviews written | 0.1 |
| Novelty bonus | Papers that open new research threads | 0.15 |

The composite score influences:
- Likelihood of being invited to collaborate
- Weight of opinions in team discussions
- Priority in resource allocation (compute time)

### 9.2 Editorial Agent Metrics

| Metric | Description |
|--------|-------------|
| Journal impact | Average citation rate of published papers |
| Rejection accuracy | Rejected papers should not be "rediscovered" as valuable later |
| Turnaround time | Speed of editorial decisions |
| Review quality | Quality of selected reviewers (measured by author satisfaction) |

### 9.3 Failed Research Storage

Rejected papers and abandoned threads are stored in a "graveyard" table:

```sql
CREATE TABLE graveyard (
  id TEXT PRIMARY KEY,
  type TEXT,              -- 'rejected_paper' | 'abandoned_thread'
  content TEXT,           -- Compressed summary
  failure_reason TEXT,    -- Why it failed
  lessons_learned TEXT,   -- What agents should avoid repeating
  created_at DATETIME
);
```

Agents can query the graveyard to avoid repeating known dead ends.

## 10. Human Oversight

### 10.1 Intervention Hooks

- **Pause**: Stop all agent activity
- **Inspect**: View any agent's current state, conversation history, or pending actions
- **Override**: Modify agent decisions or research direction
- **Inject**: Add new information or constraints mid-cycle
- **Kill**: Terminate a research thread or agent

### 10.2 Logging

All events written to structured log (JSON lines):

```json
{
  "timestamp": "...",
  "event_type": "agent_message | api_call | code_execution | state_change | error | phase_transition | literature_search | checkpoint_created | paper_submitted | review_completed | publication | memory_generated",
  "agent_id": "...",
  "thread_id": "...",
  "phase": "...",
  "content": "...",
  "metadata": {}
}
```

### 10.3 Dashboard (Post-MVP)

- Real-time view of active research threads
- Agent reputation leaderboard
- Publication statistics
- Citation graph visualization
- Resource usage monitoring

## 11. Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.12+ | Ecosystem, Claude SDK, scientific libraries |
| LLM | Claude API (claude-sonnet-4-5) | Cost-effective for agents, opus for complex reasoning |
| Vector DB | ChromaDB | Simple, local, good enough for MVP |
| Relational DB | SQLite | Zero config, sufficient for single-node |
| Containers | Docker | Standard, well-supported sandbox |
| Task orchestration | asyncio + custom state machine | No framework overhead, full control |
| Literature | arXiv API | Free, comprehensive, well-documented |
| Text extraction | PyMuPDF (fitz) | PDF to text for full papers |
| Config | YAML | Human-readable, easy to modify |

## 12. Project Structure

```
paradigm/
├── SPEC.md                   ← This file
├── ARCHITECTURE.md           ← System diagrams and data flow
├── DECISIONS.md              ← Architecture decision log
├── CLAUDE.md                 ← Claude Code instructions
├── HISTORY.md                ← Development prompt log
├── pyproject.toml
├── src/
│   └── paradigm/
│       ├── __init__.py
│       ├── __main__.py
│       ├── main.py           ← CLI entry point (click)
│       ├── config.py         ← YAML config loader + Pydantic models
│       ├── orchestrator/
│       │   ├── engine.py     ← Main orchestration loop
│       │   ├── phases.py     ← Phase state machine
│       │   └── scheduler.py  ← Agent turn-taking logic
│       ├── agents/
│       │   ├── base.py       ← Base agent class (Claude API)
│       │   ├── factory.py    ← Agent team creation
│       │   ├── memory.py     ← Episodic memory store + reflection
│       │   └── skills.py     ← Skill taxonomy + scientific skills registry
│       ├── literature/
│       │   ├── arxiv.py      ← arXiv API client
│       │   ├── corpus.py     ← Internal corpus management
│       │   ├── embeddings.py ← ChromaDB paper embeddings
│       │   ├── citations.py  ← Citation graph management
│       │   ├── prompt_utils.py ← Search request parsing + formatting
│       │   └── resources.py  ← Code/data/reference resource resolution
│       ├── sandbox/
│       │   ├── docker.py     ← Docker container management
│       │   ├── executor.py   ← Code execution pipeline
│       │   ├── models.py     ← Execution request/result models
│       │   └── safety.py     ← Safety checks and limits
│       ├── journal/
│       │   ├── paper.py      ← Paper models, section drafting
│       │   ├── review.py     ← Peer review process
│       │   └── publication.py← Publication to corpus
│       ├── storage/
│       │   ├── database.py   ← SQLite schema + operations
│       │   └── checkpoints.py← Thread checkpoint management
│       └── logging/
│           └── events.py     ← Structured event logging
├── tests/                    ← pytest test suite (22 test files)
├── docker/
│   └── Dockerfile.sandbox    ← Container image for code execution
├── configs/
│   └── default.yaml          ← Default configuration
└── data/
    └── .gitkeep              ← Runtime data directory
```

## 13. Constraints

- **Budget awareness**: Each research cycle has a configurable token budget. Orchestrator tracks usage per agent.
- **Rate limiting**: arXiv API: 1 req/3s. Claude API: respect tier limits.
- **Determinism**: All random seeds logged for reproducibility.
- **Transparency**: Every agent reasoning step is inspectable.
- **Graceful degradation**: If an API call fails, the system retries with backoff, then records the failure and continues.
