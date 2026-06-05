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

## Phase 3 — Resume from checkpoint + steering  ✅ DONE
- [x] No engine surgery: resume reuses the Phase-99 guidance inbox. The prior
      thread's checkpoint (hypothesis/findings/open-questions/next-steps/summary) +
      the operator comment are assembled into a continuation note and queued as
      first-round guidance for a fresh linked run. (Mid-phase re-entry rejected —
      the engine's phases have hard state deps; checkpoint-granularity per plan.)
- [x] `POST /api/v1/research/{cycle_id}/resume` (optional `comment`) → creates a
      continuation cycle (`resumed_from` lineage; DB column + model + store), starts
      it, queues the note. Works for interrupted/failed/aborted AND completed
      ("extend further").
- [x] Frontend: `resumeCycle()`; TerminalScreen Resume button + inline steering box;
      CycleCard quick-Resume (resumable statuses) + "continues an earlier run"
      lineage; cycleId threaded SessionPage→SessionView→TerminalScreen. +5 tests.

## Review
All 3 phases shipped. Full suite 1497; ruff + tsc + vite build clean. Resume is
checkpoint-granularity (re-derives forward with prior context), not exact
mid-experiment replay — set with the user up front. Future: thread-reuse /
draft-continuation once engine.py is refactored for phase re-entry.

## Review
Phase 1 verified: full suite 1486 pass; ruff + frontend tsc/build clean. The
enrichment also fixes a latent bug — cycle.status was set to "running" at start
and never updated, so the research tab showed every cycle as running forever.
