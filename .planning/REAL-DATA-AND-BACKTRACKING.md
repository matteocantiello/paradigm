# Real Data Mandate + Non-Linear Research Flow

Design for two coupled improvements (Prompt 256, 2026-07-08):
(1) Paradigm must never pass off synthetic data as real — when it needs data it
acquires it from wired repositories or paper sources; (2) the research cycle
stops being a one-way pipeline — a strongest-model "PI" can reflect on the
draft, send the team back (more experiments / new plan), do the same after peer
review, and — to guarantee convergence — "call it" and finish with what stands.

Reference points: Claude Science (domain-curated connectors + specialist agents
that query them; session forking) and the Berkeley astro-data guide (VizieR/CDS,
SIMBAD, MAST, IRSA, HEASARC, NED, NASA Exoplanet Archive, Zenodo, Dryad).

Evidence this matters (from our own runs): both red-noise A/B arms fabricated
"MIST-like" tracks when downloads failed (network was `none` then); the first
bridge-mode run never exercised the network at all; nothing in the prompts or
review policy *forbids* fabrication today — the editor checklist only catches
"synthetic presented as real" if it notices.

---

## Part 1 — Real Data Mandate

### D1. Policy + deterministic fabrication detection (small, high leverage)

- Config: `orchestrator.data_policy: "real_only" | "prefer_real" | "permissive"`
  (production default: `real_only`).
- EXECUTION + design-review prompt directive (real_only): fabricating datasets
  is FORBIDDEN. Explicitly allowed: bootstrap/permutation/Monte-Carlo
  resampling OF REAL DATA, null models, analytic/theoretical computation.
  If required data cannot be acquired → DESCOPE the experiment and report
  "DATA UNAVAILABLE: <what/why>" honestly — never simulate a stand-in.
- Deterministic post-execution scan of each experiment's code+stdout →
  per-experiment `data_provenance`: `real | derived | resampled | synthetic`.
  Heuristics: np.random/rng used to CREATE arrays that are then saved/analyzed
  as data (vs. resampling idioms over loaded frames), "synthetic|mock|
  placeholder|toy catalog|simulated observations" markers, zero file/network
  reads in a data-claiming experiment.
- Under real_only, `synthetic` experiments are demoted exactly like
  verification failures (excluded from successful_code + fact sheet flags) and
  become a BLOCKING editor alert. Provenance chip on the experiment panel.

### D2. Data acquisition layer — "wired repositories"

Mirrors the literature architecture (SourceProviders + [SEARCH:]/[READ:] tags),
declared per domain profile so the orchestrator stays domain-agnostic:

- New `DataProvider` protocol + registry; astro profile declares
  `data_providers: [vizier, zenodo]`.
- v1 providers (plain httpx, no heavy deps; astroquery optional later):
  - **VizieR/CDS** (astro): catalog search via TAP (`METAobj` description
    match) + bounded download of a table (`J/A+A/...` ids) as TSV/VOTable.
  - **Zenodo** (domain-agnostic): keyword/DOI search + file download.
  - **Paper-linked data**: when [READ:] ingests a paper, harvest dataset links
    (CDS references, Zenodo/Dryad DOIs, GitHub data URLs) → "data available"
    hints injected into discussion context; already-built [DATA: url] staging
    consumes them.
- New agent actions (budgeted per round, like searches):
  - `[DATASEARCH: query]` → ranked candidates (id, title, size/rows, source).
  - `[FETCHDATA: id-or-url]` → orchestrator-side download (size cap,
    provider allowlist) → staged into data/shared/data with a data card +
    provenance record; sandbox sees it the next round.
- Planning contract: the experiment plan must carry a **Data Acquisition
  Plan** — every experiment names its source (attached | fetched:<id> |
  paper-linked | theory/no-data). Under real_only, an experiment with no
  source is descoped at plan time. The interactive plan-approval gate shows it.
- Folds in deferred area C: CDS-ReadMe→`read_fwf` data cards + "report every
  dropped row" QC directive.

### D3 (later). More providers: SIMBAD cross-match, MAST, HEASARC; skills-style
reusable acquisition recipes; dataset caching across cycles.

---

## Part 2 — Non-Linear Research Flow (reflect → backtrack → call it)

New role: **PI (principal investigator)** — the strongest model in the active
tier (premium: claude-opus-4-8; open: zai-org/GLM-5.2), config override role
`pi`, a handful of calls per cycle. All verdicts are structured JSON with the
tolerant-parsing house style.

### R1. PI reflection gate after WRITING (before internal review)

Input: assembled draft + execution fact sheet + plan + experiment inventory +
hypothesis scoreboard + remaining budgets. Verdict:

- `PROCEED` — draft is coherent, go to internal review (default).
- `LOOP_BACK {target: execution | planning, directives: [...],
  success_criteria: "measurable improvement"}` — e.g. "the central claim rests
  on n=31; fetch the full catalog and re-test", "no control sample — add one".
- `CALL_IT {reason}` — stop investing; proceed to review with an honest
  Scope-and-Limitations note.

Mechanics:
- phases.py gains back-edges: WRITING→{PLANNING, EXECUTION} (and
  INTERNAL_REVIEW→EXECUTION for R2).
- Loop-back re-enters the EXISTING stage methods with reduced budgets
  (1 sprint / 1 discussion round); PI directives ride the proven
  OPERATOR-DIRECTIVE channel on planning_action_items; writing re-runs after.
- Budget: `orchestrator.max_loop_backs` (default 2 per cycle, all loops
  combined). Every verdict emits `reflection.verdict`; the Digest panel
  narrates ("PI sent the team back: needs a control sample").
- Interactive synergy: in interactive mode the PI's verdict becomes a
  DecisionHook choice — the PI proposes, the human approves/overrides
  (plumbing already exists).

### R2. Deep revision after peer review

On `major_revision`: the PI triages each reviewer demand → `textual` vs
`needs_new_analysis`. If any `needs_new_analysis` and budget remains →
LOOP_BACK to EXECUTION with directives, rewrite impacted sections, resubmit
through the existing revision loop (reviewers see the response-to-reviewers).
Otherwise the current text-only revision runs. Bounded: at most 1 deep loop
per cycle (shares max_loop_backs).

### R3. Convergence guard + "call it"

- Every LOOP_BACK must declare measurable `success_criteria`; when the flow
  returns to the same gate, the PI verdict must show improvement (blocking
  count down, judge score up, the named analysis exists). No improvement →
  **forced CALL_IT** — a target can never be looped back to twice.
- Global caps: max_loop_backs, token_budget_per_thread (already tracked),
  wall-clock ceiling. Loop-backs disabled when the budget is nearly spent.
- CALL_IT is NOT the graveyard: the paper still goes through review honestly
  and may publish or be rejected on its merits; thread records
  `called_by_pi` provenance + a human-readable status_detail.

### R4. Validation

- Events + Digest surfacing + tests per phase; selftest configs keep
  loop-backs OFF (determinism).
- A/B: linear vs reflective on 2 prompts (e.g. microturbulence + red-noise);
  measure published rate, judge scores, loop-back efficacy, cost delta.

---

## Build order (each its own session-sized chunk)

1. **D1** — data policy + fabrication detector + prompt directives.
2. **R1** — PI role + reflection gate + loop-back to execution/planning.
3. **D2** — VizieR + Zenodo providers, [DATASEARCH:]/[FETCHDATA:], planning
   data contract (folds deferred area C).
4. **R2+R3** — peer-review deep revision + convergence guard + call-it.
5. **R4** — A/B validation + eval wiring.

## Decisions (confirmed by the operator, 2026-07-08)

- data_policy: **real_only** in production/open configs (core default
  prefer_real so CLI/dev flows are unchanged; test-harness configs permissive).
- PI role: **new explicit `pi` override per tier** (premium: claude-opus-4-8,
  open: zai-org/GLM-5.2).
- max_loop_backs: **2** per cycle (all loops combined).
- CALL_IT: the called paper **still passes through review** with an honest
  limitations note.
