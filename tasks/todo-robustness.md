# Iterate-to-robustness loop (+ W3.1 experimentation refactor)

Branch: responsive-live-progress. Commit per step; do NOT merge/deploy.

## Step 1 — W3.1 refactor (PURE extract-method, no behavior change)
Gate: the existing experimentation tests + full suite must stay green after EACH extraction.
- [ ] `_ExecutionTally` dataclass — fold loose counters/flags/accumulators.
- [ ] `_setup_execution()` — executor/workspace/repo_paths/budget.
- [ ] `_run_experiment_block(block, ...)` — per-block execute→classify→record.
- [ ] `_run_sprint(sprint_num, ...)` — design review → execute rounds → checkpoint.
- [ ] `_build_caveats(...)` — network/timeout/vacuous caveats.
- Verify: full suite green (experimentation has strong coverage).

## Step 2 — iterate-to-robustness loop
- [ ] Config: `enable_robustness_loop` (default off for back-compat, ON in default.yaml),
      `robustness_max_rounds`, `robustness_convergence_tol`.
- [ ] After the main sprints, run a bounded robustness loop:
      - extract headline RESULT[...] metrics from successful experiments,
      - prompt experimentalist to STRESS-TEST them (vary thresholds/cuts/methods, subsample
        stability) — operationalizes the COMPETE ALTERNATIVES + SANITY ORACLES directives,
      - stop when headline metrics STABILIZE across a round (max rel change < tol) or the agent
        reports robust, else continue until budget.
      - fold robustness results into the evidence base / fact sheet.
- [ ] Tests: tally, convergence check, loop bound, config wiring.
- [ ] Validate with a testing-tier (cheap) cycle first, then a premium tidal cycle.

## Notes
- The published pipeline (paper-47e3f80efe7f, 7.6/10) must not regress — tests are the safety net.
