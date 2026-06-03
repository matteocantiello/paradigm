# Task: Orchestration efficiency (Prompt 67, step 3) — DIAGNOSED, PAUSED

Status: diagnosis complete, **no code changes made**. Resume later.

## Decisions (from user)
- Approach: diagnose first, then propose (done).
- Priority: **quality-first** — only cut provably-redundant waste; leave discussion depth alone.
- Steer for P1: prefer **MCP or a dedicated fetch-by-ID path** for paper lookups, NOT a
  keyword-search reroute.

## Diagnosis (data-driven, honest)
- Token by role (85.6M total): experimentalist 27.6%, synthesizer 18.8%, theorist 15.4%,
  analyst 12.9%, skeptic 8.8%, writer 8.5%, editor 6.8%.
- **Corrected**: "64% duplicate searches" was mostly legitimate cross-cycle re-search
  (within-run dedup works — literature.py:292-299, duplicates `continue` before the search is
  logged). "76% zero-result" swept in events that lack a result-count field (two event schemas).
- **Clean finding**: agents issue `id:<arxiv-id>` queries via the keyword-search interface,
  which always returns 0 — **471 zero-result `id:` queries** (e.g. `id:2509.12411` ×15,
  `id:2509.14053` ×7). Plus ~195 over-long (>=8-word) sentence queries returning 0.
- Existing guards already present: `_CONSECUTIVE_STALE_LIMIT`, `_STALE_SEARCH_THRESHOLD`
  (literature.py:270, 420). So the lever is "stop generating guaranteed-zero queries", not caps.

## Proposals (to implement when resumed)
- [ ] **P1 (high confidence, quality-neutral)** — recognize `id:<arxiv-id>` / bare arXiv-ID
      search requests and resolve them via a real **paper lookup** (MCP server or a fetch-by-ID
      method on the corpus/provider), instead of routing to keyword search. Eliminates ~471
      guaranteed-zero searches + the agent tokens around them.
      - Investigate: does the agent search syntax intend `id:` as a lookup? Where are
        `[SEARCH: ...]` requests parsed (orchestrator/literature.py `process_search_requests`)?
      - MCP angle (user's idea): a paper-lookup MCP server (e.g. arXiv/Semantic Scholar by ID)
        the agents/orchestrator can call deterministically.
- [ ] **P2 (medium)** — normalize over-long queries to keywords before the provider call;
      gate behind config; verify quality unchanged with `paradigm eval`.
- [ ] **P3 (observability)** — stamp experiment name on `code_execution` events so retry/re-run
      waste (the "44 scripts for a 2-3 script task" problem) becomes measurable. No behavior change.

## Verify-with (already built in step 2)
- Use `paradigm eval` before/after to confirm mean quality (baseline 61.0/100) does not drop.

## Reminder
- Step 1 + Step 2 changes are complete/verified but **uncommitted**. Consider committing on a
  branch before starting step 3.
