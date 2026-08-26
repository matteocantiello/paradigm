# Overnight autonomous work: Phase 1a → Phase 1 → Phase 2

Driver: implement, test at each step, run cycles as acid tests, learn from each run.
Branch: responsive-live-progress. Commit+push per bundle; do NOT merge to main or deploy VM (leave for user).

## Phase 1a — data-layer fixes (from the tidal post-mortem)  ✅ DONE
- [x] 1. Multi-table VizieR staging: split_vizier_tables → one file per sub-table.
      Validated on real I/357: 17 tables, 27,403 P<10d binaries recovered (was 0).
- [x] 2. Truncation → addressed via TAP-join steering (directive) + Gaia TAP provider (Phase 1 #8).
- [x] 3. Acquisition directive: pick right sub-table, exact column names, server-side TAP joins.
- [x] 4. Data card now parses asu-tsv (skips #meta + units/dashes) → shows real column names.

## Phase 1 — data integrity + reach
- [ ] 5. Deterministic-fabrication classifier (provenance catches randomness only today).
- [ ] 6. Binary-format schema cards (FITS/VOTable/HDF5/parquet).
- [ ] 7. Robust acquisition: concurrent multi-provider search + cross-provider fetch fallback/retry
      + discovered-id gate for FETCHDATA.
- [ ] 8. Add Gaia (ESA TAP) provider (+ SDSS if cheap).
- [ ] 9. Quality-ledger judge no-scores robustness (brittle parse).

## Phase 2 — real-insight lever
- [ ] 10. Review VALIDITY gate: "does it answer its own question in the testable regime?" (blocking).
- [ ] 11. Honor the novelty gate (is_novel=false → pivot/differentiate, don't duplicate).
- [ ] 12. Experiment-level competition/selection (run 2-3 alternatives, pick on a pre-declared metric).
- [ ] 13. Correctness layer: self-checking invariants + sanity oracles; stats-rigor as a gate.

## Cycles (acid tests)
- [ ] Cycle 1 after Phase 1a+1 → analyze → learn.
- [ ] Cycle 2 after Phase 2 → analyze → learn → iterate if needed.

## Review (fill in as I go)
