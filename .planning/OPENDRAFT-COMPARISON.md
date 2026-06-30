# OpenDraft vs. Paradigm — Design Comparison

> Analysis date: 2026-06-30. Source explored: `../opendraft` @ commit `1e0081d` (v1.7.2,
> first commit 2025-12-19, 118 commits, ~30.7k LOC Python in `engine/`, solo maintainer,
> hosted SaaS = OpenPaper.dev). Companion to `.planning/KOSMOS-COMPARISON.md`.

## TL;DR

**OpenDraft is a polished, productized academic *writing* tool; Paradigm is a *science*
engine.** OpenDraft automates "literature → structured document → verified citations →
typeset PDF/DOCX." It **deliberately cannot run experiments, form hypotheses, or generate
new findings** — its Crafter prompt enforces a "ZERO TOLERANCE" rule against inventing data
or saying "we found." Paradigm does the thing OpenDraft refuses to do (hypothesize →
experiment in a Docker sandbox → peer-review → revise).

So OpenDraft ≈ a much more *finished* version of **one slice** of Paradigm (the
write-the-paper slice), minus the science. It is "better" only inside that narrow lane —
but inside it, a few of its choices are genuinely superior and worth stealing.

---

## Architecture at a glance (OpenDraft)

- **Linear, deterministic plain-Python pipeline** (`engine/draft_generator.py:486-783`);
  LLM only at the leaves. No agentic runtime. (Same core stance as Paradigm.)
- Phases (`engine/utils/checkpoint.py:17`): `research → structure → citations → compose →
  validate → compile`. Data flows through one mutable `DraftContext` "communication bus"
  (`engine/phases/context.py:12-98`).
- **"19 agents" = 19 markdown prompt files** run sequentially through one generic
  `run_agent()` (`engine/utils/agent_runner.py:116-423`) against **one shared Gemini model**.
  8 of them (Skeptic/Verifier/Referee/Voice/Entropy/Polish/Enhancer/CitationVerifier) are
  **manual-only, never auto-invoked** (`docs/ARCHITECTURE.md` "Optional Agents").
- Concurrency: thread-based, **tier-adaptive** (free vs paid Gemini auto-detected,
  `engine/concurrency/concurrency_config.py:67-105`), confined mostly to citation research.
- Single free Gemini key; 10–20 min/draft; ~$0.35–$3.

---

## Table 1 — Similarities (convergent design)

| Dimension | Both OpenDraft & Paradigm |
|---|---|
| Orchestration | Deterministic **plain-Python**; LLM at leaves; no LangChain/CrewAI |
| "Agents" | Differentiated **system prompts**, not autonomous tool-users |
| Phase pipeline | Explicit, sequential phases |
| Checkpoint/resume | Per-phase checkpoints + resume |
| Multi-provider ambition | Gemini/OpenAI/Anthropic (+Groq/Together) |
| Citation sources | CrossRef / OpenAlex / Semantic Scholar / arXiv; S2 rate-limit hardening |
| Resilience | Circuit breakers, transient-error taxonomy, backoff, partial-output capture |
| Token tracking | Per-call token metering |
| North star | Fabricated citations = cardinal sin |

## Table 2 — Differences (and who's ahead)

| Dimension | OpenDraft | Paradigm | Ahead |
|---|---|---|---|
| Core purpose | Submittable literature-grounded *draft* | *Do science*: hypotheses→experiments→findings→review | different |
| Experiments / code exec | **None** (forbids fabricating data) | Docker sandbox `--network=none`, execution sprints | **Paradigm** |
| Hypotheses / world model | None | Unified world model, dedup-at-creation, embedding dedup | **Paradigm** |
| Tournaments / selection | None | Swiss tournaments, Elo, belief-revision choke point | **Paradigm** |
| Peer review | Skeptic/Referee/Verifier **advisory, report-only, partly not auto-run** — no loop | Journal pipeline: reviewers, scores, **revision rounds**, trajectory-aware convergence | **Paradigm** |
| Novelty detection | Keyword topical-relevance filter | Embedding novelty vs corpus | **Paradigm** |
| Output / export | **Pandoc+XeLaTeX APA PDF** + OOXML-post-processed **DOCX** | **Markdown-only** (+LaTeX math) | **OpenDraft** |
| Citation integrity | `{cite_XXX}` ID → **deterministic compiler**; LLM fallback **off at sourcing**; live DOI/HTTP existence checks; domain allowlist | Citation grounding + S2; writer can emit cite strings | **OpenDraft** (architecturally) |
| Per-role model routing | Configured but **dead code** (one model for all) | **Real, working** per-role picker | **Paradigm** |
| Live UI / steering | Supabase progress tracker + CLI | Event-sourced **Observatory**, replay, pause/resume/intervention | **Paradigm** |
| Distribution | **PyPI + npm + setup wizard + hosted free tier + llms.txt/SEO** | Local/VM deploy | **OpenDraft** |
| Standalone tools | tldr, audio digest (ElevenLabs), data-fetch (WorldBank/Eurostat/OWID), revise, expose | Cycle-focused | **OpenDraft** (breadth) |
| Languages | 57+ content (EN/DE/ES/FR metadata) | English-centric | **OpenDraft** |
| Cost / speed / barrier | 10–20 min, ~$0.35–$3, one free key | Heavier cycles, more infra | **OpenDraft** |
| Token budget | Tracked, **never enforced** | **Enforced** per-thread/agent | **Paradigm** |
| Persistence | Per-draft + citation cache | SQLite + ChromaDB, graveyard, cross-cycle memory | **Paradigm** |
| Tests | ~520 fns (78-test security suite, defect-pinned "ticket" regressions) | ~1,741 | **Paradigm** (volume) |

---

## What OpenDraft does BETTER — and why (borrow candidates)

### 1. Citation integrity is the *architecture*, not a feature ★ highest-payoff borrow
The writer never emits "(Smith, 2023)" — it emits `{cite_017}`, an index into a JSON DB
populated **only** from real API hits (`enable_llm_fallback=False` at sourcing,
`engine/utils/agent_runner.py:853`, commented "LLM hallucinates citations"). A deterministic
O(1) compiler swaps IDs → formatted refs at the very end (`engine/utils/citation_compiler.py`),
and a `{cite_MISSING:topic}` escape hatch routes unmet needs **back through the verified API
chain** instead of letting the model invent (`citation_compiler.py:107-151`). On top:
- existence-by-retrieval gate — nothing without a DOI or URL becomes a citation
  (`engine/utils/api_citations/orchestrator.py:447`);
- **live CrossRef DOI existence check** + HTTP liveness (`engine/utils/citation_validator.py:86-107,150-184`);
- curated domain allowlist + blocked-domain list (`orchestrator.py:623-723`,
  `gemini_grounded.py:52-133`).

**Why better:** Paradigm grounds citations but a writing agent can still emit a citation
string directly — integrity is a *behavior*, not an *invariant*. The ID-indirection compiler
is a cheap pattern that makes a whole bug class impossible. *(See spike below.)*

⚠️ Honesty caveat: their own `EVALUATION.md` admits **~85% verified / 10–15% hallucinated
source rate today** (target <5%), there is **no citation↔claim semantic check** (they prove
the paper exists + is topically related, not that it supports the sentence), and the
compile-time LLM fallback (`citation_compiler.py:52` enables it) is the weakest link.

### 2. Publication-grade output ★ borrow if Paradigm ever needs a typeset PDF
Hand-built XeLaTeX preamble (APA double-spacing, italic L3 headings, widow/club penalties,
roman→arabic front-matter, breakable DOI URLs, metadata title page;
`engine/utils/pdf_engines/pandoc_engine.py:201-430`) + a **markdown-sanitation pipeline that
encodes real LLM failure modes as numbered bug-fixes** (strip stray ```` ```markdown ````,
strip code fences that silently truncated a PDF 122→39 pages, escape DOI underscores;
`pandoc_engine.py:113-189,824-1055`) + DOCX cover rebuilt via raw OOXML with auto-fit tables
(`engine/utils/docx_post_processor.py`).
**Why better:** Paradigm's paper is an internal object (Markdown) headed for review;
OpenDraft's deliverable *is* the submittable artifact, so it invested where Paradigm hasn't.
⚠️ The advertised "multi-engine PDF fallback (Pandoc/LibreOffice/WeasyPrint)" and "LaTeX
export" are theatrical — only Pandoc is registered (`pdf_engines/factory.py:41-43`);
requesting the others errors.

### 3. Productization & distribution as first-class concerns
`pip install opendraft` / `npx opendraft` / `opendraft setup` wizard / hosted free tier /
llms.txt / UTM funnels. Built to be *adopted and funded* (OpenAI OSS-fund applicant).
**Why it matters:** Paradigm is more capable but has no 10-minute on-ramp for a stranger.

### 4. Pragmatic UX/robustness polish
Friendly-error translation layer (~20 patterns → human guidance, `engine/opendraft/cli.py:93-262`);
dual-mode `CLIFormatter` rewriting logs into emoji UX (`engine/utils/logging_config.py:76-151`);
**API-tier auto-detection** (probes real rate limits, caches per key,
`engine/utils/api_tier_detector.py`); graceful degradation everywhere (3-library PDF-reader
cascade, pandas-optional, digest survives ElevenLabs failure).

### 5. "AI-output-auditor → defect ticket → regression test" loop ★ cheap discipline to copy
`tests/test_ticket001..016` each pin a specific historical output defect (citation mismatch,
padding, contradiction, table numbering…); `docs/NEW_ISSUES_DEC2025.md` is the auditor that
files new tickets. A disciplined way to ratchet output quality.

### 6. Provider-as-duck-type shim
`GroqModel` reconstructs Gemini's entire response object graph
(`engine/utils/groq_adapter.py:20-67`) so the pipeline + token tracker + parser work
unmodified across providers. Clean dependency inversion.

---

## Where the comparison flatters OpenDraft (be skeptical)

- **"19 agents"** = 19 prompt files on **one** model; 8 are manual-only, never auto-run.
  Prompt headers recommending "Claude Sonnet 4.5" are documentation production ignores.
- **Per-role model routing is dead code** (`config.py:96` `USE_PRO_FOR_VALIDATION` has zero
  call sites; everything uses `ctx.model`).
- **QA/validate has no feedback loop** — Thread/Narrator/FactCheck write reports that never
  revise the draft. The quality gate is *inverted*: a high score *skips* QA to save cost
  (`draft_generator.py:744-748`), it doesn't trigger a rewrite.
- **EVALUATION.md is aspirational** — the benchmark scripts it documents don't exist in repo.
- **Self-rates "10/10"** (`ISSUES.md`) while `NEW_ISSUES_DEC2025.md` lists 3 open *Critical*
  output-leakage defects (planning text, internal metadata, raw `{cite_MISSING}` markers
  leaking into output). Version drift (CITATION.cff 2.1.0 vs 1.7.2); debug logs hardcoded to
  `/tmp/opendraft_debug.log`; ~45-file utils sprawl admitted as tech debt.

---

## Net read for Paradigm — the borrow list

1. **`{cite_XXX}` ID-indirection + deterministic compiler** → make ungrounded inline
   citations *impossible*. Highest-value, cheapest borrow. *(Spike: does a Paradigm writing
   agent currently emit ungrounded inline cites? — see findings appended below.)*
2. **A Pandoc/XeLaTeX export path** → if Paradigm ever needs a submittable PDF/DOCX, their
   sanitation+preamble is battle-tested; don't reinvent.
3. **Defect-pinned regression tests + output-auditor loop** → ratchet paper-quality the way
   they ratchet citation quality.

Do **not** envy: the "no hallucinated citations / publication-ready" headline runs ~10–15%
ahead of their own measured reality, with no claim↔citation semantic check — exactly the gap
Paradigm's peer-review loop is designed to close.
