# Refactoring Plan — July 2026 health review

Evidence base: full codebase health scan (2026-07-09) over `src/paradigm`
(37.3k LOC), `backend/api` (6.9k LOC), `frontend/src` (11.8k LOC), `tests/`
(104 files, ~1,950 tests).

## Verdict

The codebase is **healthy where it counts**: near-zero TODO/FIXME debt (2 in
56k LOC), a broad integration-leaning test suite that mirrors modules
one-to-one, a well-factored literature provider layer, and the right handler
decomposition around the engine. The debt is concentrated and structural, not
diffuse: three hand-mirrored display implementations, a god-object engine that
handlers puncture 335 times, a 1,895-line "constants" junk drawer, and a few
600+-line mega-methods.

## Do NOT touch (healthy by design)

- The `ResearchState` per-cycle-state extraction (only narrow its write surface).
- The handler decomposition itself (Writing/Review/Experimentation/Literature/
  Reflection) — right seams, wrong plumbing.
- The literature provider plugin layer (`literature/*` ~300-450 LOC each).
- The test suite shape and the fail-fast backend `ConfigParseError` behavior.
- `DisplayManager` → `PlainTextFallback` composition (the problem is the THIRD
  copy, not this pair).

## Ranked plan

Sequenced so each step de-risks the next; every step lands with the full suite
green and is its own commit.

### Wave 1 — stop the bleeding (structural)

1. **One display contract** (L effort, M risk, very high payoff).
   `display/manager.py` (163 methods) / `display/fallback.py` (152) /
   `backend/api/services/ws_display.py` (167) are synchronized BY HAND; every
   new event is added three times or the web UI silently diverges (158-method
   overlap, no Protocol/ABC anywhere). Introduce a typed `DisplayProtocol`
   (single event-name registry + payload dataclasses); a parity test asserts
   all implementations cover the registry. Migrate call sites mechanically.

2. **EngineServices context instead of engine punctures** (L effort, M-H risk,
   high payoff). Handlers reach into `engine._*` 335 times (review 103,
   literature 73, writing 70, …), mostly for `_display` (107), `_logger` (65),
   `_config` (49), `_db` (28). Pass a small `EngineServices` (display, logger,
   config, db, agent lookup, emit_event) to every handler constructor —
   neutralizes ~250 punctures with near-zero behavior change; the remaining
   state reaches become explicit `engine.state` access.

### Wave 2 — cheap mechanical wins

3. **Split `orchestrator/constants.py`** (M, low risk). 1,895 LOC mixing prompt
   templates, tuning scalars, regexes, a class, and real logic. →
   `orchestrator/prompts.py`, `orchestrator/tuning.py`, and move the
   experiment-DAG logic (`_extract_code_blocks`, `_topological_sort`,
   `_best_first_order`) into experimentation.

4. **Delete the backend config-model mirror** (S, low risk).
   `backend/api/config.py` re-declares core pydantic models "for py<3.11" —
   the deployment runs 3.12. Verify, then import the real models; KEEP the
   fail-fast ConfigParseError behavior.

5. **Dead code + repo hygiene** (S, no risk). `dashboard/` orphan (done
   2026-07-09), stale root scratch (done), `HISTORY.md` at ~500 KB — start a
   yearly archive file (`HISTORY-2026H1.md`) to keep the live log light.

6. **Frontend bundle splitting** (S, low risk). Single 952 KB chunk; add
   `manualChunks` (react vendor, graph components, markdown/katex).

### Wave 3 — behavior-adjacent surgery (after Waves 1-2 land)

7. **Decompose mega-methods** (M, medium risk):
   `experimentation.run_experimentation_phase` (664 lines!),
   `review.run_review_phase` (334), `engine._build_agent_prompt` (246),
   `experimentation._execute_with_retry` (246), `literature.
   process_literature_actions` (275). Extract-method only; the strong test
   coverage on these modules is the safety net.

8. **Shared `PaperContextBuilder`** (M, low risk). `_build_execution_fact_sheet`
   exists in engine + writing + review; forbidden-claims / allowlist /
   requirements blocks duplicated writing↔review; review reaches into 6+
   writing privates. One shared builder ends the cross-handler puncturing.

9. **Narrow `ResearchState`'s write surface** (M, medium risk). ~200 scattered
   `engine.state.*` writes (writing 70, review 45, experimentation 43).
   Add typed mutators for the hot paths (evidence merging, guidance, loop-back
   accounting) — done opportunistically as Wave-3 files are touched.

### Wave 4 — frontend + contracts

10. **`sessionStore.ts` reducer split** (M, medium risk). 653 LOC, one
    15-case switch; extract per-domain reducers.
11. **Kill the type mirrors** (M, low risk). `ws-types.ts` (30 interfaces) and
    the settings DTO triplication are hand-copies of backend pydantic models —
    generate them (openapi-typescript or a small codegen step in CI).
12. **Backend service tests** (M, low risk). `ws_display.py` (1,283 LOC) and
    `session_manager.py` (856 LOC incl. a 218-line `_run_cycle`) have no
    dedicated tests — the web product's core seams are the least protected.
    Add before Wave 1 touches them (the parity test in #1 covers much of
    ws_display).

## Suggested cadence

- Wave 2 items (3-6) are safe single-session work and can happen anytime.
- Wave 1 deserves a dedicated session each, with #12's tests landing FIRST
  as scaffolding for #1.
- Waves 3-4 ride along with feature work in their files ("touch it, tidy it").

Nothing here is urgent: no correctness risk is currently known to stem from
these structures — the cost today is review difficulty and the 3x display tax
on every new event.
