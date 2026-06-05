# Terminal action + resumable cycles

User ask (prompt 103): on any cycle end, a clear GUI action — show the paper, or
a non-convergence summary — and ALWAYS a way to continue an unfinished cycle
(after a dropped connection, etc.), logged as resumable in the research tab, with
optional steering. Sequencing chosen by user: **terminal screen first**.

## Phase 1 — Terminal action / summary  ✅ DONE
- [x] Backend `_enrich_cycle`: backfill live status + thread_id + paper_id onto the
      in-memory cycle (it was only written at start → stuck on "running", no paper).
      Wired into list + get. +4 tests.
- [x] `TerminalScreen` component: outcome (complete / no-paper / failed / stopped),
      one-line summary, stats (phase, rounds, elapsed, tokens, papers), and actions —
      **View paper** (converged) / Resume (disabled, "soon" → Phase 3) / Back to research.
- [x] Wired into `SessionView` (shown above the panels on terminal status).
- [x] `PapersPage` deep-link `?paper=<id>` so "View paper" opens directly.

## Phase 2 — Persist cycles + mark interrupted  ✅ DONE
- [x] DB `cycles` table + CRUD (`create/get/list/update/delete_cycle`) +
      `mark_running_cycles_interrupted()`. team_roles JSON round-trip.
- [x] `CycleStore` service (DB-backed; in-memory fallback shares research._cycles
      for demo mode). Wired into the lifespan; `mark_interrupted_on_startup()`.
- [x] Migrated research.py + sessions.py routes to the store; session_manager
      persists the terminal cycle (status + thread_id from engine.state — survives
      a mid-run drop — + paper_id) in the `finally`.
- [x] `CycleStatus.INTERRUPTED`; StatusBadge amber "interrupted"; CycleCard shows
      the phase reached. +6 tests.

## Phase 3 — Resume from checkpoint + steering
- [ ] Engine `run_research_cycle(resume_from_thread_id=...)`: load latest checkpoint,
      reconstruct minimal ResearchState, continue from the next phase (checkpoint-
      granularity, per the architecture — not exact mid-token replay).
- [ ] `POST /api/v1/research/{cycle_id}/resume` (+ optional steering comment → the
      guidance inbox built in prompt 99).
- [ ] Frontend Resume action (research tab + the TerminalScreen Resume button) with a
      steering-comment box.

## Review
Phase 1 verified: full suite 1486 pass; ruff + frontend tsc/build clean. The
enrichment also fixes a latent bug — cycle.status was set to "running" at start
and never updated, so the research tab showed every cycle as running forever.
