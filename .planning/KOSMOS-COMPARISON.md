# Kosmos (Edison Scientific) vs Paradigm — comparison + what to borrow

**Created:** 2026-06-08 · **Source:** Kosmos paper (arXiv:2511.02824v2, "Kosmos: An AI
Scientist for Autonomous Discovery", Edison Scientific) + their build write-up
(labs.edisonscientific.com/research/how-we-built-kosmos).

Edison Scientific is the Robin / FutureHouse lineage — the same intellectual
neighborhood Paradigm draws on (Robin, Sakana AI Scientist, Google AI co-scientist,
Virtual Lab). This doc captures how Kosmos differs from Paradigm and, concretely,
what's worth borrowing.

---

## 1. What Kosmos is (key facts)

A **data-driven discovery engine**: input = an open-ended objective **+ a real
dataset**; output = 3–4 cited discovery reports. Runs **up to 12 hours / 20 cycles**.

- **Architecture:** a **structured world model** (shared memory) coordinates many
  parallel rollouts of **two general-purpose agents**:
  - a code-writing **data-analysis agent** (LLM whose primary tool is code
    execution; writes Jupyter notebooks; no a priori tool knowledge), and
  - a **literature-search agent** (the "superhuman synthesis" / PaperQA2 lineage).
- Each cycle launches up to ~10 parallel lit-search + analysis tasks; the world
  model is updated with task-output summaries and **queried to propose the next
  cycle's tasks** (their context-management answer to "coherence over many actions").
- **Per run (avg):** ~**200 agent rollouts** (≈166 data-analysis + 36 lit-review),
  ~**42,000 lines of code** executed, ~**1,500 papers** read. (9.8× Robin's code.)
- **Traceability:** every statement cites a notebook (code) or a primary paper;
  full agent trajectories are published (platform.edisonscientific.com/trajectories).
- **Infra:** Kubernetes-managed sandboxes, gVisor + rootless + single-tenant VMs,
  JuiceFS distributed filesystem (shared across sandboxes), warm-pool of sandboxes,
  L4 GPUs, credential injection at egress, self-hosted packages, on-prem deploy.
- **Models:** not disclosed.

**Evaluation (rigorous, external):**
- **79.4% of statements accurate** by independent expert scientists — by type:
  **85.5% data-analysis, 82.1% literature-review, 57.9% interpretation/synthesis**.
- A 20-cycle run ≈ **~6 expert-months** of research (collaborator estimate; their
  own tally ≈ 4.1 expert-months).
- **Valuable findings scale ~linearly with cycles** (5.8 → 7.5 → 11.0 at cycles
  5/10/20); novelty moderate-to-complete, reasoning depth high-to-moderate.
- **7 discoveries** (metabolomics, materials, connectomics, statistical genetics,
  proteomics, transcriptomics). **3 reproduce withheld** (unpublished/post-cutoff)
  findings as a **memorization control**; 4 are novel. Notable novel: SOD2 → cardiac
  fibrosis; entorhinal flippase collapse → microglial phagocytosis in aging.

**Their stated limitations (unusually honest — and important):**
- 85% data-analysis accurate, but eval doesn't capture whether the analyses *chosen*
  were the ones most likely to yield insight. Tends to **invent obscure metrics**.
- Only **57% on interpretation** — **conflates statistically-significant with
  scientifically-valuable**; needs "scientific taste."
- Tends to make **excessively strong claims**; needs human oversight.
- **No automated way to tell if a claim is accurate / novel / significant at scale**
  — identifying valuable discoveries is human-expert-intensive.
- Datasets ≤ ~5 GB; weak on raw images / raw sequencing; can't fetch external data
  for orthogonal validation; stochastic (runs don't always converge); no mid-run
  scientist interaction; quality hinges on clean/labeled/normalized input data.

---

## 2. Similarities

- **Same core loop:** iterative cycles of lit-search + hypothesis + code-based
  analysis → synthesized report/paper.
- **Shared structured memory / world model** to hold coherence across many agent
  steps — both teams converged on this independently (Paradigm: `knowledge/
  world_model` + evidence graph; Kosmos's headline innovation).
- **Code execution in isolated sandboxes** (Paradigm: Docker `--network=none`;
  Kosmos: gVisor/k8s).
- **Per-claim traceability** to code or primary literature.
- **Domain-agnostic** by design.
- **Human-in-the-loop** is explicit in both.
- Same lineage (Robin, Sakana, Google co-scientist, Virtual Lab).

## 3. Differences

| | **Kosmos** | **Paradigm** |
|---|---|---|
| Starting point | dataset **required** → mine it | question/topic → can **generate** data (synthetic experiments) |
| Output | discovery *reports*, validated by **external humans** | a *paper* through an **internal simulated peer review** (publish/reject) |
| Agents | 2 **general-purpose**, instantiated ~200× in parallel | ~8 **differentiated roles** that **debate** |
| Structure from | world-model coordination + massive parallelism | **deterministic Python phase state-machine** + role specialization |
| Scale | ~200 rollouts, 42k LOC, 1,500 papers, 12 h | handful of agents × few rounds, ~tens of min |
| Infra | k8s, gVisor, JuiceFS, warm pools, GPUs, on-prem | single VM, SQLite + ChromaDB |
| Validation | external expert scoring + memorization control | built-in peer-review gate |

**One-liner:** Kosmos is an autonomous **data scientist** (analyze this dataset like
an expert, at scale). Paradigm is a simulated **research lab + journal** (form
hypotheses, run experiments, write **and peer-review** a paper). Kosmos analyzes
existing data; Paradigm generates and tests.

---

## 4. The key insight

**Kosmos's worst metric is Paradigm's thesis.** Their 57% interpretation score +
"no automated way to tell valuable from merely-correct" is **exactly** the
conclusion of our own parallel-branch spike (`.planning/PARALLEL-BRANCHES.md`):
**taste / selection — not more compute — is the bottleneck.** Two independent teams,
very different scales, the same wall.

And **Paradigm already has the mechanism Kosmos lacks**: a peer-review pipeline
(skeptic + reviewers + editor) that is a latent *significance selector*. Kosmos
offloads "is this valuable?" to human experts; Paradigm bakes it in.

Corollary that refines our own finding: Kosmos's findings **scale linearly with
cycles** because each cycle explores **new data-analysis tasks over a large external
dataset** — real breadth. Our spike found ideation branching *doesn't* pay because
"breadth" there was reworded framings. So the parallelism that works is **branching
over data-analysis tasks on a real dataset**, not over question framings.

---

## 5. What to borrow — prioritized

Ranked by (leverage ÷ effort), playing to Paradigm's strengths.

1. **Make peer review the *significance* selector, not just a quality gate.**
   *High leverage, medium effort.* Have reviewers/editor score **significance +
   novelty** (not only correctness), and surface "valuable vs merely-correct." This
   is the taste layer both our spike and Kosmos point to — and Paradigm is uniquely
   positioned because the journal already exists. **Our strongest differentiator.**

2. **Adopt their evaluation methodology.** *Medium effort, high credibility.*
   Extend `scripts/selftest.py` / the eval harness into: blind **Supported/Refuted**
   statement scoring **by type** (analysis / lit-review / interpretation), an
   **expert-time-saved** estimate, novelty/depth ratings, and a **memorization
   control** (run on a withheld / post-cutoff finding to prove reasoning, not
   recall). Gives Paradigm a real accuracy number it currently lacks. The
   memorization control is cheap and credibility-critical.

3. **Per-claim → code/notebook provenance.** *Medium effort, high credibility.*
   Link each *quantitative claim* in the paper to the specific experiment/notebook
   that produced it ("click any number → see the code"). We have the pieces
   (Execution Fact Sheet, figure provenance); close the loop.

4. **World-model-as-task-proposer.** *Medium-high effort.* Kosmos updates the world
   model with task summaries each cycle and **queries it to propose the next cycle's
   tasks**. Paradigm's world model is more a knowledge graph; making it also a
   queried planner (world model → next experiments/searches) would tighten the loop.

5. **Data-driven branching (the parallelism that actually works).** *Higher effort
   — ties to a broader capability gap.* Branch over **data-analysis tasks on a real
   dataset**, not ideation framings. Requires Paradigm to **ingest real datasets**
   (its biggest gap vs Kosmos, which is dataset-first). Worth it only alongside a
   real "bring your own dataset" capability.

6. **Code-as-universal-tool, earlier.** *Lower effort.* Kosmos's analysis IS
   code-writing (42k LOC/run). Let Paradigm agents write exploratory analysis code
   in ideation/planning, not only in the execution phase.

7. *(If/when targeting real labs)* **on-prem / data-privacy deployment** (minimal
   egress, credential injection). Out of scope for the current public-demo posture.

---

## 6. Take / positioning

Kosmos is ahead on **scale, infra maturity, and eval rigor** (79.4% accuracy,
expert-months, Nature-grade validation) — don't try to out-scale the 200-rollout
marathon. But the systems optimize different things, and Paradigm points straight at
Kosmos's weakest spot. Kosmos is a phenomenal hypothesis-*generator / data-miner*
that admits it can't tell valuable from correct. Paradigm is a hypothesis-*tester +
peer-reviewer*.

**They're the better engine; Paradigm can be the better referee.** "Telling good
science from plausible-but-trivial science" is — by both their admission and our own
experiment — the actual frontier. Lean into the taste/validation layer (items 1–3),
and pursue breadth only in the form Kosmos validated (item 5, data-driven).
