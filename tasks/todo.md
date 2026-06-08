# Quality Audit & Improvement — Prompt 173

Autonomous multi-hour effort. Ground every fix in real generated artifacts; verify with fresh cycles.

## Audit findings (confirmed against real PDF `paper-489a566e6225.pdf` + code)

### Area A — LaTeX/PDF (`journal/latex.py`) ✅ DONE (b147830)
- [x] **A1. Markdown tables** → booktabs `tabular` with l/c/r alignment + math/escaped cells. Verified in a real compiled PDF.
- [x] **A2. Loose-list numbering** → lists survive blank lines (1,2,3 not 1,1,1).
- [x] **A3. Robust preamble** → booktabs/microtype/caption/float/enumitem/xcolor behind `\IfFileExists` (minimal-install safe; booktabs→\hline fallback). References hanging-indent.
- [x] +9 tests.

### Area B — Figures (default matplotlib → publication quality) ✅ DONE (e8fe15d)
- [x] **B1. Publication rcParams** in `_SCIENCE_PREAMBLE` — serif+cm-math, despined, subtle grid, Okabe-Ito palette, 200-dpi tight, `useoffset=False` (kills `1e-13+…`). Both figure paths inherit it. try/except-safe. **Verified by rendering in the real sandbox image** — dramatic improvement.
- [x] **B2. Descriptive captions** — humanize experiment name into alt text; strip redundant "Figure N:" in latex. Prompt guidance: style is pre-applied, demand titles+unit-labelled axes+legend.
- [x] +9 tests.

### Area C — Citations (often sparse / incomplete) ✅ DONE (22040de)
- [x] **C1.** `citation_sections` default → whole body (intro/methods/results/discussion/conclusion).
- [x] **C2.** Retry+backoff in `_fetch_metadata` (transient 429/timeout/5xx), bounded-concurrent resolution (semaphore 4). Redundant per-ref ERROR → debug.
- [x] **C3.** `max_retries_per_paragraph` 2→3.
- [ ] (defer) Feed agent-discovered papers into bibliography — revisit if still sparse after a real run.
- [x] +8 tests.

## Verification (the "few cycles of improvement")
- [~] Flash-Lite cycle (verify-quality.yaml: experiments+grounding+latex/pdf) — RUNNING, inspect PDF.
- [ ] Production-lineup cycle (verify-production.yaml) — strong models, publish path (= task 2).

## Offered follow-ups
- [x] **(1)** Cover review's conceptual-figure branch — review prompt now asks for ≥1 figure (0760a29); review cycle generated styled schematics, PDF compiled with one figure failing (guard).
- [x] **(2)** Real production-lineup batch — verify-production.yaml → PUBLISHED, 0 preflight swaps, publication-quality PDF.
- [x] **(3)** Wire `selftest.py` into a pre-push smoke check — `.githooks/pre-push` (dcfc3dc), validated.

## Prompt 174 follow-on (same session)
- [x] **Completed-cycle routing** (9aaf884) — finished cycles open the paper (or terminal summary), not a dead reconnecting socket. `lib/cycleStatus.ts` central router + socket guard.
- [x] **gpt-5.x preflight 429 retry** (b2a0c70) — burst-induced rate-limit 429s retried before swapping; genuine quota still swaps.

## Review
Verification-driven, real-artifact discipline paid off: the first cycle's PDF surfaced 3 bugs the unit tests couldn't (hallucinated-figure crash, duplicate references, garbage URLs), and the production cycle surfaced the bare-URL resolution issue (fixed via batch+exact-id → 41/41). Net: tables/lists/figures/captions now publication-quality (verified in 2 real PDFs + a PUBLISHED paper), citations complete + correctly formatted, PDF robust to hallucinated figures, completed-cycle navigation fixed, preflight no longer false-swaps gpt-5.x. ~11 commits, full suite 1600, both branches synced. NOTE: production.yaml on the VM has citation grounding OFF — enable it (+ PERPLEXITY_API_KEY) to get the citation improvements.
