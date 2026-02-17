# Paradigm Design Document: Research Threads as First-Class Output

**Author:** Matteo Cantiello
**Status:** Draft
**Date:** February 2026
**Version:** 0.1

---

## 1. Motivation

Paradigm's current output is a markdown file that gets converted to PDF. This inherits the fundamental limitation of traditional scientific publishing: the paper is a static, flat rendering of what was originally a rich, structured, computational process. The data behind figures is discarded. The code that produced them is severed from the claims they support. The agent reasoning, literature trail, and experimental iterations that shaped the conclusions are lost.

This matters for three reasons.

First, **reproducibility**. A PDF describes an analysis in prose. Reproducing it requires reverse-engineering methods from natural language, hunting for datasets on external repositories, and guessing at implementation details the authors omitted. When the producing system had all of these artifacts in structured, executable form moments before serializing them into a document, this information loss is unnecessary.

Second, **composability**. When a future Paradigm run (or any other agent system) wants to build on previous work, it should be able to pull in the actual data, code, and intermediate results rather than parsing prose descriptions. A PDF is optimized for human reading, not machine consumption. In a world where agents both produce and consume research, the primary output format needs to serve both audiences.

Third, **the web**. PDF is a print artifact. It cannot be searched at the sub-document level, cannot embed interactive visualizations, cannot link bidirectionally to its dependencies, and cannot be updated without re-rendering the entire object. The future of scientific communication is on the web, and the output format should be native to it.

## 2. Core Concept: The Research Thread

The primary output of a Paradigm run should not be a paper. It should be a **research thread**: a versioned, self-contained repository that bundles the narrative, data, code, results, provenance metadata, and agent reasoning into an interconnected, addressable structure.

The "paper" still exists, but as one view into the thread rather than the thread itself. Other views are equally valid: a machine-readable manifest for agent consumption, an interactive web rendering, a journal-formatted PDF for submission, or a computational notebook for hands-on exploration.

A research thread is:

- **Self-contained.** Everything needed to understand and reproduce the work is inside the repository. External dependencies are pinned and documented.
- **Interconnected.** The narrative layer references data, code, and figures by stable internal identifiers. Claims are traceable to the computations that produced them.
- **Versioned.** The thread evolves through the research cycle. Each phase (ideation, planning, execution, writing, review) produces a committed state. The full history is preserved.
- **Multi-audience.** Humans read the narrative. Agents read the manifest. Reviewers inspect the code. Journals render the PDF. Each consumer gets the view they need from the same underlying structure.

## 3. Repository Structure

```
research-thread-<id>/
│
├── manifest.yaml                # Machine-readable metadata and dependency graph
├── README.md                    # Human-readable summary and navigation guide
│
├── narrative/                   # The "paper" layer
│   ├── paper.md                 # Main narrative with LaTeX math, linking to artifacts
│   ├── abstract.md              # Standalone abstract
│   ├── figures/                 # Publication-quality figures (PDF/SVG/PNG)
│   │   ├── fig01_mass_spectrum.pdf
│   │   └── fig01_mass_spectrum.svg
│   └── tables/                  # Formatted tables
│       └── tab01_correlations.csv
│
├── data/                        # Input datasets
│   ├── sources.yaml             # Provenance: URLs, DOIs, access dates, checksums
│   └── raw/                     # Original data files as ingested
│       └── gwtc3_bbh_catalog.csv
│
├── code/                        # Analysis code, exactly as executed
│   ├── requirements.txt         # Pinned dependencies
│   ├── 01_data_preparation.py
│   ├── 02_mass_distribution.py
│   ├── 03_spin_correlations.py
│   └── utils/
│       └── bootstrap.py
│
├── results/                     # Computational outputs
│   ├── intermediate/            # Intermediate products (cleaned data, fits, etc.)
│   │   └── cleaned_catalog.csv
│   └── final/                   # Products referenced in the narrative
│       ├── fig01_mass_spectrum.pdf
│       ├── correlation_matrix.json
│       └── summary_statistics.json
│
├── literature/                  # References and context
│   ├── bibliography.bib         # BibTeX references
│   ├── papers/                  # Ingested PDFs (where licensing permits)
│   └── search_log.yaml          # Literature search queries and results
│
├── agents/                      # The full research process record
│   ├── thread_log.jsonl         # Complete agent conversation log
│   ├── debates/                 # Structured records of agent debates
│   │   └── debate_001.json
│   ├── decisions.yaml           # Key decision points and rationale
│   └── review/                  # Internal review iterations
│       ├── review_round_1.md
│       └── review_round_2.md
│
├── exports/                     # Rendered outputs for different consumers
│   ├── paper.pdf                # Journal-ready PDF
│   ├── paper.tex                # LaTeX source (for journal submission)
│   ├── index.html               # Web rendering with interactive elements
│   └── notebook.ipynb           # Jupyter notebook for interactive exploration
│
└── .paradigm/                   # Paradigm-internal metadata
    ├── config.yaml              # Run configuration (model, rounds, parameters)
    ├── checkpoints/             # Phase-end state snapshots
    └── costs.yaml               # Token usage and API cost tracking
```

## 4. The Manifest

The `manifest.yaml` is the machine-readable entry point. It describes what the thread contains, how artifacts relate to each other, and what claims the work makes. An agent consuming this thread can understand its structure without parsing natural language.

```yaml
thread:
  id: "thread-f77c4ffcc059"
  created: "2026-02-15T14:23:00Z"
  paradigm_version: "0.8.0"
  status: "complete"  # or: draft, review, accepted

research:
  title: "Statistical Analysis of the LIGO-Virgo-KAGRA Gravitational-Wave Transient Catalog"
  domain: "astrophysics.gravitational-waves"
  keywords: ["gravitational waves", "compact binary mergers", "population statistics"]

data:
  inputs:
    - id: "gwtc3_catalog"
      path: "data/raw/gwtc3_bbh_catalog.csv"
      source: "https://zenodo.org/records/8177023"
      doi: "10.5281/zenodo.8177023"
      checksum: "sha256:a1b2c3..."
      accessed: "2026-02-15"
      description: "GWTC-3 BBH parameter estimation summary table"

analysis:
  steps:
    - id: "data_prep"
      script: "code/01_data_preparation.py"
      inputs: ["data/raw/gwtc3_bbh_catalog.csv"]
      outputs: ["results/intermediate/cleaned_catalog.csv"]
    - id: "mass_distribution"
      script: "code/02_mass_distribution.py"
      inputs: ["results/intermediate/cleaned_catalog.csv"]
      outputs: ["results/final/fig01_mass_spectrum.pdf"]
      depends_on: ["data_prep"]

claims:
  - id: "claim_ppisn_peak"
    statement: "Statistical evidence for a peak near m1 ~ 40 Msun"
    evidence:
      - figure: "narrative/figures/fig01_mass_spectrum.pdf"
      - statistic: "likelihood ratio 2*Delta*ln(L) = 69.4, p = 5.7e-15"
      - code: "code/02_mass_distribution.py"
    supported_by: ["data_prep", "mass_distribution"]

exports:
  pdf: "exports/paper.pdf"
  html: "exports/index.html"
  latex: "exports/paper.tex"

provenance:
  agents:
    models_used: ["claude-sonnet-4-5-20250929"]
    total_tokens: 1245000
    phases_completed: ["ideation", "planning", "execution", "writing", "review"]
    debates: 1
    review_iterations: 3
    review_outcome: "accepted"
```

## 5. Agent Consumability as a First-Class Requirement

A research thread is not just an archive for humans to inspect. It is a **live input** for the next research cycle. When a future Paradigm run — or any agent system — encounters a published thread, it should be able to:

1. **Read the manifest** to understand what was done, what was found, and what data and code are available, without parsing natural language.
2. **Fork the repository** and immediately have a working computational environment: the code runs, the data loads, the figures reproduce.
3. **Extend the analysis** by importing specific artifacts (a cleaned dataset, a utility function, a fitted model) directly into its own thread, with provenance automatically tracked.
4. **Traverse citations** at the artifact level, not just the prose level. If Thread A's figure depends on a correlation matrix from Thread B, the link is machine-resolvable — not a bibliographic reference that requires a human to find the relevant table in a PDF.

This means the manifest must be rich enough to serve as an API contract. The `claims` section isn't just documentation — it's a queryable index. An agent searching for "evidence regarding the chi_eff–mass ratio correlation in BBH mergers" should be able to find relevant threads by their claims, pull the specific data products, and assess whether the evidence is consistent with or contradicts its own findings.

### 5.1 Thread Linking and the Knowledge Graph

Threads don't exist in isolation. They form a directed graph where edges represent dependency relationships:

- **Data dependency**: Thread B uses a dataset produced or curated by Thread A.
- **Methodological dependency**: Thread B applies an analysis technique developed in Thread A.
- **Claim dependency**: Thread B's hypothesis is motivated by (or contradicts) a claim in Thread A.
- **Fork**: Thread B is a direct extension of Thread A — same data, extended analysis; or same method, new data.

These relationships are recorded in the manifest:

```yaml
dependencies:
  - thread_id: "thread-a1b2c3d4"
    relationship: "data_source"
    artifacts_used:
      - "data/raw/gwtc3_bbh_catalog.csv"
    note: "Used cleaned BBH catalog from this thread"
  - thread_id: "thread-e5f6g7h8"
    relationship: "contradicts"
    claims_referenced:
      - "claim_chieff_q_correlation"
    note: "Our bootstrap analysis shows this correlation does not survive uncertainty propagation"

forked_from: null  # or a thread_id if this is a direct extension
```

Over time, the collection of published threads forms a **knowledge graph** — a web of interconnected research where provenance is traceable end-to-end. An agent can walk this graph to understand the state of a research question: which threads support a claim, which contradict it, what data was used, and whether the conflicting results stem from different datasets, different methods, or different statistical treatments.

This is fundamentally different from the citation graph we have today. The current citation graph links papers to papers, and the links are untyped — a citation might mean "we built on this," "we disagree with this," "this provides context," or "the reviewer told us to cite this." The thread knowledge graph links specific artifacts to specific artifacts, with typed relationships. It's the difference between knowing two papers are related and knowing exactly how their data, methods, and conclusions connect.

### 5.2 Negative Results and the Completeness of Knowledge

The current publishing system has a severe structural bias: negative results rarely get published. Journals select for novelty and positive findings. Researchers self-censor null results because they don't lead to publications. The consequence is a distorted knowledge base where failed approaches are invisible, leading to duplicated effort and an inflated sense of how robust positive findings really are.

Research threads eliminate this problem by construction. A thread is valuable if its process was rigorous, regardless of whether its conclusions are positive, negative, or inconclusive. Consider three scenarios:

**A thread that finds no correlation between chi_eff and mass ratio** after careful uncertainty propagation is enormously valuable. It tells every future agent and researcher: "don't assume this correlation is real based on point estimates — here's the bootstrap analysis showing it vanishes, here's the code, here's the data, reproduce it yourself." In the current system, this might not get published. As a thread, it's a first-class node in the knowledge graph with a clear claim:

```yaml
claims:
  - id: "claim_chieff_q_null"
    statement: "No statistically significant correlation between chi_eff and q after uncertainty propagation"
    result_type: "null"
    evidence:
      - statistic: "bootstrap 95% CI for Spearman rho: [-0.159, +0.076], encompasses zero"
      - figure: "narrative/figures/fig_bootstrap_correlation.pdf"
      - code: "code/03_spin_correlations.py"
    contradicts:
      - thread: "thread-x1y2z3"
        claim: "claim_chieff_q_anticorrelation"
        reason: "Prior result did not propagate measurement uncertainties"
```

**A thread where the analysis code fails to converge** or produces ambiguous results is still useful — it documents a failed approach and the specific conditions under which it failed.

**A thread that reproduces a known result** with independent code on the same data is valuable as confirmation, especially if it quantifies agreement.

The manifest's `result_type` field (which can be `positive`, `null`, `negative`, `inconclusive`, `reproduction`) makes these threads findable and classifiable. An agent surveying a research question can explicitly search for null results and contradictions, not just confirmations.

This also changes the incentive structure around Paradigm itself. If the tool only produces outputs when results are "interesting," it inherits the publication bias of the system it's trying to improve. By treating all rigorous threads as publishable, Paradigm can contribute to a more honest knowledge base.

## 6. The Narrative Layer

The narrative (`paper.md`) uses standard markdown with LaTeX math notation and a linking convention for referencing artifacts within the thread.

```markdown
## 3. Results

### 3.1 Primary Mass Distribution

Figure {@fig:mass_spectrum} shows the primary mass distribution for the
$N = 157$ BBH events in our combined catalog. We find overwhelming
statistical evidence ($2\Delta\ln\mathcal{L} = 69.4$,
$p = 5.7 \times 10^{-15}$) for a peak near $m_1 \approx 40\,M_\odot$,
consistent with predictions from pulsational pair-instability supernovae
[@Woosley2017; @Farmer2019].

![Primary mass spectrum with fitted mixture model.
  Code: `code/02_mass_distribution.py`.
  Data: `results/final/mass_spectrum_data.json`.
  ](figures/fig01_mass_spectrum.pdf){#fig:mass_spectrum}
```

Key conventions:

- **LaTeX math** via `$...$` and `$$...$$` — no Unicode math characters.
- **Internal cross-references** via `{@fig:label}`, `{@tab:label}`, `{@eq:label}`, following pandoc-crossref conventions.
- **Citations** via `[@AuthorYear]` keys pointing to `literature/bibliography.bib`.
- **Artifact links** in figure captions and method descriptions point to the code and data that produced them.
- **Claim anchors** (optional) that can be harvested by the manifest: `{#claim:ppisn_peak}`.

This format converts cleanly to PDF via pandoc, renders on the web with MathJax/KaTeX, and is parseable by agents who can follow the artifact links.

## 7. The Web Rendering

The `exports/index.html` is a self-contained web page (or a small static site) that presents the research thread as an interactive document. It should:

- Render the narrative with proper math (KaTeX), citations (with hover previews), and cross-references.
- Make figures interactive where appropriate (zoomable, with tooltable data points).
- Link inline to the code and data that produced each figure and claim.
- Include a provenance sidebar or panel showing the agent process: which agents contributed to each section, key debates, and the review history.
- Be deployable as a static site (GitHub Pages, Netlify, or similar) with no server-side dependencies.

This is a longer-term goal. The initial implementation should focus on getting the repository structure and manifest right. The web rendering can evolve from a simple pandoc HTML export to a richer interactive experience over time.

## 8. Compatibility with Traditional Publishing

The research thread must still produce artifacts that the existing publishing ecosystem can consume. This means:

- **arXiv**: Needs a `.tex` source bundle. The `exports/` directory should contain a self-contained LaTeX project (`.tex`, `.bib`, figures) that compiles independently. This is generated from the narrative layer using pandoc with a journal-specific template, or directly by a LaTeX-aware export agent.
- **Journals**: Need the same LaTeX source, potentially with a specific document class. Paradigm should support templates for common styles (AAS journals for astrophysics, APS for physics, MNRAS, A&A, etc.).
- **Data repositories**: The `data/` directory, with its provenance metadata, maps naturally to a Zenodo or Figshare deposit.
- **Code repositories**: The thread itself is already a git repository. It can be pushed to GitHub/GitLab directly.

The key principle is that these are **exports**, not the primary format. The thread is the source of truth. The exports are renderings for specific consumers.

## 9. Integration with Paradigm's Agent Pipeline

### 9.1 What Changes

Currently, Paradigm's phases produce intermediate artifacts that are passed forward as context but not preserved in structured form. The research thread model requires each phase to write its outputs to the repository:

- **IDEATION**: Writes `agents/ideation_log.jsonl`, updates `manifest.yaml` with the research idea.
- **PLANNING**: Writes the research plan to `agents/plan.yaml`, records any debates.
- **EXECUTION**: This is the biggest change. The experimentalist agent must write code to `code/`, save data to `data/` or `results/`, and produce figures to `results/final/`. The sandbox environment should be the repository's `code/` + `data/` directories, not a throwaway temp folder.
- **WRITING**: Produces `narrative/paper.md` with proper artifact links. The writer agent needs to know the repository structure so it can reference figures and data by path.
- **INTERNAL_REVIEW**: Review rounds are saved to `agents/review/`. The editor's required changes are structured records, not just prose.

### 9.2 The Execution Sandbox

The most significant architectural change is to the EXECUTION phase. Currently, the experimentalist runs code in an isolated sandbox. In the research thread model, the sandbox should be (or mirror) the thread repository. This means:

- Code written by the experimentalist is saved to `code/` and is the actual analysis code, not throwaway scripts.
- Data loaded by the experimentalist comes from `data/raw/` and intermediate products go to `results/intermediate/`.
- Figures are saved to `results/final/` and later copied or symlinked to `narrative/figures/`.
- The `requirements.txt` is generated from the actual packages imported during execution.

This is a non-trivial change to the sandbox architecture but it eliminates the current gap between "code that was run" and "code that is preserved."

### 9.3 Git Integration

The research thread is naturally a git repository. Each phase transition should be a commit:

```
commit 1: "Initialize thread with prompt and resources"
commit 2: "IDEATION: Generated research idea"
commit 3: "PLANNING: Research plan finalized"
commit 4: "EXECUTION round 1: Data preparation"
commit 5: "EXECUTION round 2: Mass distribution analysis"
...
commit N: "WRITING: Paper draft v1"
commit N+1: "REVIEW round 1: 73 changes requested"
commit N+2: "WRITING: Paper draft v2 (post-review)"
commit N+3: "REVIEW round 2: Accepted"
commit N+4: "Export: PDF and LaTeX generated"
```

This gives full version history for free and makes the thread immediately pushable to GitHub.

## 10. Relation to Existing Standards

This design draws on several existing efforts and should be compatible with them where possible:

- **RO-Crate** (Research Object Crate): A community standard for packaging research artifacts with metadata. The `manifest.yaml` could be made RO-Crate compatible by using its JSON-LD vocabulary. This would make Paradigm threads discoverable by systems that understand RO-Crate.
- **FAIR principles** (Findable, Accessible, Interoperable, Reusable): The thread structure naturally satisfies FAIR: artifacts have identifiers (paths + manifest IDs), metadata is machine-readable, formats are standard, and provenance is complete.
- **Quarto**: A scientific publishing system that already handles markdown-with-math to multiple output formats. Paradigm's narrative layer could adopt Quarto conventions (YAML front matter, cross-reference syntax) to leverage its rendering pipeline rather than building a custom one.
- **Jupyter/MyST**: The MyST (Markedly Structured Text) markdown dialect is gaining traction in scientific computing. It extends CommonMark with roles and directives that map well to the artifact-linking conventions described here.
- **JATS (Journal Article Tag Suite)**: The XML standard used by most journals internally. A JATS export would make threads directly ingestible by journal production systems.

## 11. Implementation Roadmap

### Phase 1: Repository Structure (Near-term)

- Define and implement the thread directory structure.
- Modify each Paradigm phase to write outputs to the correct locations.
- Generate `manifest.yaml` incrementally as the pipeline runs.
- Initialize threads as git repos with per-phase commits.
- Ensure the narrative layer uses LaTeX math notation (the prompt work already underway).

### Phase 2: Artifact Linking (Medium-term)

- Implement the cross-referencing convention in the narrative layer.
- Add figure/table/code provenance to the manifest's `claims` section.
- Build the post-processing step that validates all internal links resolve.

### Phase 3: Export Pipeline (Medium-term)

- Pandoc-based PDF export with journal templates (AAS, MNRAS, A&A, APS).
- LaTeX source bundle generation for arXiv submission.
- Basic HTML export with KaTeX math rendering.

### Phase 4: Web Rendering (Longer-term)

- Interactive web rendering of the narrative with linked artifacts.
- Embeddable, interactive figures (Plotly, Bokeh, or similar).
- Agent provenance visualization (which agent wrote what, debate outcomes).

### Phase 5: Interoperability (Longer-term)

- RO-Crate compatible metadata.
- JATS XML export for journal submission pipelines.
- API for agent consumption of published threads (so future Paradigm runs can programmatically ingest previous threads as inputs).

### Phase 6: Knowledge Graph and Discovery (Longer-term)

- Thread-to-thread linking via manifest dependencies.
- Search index over published manifests for agent-driven literature discovery.
- Negative result classification and surfacing: ensure null/negative threads are findable by agents investigating related claims.
- Thread forking: allow a new Paradigm run to start from a published thread, inheriting its data and code with full provenance.
- Conflict detection: when a new thread's claims contradict an existing thread, automatically surface the disagreement and link the threads.

## 12. Open Questions

- **Storage and hosting.** Where do published threads live? GitHub repos work for code-heavy threads, but large datasets may need a data repository (Zenodo, Figshare) with the thread linking to them. How do we handle the split?
- **Licensing.** The thread bundles code, data, and text. These may have different licensing requirements. How does the manifest express this?
- **Versioning after publication.** If a thread is "published" (e.g., corresponding paper is on arXiv), can it be updated? Should updates be new commits, or entirely new threads that cite the original?
- **Privacy and intermediate reasoning.** The `agents/` directory contains the full reasoning trace. Some of this may be embarrassing, wrong, or contain information the authors would not want public. Should there be a distinction between the "public" thread and the full internal record?
- **Size constraints.** Large datasets, many figures, and full agent logs could make threads unwieldy. What belongs in the thread vs. linked externally?

- **Negative result discoverability.** How do agents and humans find relevant negative results? The current literature search paradigm is biased toward positive findings because that's what gets published and indexed. A thread-based knowledge graph needs its own discovery layer — something like a search index over manifests that can answer queries like "have any threads investigated the chi_eff–q correlation and found null results?"
- **Thread quality and trust.** Not all threads are equally rigorous. In the traditional system, peer review (however imperfectly) serves as a quality filter. What plays that role for threads? Paradigm's internal review is one layer, but a published thread that was reviewed by AI agents has a different trust profile than one reviewed by domain experts. The manifest should probably include a `review` section that describes what kind of review occurred.
- **Incentive alignment.** Researchers currently have no incentive to publish negative results because journals don't want them. Threads remove the journal bottleneck, but the career incentive structure (citations, h-index, grants) still rewards positive findings. The thread model works best in an ecosystem that values completeness of knowledge over novelty. This is partly a cultural problem, not a technical one, but the technical infrastructure can make the right thing easier.

## 13. Conclusion

The research thread model aligns Paradigm's output with what the system actually produces: not a document, but a structured, reproducible research process. The paper is an important human-readable view into that process, but it should not be the primary artifact.

By making the thread the first-class output, we enable three things that the current publishing infrastructure cannot provide. First, reproducibility by construction — the code, data, and provenance are inseparable from the claims they support. Second, agent-to-agent composability — a future research cycle can fork a thread, import its artifacts, and extend its analysis without any manual reconstruction. Third, a complete knowledge base — negative results, null findings, and failed approaches are preserved as first-class nodes in the knowledge graph, eliminating the publication bias that systematically distorts our collective understanding.

The web of knowledge that emerges from linked research threads is qualitatively different from the citation graph we have today. It connects specific artifacts to specific artifacts, with typed relationships. It is traversable by both humans and agents. And it grows more valuable with every thread added — including, and especially, the ones that tell us what doesn't work.

