# Paradigm — Architecture Decision Log

## ADR-001: Agent Implementation via System Prompts (not fine-tuned models)

**Status**: Accepted  
**Date**: 2026-02-11

**Context**: Agents need differentiated skills. Options: (a) different system prompts on same model, (b) fine-tuned models per skill, (c) different models per role, (d) tool-access restrictions.

**Decision**: System prompt differentiation on Claude Sonnet 4.5 for research agents. Claude Opus for complex reasoning tasks (editor decisions, difficult derivations) when needed.

**Rationale**: Fine-tuning is expensive, slow to iterate, and unnecessary when system prompts can effectively shape behavior. Tool restrictions add differentiation on top (e.g., only experimentalists can execute code). This is the fastest path to a working system and easy to swap later.

**Consequences**: Agent skill boundaries are "soft" — a theorist might occasionally do data analysis. This is acceptable and even realistic (real researchers cross boundaries too).

---

## ADR-002: Orchestrator as a Python Process (not an agent)

**Status**: Accepted  
**Date**: 2026-02-11

**Context**: Who coordinates agents? Options: (a) a dedicated orchestrator agent, (b) a non-AI Python process, (c) a framework like CrewAI/AutoGen.

**Decision**: A plain Python process with async orchestration. No AI framework.

**Rationale**: The orchestrator needs to be deterministic, debuggable, and fully controllable. Making it an agent adds unpredictability where we need reliability. Frameworks like CrewAI add abstraction layers that make debugging harder and constrain architecture decisions. We need full control over the communication protocol, turn-taking, and state management.

**Consequences**: More code to write upfront. Full control and visibility into every decision the system makes.

---

## ADR-003: ChromaDB + SQLite (not Postgres + pgvector)

**Status**: Accepted  
**Date**: 2026-02-11

**Context**: Need both relational storage (papers, agents, threads) and vector search (semantic retrieval).

**Decision**: SQLite for relational data, ChromaDB for vector search. Both local, zero-config.

**Rationale**: MVP runs on a single machine. SQLite handles the relational needs with zero setup. ChromaDB is the simplest vector DB that works. When/if we need to scale, migrating to Postgres + pgvector is straightforward because the data access patterns will be well-understood by then.

**Consequences**: Single-node only. No concurrent writes from multiple processes (SQLite limitation). Acceptable for MVP where the orchestrator is the single writer.

---

## ADR-004: arXiv API (not a pre-built corpus)

**Status**: Accepted  
**Date**: 2026-02-11

**Context**: Agents need access to scientific literature. Options: (a) pre-built corpus of embedded papers, (b) live arXiv API, (c) Semantic Scholar API, (d) multiple sources.

**Decision**: Primary: arXiv API for live search. Cache results locally and embed for future retrieval.

**Rationale**: arXiv is free, covers most of physics/CS/math/bio, and has a well-documented API. Pre-building a corpus limits scope and requires upfront work. Live search means agents can find anything. The 3-second rate limit is manageable. Caching means frequently-accessed papers don't require re-fetching.

**Consequences**: Depends on internet access (from the orchestrator, not the sandbox). Rate limiting requires patience. Some papers may not be on arXiv (humanities, some biology). This is acceptable for an MVP focused on quantitative sciences.

---

## ADR-005: Docker Containers for Code Execution (not microVMs)

**Status**: Accepted  
**Date**: 2026-02-11

**Context**: Code execution needs sandboxing. Options: (a) Docker containers, (b) microVMs (Firecracker), (c) gVisor, (d) nsjail.

**Decision**: Docker containers with `--network=none`, resource limits, and non-root execution.

**Rationale**: Docker is ubiquitous, well-understood, and provides sufficient isolation for the MVP. microVMs provide better isolation but require more setup (KVM, custom kernels). The attack surface is limited: agents generate Python code that runs with no network access and limited resources. We can upgrade to microVMs later if needed.

**Consequences**: Docker escape is theoretically possible but requires a kernel exploit. Acceptable risk for MVP where the threat model is "AI generates Python code" not "adversary tries to break out."

---

## ADR-006: Domain-Agnostic from Day One

**Status**: Accepted  
**Date**: 2026-02-11

**Context**: Should the system be built for a specific domain first?

**Decision**: Domain-agnostic architecture. The orchestrator, agent framework, journal, and sandbox know nothing about specific scientific fields. Domain knowledge lives entirely in agent system prompts and the literature they access.

**Rationale**: A domain-specific system would need to be refactored for generality later. The abstractions we need (hypotheses, experiments, papers, reviews) are universal across science. The cost of generality is minimal — it's mostly about not hardcoding domain assumptions.

**Consequences**: Early output quality may be lower than a domain-tuned system. We compensate by testing with domains Matteo can evaluate (astrophysics) and tuning prompts.

---

## ADR-007: Markdown for Paper Format (not LaTeX)

**Status**: Accepted  
**Date**: 2026-02-11

**Context**: What format should papers be written in?

**Decision**: Markdown with optional LaTeX math blocks. Papers are stored as markdown in the database.

**Rationale**: LLMs generate markdown far more reliably than LaTeX. Markdown is easy to parse, display, and convert. LaTeX compilation would add complexity for no MVP benefit. Math expressions can use `$...$` inline and `$$...$$` display mode, which most renderers support.

**Consequences**: Papers won't look as polished as LaTeX-typeset documents. Acceptable — the content matters more than the formatting for the MVP. LaTeX export can be added later.

---

## ADR-008: ChromaDB for Agent Episodic Memory (not SQLite)

**Status**: Accepted
**Date**: 2026-02-14

**Context**: Agents are stateless Claude API calls — they have no persistent memory across research cycles. A theorist that discovers a dead-end approach will repeat the same mistake. We need cross-cycle learning. Options: (a) store memories in SQLite and retrieve by keyword/agent, (b) store in ChromaDB and retrieve by semantic similarity, (c) append to agent system prompts directly.

**Decision**: ChromaDB with a separate `agent_memories` collection (same `vector_db_path` as paper embeddings). Semantic search with recency × similarity re-ranking.

**Rationale**: Memories need to be retrieved by topical relevance to the *current* research prompt, not by exact keyword match. A memory about "bimodal pulsation structure" should surface when studying "stellar oscillation modes" even though the words differ. ChromaDB already exists in the stack (ADR-003), using a second collection is zero new infrastructure. SQLite would require building a keyword extraction pipeline for no benefit.

**Consequences**: Memory retrieval has a semantic search step (cheap — local embeddings). All memories for all agents live in one ChromaDB collection, filtered by `agent_id` metadata. Per-agent isolation is enforced at query time, not at storage time.

---

## ADR-009: Recency × Similarity Scoring for Memory Retrieval

**Status**: Accepted
**Date**: 2026-02-14

**Context**: Raw semantic similarity alone would surface old, potentially obsolete memories forever. Options: (a) hard cutoff (delete after N days), (b) recency weighting with exponential decay, (c) manual curation by operators.

**Decision**: Exponential half-life decay combined multiplicatively with similarity score: `combined = similarity × 0.5^(age / half_life)`. Default half-life: 30 days.

**Rationale**: Hard cutoffs are brittle — a 31-day-old insight might be critical. Manual curation doesn't scale. Exponential decay is smooth, tunable, and self-correcting: memories that keep matching current research stay relevant, while stale memories naturally fade. The half-life is configurable per deployment. A `paradigm memory clear --older-than 90d` command exists for manual pruning when needed.

**Consequences**: Very old memories with high similarity can still surface (0.5^(90/30) = 0.125 weight). This is intentional — some lessons are timeless. The bounded injection (top 5 memories, max 2000 chars) prevents context pollution regardless.

---

## ADR-010: Non-Fatal Reflection (Memory Generation)

**Status**: Accepted
**Date**: 2026-02-14

**Context**: At the end of each cycle, a Claude call per agent generates episodic memories. This call could fail (API error, rate limit, malformed response). Should failure block the cycle?

**Decision**: Reflection is wrapped in try/except. Failure is logged but the cycle completes successfully. Memory is additive, never blocking.

**Rationale**: The research output (paper, checkpoint, graveyard entry) is the primary deliverable. Memories are an optimization for future cycles, not a requirement for the current one. Making reflection fatal would mean transient API issues could prevent a completed cycle from returning its results.

**Consequences**: Some cycles may produce no memories (e.g., if API quota is exhausted at the end). The system degrades gracefully — agents without memories still function, they just don't benefit from cross-cycle learning.

---

## ADR-011: Per-Cycle ChromaDB Collection Isolation for Paper Embeddings

**Status**: Accepted
**Date**: 2026-03-04

**Context**: All research cycles shared a single `paradigm_papers` ChromaDB collection. When cycle 2 searched for "red noise", it also retrieved Cepheid papers ingested by cycle 1. The contamination grew with each cycle, degrading search relevance.

**Decision**: Each cycle gets its own ChromaDB collection named `paradigm_papers_{cycle_id}`. In the CLI, `cycle_id` is a random 12-char hex UUID; in the backend, it's the session ID. The `collection_name` parameter is threaded through `Corpus` and `create_source_providers()` down to `EmbeddingStore`.

**Rationale**: `EmbeddingStore.__init__()` already accepted a `collection_name` parameter (used only for test isolation). Wiring it through the initialization chain is minimal work with high impact. Agent memories intentionally remain in a shared `agent_memories` collection — cross-cycle learning is their purpose.

**Consequences**: Each cycle starts with an empty embedding corpus. Papers from previous cycles are still in SQLite (shared) and accessible via direct DB lookups, but don't pollute semantic search. The `vector_db/` directory will accumulate per-cycle collections over time; a future cleanup job can prune old ones.

---

## ADR-012: World-Model ↔ Tournament Unification + Belief Revision (C2)

**Status**: Accepted (opt-in, default-off via `knowledge.unified_hypotheses`)
**Date**: 2026-06-29

**Context**: Analysis of 8 real VM research loops surfaced a structural flaw. The world model held TWO disjoint hypothesis populations: the ~55–107 `[HYPOTHESIS:]` tags parsed each round (all stuck at `elo=1500`/`proposed`, never revised) and a *separate* set of ≤4 hypotheses the tournament re-extracted from the last 15 messages with fresh ids. Only the latter got Elo/status, then was written back as additional entries — never merged. So `hypothesis.updated` was pinned at exactly `population+winners` (~5), beliefs never moved during a cycle, the round-robin tournament capped the field at 4 (O(n²) judge calls), and `WorldModel.update_hypothesis` / `load_snapshot` were dead code.

**Decision**: Make the world model the single hypothesis source. Behind `knowledge.unified_hypotheses` (default off): (1) a `WorldModelHandler.revise_hypothesis()` choke point — the one auditable path for every status/Elo/confidence change, emitting `hypothesis.updated` with `reason`/`source`; (2) the tournament ranks a top-K of the canonical `wm.hypotheses` *by reference* (no re-extraction); (3) dedup-at-creation via a **pluggable** matcher (conservative normalized-statement default; embedding tier swaps in with zero caller changes), emitting `hypothesis.merged`; (4) belief revision driven by tournament results, an evidence support/contradict rule (config thresholds), and the pre-registration verdict; (5) Swiss pairing so a population of 8 costs ~12 judge calls instead of round-robin's 28. A separate, always-on robustness fix routes the fragile LLM-JSON parse sites through a shared tolerant helper (`knowledge/json_utils.py`) with truncation recovery, which also salvages the judge's reasoning (previously the tournament rationales were always empty).

**Rationale**: One ledger with one id per hypothesis is the only way beliefs can accumulate (statement + Elo + status + evidence + verdict) and be revised as evidence lands — the platform's whole thesis is the taste/selector. Flag-gating + A/B replay against the captured `data_vm` threads de-risks a genuine research-behavior change. The matcher is pluggable because the A/B data showed normalized matching catches only literal restatements (a minority); the real ~100→~30 collapse needs paraphrase-aware (semantic) matching, deferred as an isolated swap.

**Consequences**: With the flag on, far fewer hypotheses (deduped), each with a moving status/Elo and an auditable revision provenance surfaced in the Observatory. Cross-cycle world-model memory (resume-time snapshot load) is intentionally deferred. Full design + the 8-step build order: [`.planning/WORLD-MODEL-UNIFICATION.md`](.planning/WORLD-MODEL-UNIFICATION.md).

---

## ADR-013: Corpus-Grounded Citations (no ungrounded inline citations)

**Status**: Accepted (always-on strip net; allow-list path opt-in, default-off via `citation.corpus_grounded_citations`)
**Date**: 2026-06-30

**Context**: A spike tracing the end-to-end citation path found a real correctness hole: a Paradigm writing agent can emit **ungrounded/fabricated inline citations that survive into the final paper**. The assembly prompt instructs the model to *author* a 15–40-entry References section from its own parametric memory (`orchestrator/constants.py`), the writer is never shown the discovered corpus (`writing.py`; `WRITING` absent from `_PHASE_CONTEXT_NEEDS`), and citation grounding is an optional, post-hoc, **default-off** Perplexity pass that leaves author-year strings "unaltered" and silently no-ops on missing key / 240 s budget / zero results. The `a831216` discovered-ID gate protects only literature *discovery* traversal, not writing. A local A/B reproduced it: the baseline paper shipped 3 ungrounded `(Author, Year)` cites and no verifiable bibliography. A peer tool (OpenDraft) makes this structurally impossible via `{cite_XXX}` ID-indirection + a deterministic compiler — see [`.planning/OPENDRAFT-COMPARISON.md`](.planning/OPENDRAFT-COMPARISON.md).

**Decision**: Adopt OpenDraft's invariant, reusing Paradigm's existing infrastructure. New pure, tested helpers in `literature/citation_validation.py`. Two layers:
1. **Allow-list path** (flag-gated `citation.corpus_grounded_citations`, default off): build a numbered `[N]` allow-list from the cycle's `LiteratureHandler.discovered_papers`, append it to both WRITING prompts (cite ONLY `[N]`; never `(Author, Year)`; do not author a bibliography), then compile the `## References` section deterministically from the cited allow-list entries (`CitationHandler.ground_from_allowlist`). Fully offline; when on it OWNS citations and the Perplexity path is skipped.
2. **Always-on safety net** (`citation.strip_ungrounded_citations`, default **true**): strip fabricated inline arXiv ids (not in the cycle's `seen_paper_ids`) from prose, and count unverifiable `(Author, Year)` cites for telemetry (`citation_safety_net` event). Pure robustness; runs regardless of the flag.

**Rationale**: An allow-list the writer cites by index, plus a deterministic compiler, makes an ungrounded inline citation *impossible by construction* rather than relying on a frequently-skipped post-hoc cleanup. It reuses what already exists (`discovered_papers`, `seen_paper_ids`, `BibliographyBuilder`) so the change is small and additive. Flag-gating + A/B matches the C2 rollout discipline (ADR-012) for a genuine writing-behavior change; the strip net ships on by default because it can only remove provably-fabricated identifiers.

**Consequences**: A/B (cheap Flash-Lite, Cepheid prompt) confirmed the design: **baseline** = 3 ungrounded author-year cites + no references; **treatment** = 7 inline `[N]` cites, 0 free-text cites, **7/7 deterministic corpus-backed references** (real discovered arXiv papers), `corpus_grounded_citations` event (7 cited of 9 discovered). Both cycles exited clean; full suite 1765 passed; +17 unit tests. The allow-list path stays default-off pending a production enablement decision (the A/B evidence supports flipping it in `production.yaml`). scite.ai citation-verification (Smart Citations: supporting/contrasting/mentioning + claim↔citation grounding, the deeper semantic gap) is a separate additive fast-follow via the existing MCP `SourceProvider` seam, pending access. A/B configs: `configs/selftest.yaml` (off) vs `configs/selftest-cite-on.yaml` (on).
