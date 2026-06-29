# World-Model ↔ Tournament Unification + Belief Revision (C2)

**Status:** DESIGN (Prompt 204). Not yet implemented. Grounded in the VM-loop
analysis (Prompt 203) + a code trace of `knowledge/` (Prompt 204).

## Goal

Make the **world model the single source of truth for hypotheses**, so that
hypotheses are created once, deduplicated, ranked, and have their *beliefs
revised over the cycle* by tournament results, evidence, and experiment
verdicts — instead of the current two-population, write-once, never-revised
design. The visible payoff: the Observatory's knowledge graph shows a *small,
evolving* set of hypotheses whose status/Elo change as evidence accrues, rather
than ~100 frozen `proposed @ 1500` nodes plus 4 disconnected tournament nodes.

### Non-goals (this phase)
- Cross-*thread* knowledge carryover (contamination risk). Cross-*cycle* carry
  is in scope only for **resume** of the same thread, and even that is optional.
- Changing the agent debate/phase structure.
- The literature-only review-bar track (separate workstream; see §10).

## Evidence (why this is needed)

From 8 real VM loops (Jun 10–24) + code trace:
- 55–107 `hypothesis.created` per cycle; **only 3–4** enter the tournament;
  `hypothesis.updated` pinned at exactly `population_size(4)+winners(1)=5`.
- Tournament `rationales` always `['',…]` (judge JSON truncates; fallback drops
  reasoning — shares root cause with the 75 `JSONDecodeError`s).
- World model ends each cycle with **both** populations, never deduped.

## Current architecture (the divergence)

| Concern | Tag set (`[HYPOTHESIS:]`) | Tournament set |
|---|---|---|
| Created in | `world_model_handler.py:136-144`, every agent every round | `tournament_handler.py:214-275`, fresh LLM re-extraction from last 15 msgs |
| IDs | fresh uuid each tag (no dedup) | fresh uuid each extraction |
| Count | 55–107 | ≤ `tournament_population_size` (prod=4) |
| Elo / status | never updated (1500 / PROPOSED) | Elo via round-robin; winners→SUPPORTED |
| Written to WM | yes | **added back as NEW entries** (`tournament_handler.py:169-184`) |
| Evidence links | via `_match_hypothesis` substring (`:224`) | none |

Key dead code / unused capability:
- `WorldModel.update_hypothesis` (`world_model.py:73`) — never called.
- `link_evidence_to_hypothesis` (`world_model.py:131`) — updates lists, never status.
- `load_snapshot` (`world_model_handler.py:254`) — never called at cycle start
  (`initialize_world_model` always fresh, `engine.py:401`).
- `Hypothesis.verdict` / `PredictionVerdict` (`models.py:143`) — prereg verdict
  exists but never flows back to `status`.

## Target architecture — "one hypothesis ledger"

```
[HYPOTHESIS:] tag ─┐
                   ├─► dedup-at-creation ──► wm.hypotheses  (THE canonical set)
agent restatement ─┘                              │
                                                  ├─ tournament RANKS a top-K of THIS set
                                                  │   (Elo + status written back BY ID, by reference)
                                                  ├─ evidence link ──► revise status (support/contradict rule)
                                                  ├─ prereg verdict ──► revise status (CONFIRMED/REFUTED)
                                                  └─ revise_hypothesis()  ← single choke point, emits hypothesis.updated
```

One `Hypothesis` object, one id, accumulating: `statement, rationale, elo,
status, confidence, supporting/contradicting evidence, verdict`. Every belief
change goes through one API and emits one event type.

## Detailed design

### 1. Single hypothesis ledger
- The tournament builds its `HypothesisPopulation` from **existing**
  `wm.hypotheses` objects *by reference* (so `record_result` mutates the
  canonical Elo), instead of constructing new `Hypothesis` objects. Delete the
  "add back as new entries" loop (`tournament_handler.py:172-178`); replace with
  status writes through the revise API (§4).

### 2. Dedup-at-creation (collapse the explosion)
- In `update_from_agent_response`, before `add_hypothesis`, check for a
  near-duplicate. If found: don't create; optionally merge `rationale` and bump
  a restatement counter; emit `hypothesis.restated` (lightweight) instead of
  `hypothesis.created`.
- Matcher tiers: (T1) normalized-statement / substring (extend `_match_hypothesis`,
  cheap, ship first); (T2, optional) embedding cosine via the existing embedding
  store (threshold ~0.85). Conservative threshold; **log every merge**.
- Expected effect: ~100 → ~20–30 distinct hypotheses.

### 3. Consolidation pass (replaces re-extraction)
- Replace `_extract_hypotheses_from_discussion` (fresh extraction → new ids)
  with a consolidation pass **over `wm.hypotheses`** that returns *canonical id
  references* (clusters + a ranked shortlist), never new statements. IDs are
  preserved; the LLM only clusters/ranks/refines wording on the existing set.
- If dedup-at-creation (§2) is strong, this can be a light **selection/ranking**
  pass rather than a merge pass. The existing fallback
  (`tournament_handler.py:280-282`, "seed from wm.hypotheses on extraction
  failure") becomes the *primary* path.

### 4. Belief-revision API (the heart)
- New `WorldModelHandler.revise_hypothesis(hyp_id, *, status=None, elo=None,
  confidence=None, reason: str, source: str)` → calls `wm.update_hypothesis`,
  emits `hypothesis.updated` with `{hypothesis_id, status, elo, reason, source}`
  (reason/source additive to the current payload). **Single choke point** for
  all belief changes.
- Wire it from four drivers:
  1. **Tournament** — winners→SUPPORTED, other competitors→UNDER_INVESTIGATION,
     plus Elo (source="tournament").
  2. **Evidence** — after `link_evidence_to_hypothesis`, evaluate a rule:
     e.g. `contradicting ≥ 2 and contradicting > supporting` → CONTRADICTED;
     `supporting ≥ 3 and supporting > 2·contradicting` → SUPPORTED + confidence
     bump (source="evidence"). Thresholds = config knobs.
  3. **Pre-registration verdict** — `CONFIRMED`→SUPPORTED, `REFUTED`→CONTRADICTED,
     `INCONCLUSIVE`→UNDER_INVESTIGATION (source="experiment"). Wire
     `Hypothesis.verdict` → status.
  4. **(Optional) explicit agent tag** `[STATUS: <hyp keyword> | supported|
     contradicted|abandoned|refined | why]` for human-like revision in debate.
- Net: hypotheses traverse PROPOSED → UNDER_INVESTIGATION → SUPPORTED/
  CONTRADICTED/REFINED/ABANDONED over the cycle — real consolidation.

### 5. Tournament selection + bounded pairing
- Selection: top-K of the consolidated canonical set (K = `tournament_population_size`,
  raise default 4 → ~6–8), chosen by evidence support / recency / agent diversity
  or the consolidation ranking.
- Pairing: replace O(n²) round-robin (`hypothesis_tournament.py:59-74`) with
  **Swiss** (~⌈log₂K⌉ rounds) for K>4; keep round-robin for K≤4 (cheap). For K=8:
  round-robin=28 judge calls vs Swiss(3 rounds)=12. Deterministic pairing (no RNG).

### 6. Judge reasoning (fold in T1 / JSON robustness)
- Reorder the judge JSON so `reasoning` precedes `margin`
  (`constants.py:1606-1615`) so truncation keeps the reasoning.
- In `parse_judge_verdict` fallback (`tournament_handler.py:60-71`), salvage
  reasoning (regex / raw prose) instead of hardcoding `""`.
- Migrate hypothesis extraction + prereg parsing to a **shared tolerant
  JSON helper** (extract `_first_json_object` + truncation recovery into
  `knowledge/json_utils.py`); add `metadata_key` so failures are attributable.
  (This is the Phase-1 JSON fix; it belongs here because it's what makes the
  tournament/world-model data real.)

### 7. Cross-cycle persistence (optional, resume-only)
- `initialize_world_model` (`engine.py:401`): when the cycle **resumes** an
  existing thread that has a snapshot, `load_snapshot` to carry Elo/status
  forward; otherwise fresh. No cross-thread carry. Gate behind a flag; lowest
  priority — within-cycle consolidation (§4) is the main win.

### 8. Events + frontend compatibility
- Keep `hypothesis.created` / `hypothesis.updated`; add additive
  `reason`/`source` to the updated payload. New lightweight `hypothesis.merged
  {from_id, into_id}` (and/or `hypothesis.restated`) for dedup.
- Frontend: the replay reducer (`lib/replay/reducer.ts`) + live
  `KnowledgeGraph` must handle a merge (collapse/remove a node) — mechanically
  similar to the backward-scrub node removal already implemented. Validate
  against a real `data_vm` thread.
- UX payoff: far fewer nodes, and they change color/status over the run.

### 9. Prompts
- `[HYPOTHESIS:]` guidance: prefer restating/refining an existing hypothesis to
  spawning near-duplicates; teach `[STATUS:]`/`[EVIDENCE:]` for revision.
- Consolidation prompt: cluster by canonical id, return id references.

## 10. Adjacent: literature-only review-bar track (team decision)

Chosen separately (Prompt 204): rather than force an experimentalist, make the
editor's empirical bar **conditional**. When EXECUTION was skipped
(`should_experiment == False`, `engine.py:509-514`), branch the editor-review
template (`constants.py:538-560`, assembled `review.py:259-263`) to not require
experimental figures / quantitative results, and lean on conceptual figures
(`enable_conceptual_figures`). Tracked here because it shares the review +
world-model surface, but it can ship independently.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Research-behavior change (winner/paper quality regresses) | Feature flag `knowledge.unified_hypotheses` (default OFF). A/B replay against real `data_vm` threads; compare winner + paper before flip. |
| Dedup over-merges distinct hypotheses | Conservative threshold, normalized match first (embeddings later), log every merge, keep originals' rationale. |
| Judge-call cost blows up with larger K | Swiss/seeded pairing, K cap, round-robin only for K≤4. |
| Frontend replay breaks on merges | Additive events; reducer handles merge like backward-scrub removal; test against a real thread. |
| Cross-cycle contamination | Resume-only, flag-gated, off by default. |

## Rollout / testing

- **Flag-gated, incremental** — every step below is independently shippable and
  testable behind `knowledge.unified_hypotheses`.
- **Unit:** dedup matcher; revision rules (evidence thresholds, prereg→status);
  Swiss pairing determinism; revise-API event emission.
- **Integration:** a functional cycle asserting a *single* hypothesis set,
  `hypothesis.updated` > 5, and observed PROPOSED→SUPPORTED/CONTRADICTED
  transitions.
- **Regression:** events still emit; replay reducer + KnowledgeGraph handle
  merge; `parse_judge_verdict` keeps reasoning.
- **Real-data validation:** re-run `buildKnowledgeGraph` / the replay reducer
  over a `data_vm` thread under the new emission → confirm fewer, status-changing
  nodes.

## Implementation order (each shippable behind the flag)

1. **Belief-revision choke point** — `revise_hypothesis` + route the tournament
   write-back through it, mutating canonical objects by reference (no new ids).
   *(makes `hypothesis.updated` meaningful; no selection change yet)*
2. **Tournament ranks the canonical WM set** — population from `wm.hypotheses`,
   selection heuristic; retire the re-extraction. *(the core unification)*
3. **Dedup-at-creation** — normalized match in `update_from_agent_response`;
   emit `hypothesis.merged`. *(collapse the explosion)*
4. **Evidence-driven + prereg-verdict status revision.** *(real consolidation)*
5. **Bounded pairing (Swiss) + raise population size.**
6. **Judge-reasoning salvage + shared tolerant-JSON helper** (T1 + JSON fix).
7. **Frontend** — replay reducer + KnowledgeGraph merge handling.
8. *(Optional)* resume-only cross-cycle snapshot load.

## Locked decisions (Prompt 204)

- **Dedup aggressiveness:** normalized-statement match first, behind a
  **pluggable matcher interface** so embedding similarity can drop in later
  without rework (safe-first for an irreversible merge). → §2
- **Tournament size + pairing:** raise population **4 → 8**, **Swiss** pairing
  (~12 judge calls); round-robin retained for n≤4. Config-tunable. → §5
- **Cross-cycle memory:** **DEFER.** `load_snapshot` stays a documented
  follow-up; keep the flag's blast radius to within-cycle consolidation. → §7
- **Evidence→status thresholds:** config knobs with defaults — CONTRADICTED when
  `contradicting ≥ 2 and contradicting > supporting`; SUPPORTED when
  `supporting ≥ 3 and supporting > 2·contradicting` (+confidence bump); else
  UNDER_INVESTIGATION once it has evidence or competes. → §4
- **Literature-only review track (§10):** ship **separately, BEFORE C2** as a
  standalone quick win (independent of the world-model work).

## Finalized build order

**Step 0 — Literature-only review track (ships first, NOT under the C2 flag).**
Branch the editor-review prompt to drop the experimental-figure / quantitative
bar when `should_experiment == False`; lean on conceptual figures. Fixes 2 of
the dead VM runs. (§10)

**C2 (behind `knowledge.unified_hypotheses`, default off):**
1. `revise_hypothesis` choke point + route tournament write-back through it
   (mutate canonical objects by reference). *(makes `hypothesis.updated`
   meaningful; no selection change yet)*
2. Tournament ranks the canonical WM set; retire the re-extraction. *(core
   unification)*
3. Dedup-at-creation — normalized, pluggable matcher; emit `hypothesis.merged`.
4. Evidence-driven + prereg-verdict status revision (threshold defaults above).
5. Swiss pairing + population 8.
6. Judge-reasoning salvage + shared tolerant-JSON helper (`knowledge/json_utils.py`).
7. Frontend — replay reducer + KnowledgeGraph merge handling.
8. ~~Cross-cycle snapshot~~ — **deferred** (out of scope this phase).

Each step is independently shippable and validated by A/B replay against real
`data_vm` threads before the flag is flipped on.
