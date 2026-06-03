# Task: Evaluation harness (Prompt 67, step 2)

## Decisions (from user)
- **Scope**: Both — Phase A offline scorer over `data/papers` now; structured so a `--live`
  flag can reuse the same rubric on fresh runs later.
- **Scoring**: Deterministic metrics + LLM "taste judge" (novelty, rigor, clarity, significance,
  honesty), blended into one quality score. Judge is optional (skips cleanly without API key).
- **Constraint**: domain-agnostic — no hardcoded scientific-domain assumptions.

## Plan
- [ ] `src/paradigm/eval/models.py` — DeterministicMetrics, JudgeScores, PaperScore, EvalReport.
- [ ] `src/paradigm/eval/metrics.py` — deterministic metrics from paper markdown + DB record
      (outcome→score, body size, #sections, references, bare-URL ratio, figure validity, citations).
- [ ] `src/paradigm/eval/judge.py` — optional LLM judge via the provider abstraction; resilient.
- [ ] `src/paradigm/eval/harness.py` — collect papers (DB + paper dir), score each, blend,
      aggregate, render terminal table + write JSON/CSV to `data/eval/`. `score_paper()` reused by live.
- [ ] DB helper `get_thread_id_for_paper` for the token-cost metric.
- [ ] CLI: `paradigm eval` (offline default; `--judge/--no-judge`, `--limit`, `--live` stub).
- [ ] `tests/test_eval.py` — deterministic metrics + blending + collection (no API).
- [ ] Run baseline over existing `data/papers`; report.

## Status: Phase A DONE
- [x] models / metrics / judge / harness / DB helper / CLI `eval` / tests (9) — all landed.
- [x] ruff clean; full suite **1235 passed**; baseline rendered over real `data/papers`.

## Baseline (63 generated papers, deterministic-only)
- Mean quality **61.0/100**. Outcomes: rejected 24, writing_failed 24 (legacy), published 14, reviewed 1.
- Harness auto-surfaced the editor's complaints as metrics:
  - non-existent figures (e.g. paper-37146874e965 references 32, 0 present)
  - bare-URL citations (e.g. paper-98e5f2add2a9 104/106 bare)

## Remaining (Phase B — opt-in live)
- [ ] Wire `--live N`: reuse main.py's engine setup to run N seed prompts end-to-end, then
      `score_paper()` each. Currently a clean ClickException stub.
- [ ] (nice-to-have) token-efficiency column in the report (tokens already mapped per paper).

## Verification
- ruff clean, pytest green (1235), baseline report renders over real data + writes JSON/CSV to data/eval/.
