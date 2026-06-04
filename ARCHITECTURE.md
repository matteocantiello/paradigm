# Paradigm — Architecture

## System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HUMAN OPERATOR                                │
│  CLI commands: run, status, inspect, pause, override, papers         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR                                 │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ Phase Machine │  │  Scheduler   │  │   Token Budget Tracker   │   │
│  │              │  │ (turn-taking)│  │                          │   │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    Message Router                             │    │
│  │  All agent ↔ agent communication passes through here         │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                  Checkpoint Manager                           │    │
│  │  Compress conversation → summary, save/load thread state     │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                  Agent Memory Store                            │    │
│  │  Episodic memories: inject at start, reflect at end           │    │
│  │  ChromaDB "agent_memories" collection, recency × similarity   │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────────────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Theor.│ │Analyt│ │Synth.│ │Exper.│ │Skept.│  ← Research Agents
│  01  │ │  01  │ │  01  │ │  01  │ │  01  │     (Claude API calls
└──┬───┘ └──────┘ └──────┘ └──┬───┘ └──────┘      with skill prompts)
   │                          │
   │  (generates code)        │  (generates code)
   │                          │
   ▼                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CODE SANDBOX (Docker)                           │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐                         │
│  │  Container A      │  │  Container B      │  --network=none (default)│
│  │  Python 3.12      │  │  Python 3.12      │  CPU/mem limits        │
│  │  numpy,scipy,...  │  │  numpy,scipy,...  │  5min timeout           │
│  └──────────────────┘  └──────────────────┘                         │
│                                                                      │
│  Safety: code logged → pattern scan → execute → capture output       │
└─────────────────────────────────────────────────────────────────────┘

   ▼ (paper draft ready)

┌─────────────────────────────────────────────────────────────────────┐
│                         JOURNAL                                      │
│                                                                      │
│  ┌──────────┐     ┌──────────┐  ┌──────────┐                       │
│  │  Editor   │────►│Reviewer A│  │Reviewer B│  ← Journal Agents     │
│  │  Agent    │     │ (strict) │  │(methods) │                       │
│  └────┬─────┘     └────┬─────┘  └────┬─────┘                       │
│       │                │              │                              │
│       ▼                ▼              ▼                              │
│  ┌──────────────────────────────────────────┐                       │
│  │  Decision: Accept / Revise / Reject       │                       │
│  └──────────────────────────────────────────┘                       │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                                   │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │   SQLite      │  │   ChromaDB   │  │   Event Log (JSONL)      │   │
│  │              │  │              │  │                          │   │
│  │ - papers     │  │ - paper      │  │ - all agent messages     │   │
│  │ - agents     │  │   embeddings │  │ - API calls              │   │
│  │ - threads    │  │ - agent      │  │ - code executions        │   │
│  │ - graveyard  │  │   memories   │  │ - state changes          │   │
│  │ - citations  │  │              │  │ - errors                 │   │
│  │ - tokens     │  │              │  │ - memory reflections     │   │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

           ▲
           │ (search)
           │
┌─────────────────────────────────────────────────────────────────────┐
│                    LITERATURE SERVICE                                 │
│                                                                      │
│  ┌──────────────┐  ┌──────────────────────┐                         │
│  │  arXiv API    │  │  Internal Corpus     │                         │
│  │  (live search)│  │  (published papers)  │                         │
│  │  rate-limited │  │                      │                         │
│  └──────────────┘  └──────────────────────┘                         │
│                                                                      │
│  Unified search: query → [arXiv results + internal results] → rank  │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow: One Research Cycle

```
1. SEED
   Human provides prompt → Orchestrator creates thread → Phase: SEEDING
   ↳ Agent episodic memories retrieved from ChromaDB (per-agent, recency-ranked)
   ↳ Graveyard lessons loaded (dead-end avoidance)
   ↳ Perplexity seed discovery (if enabled): pre-seeds literature corpus with key papers

2. IDEATION (configurable rounds, research agents — writer/editor excluded)
   Round 1: Each agent proposes ideas/hypotheses (with memory context)
   Round N: Agents respond, critique, refine
   Live literature search: agents embed [SEARCH: ...] tags, orchestrator fetches arXiv
   Output: Ranked hypotheses + literature context

3. PLANNING (configurable rounds, research agents — writer/editor excluded)
   Round 1: Propose research plan (tasks, assignments, timeline)
   Round N: Refine and finalize, with continued literature search
   Output: Research plan checkpoint

4. EXECUTION (experimentalist leads, analyst + theorist support)
   Agents generate Python code for experiments (```python blocks)
   Code runs in Docker sandbox (--network=none by default, --network-access to enable)
   Results captured, figures extracted
   Multi-round: propose → execute → analyze → retry on failure
   Circuit breaker: halt if failure rate exceeds threshold
   Output: Experimental results + figures

5. WRITING (writer leads, all contribute sections)
   Section drafting: each role assigned specific sections
   Writer assembles and edits for coherence
   ↳ LaTeX math enforcement: Unicode math chars converted to LaTeX notation
   ↳ Citation grounding (if enabled): Perplexity inserts arXiv references into citable sections
   Editor does internal review → accept or revise
   Figures embedded inline from execution phase
   Output: Paper draft (markdown)

6. SUBMISSION
   Paper submitted to Editor agent
   Editor does desk review (reject if below threshold)
   Editor assigns 2 Reviewer agents

7. PEER REVIEW (2 reviewers, independent)
   Each reviewer produces structured review
   Editor synthesizes decision

8. DECISION
   Accept → Publication pipeline
   Revise → Feedback to team, revision cycle (up to max_revision_rounds)
   Reject → Graveyard with lessons learned

9. PUBLICATION
   Paper status → published
   Abstract + sections embedded in ChromaDB
   Citation graph updated
   Paper discoverable by future research cycles

10. REFLECTION (post-cycle)
    Each agent that contributed undergoes a reflection call (Sonnet, temp=0.3)
    3-5 episodic memories extracted per agent (insight/mistake/strategy/collaboration)
    Memories stored in ChromaDB for retrieval in future cycles
```

## Correctness Kernel (optional sub-phases)

Empirical/computational science has no proof checker (the way formal math has a kernel
that makes hallucination structurally impossible). Paradigm manufactures **proxy
kernels** that slot into the cycle as default-off, opt-in gates. When enabled they add
two sub-phases and three human-gate points; the legacy autonomous flow is unchanged when
they are off.

```
 PLANNING
    │
    ▼  (if knowledge.enable_preregistration)
 PRE_REGISTRATION   Theorist freezes one machine-readable, falsifiable PredictionRule
                    per hypothesis (metric token + direction + bounds + REQUIRED
                    refutation condition). Non-falsifiable hypotheses are dropped.
                    Rules are injected into the EXECUTION prompt.
    │
    ▼
 EXECUTION          Experimentalist prints results as RESULT[label]=value
                    (the "console-as-data-bus" contract).
    │
    ▼  (if orchestrator.enable_verification)
 VERIFICATION       Each successful experiment re-runs in a FRESH, seeded
                    --network=none `verify/<thread>` workspace. A result is "accepted"
                    only if its RESULT[...] tokens reproduce within tolerance; otherwise
                    it is demoted (accepted | nondeterministic | rejected). If nothing
                    reproduces → status `verification_failed`, abort before WRITING.
                    Post-execution, each frozen rule is evaluated → confirmed | refuted
                    | inconclusive (computed ONLY from the frozen rule).
    │
    ▼
 WRITING / REVIEW   Fact Sheet carries the verification ledger + pre-registration
                    verdicts; refuted hypotheses become FORBIDDEN claims.
```

**Hybrid human-gate + provenance** (`orchestrator.human_gate_mode` = off | advisory |
blocking). Configurable checkpoints at `problem_selection` (pre-IDEATION),
`pre_registration`, and `final_verification`, reusing the `InterventionHook`. `blocking`
with no hook registered falls back to *continue* (deadlock guard), so an autonomous run
never hangs. Each paper records an engine-written `ProvenanceRecord` (framed_by /
registered_by / verified_by) — never written by agents, so it can't be confabulated.

**Persistence.** `verification`, `prereg`, and `provenance` are stored as JSON columns on
the `papers` table (added via idempotent `ALTER TABLE`), and read back by `paradigm eval`
(reproduction-pass-rate, pre-registration verdict).

**Output formats** (Phase 2). Optional figure-aware multimodal review (the editor sees the
actual figures), journal-ready LaTeX/PDF output, and resolve-or-drop citations are layered
on the WRITING/REVIEW phases — all default-off toggles.

## Agent Interaction Model

Agents interact through structured messages, never free-form conversation. This keeps interactions parseable and auditable.

```
Message {
  from: agent_id
  to: "team" | agent_id | "editor"
  thread_id: uuid
  phase: ResearchPhase
  type: MessageType
  content: string (the actual reasoning/proposal/critique)
  references: [{type: "arxiv"|"internal", id: string}]
  code: optional string (for execution phase)
  metadata: dict
}

MessageType:
  - proposal     (new idea, hypothesis, research direction)
  - critique     (challenge to a proposal)
  - question     (request for clarification)
  - result       (experimental outcome, analysis finding)
  - draft_section (piece of paper writing)
  - review       (peer review of paper)
  - decision     (editorial accept/reject/revise)
  - summary      (checkpoint summary)
```

## Checkpoint Compression Strategy

Context windows are finite. The checkpoint system prevents conversations from growing unbounded.

**When to compress**: After each phase transition, the orchestrator summarizes the phase's conversation into a structured checkpoint.

**What's preserved**: Hypotheses, decisions, key evidence, references, code snippets, results.

**What's discarded**: Tentative reasoning, exploratory tangents, rejected ideas (unless they contain lessons).

**How**: The orchestrator calls Claude with the full phase conversation and a "summarize into this JSON structure" prompt. The resulting checkpoint becomes the input for the next phase.

```
Phase N conversation (might be 50k tokens)
        │
        ▼
  Claude summarization call
        │
        ▼
Phase N checkpoint (typically 2-5k tokens)
        │
        ▼
Phase N+1 starts with checkpoint as context
```

## Agent Episodic Memory

Cross-cycle learning that persists between research runs.

```
┌─────────────────────────────────────────────────────────┐
│                    MEMORY LIFECYCLE                       │
│                                                          │
│  Cycle N end:                                            │
│    engine → generate_reflections()                       │
│         ↓ (one Claude call per agent, Sonnet, temp=0.3)  │
│    parse [type] content lines → Memory objects           │
│         ↓                                                │
│    AgentMemoryStore.add_memories() → ChromaDB            │
│                                                          │
│  Cycle N+1 start:                                        │
│    _build_agent_prompt(agent, phase, round)               │
│         ↓                                                │
│    AgentMemoryStore.search(seed_prompt, agent_id)        │
│         ↓                                                │
│    rank_memories_with_recency(results, half_life=30d)    │
│         ↓ (top 5 by similarity × recency)                │
│    format_memory_context() → inject into prompt          │
└─────────────────────────────────────────────────────────┘
```

**Key properties:**
- Per-agent isolation: each agent sees only their own memories
- Recency decay: `score = similarity × 0.5^(age_days / half_life_days)`
- Bounded: max 5 memories, max 2000 chars injected per prompt
- Non-fatal: reflection failure doesn't block the cycle
- Stored alongside paper embeddings in the same ChromaDB path (different collection). Paper embeddings use per-cycle isolated collections (`paradigm_papers_{cycle_id}`), while agent memories share a single `agent_memories` collection across cycles

## Reputation & Incentives

```
Research Agent Score = 
    0.30 × papers_published
  + 0.30 × citation_impact (normalized)
  + 0.15 × collaboration_score
  + 0.10 × review_quality
  + 0.15 × novelty_bonus

Editorial Agent Score =
    0.40 × journal_citation_rate (avg citations of accepted papers)
  + 0.30 × rejection_accuracy (rejected papers that aren't later vindicated)
  + 0.20 × review_turnaround
  + 0.10 × author_satisfaction (revision quality)
```

Scores are injected into agent system prompts as context, creating pressure to maintain and improve reputation. High-reputation agents get priority in collaboration invitations and more compute budget.
