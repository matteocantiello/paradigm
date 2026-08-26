# Overnight autonomous work: Phase 1a → Phase 1 → Phase 2

Driver: implement, test at each step, run cycles as acid tests, learn from each run.
Branch: responsive-live-progress. Commit+push per bundle; do NOT merge to main or deploy VM (leave for user).

## Phase 1a — data-layer fixes (from the tidal post-mortem)  ✅ DONE
- [x] 1. Multi-table VizieR staging: split_vizier_tables → one file per sub-table.
      Validated on real I/357: 17 tables, 27,403 P<10d binaries recovered (was 0).
- [x] 2. Truncation → addressed via TAP-join steering (directive) + Gaia TAP provider (Phase 1 #8).
- [x] 3. Acquisition directive: pick right sub-table, exact column names, server-side TAP joins.
- [x] 4. Data card now parses asu-tsv (skips #meta + units/dashes) → shows real column names.

## Phase 1 — data integrity + reach  ✅ DONE
- [x] 5. Deterministic-fabrication classifier: self-labeled stand-ins → synthetic even w/o randomness.
- [x] 6. Binary-format cards: FITS header (columns/dims, stdlib) + HDF5/parquet/npy loader hints.
- [x] 7. Concurrent multi-provider search (asyncio.gather) + one fetch retry.
      (skipped strict discovered-id gate — would break direct gaia:<table> fetches.)
- [x] 8. Gaia (ESA TAP) provider — LIVE-validated: 5000 NSS orbits, mixed types, 1548 P<10d.
- [x] 9. Judge robustness: max_tokens 1024→16384 + first_json_object salvage fallback.

## Phase 2 — real-insight lever  ✅ DONE (directive/gate level)
- [x] 10. Editor review VALIDITY gate: mandatory check #7 — tests its own hypothesis, in-regime,
      no artefactual headline; unreframed overclaim = blocking (honest pilot still OK).
- [x] 11. Novelty: already handled — differentiation directive queued on is_novel=false; #10 reinforces.
- [x] 12. COMPETE ALTERNATIVES in the validity directive (run 2-3, pick on pre-declared metric).
      (Deeper engine-level experiment tournament deferred — needs W3.1 refactor first; higher risk.)
- [x] 13. REGIME RELEVANCE + SANITY ORACLES directive (agents write in-sandbox assertions = self-enforcing).

## Extra bug (from run-1 post-mortem)
- [ ] Review blocking-counter mis-parse: iter said "Blocking: None" but counter logged 8 →
      paper died on revision_exhausted technicality, not a real decision.

## Cycles (acid tests)
- [ ] Cycle 1 after Phase 1a+1 → analyze → learn.
- [ ] Cycle 2 after Phase 2 → analyze → learn → iterate if needed.

## Review (fill in as I go)
