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
│  │  Container A      │  │  Container B      │  --network=none        │
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
│  │ - papers     │  │ - embeddings │  │ - all agent messages     │   │
│  │ - agents     │  │ - semantic   │  │ - API calls              │   │
│  │ - threads    │  │   search     │  │ - code executions        │   │
│  │ - graveyard  │  │              │  │ - state changes          │   │
│  │ - citations  │  │              │  │ - errors                 │   │
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

2. IDEATION (3 rounds, all research agents)
   Round 1: Each agent proposes ideas/hypotheses
   Round 2: Agents respond to each other's proposals
   Round 3: Convergence — agents vote/prioritize
   Output: Ranked list of hypotheses

3. PLANNING (2 rounds, all research agents)
   Round 1: Propose research plan (tasks, assignments, timeline)
   Round 2: Refine and finalize
   Output: Research plan checkpoint

4. LITERATURE (synthesizer leads, all contribute)
   Orchestrator calls arXiv API based on agent queries
   Agents review and summarize relevant papers
   Output: Literature review checkpoint

5. EXECUTION (experimentalist leads, theorist supports)
   Agents generate Python code for experiments
   Code runs in Docker sandbox
   Results captured and returned to agents
   Agents interpret results
   Output: Experimental results checkpoint

6. WRITING (writer leads, all contribute sections)
   Sections assigned by skill:
     - Writer: abstract, introduction, conclusion
     - Theorist: methods/theory section
     - Analyst: results section
     - Synthesizer: discussion section
   Writer assembles and edits for coherence
   Skeptic does internal review
   Output: Paper draft

7. SUBMISSION
   Paper submitted to Editor agent
   Editor does desk review (reject if below threshold)
   Editor assigns 2 Reviewer agents

8. PEER REVIEW (2 reviewers, independent)
   Each reviewer produces structured review
   Editor synthesizes decision

9. DECISION
   Accept → Publication pipeline
   Revise → Feedback to team, return to WRITING
   Reject → Graveyard with lessons learned

10. PUBLICATION
    Paper status → published
    Abstract + sections embedded in ChromaDB
    Citation graph updated
    Author reputations updated
    Paper discoverable by future research cycles
```

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
