# Task: Phase 1 — Correctness Kernel (Prompt 72)

Approved roadmap: `literature/2026-06_Unified-Roadmap.md` (source plan `~/.claude/plans/squishy-crafting-dahl.md`).
Build order **1A → 1C → 1B → 1E → 1D** + interop slice. Every feature default-off, plain-Python, test-gated.

> The completed Prompt-67 reliability + eval-harness todo is preserved in git history and HISTORY.md (Prompt 67).

## 1A — Falsifiability / Pre-registration  *(D11 + hybrid gate)*  ✅ DONE (full suite green: 1265 passed)
- [x] `knowledge/models.py`: added `PredictionDirection`, `PredictionVerdict`, `PredictionRule` (`is_well_formed`/`holds`); extended `Hypothesis` (`prediction_rule_id`, `verdict`).
- [x] `orchestrator/preregistration.py`: `PreRegistrationHandler.run_freeze()` (theorist authors, well-formedness reject gate) + `.evaluate(experiment_metadata)` (deterministic verdict from frozen `metric_stdout_key`).
- [x] `phases.py`: added `PRE_REGISTRATION`; transitions PLANNING→PRE_REGISTRATION→EXECUTION (legacy PLANNING→EXECUTION kept) + description + display icon.
- [x] `state.py`: `selected_hypotheses`, `registered_rules`, `prereg_verdicts`.
- [x] `config.py` (`KnowledgeConfig`): `enable_preregistration=False`, `prereg_require_refutation=True`, `prereg_on_empty="advisory"`.
- [x] `engine.py`: capture tournament winners → `selected_hypotheses`; PRE_REGISTRATION block (+ blocking-abort `prereg_failed`); post-EXECUTION `evaluate`; inject rules into EXECUTION propose prompt.
- [x] `constants.py`: `_PREREGISTRATION_PROMPT`; `experimentation.py` injects rule tokens + `_format_rule_bound`.
- [x] `writing.py`: prereg verdicts in Execution Fact Sheet + refuted→FORBIDDEN-CLAIMS.
- [x] `tests/test_preregistration.py` (24 tests) + `test_phases.py` updated.
- [ ] DEFERRED to 1D: persist `prereg`/`prereg_verdicts` to SQLite (only consumed by the eval extension). Skeptic adversarial re-check of rules also deferred (well-formedness gate covers the core).

## 1C — Tree-search / step-restart  *(D2 / Denario restart_at_step)*  ✅ DONE (full suite 1275 passed)
- [x] `constants.py`: `CodeBlock.restart_at_step` + `# RESTART_AT: <k>` parsing; `_best_first_order(...)` (dependency-respecting Kahn traversal preferring non-buggy ready nodes, deterministic RNG).
- [x] `experimentation.py`: best-first ordering applied after topo-sort (default-off); `_buggy_experiments` tracked across rounds; step-restart retry guidance reusing the workspace manifest (default-off).
- [x] `config.py`: `enable_step_restart`, `enable_best_first_nodes`, `debug_buggy_node_prob`, `max_step_restarts_per_experiment`.
- [x] `tests/test_tree_search.py` (10 tests: RESTART_AT parsing + best-first dependency/preference/determinism/cycle).
- [ ] DEFERRED: rigid per-step artifact dirs (`workspace/<exp>/step_<k>/`) — current resume is prompt/manifest-driven, which fits the atomic-block model; full sub-step machinery only if needed.

## 1B — Verification Kernel  *(D1 / console-as-data-bus / resolve-or-drop)*  ✅ DONE (full suite 1294 passed)
- [x] `orchestrator/verification.py`: `verify_experiments()` (fresh isolated `verify/<thread>` workspace, seeded re-exec, `RESULT[...]` tolerance compare → accepted/rejected/nondeterministic) + `apply_gate()` (demote non-accepted).
- [x] `knowledge/models.py`: `VerificationRecord`; `state.py`: `verification_records`, `dropped_claims`.
- [x] `phases.py`: `VERIFICATION` sub-phase (EXECUTION→VERIFICATION→{POST_EXECUTION,WRITING}; legacy retained) + description + icon.
- [x] `engine.py`: VERIFICATION block after the execution go/no-go gate; demote non-accepted; abort `verification_failed` if none reproduce.
- [x] `experimentation.py`: console-as-data-bus contract (`RESULT[label]=value`) injected into the EXECUTION prompt (gated on `enable_verification`).
- [x] `writing.py`: Verification Ledger in the Fact Sheet. **resolve-or-drop achieved at the source**: demoted experiments → `failure` metadata → existing FAILED/FORBIDDEN machinery (writer can only use ACCEPTED numbers).
- [x] `config.py` flags (`enable_verification`, tolerance, seed, reexec_budget, abort_on_verification_failure).
- [x] `tests/test_verification.py` (19 tests) + `test_phases.py`.
- [ ] DEFERRED: sympy/units/leakage checker battery (LLM-authored assertions) — core re-execution shipped; battery is a follow-up. `verification` SQLite column → 1D (eval reads it). Post-hoc paper-text claim surgery not needed (source-level gate covers it).

## 1E — Hybrid human-gate + provenance  *(Nature/Imas / Operon)*
- [ ] `engine.py`: `_human_gate(point)` (off/advisory/blocking + no-hook deadlock guard) at `problem_selection`/`pre_registration`/`final_verification`.
- [ ] `knowledge/models.py`: `ProvenanceRecord`; persist to `papers.provenance`; engine-written `framed_by`/`verified_by`.
- [ ] `config.py`: `human_gate_mode`, `human_gate_points`; CLI hook renders gate payload (`main.py`).
- [ ] `tests/test_human_gate.py`.

## 1D — Eval extension (selection gate)  *(D3)*
- [ ] `eval/seeds.py`: `SeedPrompt` + `split_seeds` (hash-fixed train/selection/test).
- [ ] `eval/models.py`/`metrics.py`: `reproduction_pass_rate`, `prereg_verdict`, `claims_dropped`; `OUTCOME_SCORES` for `verification_failed`/`prereg_failed`.
- [ ] `eval/calibration.py`: balanced-accuracy threshold vs real published/rejected; persist `data/eval/calibration.json`.
- [ ] `main.py`/`harness.py`: shared `build_engine`; wire `paradigm eval --live N --split selection`.
- [ ] extend `tests/test_eval.py`.

## Interop slice — fetch-by-ID lookup  *(D10)*
- [ ] `orchestrator/literature.py` `process_search_requests()`: detect `id:<arxiv-id>` → fetch-by-ID provider (behind `provider_factory.py`), not keyword search.
- [ ] optional FutureHouse PaperQA novelty provider.
- [ ] verify quality-neutral via `paradigm eval`.

## Verification gate
- `ruff check` clean; full `pytest` green (~1235 tests + new); `paradigm eval` offline unchanged (new metrics default None/0); `paradigm eval --live N --split selection --judge` reports reproduction-pass-rate. Selection-split mean quality ≥ 61/100 baseline.

---

## Progress log
- (in progress) Housekeeping: roadmap doc + todo seeded. Starting 1A.
