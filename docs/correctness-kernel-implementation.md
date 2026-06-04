# Paradigm — Correctness Kernel & Output Quality: Implementation Summary

**Period:** 2026-06-03 → 2026-06-04 · **Branches:** `phase1-correctness-kernel` (PR #12), `phase2-output-quality`
**Companion docs:** `literature/2026-06_Research-Synthesis_and_Development-Directions.md` (the 15-source synthesis, directions D1–D12), `literature/2026-06_Denario-vs-Paradigm-Architecture-Analysis.md`, `literature/2026-06_Unified-Roadmap.md`.

This document summarizes everything implemented, with the **motivation** (why) and the **technical solution** (how) for each change. Every feature is behind a **default-off config flag** — the legacy autonomous pipeline is byte-for-byte unchanged until opted in. Full test suite went from ~1226 → **1355 passing**, ruff clean throughout.

---

## 0. Motivation (the through-line)

Paradigm's measured pain points were: ~38% of runs ended in `writing_failed`, ~65% token waste, weak systematic evaluation, and **output-quality / trustworthiness variability** — papers built on failed experiments, fabricated numbers, bare-URL citations.

A literature review of 15 frontier AI-for-science sources plus a code-level comparison with **Denario** (Paradigm's closest competitor) converged on one high-confidence thesis:

> **Empirical/computational science has no Lean kernel** (the way formal math does, where a proof checker makes hallucination structurally impossible). So Paradigm must **manufacture proxy kernels** — deterministic re-execution, pre-registered falsifiable predictions, and cheap checkers — and make them *publication gates*.

The operator chose three guiding decisions: **(1)** harden *correctness* first; **(2)** a **hybrid + provenance** human posture (autonomous by default, configurable gates, recorded accountability); **(3)** **consume** external agents for literature interop where cheap. Phase 1 implements the correctness kernel; Phase 2 (in progress) adds output quality & credibility.

---

## 1. Phase 1 — The Correctness Kernel

Build order was `1A → 1C → 1B → 1E → 1D` + an interop slice (1B depends on 1A's frozen rules; 1D measures all).

### 1A · Falsifiability / Pre-registration  — direction **D11**
**Motivation.** Gauss/OpenGauss showed verification only certifies *the proof*, not *that you asked the right question* (the "statement-vs-intent" gap). The empirical analog: an agent can correctly compute an answer to the *wrong* question, or reinterpret a result after seeing it. Pre-registration forces a falsifiable claim **before** execution and blocks post-hoc redefinition.

**Technical solution.**
- New models (`knowledge/models.py`): `PredictionRule` (metric name, a strict `metric_stdout_key` token, a direction `inside|outside|greater|less` with bounds, optional `significance_max_p`, a **required** `refutation_condition`, a `frozen` flag) with `is_well_formed()` and `holds(value)`; plus `PredictionDirection`/`PredictionVerdict` enums and `Hypothesis.prediction_rule_id`/`verdict`.
- New handler `orchestrator/preregistration.py`: `run_freeze()` — the theorist authors one rule per candidate hypothesis (tournament winners, else world-model fallback); a **well-formedness reject gate** drops non-falsifiable hypotheses. `evaluate()` — after execution, derives `confirmed|refuted|inconclusive` **only from the frozen rule** vs the captured stdout (greps `metric_stdout_key=value`), so a result can't be reinterpreted.
- New `PRE_REGISTRATION` sub-phase (`phases.py`) between PLANNING and EXECUTION (legacy PLANNING→EXECUTION retained); engine wires the freeze + post-execution evaluation and injects the rules into the EXECUTION prompt. Verdicts feed the writing **Execution Fact Sheet** and turn refuted hypotheses into **FORBIDDEN claims** (refuted/negative results are framed as publishable, never spun).
- Flags: `knowledge.enable_preregistration` (off), `prereg_require_refutation` (True), `prereg_on_empty` (`advisory`).

### 1C · Tree-search / step-restart  — direction **D2** (+ Denario `restart_at_step`)
**Motivation.** The independent critique of the AI Scientist found ~50% experiment failure from a brittle *linear* loop. AI Scientist v2 fixed it with stage-checkpointed tree search; Denario with `restart_at_step`. Goal: don't redo completed work, and spend the experiment budget on promising experiments first.

**Technical solution.**
- `constants.py`: `CodeBlock.restart_at_step` (parsed from a `# RESTART_AT: <k>` comment) and `_best_first_order(...)` — a dependency-respecting Kahn traversal that, among ready nodes, prefers experiments that have **not** failed before, promoting a ready "buggy" node only with probability `debug_buggy_node_prob` (deterministic for a seeded RNG).
- `experimentation.py`: applies best-first ordering after the topological sort; tracks `_buggy_experiments` across rounds; injects "resume from prior artifacts" guidance into the retry prompt (reusing the workspace manifest).
- Flags: `orchestrator.enable_best_first_nodes`, `enable_step_restart`, `debug_buggy_node_prob`, `max_step_restarts_per_experiment` (all off/default).

### 1B · Verification Kernel — re-execution as ground truth  — direction **D1** (+ Denario console-as-data-bus)
**Motivation.** *The centerpiece.* The single highest-leverage fix for trustworthiness: a reported result is only "real" if it **reproduces**. This is Paradigm's proxy for the Lean kernel.

**Technical solution.**
- New module `orchestrator/verification.py`: `VerificationKernel.verify_experiments()` re-runs each `successful_code` block in a **fresh, isolated `verify/<thread>` workspace** with a **deterministic seed preamble** under `--network=none`, extracts `RESULT[label]=value` tokens from the original *and* the re-run stdout, and classifies each experiment `accepted` (reproduced within `verification_tolerance`), `nondeterministic` (drifted), or `rejected` (didn't re-run). `apply_gate()` **demotes** every non-`accepted` experiment out of `successful_code` and flips its metadata to `failure`, so existing FAILED/FORBIDDEN machinery prevents the writer from citing unverified numbers.
- **Console-as-data-bus contract** (from Denario): when verification is on, the EXECUTION prompt requires the experimentalist to print every key number as `RESULT[label]=value`; these exact tokens are what the kernel re-extracts and compares.
- New `VerificationRecord` model; new `VERIFICATION` sub-phase; engine gate aborts the cycle `verification_failed` (before WRITING) if nothing reproduces. A **Verification Ledger** is added to the Fact Sheet.
- Flags: `orchestrator.enable_verification` (off), `verification_tolerance` (1e-6), `verification_seed`, `verification_reexec_budget`, `abort_on_verification_failure`.

### 1E · Hybrid human-gate + provenance  — Nature / Imas / Operon
**Motivation.** *"Why AI cannot do good science without humans"* (Nature) and the economics of scarcity (Imas) argue the durable value is human judgment at a few gates (problem-selection, verification, accountability) — and that this must be a *legible* artifact, not an afterthought. But the platform must stay autonomous by default.

**Technical solution.**
- New module `orchestrator/human_gate.py`: pure `decide_human_gate(mode, points, point, hook, thread_id)` with three modes — `off` (always continue), `advisory` (surface the decision, never block — *cannot deadlock*), `blocking` (defer to the intervention hook; **if no hook is registered, continue with a logged reason** — explicit deadlock guard). Plus `build_provenance(...)` → a `ProvenanceRecord` (framed_by / registered_by / verified_by, gate decisions, prereg rule ids, verification summary), all **written by the engine, never by agents**, so it can't be confabulated.
- Engine: `_human_gate`/`_handle_gate_decision` wired at `problem_selection` (pre-IDEATION), `pre_registration` (post-freeze), `final_verification` (post-verify); `_record_provenance()` after writing, only when gates/verification/pre-registration were active (default runs untouched).
- Flags: `orchestrator.human_gate_mode` (`off`), `human_gate_points`.

### 1D · Eval extension — the selection gate  — direction **D3**
**Motivation.** "Weak evaluation" was a top pain point, and every later improvement (taste, skill-evolution) needs a *measurable, held-out* signal. SkillOpt's lesson: improvement must be gated by a held-out split, not vibes.

**Technical solution.** (extends the existing `src/paradigm/eval/` harness, not a rewrite)
- `eval/seeds.py`: `SeedPrompt` + **hash-fixed** `split_seeds` (train/selection/test) — the test split never leaks and adding seeds never reshuffles existing assignments.
- `eval/calibration.py`: pure `fit_threshold` — a balanced-accuracy sweep that maps the LLM judge's score to the **real published/rejected boundary** from the DB; `calibrate_from_db` driver + JSON persistence.
- New metrics (`eval/models.py`/`metrics.py`): `reproduction_pass_rate`, `prereg_verdict`, `claims_dropped` (reported-only, so the deterministic baseline is unchanged) + `OUTCOME_SCORES` for the new `verification_failed`/`prereg_failed` statuses; `compute_metrics` reads the persisted JSON.
- `harness.py`/`main.py`: `run_live_eval` + `score_thread_paper`; `_run_research` now returns its thread id; `paradigm eval --live N --split {train,selection,test}` wired.
- **SQLite persistence (folded in from 1A/1B/1E):** idempotent `verification`/`prereg`/`provenance` columns on `papers` (PRAGMA-guarded `ALTER`); the engine persists the records in `_record_provenance`.

### Interop slice · fetch-by-id  — direction **D10**
**Motivation.** Diagnosis found **471 guaranteed-zero `id:<arxiv-id>` queries** — agents issuing arXiv-id lookups into the keyword-search interface, which can never satisfy them. Pure wasted budget.

**Technical solution.** `orchestrator/literature.py`: `_extract_arxiv_id_query` (anchored regex; ordinary keyword queries never match) + `_resolve_id_query`, which routes such queries to a direct fetch-by-id (`corpus.read_paper`) instead of keyword search. It counts against the search budget but **not** the keyword-stale throttle (a precise lookup is legitimate).

---

## 2. Live validation (Prompt 73–74)

**What.** A full `--testing` cycle (cheap open-weight models) with **all Phase-1 flags enabled** via a dedicated isolated config (`configs/validate.yaml`, `--network=none`, separate `data_validate/`), on a deliberately self-contained, reproducible prompt: *"how does the standard error of the sample mean scale with n; does it follow 1/√n?"*

**Result — the kernel works end-to-end.** The verification kernel **re-executed all 3 experiments in a fresh `--network=none` sandbox and reproduced 13 `RESULT[]` metrics with max relative error `0.00e+00`**; all three advisory gates fired; provenance persisted (`verified_by=kernel`, `accepted:3/total:3`); `paradigm eval` read the persisted records back (`reproduction_pass_rate=1.0`).

**Refines surfaced and applied** (all unit-tested):
1. **Review convergence** (`orchestrator/review.py`): the editor recommended "revise" with **0 required changes** twice → loop never converged (the only thing that blocked publication). Extracted `_resolve_internal_recommendation`: "revise" with no required changes → **accept** (nothing actionable to revise); "revise" with ≥4 failed mandatory checks → reject (unchanged).
2. **Pre-registration prompt** (`constants.py`): added a concrete worked example so the theorist emits well-formed `PredictionRule` JSON (the live run had frozen 0 rules because the model's output failed the well-formedness gate — the gate worked, the authoring didn't).
3. **Dead testing models** (`configs/default.yaml`): `deepseek-ai/DeepSeek-V3.1` is no longer served serverless on Together (every call 400'd) → switched `testing_overrides` to `DeepSeek-V4-Pro` / `Kimi-K2.6` / `GLM-5.1` (the skeptic on a different family from the generators = cross-model adversarial diversity).

Non-fatal notes logged: an occasional checkpoint-JSON parse fallback; a `SyntaxWarning '\s'` in agent-written code.

---

## 3. Phase 2 — Output quality & credibility (started)

### P2-cite · resolve-or-drop citation finalize  *(done)*
**Motivation.** Unresolved references render as **bare URLs**, which the internal editor rejects — a documented driver of `writing_failed`. Completes 1B's resolve-or-drop discipline at the bibliography stage.

**Technical solution.** `literature/bibliography.py`: `drop_unresolved_references` (drop refs whose metadata didn't resolve, renumber survivors, return an original→new index remap) + `remap_citation_markers` (rewrite in-text `[N]` markers, removing dropped ones so no citation dangles); wired into `citation_handler.py` behind `citation.drop_unresolved_citations` (off).

### P2-LaTeX · journal-ready LaTeX + compile-repair  *(planned)*
Journal presets + `xelatex` compile + `.log`→LLM-fix→recompile loop. The "ship a real paper" centerpiece.

### P2-VLM · figure-aware multimodal review (D8)  *(planned)*
Vision support in `AnthropicProvider`; render figures into the reviewer prompt to catch caption↔figure mismatches and missing/duplicate figures.

---

## 4. Reference

### New source files
| File | Feature |
|---|---|
| `orchestrator/preregistration.py` | 1A |
| `orchestrator/verification.py` | 1B |
| `orchestrator/human_gate.py` | 1E |
| `eval/seeds.py`, `eval/calibration.py` | 1D |
| `configs/validate.yaml` | live validation |
| `tests/test_preregistration.py`, `test_tree_search.py`, `test_verification.py`, `test_human_gate.py`, `test_eval_selection.py`, `test_literature_id_lookup.py`, `test_citation_drop.py` | tests (~100 new) |

### New models / phases
- Models (`knowledge/models.py`): `PredictionRule`, `PredictionDirection`, `PredictionVerdict`, `VerificationRecord`, `ProvenanceRecord`; `Hypothesis` gains `prediction_rule_id`/`verdict`.
- Phases (`phases.py`): `PRE_REGISTRATION`, `VERIFICATION` (added as additional transitions; legacy paths retained).

### New config flags (all default-off / backward-compatible)
| Group | Flag | Default |
|---|---|---|
| `knowledge` | `enable_preregistration` | `false` |
| `knowledge` | `prereg_require_refutation` | `true` |
| `knowledge` | `prereg_on_empty` | `"advisory"` |
| `orchestrator` | `enable_verification` | `false` |
| `orchestrator` | `verification_tolerance` | `1e-6` |
| `orchestrator` | `verification_seed` | `12345` |
| `orchestrator` | `verification_reexec_budget` | `20` |
| `orchestrator` | `abort_on_verification_failure` | `true` |
| `orchestrator` | `enable_best_first_nodes` | `false` |
| `orchestrator` | `enable_step_restart` | `false` |
| `orchestrator` | `debug_buggy_node_prob` | `0.3` |
| `orchestrator` | `max_step_restarts_per_experiment` | `2` |
| `orchestrator` | `human_gate_mode` | `"off"` |
| `orchestrator` | `human_gate_points` | `[problem_selection, pre_registration, final_verification]` |
| `citation` | `drop_unresolved_citations` | `false` |

### Cross-cutting design discipline
Plain-Python (no frameworks); every feature default-off; idempotent `ALTER TABLE ... ADD COLUMN` (PRAGMA-guarded, no migration framework); new phases as *additional* transitions; each feature its own tested commit; full suite green at every step.

---

## 5. Status & what's next
- **PR #12** (`phase1-correctness-kernel` → `main`): reliability + eval harness + Phase 1 Correctness Kernel + validation refines. Open. (Superseded #11.)
- **`phase2-output-quality`** (branch, pushed): P2-cite. Phase-2 PR to be opened when the phase is further along.
- **Next:** P2-LaTeX, P2-VLM (Phase 2); then the roadmap's Phase 3 (taste judge, diversity, cross-model adversarial review), Phase 4 (gated skill-evolution, reputation), Phase 5 (MCP interop).
- **Optional:** a re-validation run would confirm the refines (1A now freezing rules; editor converging to a published paper) end-to-end — deferred (a full cheap cycle ran ~1h41m / ~850K tokens).
