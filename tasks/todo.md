# Task: Fix the 24 `writing_failed` runs (Prompt 67, step 1)

## Diagnosis (evidence-based)
All 24 `writing_failed` papers have substantial bodies (10k–65k chars) — none are crashes.
Every one was killed by the **internal editor at INTERNAL_REVIEW**, before peer review.
- **Bucket A** (~half): editor *correctly* rejected papers built on failed/synthetic experiments,
  forbidden claims, non-existent figures, bare-URL references. Root cause is upstream — a full
  ~1M-token cycle is wasted writing a doomed paper.
- **Bucket B** (~half): revise-loop ran all 5 iterations as "Revise", never "Accept" → fell
  through to `writing_failed` (review.py:330). Recurring blocker: "math notation violations".
- **2 live code bugs** feeding the above:
  - `tournament_handler.py:150,211` call `provider.complete(system_prompt=, user_prompt=)` —
    wrong signature → TypeError → tournament silently broken (188 errors).
  - `SourceResult.id: str` but S2/biorxiv/pubmed/nasa_ads can return None → 144 validation
    errors → lost lit → bare-URL citations (which the editor then rejects for).

## Plan (all 5, in order)

- [x] **1. Tournament `complete()` signature** — FIXED tournament_handler.py:150,211 to
      `system=`/`messages=[{role:user,...}]`. Root cause of the test miss: the test mocks at
      tests/test_hypothesis_tournament.py:301,382 had encoded the *buggy* signature
      (`system_prompt, user_prompt`); updated both to the real Protocol signature so they now
      guard the regression. 50 tournament/provider tests pass.
- [x] **2. `SourceResult.id` None-handling** — FIXED with a `model_validator(mode="before")`
      on SourceResult (domains/base.py) that synthesizes a stable `src-<sha1>` id from url/title
      when the upstream id is falsy. Covers all providers at one point. 4 new tests pass.
- [x] **3. Post-EXECUTION go/no-go gate** — DONE. Added `abort_on_execution_failure: bool=True`
      (config.py); engine.py aborts after EXECUTION with status `execution_failed` when
      `successful_code` is empty (verified trustworthy: vacuous runs are reclassified to FAILURE
      upstream). New display method `execution_failed_abort` in manager/fallback/ws_display.
      2 new orchestrator tests (fires + can-be-disabled); isolated test_empty_paper_guard to the
      writing guard. 102 orchestrator tests pass.
- [x] **4. Revise-loop convergence** — DONE.
      (4a) `run_revision` now re-applies `sanitize_unicode_math` (review.py) so revisions can't
      reintroduce Unicode math — the recurring "mathematical notation violations" blocker that
      kept papers stuck on "Revise" for all 5 rounds.
      (4b) Stall early-exit: if the editor's required-change count fails to decrease for
      `_REVIEW_STALL_LIMIT=2` consecutive iterations, the loop breaks early instead of burning
      the remaining rounds. New test proves it stops at 3 of 5.
- [x] **5. Split misleading `writing_failed`** into distinct, honest statuses — DONE:
      `writing_incomplete` (empty/too-short paper, writing.py), `review_rejected` (editor reject,
      review.py), `revision_exhausted` (never accepted / stalled, review.py). `execution_failed`
      added in #3. Updated engine post-review detection, display methods (manager/fallback/ws,
      now take a `status` arg), terminal color map (components.py, keeps legacy `writing_failed`),
      and frontend StatusBadge (red/amber/orange styles + underscore→space labels). Tests updated.

## Verification
- `ruff check src backend` → clean. Full `pytest` → **1226 passed** (+7 new regression tests).
- Frontend `tsc --noEmit` → exit 0.

## Review
All 5 fixes landed in order. Key reframing from the diagnosis: the 24 `writing_failed` runs were
NOT crashes — they were the internal editor (correctly) blocking papers built on failed
experiments + the revise loop never converging. So the fixes target (a) two real upstream code
bugs that degraded research quality (tournament signature, SourceResult.id), (b) catching doomed
cycles *before* the expensive WRITING phase (#3), (c) removing the dominant non-converging blocker
and capping wasted revision rounds (#4), and (d) honest, queryable end-state reporting (#5).

Files touched: src/paradigm/{knowledge/tournament_handler, domains/base, config,
orchestrator/engine, orchestrator/review, orchestrator/writing, display/manager, display/fallback,
display/components}.py; backend/api/services/ws_display.py; frontend StatusBadge.tsx; +tests.

Next: step 2 (evaluation harness) then step 3 (orchestration efficiency).
