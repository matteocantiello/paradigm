# Paradigm — Unified Frontier-Informed Roadmap

> Approved 2026-06-03 (HISTORY Prompt 72). Source plan: `~/.claude/plans/squishy-crafting-dahl.md`.
> Fuses the external-source synthesis (`2026-06_Research-Synthesis_and_Development-Directions.md`, directions D1–D12) with the Denario comparison (`2026-06_Denario-vs-Paradigm-Architecture-Analysis.md`).

## Context

The recurring, highest-confidence conclusion (an external-paper idea *and* a shipping competitor both pointing the same way): **empirical science has no Lean kernel, so build proxy kernels** — re-execution + pre-registered falsifiable predictions + cheap checkers — and make them publication gates. This attacks Paradigm's three pain points at the root: residual no-paper failures, output-quality variability, and (most importantly) *trustworthiness* of generated results.

**Already done** (Prompt-67 branch `prompt67-reliability-eval`, verified): root-caused `writing_failed`; fixed the tournament-signature bug (188 errors) and `SourceResult.id`-None bug (144 errors); added a post-EXECUTION abort gate; fixed revise-loop convergence; split `writing_failed` into honest statuses (`execution_failed`/`writing_incomplete`/`review_rejected`/`revision_exhausted`); shipped an eval harness (`src/paradigm/eval/`, `paradigm eval`, baseline **61/100** over 63 papers). This roadmap **builds on** these.

**Operator decisions:**
- **First focus = Harden correctness** → Phase 1 is the *Correctness Kernel*.
- **Posture = Hybrid + provenance** → human gates configurable (off/advisory/blocking), autonomous by default; every paper records human-vs-agent provenance.
- **Interop = Consume external agents** → fetch-by-ID/MCP paper-lookup provider (kills 471 dead `id:` queries) + optional FutureHouse PaperQA novelty, behind the existing literature abstraction. Exposing Paradigm as an MCP server is **deferred**.

## Principles / Constraints

- **Plain-Python, no frameworks.** Denario's wins are absorbed as leaf-level techniques.
- **Minimal impact:** every new behavior behind a default-off config flag; new DB columns via idempotent `ALTER TABLE ... ADD COLUMN` (guarded by `PRAGMA table_info`); new phases added as *additional* allowed transitions — legacy paths unchanged until opted in.
- **Measurable:** `paradigm eval` is the gate. A change "wins" only if it doesn't regress mean quality on a held-out *selection* split (confirmed once on *test*).

---

## PHASE 1 — Correctness Kernel

Build order: **1A → 1C → 1B → 1E → 1D** (1B needs 1A's frozen rules and is cheaper with 1C's step artifacts; 1D measures all).

### 1A. Falsifiability / Pre-registration  *(D11; also a hybrid gate)*
Freeze, before EXECUTION, each selected hypothesis's machine-readable prediction + decision rule; reject in planning any hypothesis lacking a refutation condition; compute the post-execution verdict **only** against the frozen rule; refuted results are first-class/publishable.
- **Models** (`knowledge/models.py`): `PredictionRule` (metric_name, `metric_stdout_key` strict token, direction, low/high, `significance_max_p`, `refutation_condition` REQUIRED, `frozen`); `Hypothesis` gains `prediction_rule_id`, `verdict`.
- **Handler** `orchestrator/preregistration.py` (`run_freeze()` / `evaluate()`): theorist authors rules, skeptic checks; reject gate drops rule-less hypotheses to the graveyard. Verdict = grep frozen `metric_stdout_key` in captured stdout → `confirmed|refuted|inconclusive`.
- **Sub-phase** `PRE_REGISTRATION` between PLANNING and EXECUTION; rules injected into EXECUTION prompt; verdicts feed the Execution Fact Sheet + FORBIDDEN-CLAIMS (`writing.py`).
- **Config** (`KnowledgeConfig`): `enable_preregistration=False`, `prereg_require_refutation=True`, `prereg_on_empty="advisory"`.

### 1B. Verification Kernel — re-execution as ground truth  *(D1; console-as-data-bus + resolve-or-drop)*
A reported result is "accepted" only if its committed code re-runs in a fresh `--network=none` container with a stored seed and reproduces within tolerance; plus a checker battery and per-claim resolve-or-drop.
- **Module** `orchestrator/verification.py` (`verify_experiments()` / `resolve_or_drop_claims()`), reusing `CodeExecutor` with a fresh `data_dir/verify/<thread>` workspace. Source = `state.successful_code`.
- **Console-as-data-bus:** experimentalist prints every reported number as `RESULT[label]=value`; analyst/skeptic interpret only captured stdout.
- **Checker battery** (in-sandbox assertions): sympy symbolic re-derivation, unit/dimensional, train/test-leakage → `CHECK[...]=pass/fail`.
- **Resolve-or-drop:** every numeric claim must match a reproduced `RESULT[...]` or be dropped; every citation must resolve or be dropped.
- **Model** `VerificationRecord`; new state `verification_records`, `dropped_claims`.
- **Sub-phase** `VERIFICATION` before WRITING; gate demotes non-`accepted` experiments into FORBIDDEN-CLAIMS; if none verify → `verification_failed`, abort before writing. "Verification Ledger" in the Fact Sheet.
- **Config:** `enable_verification=False`, `verification_tolerance=1e-6`, `verification_seed`, `enable_checker_battery=True`, `abort_on_verification_failure=True`, `verification_reexec_budget=20`.

### 1C. Tree-search / step-restart in experimentation  *(D2; Denario `restart_at_step`)*
- **Extend `CodeBlock`** (`constants.py`): `restart_at_step`, `is_buggy`; parse `# RESTART_AT: <k>`.
- **Per-step artifacts** under `workspace/<experiment>/step_<k>/`; resume in `_execute_with_retry`; learned-constraints + circuit-breaker unchanged.
- **Best-first (optional):** `_best_first_order(...)` — non-buggy first, fixed `debug_buggy_node_prob`; deterministic RNG seeded by `thread_id`; respects topological order.
- **Config** (`OrchestratorConfig`): `enable_step_restart=False`, `enable_best_first_nodes=False`, `debug_buggy_node_prob=0.3`, `max_step_restarts_per_experiment=2`.

### 1E. Hybrid human-gate + provenance  *(Nature/Imas; Operon posture)*
- **Reuse `InterventionHook` / `_check_intervention`** at `problem_selection` / `pre_registration` / `final_verification`.
- **Gate modes** (`OrchestratorConfig.human_gate_mode ∈ off|advisory|blocking`): `off`→continue; `advisory`→show payload + continue; `blocking`→hook, **and if no hook registered, continue with a logged warning** (deadlock guard).
- **Provenance:** `ProvenanceRecord` persisted to `papers.provenance`; `framed_by`/`verified_by` written by the engine (not agents). Surfaced in the eval report.

### 1D. Eval extension — the selection gate  *(D3; extend, don't rebuild)*
- **Seeds + splits** (`eval/seeds.py`): `SeedPrompt`s; `split_seeds(...)` hash-fixed train/selection/test.
- **Metrics** (`eval/models.py`/`metrics.py`): `reproduction_pass_rate`, `prereg_verdict`, `claims_dropped`; `OUTCOME_SCORES` for `verification_failed`/`prereg_failed`.
- **Calibration** (`eval/calibration.py`): plain-Python balanced-accuracy threshold mapping judge score → real 14-published/24-rejected boundary; persist `data/eval/calibration.json`.
- **Wire `--live`** (`main.py`/`harness.py`): shared `build_engine(config, seed)`; `paradigm eval --live N --split selection --judge`.

### Phase-1 interop slice
- **Fetch-by-ID lookup** in `orchestrator/literature.py` `process_search_requests()`: detect `id:<arxiv-id>` → dedicated fetch-by-ID provider (behind `provider_factory.py`), not keyword search. Optional PaperQA novelty provider. Verify quality-neutral via `paradigm eval`.

---

## LATER PHASES (sequenced; detailed when each begins)

**PHASE 2 — Output quality & credibility ("ship a real paper"):** journal-ready LaTeX + LLM compile-repair loop (`journal/latex.py`); figure-aware multimodal review (D8 — vision in `AnthropicProvider`, figures into reviewer prompt); resolve-or-drop citation finalize; per-section caching + paper versioning; controlled-vocab keywords. Exit: one defensible, reproducible, submittable paper.

**PHASE 3 — Smarter selection & adversarial review:** taste judge (`knowledge/taste.py`, position-swap, win-rate) as tournament adjudicator; Elo tiered-debate cost + stabilization stopping; diversity/proximity step; cross-model adversarial review + `/kill-argument` (D4/D5/D6).

**PHASE 4 — Self-improvement (compounding; depends on 1D):** gated skill optimization replacing free-text reflection (rejected-edit buffer + meta-skill); self-evolving 142-skill library + pruning; anti-repetition graveyard; real reputation system; safe unattended overnight runs (D7/D12).

**PHASE 5 — Interop & reach (optional):** alphaXiv/Paperclip MCP providers; paper→repo reproduction. Exposing Paradigm as MCP server deferred.

---

## Dependencies
- **1D (eval) is the backbone** — selection gate for Phase 3 (taste calibration) and Phase 4 (skill-evolution).
- **1A → 1B**; **1C** makes 1B cheap; **1B → Phase 2** credibility. Phase 2's multimodal provider work is reused by Phase 3's cross-model review.

## Verification
- Per-feature unit tests (`test_preregistration.py`, `test_verification.py`, extend `test_experimentation.py`/`test_eval.py`/`test_phases.py`/`test_human_gate.py`).
- `paradigm eval` offline must still produce a number (new metrics default None/0 — backward compatible); then `paradigm eval --live N --split selection --judge`. **Gate:** selection-split mean quality ≥ 61/100 baseline, reproduction-pass-rate > 0 with verification on.
- `ruff` clean + full pytest suite green before merge.

## Traceability (direction → phase)
D1→1B · D2→1C · D3→1D · D4→P3 · D5→P3 · D6→P3 · D7→P4 · D8→P2 · D10→P1 interop+P5 · D11→1A · D12→P4 · human-gates/provenance→1E · Denario LaTeX/compile-repair→P2 · Denario multimodal referee→P2/D8 · Denario restart_at_step→1C · Denario resolve-or-drop→1B/P2 · Denario console-as-data-bus→1B.
