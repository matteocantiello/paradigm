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
