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
- [ ] **(1)** Cover review's conceptual-figure branch (force figure references).
- [ ] **(2)** Real production-lineup batch (strong models, publish path) — config ready.
- [x] **(3)** Wire `selftest.py` into a pre-push smoke check — `.githooks/pre-push` (dcfc3dc), validated.

## Review
(to be filled in)
