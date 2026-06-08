# Parallel-Branch Research (phase-level beam search)

**Status:** Phase-0 done → **shelved for ideation** (2 runs, 12 seeds: branching
ties sequential, both tie a single pass; selection/taste — not parallelism — is the
lever). See §10 _Results_. Harness + diversity-merge prompt kept for reuse.
**Owner:** —  ·  **Created:** 2026-06-08

A research modality where, at each phase of a cycle, we fan out **B** diverse
variations, run them in parallel, then **prune + synthesize** to **K** survivors
before the next phase. Formally: **beam search / evolutionary search at
research-phase granularity** — a *diverge → converge* funnel. `B=1, K=1` everywhere
is exactly today's pipeline, so this is a strict generalization.

---

## 1. The question

> Does spending the marginal token on **breadth of framing** (parallel branches,
> synthesized between stages) beat spending it on **depth within one framing**
> (more rounds / debates), or on a **portfolio** (more independent cycles)?

And the user's sharper version: *is 10 parallel branches-with-synthesis better than
10 serial cycles?*

They optimize different things:

| | 10 serial cycles | 10 parallel branches + inter-stage synthesis |
|---|---|---|
| Output | 10 independent papers (portfolio) | **1** paper pooling 10 explorations, dead ends pruned |
| Optimizes | coverage / throughput | depth / quality of a *single* artifact |
| Wall-clock | 10× | ~1× (embarrassingly parallel) |
| Tokens | 10× | ~10× (same spend, compressed in time) |

So the real axis is **where the marginal token goes**:
- **rounds** → depth within a fixed framing (diminishing after ~2–3; can't rescue a bad framing).
- **branches** → breadth of framing (a different axis rounds can't reach).
- **cycles** → portfolio of shallow results.

## 2. Why branches should help (theory)

The highest-leverage decision in research is the **quality of the question /
approach**, decided early (ideation/planning). Serial rounds refine the *execution*
of one approach but can't recover from a mediocre framing. Branches generate many
framings and keep the best — attacking the highest-variance, highest-leverage
decision. Supporting intuitions:

- **Anti-anchoring**: a single thread anchors on its first hypothesis (the platform
  literally has anti-repetition rules fighting this symptom). Independent branches
  each commit to a different framing.
- **Error isolation**: a bad early assumption propagates in a serial cycle; a
  dead-end branch is *dropped*, not carried.
- **Exploration vs exploitation**: ideation rewards exploration; rounds are
  exploitation. best-of-diverse-N attacks the part that matters.
- **Mirrors real science**: many labs pursue different approaches; the field
  synthesizes; dead ends are abandoned — more like science than one lab iterating.

This is **tree-of-thoughts / beam search / evolutionary search** applied at phase
granularity. (Consistent with the dev-directions memo: tree-search execution +
taste judge.)

## 3. The make-or-break: synthesis / selection (taste)

All the value lives in the **prune + synthesize** step:
- A weak merger collapses divergent branches into mush, or picks arbitrarily → 10×
  cost for nothing.
- LLM "variations" are often reworded, not substantively diverse → must **enforce**
  diversity (distinct lenses/personas/constraints/temperatures per branch + a
  redundancy penalty).
- We don't yet have a strong **research-taste judge**. So this is really a bet on
  building good selection + synthesis — independently the most valuable capability
  on the roadmap, and useful even if the full beam never ships.

## 4. It composes existing primitives (small new surface)

| Operator | Already exists | File |
|---|---|---|
| **Selection** (rank, keep top-K) | Elo `HypothesisPopulation` (round-robin, `tournament_winners`) | `knowledge/hypothesis_tournament.py` |
| **Merge** (combine survivors) | synthesizer phase-closing synthesis | `orchestrator/constants.py` `_SYNTHESIS_CLOSING_TEMPLATES` |
| **Branch state** | compressed thread state, `to_context_string` | `storage/checkpoints.py` |
| **Parallelism** | asyncio everywhere | engine |
| **Cost control** | per-thread/agent token budgets | config |

The genuinely new engineering:
1. **Isolate `ResearchState` per branch** — today it's one rich ~30-field mutable
   object assuming a single thread (`thread_id`, contexts, `world_model`,
   `evidence_graph`, `execution_figures`, `selected_hypotheses`, …). A branch needs
   its own copy.
2. A thin **`BranchManager`**: fork → `asyncio.gather` over branch coroutines →
   prune (select and/or merge) at phase boundaries.

The existing hypothesis tournament is the **seed** of this — it already does
population-based selection, just confined to ranking hypotheses inside ideation.

## 5. The shape to build: a diverge→converge funnel

Not flat 10-branches-all-the-way (that's 10× through the *expensive* execution
stage, and writing doesn't benefit from divergence). A **beam that narrows**:

```
Ideation:   B=8 framings  ──tournament──▶ keep K=3
Planning:   each ×2 plans ──tournament──▶ keep K=2
Execution:  run the 2     ──synthesize──▶ keep 1 (+ graft best findings)
Writing:    1 (converged)
```

Puts breadth where variance is highest (early), converges where convergence is good
(late), bounds cost, and **composes with** rounds+debate (branch for breadth, then
rounds for depth within survivors).

**Parameters:** `branch_phases` (which phases fan out), `B` (branching factor, per
phase), `K` (beam width, per phase), `policy ∈ {select, merge, hybrid}`,
`diversity` (lenses/personas), per-branch token budget.

## 6. Development route

Gate the big refactor behind a cheap spike — the whole thing hinges on an empirical
question.

- **Phase 0 — Spike (branch *only* ideation), standalone, no engine changes.**
  `scripts/branch_spike.py`. Generate `B` deliberately-diverse hypothesis sets,
  select/synthesize top-K, score with an independent blind judge. **Gate:** does
  branch-of-B-ideation beat N-rounds at *equal token budget*?
- **Phase 1 — Generalize.** `ResearchState` cloning + `BranchManager` (fork →
  gather → prune) usable at any phase; config (`branch_phases`, `B`, `K`, policy).
  Checkpoints as branch state; DB gets a `parent_branch` link.
- **Phase 2 — Selection/synthesis quality (the real work).** Diversity enforcement;
  a real taste judge (multi-criterion, **held-out independent model** to avoid
  self-grading bias); merge-by-grafting (keep winner, transplant best
  findings/citations from runners-up).
- **Phase 3 — Eval + tune the funnel (which phases, B/K schedule) + a "research
  forest" UI.**

## 7. Testing methodology (we measure, not assume)

A/B harness (extends `scripts/selftest.py` + the spike):
- Fixed seed set (~15–20 prompts across domains); each config run **M times**
  (variance is high — Phase 3).
- Configs: `baseline-1round`, `baseline-Nround`, `branch-ideation`, `branch-funnel`.
- Score multi-dimensionally with an **independent, blind** judge: publish rate,
  reviewer scores (novelty/rigor/clarity/significance), an independent held-out
  judge, novelty check — **and tokens + wall-clock**.
- Report **quality vs cost (Pareto)**. The metric that matters is
  quality-per-token and quality-per-wall-clock, not raw quality.

## 8. Risks / open questions

- **Synthesis bottleneck** (#1 risk) — covered above.
- **Superficial diversity** — needs enforcement + a redundancy penalty.
- **Combinatorial blow-up** — bounded by hard beam width `K` + per-branch budget.
- **Judge bias** — use an independent model; blind the method label.
- **Where does branching stop paying?** Hypothesis: high value at ideation/planning,
  low at writing. The eval decides.
- **Diminishing returns of B** — best-of-N is ~log; find the knee (likely B≈4–8).

## 9. Recommendation

Worth it — but **earn the refactor with the Phase-0 spike**. If branch-ideation
beats 3-rounds at equal budget (~70% prior for ideation specifically), generalize.
If synthesis is the bottleneck (very possible), we learned it cheaply and the fix —
a taste judge — was on the roadmap anyway.

## 10. Results (Phase-0 spike)

`scripts/branch_spike.py` — generator Gemini `gemini-2.5-flash-lite`, independent
blind judge Claude `claude-sonnet-4-6`. Both strategies share the SAME consolidation
step, so the only variable is how candidates are GENERATED.

**Run 1 — 2026-06-08, 4 astro seeds, 1 run each (overall = mean of 5 dims, 1–10):**

| variant | overall | breadth | tokens | quality/1k |
|---|---|---|---|---|
| baseline-1 (1 pass) | 5.20 | 5.5 | 2.8k | **1.83** |
| **baseline-3 (3 rounds)** | **5.95** | **6.2** | 8.7k | 0.69 |
| branch-6 (6 lenses → top-3) | 5.25 | 5.2 | 9.7k | 0.54 |

**Sequential rounds beat parallel branches.** baseline-3 won 3/4 seeds outright.
branch-6 was ~indistinguishable from a single pass (5.25 vs 5.20) at **3.4× the
cost**, and — damningly — scored *lower on breadth* than baseline-3, the very axis
branching was meant to win.

**Interpretation (this is the make-or-break risk from §3 showing up exactly where
predicted):**
- The diversity the branches generated **did not survive consolidation**. With the
  same naive "pick the strongest K" synthesis, baseline-3's *iteratively refined*
  pool consolidated better than branch-6's *6 independent* shots. Rounds let later
  ideas build on earlier ones; branches never talk before the merge.
- So **the bottleneck is selection/synthesis, not parallelism.** Fanning out is
  cheap; *keeping the diversity through the merge* is the hard, unsolved part.

**Caveats (don't over-conclude):** N=4 seeds, 1 run each (noisy); ideation-quality
is a *proxy* for final-paper quality; one coarse integer-scoring judge (pairwise
Elo would discriminate better); cheapest generator + the *simplest* branching.
The negative result is about THIS naive implementation, not the concept ceiling.

**Run 2 — 2026-06-08, 8 seeds (astro + bio + ML + materials), the decisive test.**
Added a **diversity-preserving merge** (`branch-B-div`, coverage-first) applied to
the SAME branch candidates as the naive merge, so the merge is the only variable.

| variant | overall | breadth | tokens | quality/1k |
|---|---|---|---|---|
| baseline-1 (one pass) | 5.47 | 4.9 | 2.8k | **1.96** |
| baseline-3 (3 rounds) | 5.53 | 4.8 | 8.6k | 0.64 |
| branch-6 (naive merge) | 5.33 | 5.5 | 9.8k | 0.54 |
| branch-6-div (diversity merge) | 5.35 | **6.0** | 9.7k | 0.55 |

**Two clear findings:**
1. **The diversity merge works *mechanically*** — it lifted breadth to 6.0 (vs naive
   5.5, vs sequential ~4.8). So the branches DO carry real diversity, and a better
   merge CAN preserve it. The §3 hypothesis was right.
2. **…but it didn't lift OVERALL quality.** More breadth came at the cost of
   specificity (5.4) and rigor (4.6) — a wash. And the bigger picture: **all four
   strategies tie on overall (5.33–5.53), within noise.** Nothing beats a *single
   pass* on quality, and a single pass wins decisively on quality-per-token (1.96
   vs ~0.55). The extra 3.5× compute (rounds OR branches) bought ~nothing for
   ideation. Per-seed there's no consistent winner (branching wins 2/8, loses 3/8).

### Verdict

**Do NOT pursue parallel branching at IDEATION, and do NOT do the engine refactor.**
Two runs (12 seeds total) say the same thing: for ideation, marginal compute —
serial *or* parallel — does not reliably improve quality. Ideation is cheap and a
single good pass is ~as good as 3.5× the spend. The diversity merge is a real,
reusable capability (it does raise coverage) but coverage alone doesn't lift the
aggregate under an equal-weighted rubric.

**What the spike actually taught us (the valuable part):**
- The lever for research *quality* is **not** more ideation compute. It's
  downstream (execution rigor, citation/review quality) and — the deeper one — a
  **better selector/taste judge**. Best-of-N only pays if you can *tell* the best
  from the rest; the judge here is coarse. A real taste model is the unlock, and
  it makes branching, tournaments, and best-of all work better. (Consistent with
  the taste-judge dev direction.)
- A genuinely open question this metric can't answer: it scores the **mean** quality
  of the consolidated set, but the reason to branch is the **max** — insurance that
  *one* branch hit gold and the pipeline develops it. A "best-of / does the set
  contain a standout" metric (and branching at PLANNING/EXECUTION, where a bad
  design is expensive to discover serially) is the only thing that would reopen
  this — but the bar is now high after two flat runs.

Net: shelved for ideation. Reusable artifacts: the A/B harness, the diversity-merge
prompt, and a sharpened thesis that **selection/taste — not parallelism — is the
quality lever.**
