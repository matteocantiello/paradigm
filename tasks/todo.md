# Plan — fixes from the 2026-07-01 critical review + refactor pass (Prompt 234)

Source: two-agent audit (critical diff review of 97e15cc→a5a0136 + codebase health scan).
(Previous contents: Prompt 173 quality audit — completed, see HISTORY.md.)

## A. Correctness fixes (recent-change mistakes) — do first

- [x] **A1. Revision bypasses citation invariant (MODERATE, ADR-013 hollowed out)**
      `review.py` internal-review revision (~506/545) and `run_revision_phase` (~912-921) save the
      writer's raw revised body with no `validate_and_strip_citations` (nor
      `compile_allowlist_citations` when enabled). Fix: re-run the citation net after every body
      rewrite at both save points; append the allow-list block to revision prompts. + tests.
- [x] **A2. Mandatory-check "passed" early-return matches negated text (MODERATE)**
      `review.py:182-187` — "was NOT passed" / "only 1 of 5 passed" → returns 0 failures, so the
      revise→reject escalation never fires. Fix: require affirmative "all … passed" and reject the
      match when `not|fail|only|except` appears in the span. + regression tests with the three
      verified bypass strings.
- [x] **A3. Non-arXiv seed fetches pollute the arXiv circuit breaker (MODERATE)**
      `corpus.fetch_and_ingest_url` → `arxiv.py fetch_pdf_bytes` → `_rate_limited_get` counts
      journal-site 403s against the arXiv breaker (2 failures → 120 s open, right before IDEATION
      searches) and serializes behind the 3 s arXiv cadence. Fix: plain httpx GET for external
      URLs (or a `note_failures=False` path); optionally cap total seed-fetch wall time.
- [x] **A4. `ext-…` papers render as fake arXiv references (MODERATE)**
      `citation_validation.py:152-158` — external papers print as
      `arXiv:ext-ab12… https://arxiv.org/abs/ext-…`, authors "Unknown". Fix: carry source URL
      into allow-list entries; render journal/URL form for `ext-` ids.
- [x] **A5. Editor 16384-token headroom inert on internal review (MODERATE)**
      `review.py:439` passes explicit `max_tokens=_REVIEW_MAX_TOKENS` (8192), overriding the
      production.yaml editor setting that commit 9576957 added for Sonnet 5 thinking headroom.
      Fix: `max_tokens=max(_REVIEW_MAX_TOKENS, editor.max_tokens)`.
- [x] **A6. Title-extraction can be worse than line 0 (MINOR)**
      `prompt_utils.py:576-599` — start-anchored `nature|science|…` skips real titles
      ("Nature of the compact object in GW190814") and returns the author list. Fix: require
      journal tokens to be followed by volume/date patterns; abstract slice should start after
      the chosen title line (also covers finding #7).
- [x] **A7. External papers never populate full-text reads (MINOR)**
      `orchestrator/literature.py:384` — pass the actual URL as `oa_pdf_url` for ext papers so
      `[READ:]` gets full text instead of the 500-char stub.
- [x] **A8. `finalize_digest` DB read outside the guard (MINOR)**
      `writing.py:1421-1429` — wrap `get_paper` in the same never-break-the-cycle try/except.

## B. Small high-leverage refactors (proven bug sources) — same pass or next

- [x] **B1. Consolidate LLM-JSON parsing onto `knowledge/json_utils.py`** (S) — migrate
      engine.py convergence parser, eval/judge.py, eval/metrics.py, agents/memory.py,
      agents/topics.py. This bug family (Elo all-1500, forced-major_revision) has hit twice.
- [x] **B2. Make config-parse failure fatal in the backend** (S) — kill the silent fallback that
      caused the VM "vanished data" incident.
- [x] **B3. executions/ TTL pruning** (S) — age/keep-last-N sweep (1,140 dirs locally; VM worse).
- [x] **B4. Dead-code sweep** (S) — `reflection_model`, `_get_call_name`,
      `ExecutionResult.started_at`, stop creating the unused `events` table.
- [x] **B5. ws.py checkpoint/rewind silent no-ops** (S) — hide the UI or implement.

## C. Structural refactor — opportunistic, not now

- [x] C1. Extract `orchestrator/artifacts.py` (~390 lines of pure save/log I/O) from engine.py (M).
- [x] C2. Decompose `_run_cycle_impl` (515-line god method) into per-phase-group methods (M,
      medium risk — heart of the system; lean on test_orchestrator + a selftest run).
- NOT worth it now: SQLite per-session connections (WAL holding, no lock errors),
  DisplayManager/ws_display Protocol dedup, constants.py/writing.py splits.

## D. Housekeeping / ops

- [ ] D1. gitignore `data_vm2/` (220 MB), decide fate of PROMPT-*.md, paper-489a566e6225.pdf,
      configs/selftest-exp.yaml.
- [ ] D2. VM deploy still pending (a5a0136 not deployed; NASA_ADS_API_KEY + frontend
      `npm run build` + restart). ADS key rotation after deploy.
- [x] D3. main is 143 commits behind (last 2026-06-05) — decide whether to merge
      responsive-live-progress → main after the A-fixes land.

## Review (2026-07-02)

All A (8/8) + B (5/5) items implemented, tested, committed:
- 1c5c6fe fix(literature): A3 breaker isolation + A6 title/abstract + A7 ext full-text
- 2635795 fix(review+citations): A1 revision citation net + A2 negation guard + A4 ext
  references + A5 editor tokens + A8 digest guard
- 81e2439 refactor(parsing): B1 - engine/judge/metrics on json_utils (memory.py and
  topics.py inspected: line-based protocols, NOT JSON - left alone)
- f4bdf51 fix(backend): B2 fatal ConfigParseError (missing file still quiet-defaults)
- 62dadb5 chore(sandbox+storage): B3 executions retention (30d/500) + B4 dead code
- d012811 fix(ws): B5 checkpoint/rewind -> explicit not_supported error frames

Full suite 1843 passed (+46 new tests), ruff clean.
C done 2026-07-02: e5a69b3 (C1 artifacts.py extraction, engine 2467->2116) +
c48bfeb (C2 _run_cycle_impl 515-line god method -> ~50-line sequencer over
per-stage methods + _intervention_gate/_announce_discussion_phase helpers);
suite 1843 green, side-effect call counts verified identical. Merged to main.
Remaining D: gitignore data_vm2/ + scratch files; VM deploy; ADS key rotation.
NOTE for the operator: after B2, a broken production.yaml now aborts backend
startup with a clear error instead of silently serving an empty data dir.

---

# Plan — dataset attachment + prompt pre-processing (Prompt 239, 2026-07-06)

Existing plumbing this builds on: ResourceType.DATA + staging at data/shared/data/
(sandbox-mounted RO at /data/shared), state.data_context injected into every
discussion-phase prompt (engine.py:1428) AND the experimentalist context;
role-model overrides via config.agent.overrides + get_provider_and_model_for_role.

## Phase 1 — Data card + local-dataset staging (core)  [the deferred #4]
- [x] 1a. `build_data_card(path)` in literature/resources.py — stdlib-only schema
      preview: filename+size; CSV/TSV: header, inferred dtypes, first 5 rows,
      value-counts of low-cardinality cols (first 1000 rows); JSON: top-level keys;
      text: first lines; binary: size only. Cap ~2k chars/file. No pandas dep.
- [x] 1b. `stage_local_dataset(path, shared_dir)` — copy file/dir into
      data/shared/data/ (sanitized names, collision-safe), return ResolvedResource
      (DATA, sandbox_path=/data/shared/data/<name>, summary=data card).
- [x] 1c. build_data_context appends the data card for EVERY DATA resource
      (URL-downloaded too — fixes schema-blindness generally, the original #4).
- [x] 1d. Engine: `run_research_cycle(..., datasets: list[Path] | None)` → staged
      during seeding into state.resolved_resources (so data_context carries them);
      emit `dataset.attached` events.
- [x] 1e. CLI: `paradigm run --data <path>` (repeatable; file or dir).

## Phase 2 — Backend API + session wiring
- [x] 2a. `POST /api/v1/research/{cycle_id}/datasets` multipart upload → stage to
      data/shared/data/; sanitize filename (no traversal), size cap 100 MB,
      extension allowlist (.csv .tsv .txt .json .dat .fits .parquet .zip → zip
      extracted? NO — keep v1 simple: no archives). Returns staged path list.
- [x] 2b. Persist per-cycle dataset paths (cycles table `datasets` JSON column,
      auto-migration on startup like status_detail) + include in cycle GET model.
- [x] 2c. session_manager passes cycle.datasets → run_research_cycle(datasets=…).

## Phase 3 — Frontend (SetupWizard)
- [x] 3a. File picker/drop zone in the Prompt step (type+size validation, list of
      attached files with remove). On submit: create cycle → upload files →
      start session.
- [x] 3b. Show attached datasets on the session/cycle view (chip list).

## Phase 4 — Prompt pre-processing ("prompt_refiner")
- [x] 4a. Config: `orchestrator.enable_prompt_preprocessing: bool = True`; model
      resolved via role `prompt_refiner` (reuses overrides + GUI model picker);
      production.yaml override → claude-opus-4-8 (the strong-model first pass).
- [x] 4b. Engine stage `_refine_seed_prompt()` at cycle start (BEFORE seeding, so
      thread title/hypothesis, resources, topics, requirements checklist and every
      agent prompt all use the refined brief). Prompt: rewrite into a structured
      research brief (question, context, explicit deliverables, constraints);
      PRESERVE all URLs/paths/numbers/formulae VERBATIM; do not invent
      requirements; output only the brief.
- [x] 4c. Deterministic guards: any URL present in the original but missing from
      the refined text is re-appended verbatim in a "## Resources" block; empty /
      too-short / failed output → keep original. Best-effort, never breaks a run.
- [x] 4d. Provenance: threads get `original_prompt` column (auto-migration);
      state.original_prompt kept; emit `prompt.refined` event (before/after) +
      display notice; backend cycle keeps the USER's original as seed_prompt so
      terminal-screen "Retry with this prompt" retries the original.
- [x] 4e. Selftest/validate configs: preprocessing OFF (cost + determinism).

## Phase 5 — Verify + ship  [DONE 2026-07-06]
Commits 5611891 (data card+staging+CLI), df2880e (upload API), 082aa61 (wizard UI),
3594999 (prompt refiner). Full suite 1903 green, ruff clean, frontend tsc+eslint+vite
clean, pushed. LIVE-validated: Opus refiner on the real red-noise prompt (13/13 URLs
preserved verbatim, faithful structured brief incl. the MIST deliverable, ~1k out
tokens); build_data_card on a real Bowman CSV (columns+dtypes+value counts+head).
- [x] Tests per phase (card builder edge cases incl. dtype inference + caps;
      staging collisions/sanitization; upload endpoint traversal/size/type; refiner
      URL-guard + fallback + disabled; engine wiring; CLI flag). Full suite + ruff.
- [ ] Optionally: one trimmed live cycle with a small CSV attached to see the card
      + refined brief in the transcript.
- [ ] Update .env/README/production.yaml docs; commit per phase; push.

Decisions taken (flag if you disagree): refiner default ON, automatic (no
approve-gate; visible via event + original kept); Opus 4.8 as refiner in
production; uploads capped at 100 MB, no archives in v1; datasets stage into the
EXISTING shared data dir (provenance tags from fix E already mark them
[saved this run]).

---

# Plan — Landing + Setup UX + Interactive Mode v1 (Prompt 243, 2026-07-06)

Approved scope: all three phases; prompt-first landing direction.

## Phase 1 — Prompt-first landing page
- [ ] Redesign `frontend/src/pages/Dashboard.tsx`: hero = wordmark + tagline + large
      "What should we investigate?" prompt console (textarea, attach-data affordance,
      Configure → opens wizard prefilled, quick Launch)
- [ ] Running now + Latest papers below the hero; stats as a compact strip
- [ ] Stay inside the Observatory design system (index.css tokens)

## Phase 2 — Setup flow v2 (SetupWizard)
- [ ] Wizard accepts prefill (prompt + files) from the landing hero
- [ ] Mode step gains Interactive vs Autonomous choice (per-cycle)
- [ ] Real validation; dataset add/remove on Review step; per-file upload status,
      failed upload doesn't silently orphan the cycle
- [ ] Client-side dataset preview (CSV/TSV columns + head) in the wizard
- [ ] Team step: explicit selected state (not opacity only); Esc + X close

## Phase 3 — Interactive mode v1 (structured decisions)
- [ ] Backend: honor ApprovalRequestMsg.options + ApprovalResponseMsg.notes/modifications
      (currently discarded in respond_to_approval)
- [ ] Engine: structured decision points with timeout→autonomous fallback:
      ideation→planning = pick among ranked tournament hypotheses;
      planning→execution = approve experiment plan + notes
- [ ] Per-cycle interactive flag: wizard → POST /research → session wires blocking
      gates for that cycle only
- [ ] Frontend: ApprovalDialog → structured DecisionDialog (option cards, notes);
      re-enable InteractionBar (SHOW_INTERACTION_BAR)
- [ ] Decision notes injected as guidance into the next round

## Verification
- [ ] pytest green; ruff clean; npm run build green; visual pass
- [ ] Live smoke: interactive test cycle exercising a decision gate

## Review (Prompt 243) — DONE 2026-07-06
All three phases shipped. Phase 1: Dashboard.tsx rewritten as a prompt-first hero
("What should we investigate?" console with attach-data chips + quick Launch +
Configure→wizard prefill), stats as a quiet inline strip. Phase 2: SetupWizard v2 —
shared useLaunchCycle hook (create→upload→start with per-file progress and a
resume-safe Retry that never duplicates the cycle), DatasetPicker with client-side
CSV/TSV column peek, Supervision step (Autonomous vs Interactive per cycle),
15-char prompt gate, ≥1-role team gate with explicit check state, Esc/X close.
Phase 3: interactive mode v1 — cycles.interactive column (idempotent migration) →
create/resume/session wiring; DecisionHook (thread_id, decision_type, payload)→dict
alongside InterventionHook; engine decision points: hypothesis_selection (full
tournament ranked field offered, winners preselected, user subset applied to
state.selected_hypotheses, notes→next-round guidance) and experiment_plan
(plan approval; notes appended as OPERATOR DIRECTIVE the experimentalist sees);
SessionManager._request_decision rides the approval channel (ApprovalRequestMsg
gains decision_type/choices/multi_select/default_ids; ApprovalResponseMsg
notes/modifications now honored end-to-end); 300s timeout → agents' own choice.
ApprovalDialog renders choice cards + countdown; InteractionBar re-enabled.
Verified: 1918 tests green (15 new in test_interactive_mode.py), ruff clean,
tsc+eslint+vite clean, headless-Chrome visual pass on landing + wizard.
NOT verified live: a real interactive cycle exercising a decision gate end-to-end
(needs a running backend + a watched session) — suggested next step.
