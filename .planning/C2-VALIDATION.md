# C2 + backlog — production validation (2026-06-30)

Same-topic before/after on the VM, with C2 (world-model unification) + backlog 1–4
deployed. Compares two real **copper / Alzheimer's** runs:

- **OLD** `thread-ad41e860f1a1` — pre-C2 (Jun 15), `unified_hypotheses` off.
- **NEW** `thread-b370b177fe44` — C2 + backlog live (the suggested test prompt).

## Results

| Metric | OLD (pre-C2) | NEW (C2 + backlog) | |
|---|---|---|---|
| Tournament re-extractions | 4 | **0** | unification: one canonical population |
| `hypothesis.created` (tag) | 63 | 98 | (more rounds/debates in the beefier config) |
| `hypothesis.merged` (dedup) | 0 | **5** | #1 firing |
| `hypothesis.updated` | 5 | **15** | 3× — beliefs actually move |
| Update **sources** | `{?: 5}` (no provenance) | **`{tournament: 10, evidence: 3, experiment: 2}`** | all three drivers |
| Tournament rationales | **0/6** (empty-rationale bug) | **12/12** | reasoning salvage |
| Semantic Scholar 429s (this run) | 9 | **0** | #2 breaker/key |
| JSON-decode errors | 0 | 0 | tolerant parsing holds |
| Non-arXiv reads | abstracts | **PMIDs at 1.4k–2.7k chars, 0 "Abstract only"** | #3 open-access full text |
| Outcome / duration | published / 75 min | **published / 56 min** | faster |

## The headline: belief revision from evidence AND a refuted experiment

The NEW run's `hypothesis.updated` provenance shows the full falsification loop:

```
source=evidence     status=supported            reason=evidence 4+/0-
source=evidence     status=supported            reason=evidence 3+/0-
source=experiment   status=contradicted         reason=prereg refuted        # ← a pre-registered prediction was REFUTED
source=experiment   status=under_investigation  reason=prereg inconclusive
source=tournament   status=supported            reason=tournament winner
```

A hypothesis was marked **CONTRADICTED because a pre-registered experiment refuted
it**, others **SUPPORTED as evidence accumulated** — the world model changed its
mind from multiple signal sources. This is the C2 thesis realized end-to-end.
(Implies `enable_preregistration` is on for the VM run.)

## Per-feature confirmation

- **C2 unification** — 0 tournament re-extractions (was 4); single canonical set.
- **#1 semantic dedup** — 5 merges (was 0). These were *literal* restatements
  (the VM ran with `hypothesis_dedup: normalized`). The repo now defaults to
  `embedding` (threshold 0.75) to also fold paraphrases — re-validate the merge
  count + ranked-set diversity on the next cycle.
- **#2 S2 rate-limiting** — 0 × 429 in the run's window (was 9).
- **#3 non-arXiv reads** — PubMed PMIDs read at full body length with zero
  abstract-only fallbacks; `read_paper` returns None for non-arXiv ids, so real
  text + no fallback marker = the open-access PDF path fetched it.
- **#4 review trajectory** — NOT exercised: the paper was accepted at internal
  review iteration 1 with 0 required changes (cleaner than OLD, which took a peer
  `major_revision` round). The converge-extend / diverge-cutoff logic only engages
  when a paper needs iterative revision. See "Next validation" below.

## Next validation — stress #4 (a deliberately "messy" prompt)

To exercise the trajectory logic, run a topic that invites overreach so the
editor sends it back several times (whittling required-changes down = converging,
or piling up = diverging):

> Propose and rigorously defend a single unifying quantitative law that predicts
> maximum mammalian lifespan **from first principles** (not curve-fitting). Derive
> the scaling exponent, compute predictions for 8–10 species, and demonstrate it
> outperforms standard body-mass allometric scaling. State the law as a bold,
> falsifiable claim with explicit numbers and confidence intervals.

Watch the internal-review iterations: a converging draft should now run *past*
`max_review_iterations` (up to `+ review_convergence_extra`) instead of dying at
the cap; a diverging one should break on the first required-changes increase.
