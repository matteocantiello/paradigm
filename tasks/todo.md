# Plan — fixes from the 2026-07-01 critical review + refactor pass (Prompt 234)

Source: two-agent audit (critical diff review of 97e15cc→a5a0136 + codebase health scan).
(Previous contents: Prompt 173 quality audit — completed, see HISTORY.md.)

## A. Correctness fixes (recent-change mistakes) — do first

- [ ] **A1. Revision bypasses citation invariant (MODERATE, ADR-013 hollowed out)**
      `review.py` internal-review revision (~506/545) and `run_revision_phase` (~912-921) save the
      writer's raw revised body with no `validate_and_strip_citations` (nor
      `compile_allowlist_citations` when enabled). Fix: re-run the citation net after every body
      rewrite at both save points; append the allow-list block to revision prompts. + tests.
- [ ] **A2. Mandatory-check "passed" early-return matches negated text (MODERATE)**
      `review.py:182-187` — "was NOT passed" / "only 1 of 5 passed" → returns 0 failures, so the
      revise→reject escalation never fires. Fix: require affirmative "all … passed" and reject the
      match when `not|fail|only|except` appears in the span. + regression tests with the three
      verified bypass strings.
- [ ] **A3. Non-arXiv seed fetches pollute the arXiv circuit breaker (MODERATE)**
      `corpus.fetch_and_ingest_url` → `arxiv.py fetch_pdf_bytes` → `_rate_limited_get` counts
      journal-site 403s against the arXiv breaker (2 failures → 120 s open, right before IDEATION
      searches) and serializes behind the 3 s arXiv cadence. Fix: plain httpx GET for external
      URLs (or a `note_failures=False` path); optionally cap total seed-fetch wall time.
- [ ] **A4. `ext-…` papers render as fake arXiv references (MODERATE)**
      `citation_validation.py:152-158` — external papers print as
      `arXiv:ext-ab12… https://arxiv.org/abs/ext-…`, authors "Unknown". Fix: carry source URL
      into allow-list entries; render journal/URL form for `ext-` ids.
- [ ] **A5. Editor 16384-token headroom inert on internal review (MODERATE)**
      `review.py:439` passes explicit `max_tokens=_REVIEW_MAX_TOKENS` (8192), overriding the
      production.yaml editor setting that commit 9576957 added for Sonnet 5 thinking headroom.
      Fix: `max_tokens=max(_REVIEW_MAX_TOKENS, editor.max_tokens)`.
- [ ] **A6. Title-extraction can be worse than line 0 (MINOR)**
      `prompt_utils.py:576-599` — start-anchored `nature|science|…` skips real titles
      ("Nature of the compact object in GW190814") and returns the author list. Fix: require
      journal tokens to be followed by volume/date patterns; abstract slice should start after
      the chosen title line (also covers finding #7).
- [ ] **A7. External papers never populate full-text reads (MINOR)**
      `orchestrator/literature.py:384` — pass the actual URL as `oa_pdf_url` for ext papers so
      `[READ:]` gets full text instead of the 500-char stub.
- [ ] **A8. `finalize_digest` DB read outside the guard (MINOR)**
      `writing.py:1421-1429` — wrap `get_paper` in the same never-break-the-cycle try/except.

## B. Small high-leverage refactors (proven bug sources) — same pass or next

- [ ] **B1. Consolidate LLM-JSON parsing onto `knowledge/json_utils.py`** (S) — migrate
      engine.py convergence parser, eval/judge.py, eval/metrics.py, agents/memory.py,
      agents/topics.py. This bug family (Elo all-1500, forced-major_revision) has hit twice.
- [ ] **B2. Make config-parse failure fatal in the backend** (S) — kill the silent fallback that
      caused the VM "vanished data" incident.
- [ ] **B3. executions/ TTL pruning** (S) — age/keep-last-N sweep (1,140 dirs locally; VM worse).
- [ ] **B4. Dead-code sweep** (S) — `reflection_model`, `_get_call_name`,
      `ExecutionResult.started_at`, stop creating the unused `events` table.
- [ ] **B5. ws.py checkpoint/rewind silent no-ops** (S) — hide the UI or implement.

## C. Structural refactor — opportunistic, not now

- [ ] C1. Extract `orchestrator/artifacts.py` (~390 lines of pure save/log I/O) from engine.py (M).
- [ ] C2. Decompose `_run_cycle_impl` (515-line god method) into per-phase-group methods (M,
      medium risk — heart of the system; lean on test_orchestrator + a selftest run).
- NOT worth it now: SQLite per-session connections (WAL holding, no lock errors),
  DisplayManager/ws_display Protocol dedup, constants.py/writing.py splits.

## D. Housekeeping / ops

- [ ] D1. gitignore `data_vm2/` (220 MB), decide fate of PROMPT-*.md, paper-489a566e6225.pdf,
      configs/selftest-exp.yaml.
- [ ] D2. VM deploy still pending (a5a0136 not deployed; NASA_ADS_API_KEY + frontend
      `npm run build` + restart). ADS key rotation after deploy.
- [ ] D3. main is 143 commits behind (last 2026-06-05) — decide whether to merge
      responsive-live-progress → main after the A-fixes land.

## Review

(to be filled in after implementation)
