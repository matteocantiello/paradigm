# Refactoring Playbook — July 2026

Execution-ready plan from the 2026-07-09 health scan (`src/paradigm` 37.3k LOC,
`backend/api` 6.9k, `frontend/src` 11.8k, 104 test files / ~1,950 tests).
Each work item below is meant to be executable in a future session without
re-deriving the analysis: goal → files → procedure → verification → commit.

## Verdict (context)

Healthy where it counts: 2 TODOs in 56k LOC, integration-leaning tests
mirroring modules 1:1, well-factored literature providers, correct handler
seams. Debt is concentrated: a triple hand-mirrored display surface, an engine
that handlers puncture 335×, a 1,895-line constants junk drawer, and a few
600+-line mega-methods.

## Global rules (apply to every item)

- One work item = one commit (or a short series); the FULL suite must be green
  at every commit; `ruff check` + `ruff format` clean.
- **No behavior change.** These are structure-only refactors; if a behavior
  bug is discovered mid-refactor, fix it in a SEPARATE commit first.
- Frontend items also require `npx tsc -b` + `npm run build` green.
- After each wave: run one live `--testing`-tier cycle end-to-end (cheap) as a
  smoke test before starting the next wave.
- Do NOT touch (healthy by design): the `ResearchState` extraction pattern,
  the handler decomposition itself, `literature/` provider layering, the
  fail-fast backend `ConfigParseError` behavior, DisplayManager→fallback
  composition.

---

## Wave 0 — safety scaffolding (do FIRST)

### W0.1 Display parity test  (S, no risk)
**Goal:** a test that mechanically asserts the three display implementations
cover the same event surface, so W1.1 can refactor against it and future
events can't silently diverge.
**Files:** new `tests/test_display_parity.py`.
**Procedure:**
1. Enumerate public methods via `dir()` on `paradigm.display.manager.
   DisplayManager`, `paradigm.display.fallback.PlainTextFallback`, and
   `backend.api.services.ws_display.WebSocketDisplayAdapter` (exclude
   `_`-prefixed and a small explicit allowlist of impl-specific extras, e.g.
   ws `_notify`, manager `_refresh`).
2. Assert `manager_methods - adapter_methods == set()` and vice versa with a
   documented exceptions set; print the diff on failure.
3. Freeze today's diff as the exceptions set; shrinking it is progress.
**Verify:** test passes today; deliberately removing a method makes it fail.

### W0.2 Backend service tests  (M, low risk)
**Goal:** protect the web product's core seams before Wave 1 touches them.
**Files:** new `tests/test_session_manager_lifecycle.py`,
`tests/test_ws_display_adapter.py`.
**Procedure:**
- session_manager: create→start(demo path)→pause/resume→abort lifecycle with
  a stub engine; terminal-status persistence to a fake cycle_store; tier
  grafting (`apply_tier` called with meta's model_tier); guidance inbox drain.
- ws_display: for ~10 representative methods (phase_transition, round_start,
  agent_response streaming, experiment_update, guidance_delivered,
  run_parked), assert the broadcast message type + payload fields using a
  recording fake manager (pattern exists in tests/test_ws_*.py).
**Verify:** new tests green; no production code changes.

---

## Wave 1 — structural (one session each)

### W1.1 One display contract  (L, medium risk, the big one)
**Problem:** `display/manager.py` (1,491 LOC / 163 methods),
`display/fallback.py` (647/152), `backend/api/services/ws_display.py`
(1,283/167) are synchronized by hand (158-method overlap, no Protocol).
Every new event is written 3×, or the web UI silently diverges.
**Design:**
1. New `src/paradigm/display/protocol.py`: `class DisplayProtocol(Protocol)`
   with the FULL typed method surface (signatures lifted verbatim from
   DisplayManager — mechanical; keep `-> None`).
2. Engine + handlers type `self._display: DisplayProtocol` (no call-site
   changes — duck typing already matches).
3. W0.1's parity test switches to: every implementation satisfies the
   Protocol (`isinstance` won't work for non-runtime Protocols; assert via
   the method-set diff against `DisplayProtocol.__annotations__`/inspected
   members).
4. OPTIONAL second step (separate commit, only if step 1-3 proves stable):
   collapse per-event methods into `emit(DisplayEvent)` with a frozen event
   dataclass registry. Do NOT start here — the Protocol alone stops the
   divergence and is low-risk.
**Order:** W0.1 → protocol file → annotate engine/backend → parity test on
Protocol. **Verify:** suite + one live testing-tier cycle with the web UI
open (events visibly flowing).

### W1.2 EngineServices context  (L, medium-high risk)
**Problem:** handlers reach into `engine._*` 335× (review 103, literature 73,
writing 70, citation 32, debate 25, artifacts 25); top targets `_display`
(107), `_logger` (65), `_config` (49), `_db` (28) — a service locator smell.
**Design:**
1. New `src/paradigm/orchestrator/services.py`:
   ```python
   @dataclass(frozen=True)
   class EngineServices:
       config: Config
       db: Database
       logger: EventLogger
       display: DisplayProtocol
       emit_event: Callable[..., None]
       find_agent_by_role: Callable[[str], Agent | None]
   ```
2. Engine builds ONE instance in `__init__` (`self.services`); each handler
   constructor becomes `__init__(self, engine)` → keep engine ref BUT add
   `self._svc = engine.services`, then mechanically rewrite inside each
   handler: `self._engine._display` → `self._svc.display`, `._logger` →
   `.logger`, `._config` → `.config`, `._db` → `.db`,
   `self._engine._find_agent_by_role` → `self._svc.find_agent_by_role`,
   `self._engine.emit_event` → `self._svc.emit_event`.
3. One handler per commit (order by puncture count: artifacts → debate →
   citation → writing → literature → review). `engine.state` reaches stay
   AS-IS (that's legitimate shared state, W3.3's business).
4. Display swap-ability note: the ws adapter path sets `engine._display`
   after construction? (verify — if so, services must be built after display
   injection, or display becomes a property on services).
**Verify:** `grep -c "self\._engine\._" src/paradigm/orchestrator/*.py` drops
from ~335 to <100 (state + handler-to-handler only); suite green per commit.

---

## Wave 2 — cheap mechanical wins (can run anytime, any order)

### W2.1 Split `orchestrator/constants.py`  (M, low risk)
1,895 LOC mixing five concerns. **Target layout:**
- `orchestrator/prompts.py` — every `_*_PROMPT*`, `_PHASE_INSTRUCTIONS`,
  `_MODE_*_OVERRIDES`, directives (`_DATA_POLICY_DIRECTIVES`,
  `_STATS_RIGOR_DIRECTIVE`, `data_policy_directive`).
- `orchestrator/tuning.py` — numeric budgets/thresholds/limits
  (`_WRITING_MAX_TOKENS`, `_MIN_PAPER_LENGTH`, caps, `_*_PER_ROUND`…) +
  type aliases (`InterventionHook`, `DecisionHook`).
- experiment-DAG logic → `orchestrator/code_blocks.py` (`CodeBlock`,
  `_extract_code_blocks`, `_topological_sort`, `_best_first_order`) — or
  directly into experimentation.py if no other consumer.
- `constants.py` remains as a REEXPORT shim (`from .prompts import *` etc.)
  for one release so external imports/tests don't churn; delete the shim in
  a follow-up.
**Procedure:** move symbols by category, update imports mechanically
(`ruff check --fix` catches unused), keep the shim. **Verify:** suite; grep
no file imports removed names from constants directly.

### W2.2 Delete the backend config mirror  (S, low risk)
`backend/api/config.py` re-declares core models "to avoid importing paradigm
(needs 3.11+)" — but `pyproject.toml` already sets `requires-python >= 3.11`,
so the rationale is void. **Procedure:** import `AgentOverrideConfig`,
`AgentConfig`, `StorageConfig` from `paradigm.config`; keep `BackendConfig` +
`load_backend_config` + `ConfigParseError` (the fail-fast behavior is a
deliberate hardening — preserve exactly, tests exist). Delete the duplicated
model classes. **Verify:** backend tests + boot the API once.

### W2.3 Frontend bundle split  (S, low risk)
952 KB single chunk; no `manualChunks` in `frontend/vite.config.ts`.
**Procedure:** add
`build.rollupOptions.output.manualChunks = { react: ['react','react-dom','react-router-dom'], markdown: ['react-markdown','remark-gfm','remark-math','rehype-katex','katex'], viz: ['d3-force'] }`.
**Verify:** `npm run build` — main chunk < 500 KB, no warning; app loads.

### W2.4 HISTORY.md archive  (S, no risk)
496 KB and growing every prompt. **Procedure:** move entries before 2026-07-01
to `HISTORY-archive-2026H1.md`; leave a pointer line at the top of HISTORY.md.
(Keep the append-on-every-prompt convention — just on a lighter file.)

### W2.5 Settings DTO diet  (S-M, low risk)
`backend/api/models/settings.py` declares 7 `*Settings` + 7 `*SettingsUpdate`
+ `AllSettings` shadowing core configs. **Procedure:** generate the read
models from the core pydantic classes (`model_construct`/`model_dump` on the
real config objects, filtered to the exposed fields) OR at minimum collapse
the `*SettingsUpdate` twins via `Optional[...]`-ized single classes. Keep the
route contract identical (frontend types unchanged until W4.2).

---

## Wave 3 — behavior-adjacent surgery (AFTER Waves 0-2; ride along with feature work)

### W3.1 Mega-method decomposition  (M, medium risk)
Extract-method only, no logic changes. Targets and seams:
- `experimentation.run_experimentation_phase` (664 lines) → extract:
  `_setup_execution()` (executor/workspace/repo paths),
  `_run_sprint(sprint_num, …)`, `_run_experiment_block(block, …)` (the
  per-block execute/classify/record body), `_build_caveats(...)`. The
  existing local-counter tangle (`_total_experiments`, breaker flags) moves
  into a small `_ExecutionTally` dataclass.
- `review.run_review_phase` (334) → `_build_editor_prompt(...)`,
  `_editor_call_with_retries(...)`, `_apply_review_decision(...)`.
- `engine._build_agent_prompt` (246) → per-section builders
  (`_context_blocks`, `_guidance_block`, `_mode_overrides`).
- `literature.process_literature_actions` (275) → one small handler per tag.
**Verify:** suite (these modules have the strongest coverage: 3,015 + 2,320
+ 1,515 test LOC) + one live testing-tier cycle.

### W3.2 Shared `PaperContextBuilder`  (M, low risk)
`_build_execution_fact_sheet` exists in engine + writing + review;
forbidden-claims/allowlist/requirements blocks duplicated writing↔review;
review reaches into 6+ writing privates. **Procedure:** new
`orchestrator/paper_context.py` owning fact sheet, forbidden-claims block,
citation-allowlist block, requirements block, figure/reference validators;
writing + review consume it; delete the duplicates. **Verify:** suite; grep
`self._engine._writing\._` in review.py → 0.

### W3.3 Narrow `ResearchState` writes  (M, medium risk — opportunistic)
~200 scattered `engine.state.*` writes. Add typed mutators for the hot paths
only: `state.merge_execution(exp_result)` (exists as engine helper — move it
onto state), `state.record_loop_back(verdict)`, `state.queue_guidance(text,
round)`. Adopt in files as W3.1 touches them; don't do a big-bang sweep.

---

## Wave 4 — frontend + contracts

### W4.1 sessionStore reducer split  (M, medium risk)
653 LOC, one 15-case switch. **Procedure:** extract
`frontend/src/stores/reducers/{agents,literature,knowledge,draft,experiments,
steering}.ts`, each `(state, msg) => partial`; the switch becomes a dispatch
table. No store-shape changes (components untouched). **Verify:** tsc +
build + manual live-session smoke (stream, steering echo, digest).

### W4.2 Kill the TS type mirrors  (M, low risk)
`ws-types.ts` (30 interfaces) + settings/API types are hand-copies of backend
pydantic models. **Procedure:** add `scripts/gen_ts_types.py` (pydantic →
JSON schema → `openapi-typescript`/`json-schema-to-typescript`), emit
`frontend/src/api/generated.ts`, migrate imports gradually (start with
ws-types), add a CI check that regeneration is clean.
**Verify:** tsc; generated types match hand types (diff review) before
deleting the originals.

---

## Suggested execution order

| Session | Items | Gate |
|---|---|---|
| 1 | W0.1 + W0.2 | new tests green |
| 2 | W2.1 + W2.2 + W2.3 + W2.4 (+W2.5 if time) | suite + build + API boot |
| 3 | W1.1 | parity on Protocol + live smoke |
| 4-5 | W1.2 (handlers in puncture order) | puncture count < 100 |
| 6 | W3.1 (experimentation) + W3.2 | suite + live smoke |
| later | W3.1 rest, W3.3, W4.1, W4.2 | ride along with feature work |

Nothing is urgent; no known correctness risk stems from these structures.
The payoff is review speed, safe extension (display events, new handlers),
and ending the 3× display tax.
