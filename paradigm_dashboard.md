# Paradigm: Real-Time Research Dashboard — Implementation Plan

## Context

Paradigm is a Python CLI tool that orchestrates multi-agent AI research cycles. Specialized agents (theorist-0, analyst-1, experimentalist-2, synthesizer-3, skeptic-4, writer-5, editor-6) collaborate through phases (IDEATION → PLANNING → EXECUTION → WRITING → INTERNAL_REVIEW) to conduct research: they search literature, traverse citation graphs, propose and debate hypotheses, run computational experiments, and write/review a paper. A typical research cycle lasts ~1 hour. Output is saved in a per-run thread/paper folder.

We are adding a **web dashboard** that visualizes the *epistemic* state of a research run — what the system currently believes and why — as distinct from operational state (tokens, agent activity), which is already handled by the terminal UI.

**Read the codebase first.** Before writing any code, explore the repository and identify:
- How phases, rounds, and agents are orchestrated (the main loop)
- Where hypotheses are created, debated, selected (tournament selection logic)
- Where the world-model / evidence-graph layer lives
- Where literature search, paper reading, and citation traversal happen
- Where experiments are dispatched and results/figures are saved
- Where debates are triggered and resolved
- Where review iterations happen
- Whether an event system or DisplayManager already exists (one may have been added recently for the rich terminal UI — if so, build on it; do not create a parallel system)
- The structure of the thread/paper output folder

Report what you find before implementing. Adjust naming/paths in this plan to match codebase conventions.

---

## Architecture Overview

**Event-sourced design.** The research engine emits structured events. The dashboard state is a pure function of the event stream. This gives us replay for free and keeps the dashboard fully decoupled from engine logic.

```
Research Engine
   │ emits
   ▼
Event Bus (in-process)
   ├── Listener 1: plain-text log file (existing)
   ├── Listener 2: rich terminal UI (existing/in progress)
   └── Listener 3: JSONL event writer  ←── NEW
                      │ writes
                      ▼
        thread-<id>/agents/events.jsonl  (append-only)
                      │
        ┌─────────────┴──────────────┐
        ▼                            ▼
   Replay mode                  Live mode
   (load file)                  (watch file + SSE)
        │                            │
        └────────────┬───────────────┘
                     ▼
            FastAPI server  →  SSE endpoint  →  React dashboard
```

**Build order: replay first, live second.** The replay viewer is the same rendering code minus the transport. It is easier to debug, immediately useful for finished threads, and a demo asset. Live streaming is then a one-line change of data source.

---

## Part 1: Event Reporting (Python, in Paradigm core)

### 1.1 Event envelope

Every event shares a common envelope:

```json
{
  "seq": 142,
  "ts": "2026-06-09T14:23:01.512Z",
  "type": "hypothesis.updated",
  "phase": "IDEATION",
  "round": 2,
  "agent": "theorist-0",
  "payload": { }
}
```

- `seq`: monotonically increasing integer, unique within a run. The dashboard orders by `seq`, never by timestamp.
- `agent`: null for engine-level events (phase changes, checkpoints).
- One JSON object per line in `events.jsonl`. The file is append-only; never rewrite past lines.

### 1.2 Event types and payloads

Implement these event types. If the codebase lacks the data for some, emit what is available and leave a TODO.

**Run lifecycle**
- `run.started` — payload: thread_id, prompt summary (first 500 chars), config (rounds, model, mode)
- `run.completed` — payload: status (success/failed), paper_id, duration_s, totals (searches, papers_read, experiments, debates, tokens)
- `phase.started` / `phase.completed` — payload: phase name, rounds planned
- `round.started` / `round.completed` — payload: round number, active agents
- `checkpoint.saved` — payload: phase

**Literature**
- `resource.ingested` — payload: url, kind (paper/reference/code_file), title, saved_pdf (bool)
- `search.performed` — payload: query, n_results, n_new. Do NOT emit one event per result.
- `paper.read` — payload: arxiv_id or identifier, title, chars_read, relevance_note if available
- `citation.followed` — payload: source_paper_id, direction (refs/cited_by), n_found, list of paper ids if available (ids only, not full metadata)
- `paper.flagged_relevant` — payload: paper_id, title, reason (if the world model marks papers as relevant; otherwise skip)

**Hypotheses / world model**
- `hypothesis.created` — payload: hypothesis_id, statement (full text), author agent
- `hypothesis.updated` — payload: hypothesis_id, new status. Status enum: proposed | debated | selected | testing | supported | rejected | inconclusive
- `tournament.round` — payload: matchups [[hyp_a, hyp_b, winner]], rationale snippets if available
- `claim.extracted` — payload: claim_id, statement, source (paper_id or experiment_id)
- `evidence.linked` — payload: claim_id, hypothesis_id, relation (supports/contradicts), weight if available

**Debates**
- `debate.started` — payload: debate_id, challenger, defender, topic (full text)
- `debate.turn` — payload: debate_id, agent, summary (first ~200 chars of argument)
- `debate.resolved` — payload: debate_id, outcome (concede_defender/concede_challenger/judge), winner, n_turns

**Experiments**
- `experiment.started` — payload: experiment_id, title, hypothesis_id if linked
- `experiment.completed` — payload: experiment_id, status (success/failure), retries, artifacts: list of {path, kind: figure|table|data, caption if available}
- `artifact.created` — payload: path, kind, experiment_id. Figures must be referenced by path relative to the thread folder so the server can locate them.

**Writing & review**
- `section.drafted` — payload: section name, author agent, word_count
- `paper.assembled` — payload: paper_id, word_count, n_figures, n_references
- `review.iteration` — payload: iteration number, recommendation (accept/revise/reject), n_required_changes
- `review.final` — payload: outcome (accepted / max_iterations_reached)

**Warnings (light touch)**
- `warning.emitted` — payload: kind (cap_reached/budget_spent/api_error), message. Routine skip/dedup messages should NOT be events — they stay in the log file only.

### 1.3 Emission rules

- Events are facts, not UI instructions. No formatting, no colors.
- Bursty operations (a search returning 50 results) emit ONE aggregate event.
- Full text where it matters (hypothesis statements, debate topics) — the dashboard truncates for display, but the event log doubles as a provenance record for the research-thread design, so don't pre-truncate below ~2000 chars.
- Event writing must never interrupt the run: wrap the writer in try/except; on any write problem, note it on stderr and let the research cycle continue.
- Flush after every write (the file is read incrementally in live mode).

### 1.4 Where this lives

If an event bus / DisplayManager exists from the terminal UI work, add the JSONL writer as another listener and extend the event vocabulary. If not, create `paradigm/events.py` with an `EventBus` class (subscribe/emit), wire the existing log and terminal output through it where convenient, and add emit calls at the orchestration points identified during code exploration. Keep emit calls one-liners; no logic at call sites.

---

## Part 2: Dashboard Server (Python, FastAPI)

New module, e.g. `paradigm/dashboard/server.py`, launched via:

```
paradigm dashboard <thread-id-or-path>      # replay mode (finished or running thread)
paradigm run ... --dashboard                # live mode: starts server alongside the run, prints URL
```

Endpoints:
- `GET /` — serves the built React app (static files)
- `GET /api/threads` — list available threads (id, title, status, date) by scanning the data/papers or threads directory
- `GET /api/threads/{id}/events` — full events.jsonl as JSON array (replay)
- `GET /api/threads/{id}/stream` — SSE endpoint. Sends all existing events, then watches the file and pushes new lines as they appear (check the file every 500 ms; no inotify dependency)
- `GET /api/threads/{id}/artifacts/{path}` — serves figures/files from inside the thread folder. Resolve the requested path first and only serve files whose resolved location is inside that thread's directory; return 404 for anything else.

Implementation notes:
- SSE over WebSockets — one-directional is all we need, simpler to implement and proxy.
- This is a personal, single-user tool: listen on localhost by default, with a `--host` option for the cloud deployment.
- Dependencies: fastapi, uvicorn, sse-starlette (or hand-rolled SSE — fine either way).

---

## Part 3: Dashboard Frontend (React)

Lives in `dashboard/` at repo root (Vite + React + TypeScript preferred; plain JS acceptable). Build output is served by FastAPI. Keep dependencies lean: d3-force or Cytoscape.js for graphs, no heavy UI framework — custom CSS, dark theme.

### 3.1 State model

A single reducer consumes events in `seq` order and produces dashboard state:

```typescript
interface DashboardState {
  run: { threadId, status, phase, round, startedAt, stats }
  hypotheses: Map<id, { statement, status, author, history: StatusChange[] }>
  papers: Map<id, { title, read, relevant, discoveredVia }>
  citationEdges: Edge[]            // paper -> paper
  claims: Map<id, { statement, source }>
  evidenceEdges: { claimId, hypothesisId, relation, weight }[]
  debates: Map<id, { challenger, defender, topic, turns, outcome }>
  experiments: Map<id, { title, status, retries, artifacts }>
  review: { iterations: { n, recommendation, changes }[] , outcome }
  ticker: Event[]                  // last ~50 raw events for the side feed
}
```

The reducer must be a pure function `(state, event) => state`. This is the cornerstone: replay, scrubbing, and live mode all just feed events through it.

### 3.2 Layout

Single page, three zones:

- **Top status bar**: thread id, phase stepper (✓ IDEATION ▸ PLANNING ▸ ...), round, elapsed time, headline counters (papers read, hypotheses alive, experiments done). Compact — one row.
- **Central canvas**: the main view, phase-adaptive (see 3.3), with manual tab override.
- **Right rail (collapsible)**: live event ticker — timestamped one-liners, color-coded by agent, auto-scrolling with pause-on-hover.

Plus, in replay mode, a **bottom scrubber**: timeline slider over `seq`, play/pause, speed control (1×, 5×, 20×, 60×). Phase boundaries and debates marked as ticks on the timeline. Scrubbing backward = re-run reducer from event 0 to target seq (cheap; a 1-hour run is a few thousand events).

### 3.3 Views (tabs on the central canvas)

Default tab follows the current phase; user can pin any tab.

**A. Hypotheses (default for IDEATION/PLANNING)**
Kanban-style columns by status: Proposed → Debated → Selected → Testing → Resolved (supported/rejected/inconclusive, with color: green/red/grey). Cards show statement (truncated, expandable), author agent (colored dot — reuse terminal UI agent colors: theorist blue, analyst orange, experimentalist green, synthesizer magenta, skeptic red, writer cyan, editor yellow), and a small history strip. Card moves animate (~300 ms). Tournament rounds render as a small bracket overlay or sequence of matchup chips on the relevant cards.

**B. Literature (default during heavy searching)**
Force-directed graph. Nodes = papers; appear on `paper.read`, `citation.followed`, `paper.flagged_relevant` — NOT on every search hit (searches only increment a "scanned" counter in the corner, e.g. "186 results scanned"). Node size by degree, fill when read, halo when flagged relevant. Edges from citation traversal. New nodes animate in over ~300 ms with the force simulation gently reheated (alpha target bump, then decay) — never dump a burst of nodes in one frame; queue and stagger insertions ~100 ms apart. Click node → side panel with title, id, who read it, relevance note. Keep it performant: cap visible labels (show on hover/zoom), use canvas rendering if node count exceeds ~300.

**C. Evidence (default late PLANNING / EXECUTION)**
Bipartite graph or matrix: hypotheses on one side, claims on the other; green edges = supports, red = contradicts, thickness = weight. When an evidence link flips a hypothesis status, flash the hypothesis node. This is the "watch the system change its mind" view.

**D. Experiments (default for EXECUTION)**
Grid gallery. Each experiment is a card: title, status chip (running/success/failure/retrying), linked hypothesis. When an `artifact.created` event arrives with kind=figure, the card shows the figure thumbnail (served via the artifacts endpoint) — images materializing in real time is the strongest "research is happening" signal, make it prominent. Click → lightbox with full figure and metadata.

**E. Paper (default for WRITING/REVIEW)**
Document outline as sections appear (`section.drafted`), with author agent and word count per section. Review panel: iteration table (recommendation, required changes) with a sparkline of the changes trajectory (e.g. 73 → 0 → 0) and final outcome banner.

**Debates (overlay, any phase)**
`debate.started` triggers a prominent toast/modal-lite overlay in gold: challenger vs defender (agent colors), topic. Turns append as they arrive. On `debate.resolved`, show outcome and collapse to a pill in the status bar (clickable to reopen). Debates also appear as gold ticks on the replay timeline.

### 3.4 Animation & pacing principles

- Insertions animate ~300 ms; never block on animation (state is already updated, animation is presentation only).
- Buffer bursty event groups client-side: process events in requestAnimationFrame batches, stagger visual insertions.
- At replay speeds >5×, disable per-item animations and switch to batch updates (otherwise 60× looks chaotic).
- Everything keyed by stable ids so React reconciliation handles replay scrubbing cleanly.

---

## Part 4: Implementation Phases

Work in this order; each phase should end in a working, demonstrable state.

**Phase 1 — Events.** Explore codebase, report findings. Implement event bus (or extend existing), JSONL writer, and add event reporting calls throughout the orchestrator using the full event vocabulary. Acceptance: running `paradigm run` on a short cycle produces a well-formed `events.jsonl`; a `scripts/check_events.py` script confirms the schema, monotone seq, and parseability.

**Phase 2 — Replay server + skeleton frontend.** FastAPI server with threads list, events endpoint, artifact serving. React app with reducer, status bar, ticker, and the Hypotheses + Experiments views (no graphs yet). Scrubber with play/speed. Acceptance: `paradigm dashboard <thread>` replays a finished run end to end.

**Phase 3 — Graph views.** Literature force graph and Evidence view, with the burst-buffering and animation rules above. Debate overlay. Paper/review view. Acceptance: a full replay of a real 1-hour thread is smooth at 20× on a laptop.

**Phase 4 — Live mode.** SSE endpoint with incremental file reading; frontend switches data source (replay array vs EventSource) behind one interface; `--dashboard` option on `paradigm run` that starts uvicorn in a background thread and prints the URL. Acceptance: dashboard tracks a live run with <1 s latency; closing and reopening the dashboard mid-run recovers full state from the JSONL.

**Phase 5 — Polish (only if time permits).** Thread picker landing page, export current view as PNG, shareable replay link with `?t=<seq>` deep-link, dark/light toggle.

Do NOT build in this version: the citation-graph-of-published-threads overlay (cross-thread knowledge graph), accounts or login, multi-user support, editing/steering from the dashboard. These are explicitly out of scope.

---

## Part 5: Conventions & Constraints

- Python: match existing project style and tooling (check for ruff/black/pyproject config). Type hints throughout.
- New runtime dependencies (Python): fastapi, uvicorn, sse-starlette. Gate them behind an optional extra (`pip install paradigm[dashboard]`) so the core tool stays lean.
- Frontend: Vite + React + TypeScript, d3-force (or Cytoscape.js — your call, justify it), no component library. Commit a built `dist/` OR add a build step to the docs — your call, but `paradigm dashboard` must work without requiring the user to run npm.
- The events.jsonl lives inside the thread folder (it is part of the research record per our research-thread design). Never write dashboard state anywhere else.
- Test with the existing finished threads in the data/papers directory; if event logs don't exist for old threads, add a small synthetic event generator (`scripts/generate_demo_events.py`) that produces a realistic ~1-hour run compressed into a demo file, for frontend development without spending API tokens.

## Questions to Resolve During Code Exploration

1. Does a DisplayManager/event system from the terminal UI work already exist? Extend, don't duplicate.
2. What are the actual internal names/ids for hypotheses, claims, and the world-model entities? Use those.
3. Are figures saved with stable paths during EXECUTION, and when? (Needed for artifact events.)
4. Is the orchestrator async or sync? (Determines whether the live server runs in a thread or a task.)
5. How are debates currently represented — is there a turn structure to hook `debate.turn` events into?

Report answers and any plan adjustments before starting Phase 1 implementation.
