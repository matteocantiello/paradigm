# External Research Synthesis & Development Directions for Paradigm

**Date:** 2026-06-03
**Author:** Prepared from a fan-out reading of 15 external sources supplied by the operator, cross-referenced against Paradigm's current codebase (`src/paradigm/`), the competitive landscape analysis, and the known operational pain points (≈38% of runs end in `writing_failed`, ≈65% token waste, weak systematic evaluation, output-quality variability; live DB: 14 published / 24 rejected / 24 writing_failed / 189 external papers).
**Purpose:** Distill what is transferable to Paradigm from the current AI-for-science frontier, then lay out concrete, prioritized development directions tied to specific modules.

> **How to read this:** §1 is a source-by-source reference table with access status. §2 is the thematic synthesis (the patterns that recur across sources). §3 is the core deliverable — detailed, prioritized development directions, each tied to a Paradigm module. §4 is a phased roadmap. §5 covers strategic positioning (human-in-the-loop / scarcity). §6 lists provenance caveats.

---

## 1. Sources Read (with access status)

| # | Source | What it is | Access |
|---|--------|-----------|--------|
| 1 | [Auto-claude-code-research-in-sleep (ARIS)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) | Markdown-only autonomous-research skill library for Claude Code; adversarial cross-model review "while you sleep" (~11k★, actively maintained) | ✅ README + skill files |
| 2 | [Anthropic Claude "Operon"](https://www.testingcatalog.com/anthropic-tests-claude-operon-for-scientific-research-in-biology/) | Leaked/early desktop app mode for computational biology (persistent projects, local data, Plan/Auto) | ✅ read (pre-release, medium credibility) |
| 3 | [Sakana AI Scientist — Nature](https://sakana.ai/ai-scientist-nature/) | First AI-generated paper to pass workshop peer review (v2, ICLR ICBINB) | ✅ via announcement + mirrors |
| 4 | [The AI Scientist (v1)](https://arxiv.org/abs/2408.06292) | End-to-end automated ML research pipeline; idea→code→write→auto-review | ✅ abstract + v2 + independent critique |
| 5 | [OpenGauss / Gauss (Math.inc)](https://github.com/math-inc/OpenGauss) | Autoformalization agent for Lean 4; verification-as-ground-truth; thousands of parallel agents | ✅ README + Math.inc pages |
| 6 | [AlphaXiv MCP (Pento writeup)](https://www.pento.ai/blog/research-paper-to-production) | Hosted MCP server exposing arXiv corpus + AI breakdowns + paper-linked GitHub repo reading | ✅ read |
| 7 | [AI Can Learn Scientific Taste](https://www.alphaxiv.org/abs/2603.14473) | RLCF: train a "scientific taste" judge from citation-pair preferences; win-rate reward | ✅ via arXiv HTML mirror (alphaxiv 403'd) |
| 8 | [Self-evolving Agent Skills (SkillOpt)](https://arxiv.org/abs/2605.23904) | Text-space optimizer for agent skills with a held-out gate; "gradient descent on prompts" | ✅ abstract + PDF pp.1–10 |
| 9 | [Why AI cannot do good science without humans — Nature](https://www.nature.com/articles/d41586-026-01551-3) | Editorial: empowerment-not-replacement; enumerates irreplaceable human roles | ✅ read |
| 10 | [Claude 101 for academia (Mushtaq Bilal)](https://x.com/MushtaqBilalPhD/status/2052338632426467550) | Practitioner workflows: file-grounded research assistant, project memory, skills | ⚠️ X 402'd; reconstructed from his LinkedIn long-form + search |
| 11 | [Accelerating scientific research with Gemini](https://arxiv.org/abs/2602.03837) | Human+Gemini-Deep-Think case studies; adversarial-reviewer + neuro-symbolic verify (**not** the Co-Scientist paper) | ✅ abstract |
| 12 | [What will be scarce? (Alex Imas)](https://aleximas.substack.com/p/what-will-be-scarce) | Economics of scarcity under cheap AI: relational goods, provenance, taste, trust appreciate | ✅ read |
| 13 | [Paperclip (literature MCP)](https://paperclip.gxl.ai/) | Agent-first literature CLI + hosted MCP; papers-as-filesystem; map/reduce; stateful `--from` | ⚠️ site 403'd; covered via authoritative GitHub README |
| 14 | [Paperclip CLI blog](https://gxl.ai/blog/paperclip) | Design philosophy: stateful search, filesystem-as-API, git-like paper collections | ⚠️ 403'd; reconstructed from README + search |
| 15 | [A new consciousness of mathematics](https://apoorvapanidapu.substack.com/p/a-new-consciousness-of-mathematics) | Generation/verification are being automated; **digestion** (human understanding) + taste become the bottleneck | ✅ read |

> Two additional anchor papers surfaced during reading and are referenced below because they are the actual technical sources behind two of the links: **Google DeepMind "AI co-scientist"** (arXiv:2502.18864 — the Elo tournament / generate-debate-evolve system, lab-validated in *Nature*, May 2026) and **AI Scientist v2** (arXiv:2504.08066 — the tree-search experiment manager behind the Nature milestone).

---

## 2. Thematic Synthesis

Across very different modalities (ML automation, formal math, literature tooling, economics, editorial opinion), seven patterns recur. They are the lens for §3.

### Theme A — Verification is the moat; build a "kernel" even when you have no kernel
Gauss eliminates hallucination structurally: the model may reason/hallucinate freely during search, but **nothing enters the output unless the Lean kernel re-checks it** (the de Bruijn criterion). This is *why* it can run thousands of agents and trust the survivors. The AI Scientist's worst, most-cited failures are the mirror image: hallucinated citations, fabricated numbers, ~57% train/test overlap, "Conclusions Here" placeholder text shipped to reviewers, and a reviewer self-rating 2/5 confidence. The math-consciousness essay adds the crucial caveat: even a perfect kernel only certifies *the proof*, not *that you asked the right question* (the statement-vs-intent gap → semantic hallucination).

**For Paradigm:** empirical/computational science has no Lean kernel, so it must **manufacture proxy kernels**: deterministic re-execution, symbolic checks (sympy), unit/dimensional checks, and pre-registered falsifiable predictions. This is the single highest-leverage theme — it attacks the no-paper rate, the quality variability, *and* the trust/credibility problem at once.

### Theme B — Selecting the right idea ("taste") is the real work, and it is learnable
"AI Can Learn Scientific Taste" shows a small generative judge (Qwen3-4B/30B), trained on citation-matched preference pairs, **out-ranks GPT-5.2/Gemini-3 on idea quality (80.6% vs 72–76%)** and transfers across fields and to peer-review prediction (79%). DeepMind's Co-Scientist operationalizes the same instinct as an **Elo tournament** where pairwise *debates* decide rankings, and crucially shows **Elo correlates with real answer quality (GPQA concordance)** — so a self-generated rating is a trustworthy stopping signal. The math essay independently argues taste/problem-selection is the scarce, valuable act that benchmarks don't measure.

**For Paradigm:** it already has `knowledge/hypothesis_tournament.py` + `orchestrator/debate.py`. The gap is a *taste signal* to adjudicate matches and a *calibration* against its own real outcomes (published vs rejected).

### Theme C — Self-improvement must be reproducible (gated), not vibes-based
SkillOpt reframes skill text as the "external state of a frozen agent" and optimizes it like weights: **bounded edits (a learning rate), proposed by a separate optimizer model from success/failure minibatches, accepted only if they beat a held-out selection split**, with a **rejected-edit buffer** (negative feedback at zero deployment cost) and an epoch-wise **meta-skill**. Ablations show the held-out gate and meta-skill are load-bearing (+22 pts). ARIS adds the operational version: "failed ideas become anti-repetition memory."

**For Paradigm:** its end-of-cycle reflection currently accretes 3–5 free-text episodic memories per agent — improvement with no gate and no negative feedback. The reputation system and skeptic/reviewer scores are *exactly the selection metric SkillOpt needs* but aren't wired as an optimization gate.

### Theme D — Adversarial robustness needs a *different* judge, and autonomy needs guardrails
ARIS's core principle: **"a loop can DRIVE but it cannot ACQUIT"** — execution-completeness is self-judged, but correctness/quality verdicts must come from a *different model family* (or at minimum a fresh, context-isolated thread) under a strict **reviewer-independence protocol** (no "we fixed X since last round," only the current artifact is admissible). Its `/kill-argument` test has one thread write the harshest area-chair rejection and an independent adjudicator classify each point answered/partial/unresolved with file:line evidence — catching the failure that local checks miss: *every component is correct but the paper oversells*. For unattended runs: **bounded internal rounds (not cron loops), recovery checkpoints, an edit-whitelist (forbidden ops like new-citation/new-number), GAP_REPORT markers instead of fabrication.** Nature reinforces this from the opposite side: AI cannot reliably catch its own errors, so an all-AI review loop inherits the same blind spots.

**For Paradigm:** the skeptic agent is currently *another Claude agent* — same-model blind spots. Hardening it into a cross-model red-team is cheap and high-impact.

### Theme E — Execution robustness comes from tree search + stage budgets, not a linear loop
AI Scientist v2's headline fix was replacing v1's brittle linear loop with a **4-stage agentic tree search** (prototype → tune → agenda → ablation) driven by an **Experiment Progress Manager**: best-first over non-buggy nodes, with a fixed probability of *picking a buggy node to debug*, per-stage budgets and stopping criteria, multiple seed replications, and **VLM figure checks** + length-aware reflection that killed the embarrassing format defects. The independent critique of v1 measured a ~50% experiment-failure rate and trivial code deltas — i.e., linear loops barely change the code before giving up.

**For Paradigm:** `orchestrator/experimentation.py` is a linear propose→execute→analyze→retry loop with a circuit breaker — structurally v1, which is structurally where the 38% `writing_failed` comes from.

### Theme F — The agent-native interface to literature is MCP, and papers should be served pre-digested
Both alphaXiv and Paperclip converged on **hosted HTTP MCP** as the integration surface, and on **not dumping raw PDFs**: alphaXiv's `get_paper_content` returns an *LLM-optimized structured breakdown by default*; Paperclip models **every paper as a directory** (`/papers/<id>/content.lines` with stable `L<n>` citation anchors, `sections/`, `figures/`) and adds `map`/`reduce` (parallel per-paper reads → synthesis), **stateful `--from`** narrowing, git-like paper collections with BibTeX/RIS export, and **paper-linked GitHub repo reading** (the missing bridge from paper → runnable code).

**For Paradigm:** it has a rich in-house literature service (`literature/` with arXiv/bioRxiv/PubMed/ADS/S2/Perplexity + novelty + citation_chains + corpus) but **exposes nothing as MCP** and has **no paper→repo reproduction path** feeding the sandbox. This is both an interop opportunity (let external agents query Paradigm) and a capability gap (let Paradigm consume external corpora + reproduce code).

### Theme G — Humans stay at the gates; throughput is the wrong goal
Nature enumerates the irreplaceable human roles: **problem framing, hypothesis prioritization, output verification (fabrication/misinterpretation), data-use appropriateness, ethics, learning-from-failure**. Imas's economics says it sharply: when AI makes cognition cheap, *AI-reproducible output is intrinsically non-scarce and gets devalued* (humans paid a 44% premium for human-made art vs only 21% for AI art) — what appreciates is **taste, judgment/verification (the trust stamp), provenance/accountability, and curation**, because human involvement there is a *complement* to AI, not a substitute. Bilal's practitioner workflows independently land on the same boundary ("outsource your labor, not your thinking; AI is a research assistant, not a supervisor"). Operon's product shape (persistent project workspace, durable system prompt, local data, Plan vs Auto modes) is what real adoption looks like — and notably Anthropic is *not* building the autonomous research→write→peer-review→reputation loop, leaving that as Paradigm's differentiation.

**For Paradigm:** its `InterventionHook` (continue/pause/abort) is the right primitive but is optional; the strategic move is to make a few human gates *mandatory* and to reframe success metrics from volume to insight + verified-reproducibility.

---

## 3. Development Directions (detailed, prioritized)

Each direction lists: **why** (sources), **what to build**, **where** (modules), **effort**, and **risks**. Priority tiers reflect leverage against the known pain points.

---

### TIER 1 — Fixes the core failure modes (do these first)

#### D1. A "Verification Kernel" — re-execution + checkers as a hard publication gate
**Why:** Theme A (Gauss de Bruijn discipline; AI Scientist hallucination failures; math essay statement-vs-intent gap). This is the master fix for quality variability *and* credibility.
**What to build:**
1. **Deterministic re-execution gate.** Before a result can be written into a paper, re-run its generating code from committed code+data+seed in a clean `--network=none` container and assert the reported number reproduces within a stored tolerance. Treat re-execution as Paradigm's kernel: agents may explore freely, but only reproduced results are "accepted."
2. **Cheap checker battery** run by the skeptic/analyst as *executable* assertions (not prose): sympy symbolic re-derivation of analytic claims; dimensional/unit consistency (`pint`); sanity invariants (conservation laws, limiting cases, monotonicity, error-bar plausibility); train/test leakage detection (the v2 audit found ~57% overlap).
3. **Claim blueprint DAG with `sorry`-style placeholders.** Decompose each paper into a DAG of atomic, individually-checkable claims; unverified ones are explicit `sorry` markers; **publication is blocked while any `sorry` remains**, and a `#print axioms`-equivalent audit lists what's still unbacked. (Mirrors Lean blueprint/sorry decomposition.)
4. **Anti-fabrication lint** before submission: ban hallucinated citations (every `\cite` must resolve in the corpus/literature service), ban new numeric claims not traceable to an executed artifact, and scan for placeholder strings ("Conclusions Here", "TODO", `DATA_NEEDED`).
**Where:** new `orchestrator/verification.py` gate invoked between WRITING→SUBMISSION; extend `sandbox/` for re-run-from-artifact; new checker hooks in `knowledge/conflict_detection.py`; `journal/review.py` consumes the verification report; `storage/` persists the claim DAG + verification status per paper.
**Effort:** L (multi-week), but highest ROI. Ship incrementally: start with citation-resolution + placeholder lint (days), then numeric-traceability, then full re-execution.
**Risks:** re-execution cost (mitigate with caching + only re-running claims that reach the paper); tolerance tuning; not all claims are mechanically checkable (that's what the `sorry`/digestion gate is for).

#### D2. Tree-search execution with an Experiment Progress Manager
**Why:** Theme E (AI Scientist v2 tree search; v1's ~50% experiment-failure). Directly targets the 38% `writing_failed`.
**What to build:** Replace the linear execution loop with a **best-first tree** over Docker runs, managed by a stage machine: Stage 1 prototype (stop when it runs) → Stage 2 tune (stop at convergence) → Stage 3 agenda (run to budget; increase complexity if finishing early) → Stage 4 ablation. Each node carries {plan, code, error trace, metrics, evaluator feedback, figure paths, status: buggy/non-buggy}. Best-first over non-buggy nodes by an LLM evaluator, **with a fixed probability of selecting a buggy node to debug** (cheap failed-run recovery). Launch multiple seed replications per stage for mean±std. Per-stage compute/token budgets with explicit stopping criteria.
**Where:** rewrite `orchestrator/experimentation.py` around a node/tree model; reuse `orchestrator/scheduler.py` for parallel node execution; `sandbox/` runs nodes; checkpoint each stage's best node via `storage/checkpoints`.
**Effort:** L. **Risks:** orchestration complexity (keep the tree logic in plain Python per the DECISIONS constraint); parallel Docker resource limits.

#### D3. Held-out evaluation harness + calibrate the reviewer against real outcomes
**Why:** Themes B & C (SkillOpt's held-out gate; taste paper's position-swap hygiene; AI Scientist's reviewer validated at balanced-acc 0.65/F1 0.57 against real ICLR decisions). Paradigm's pain point #2 ("weak evaluation") and a prerequisite for D4/D5.
**What to build:**
1. A **frozen seed set** of research prompts with known-good expected outcomes; split into train / selection / test (test locked until final report).
2. A repeatable **scorer** producing per-cycle metrics: paper-yield (no-paper rate), cost/paper + tokens/paper, reviewer score, reproduction pass-rate, novelty verdict accuracy.
3. **Calibrate the editor/reviewer agent**: benchmark it against the real DB outcomes (14 published / 24 rejected) — does its accept/reject predict the historical decision? Report balanced-accuracy/F1; correct the documented conservative ("reject everything") bias. Ensemble multiple reviews + self-reflection (the v1 recipe).
4. Mandatory **position-swap + order-randomization** for every LLM-as-judge call (kills first-option bias).
**Where:** new `tests/eval/` harness + `eval/` module; consumes `logging/events.py`, `storage/database`; reuses `journal/review.py`.
**Effort:** M. **Risks:** small ground-truth set (38 decided papers) — supplement with held-out external peer-review labels.

#### D4. Cross-model adversarial review + `/kill-argument` phase
**Why:** Theme D (ARIS "a loop cannot acquit"; Nature "AI can't catch its own errors").
**What to build:**
1. Route final quality verdicts through a **different model family** (or, minimally, a fresh context-isolated thread on a different provider) under the **reviewer-independence protocol**: the reviewer sees only the current artifact — no "we fixed X," no prior thread IDs, no fix-summaries. Save full prompt/response traces for audit.
2. Add a **`/kill-argument`** step to `journal/`: Thread 1 writes the strongest possible rejection memo; an *independent* adjudicator classifies each point answered/partial/unresolved with file:line evidence. Detect-only/non-blocking; surfaces the "everything checks out but the paper oversells" failure.
**Where:** `agents/providers.py` already supports multi-provider routing — use it to assign the skeptic/reviewer a different provider; new `orchestrator/review.py` / `journal/review.py` step; traces to `logging/`.
**Effort:** M. **Risks:** cost/latency of a second model (gate behind the assurance level — only for submission-grade runs).

---

### TIER 2 — Compounding quality & efficiency

#### D5. A trained "scientific taste" judge wired into the hypothesis tournament
**Why:** Theme B (taste paper RLCF; Co-Scientist Elo). Attacks idea-selection variability and (via early pruning) token waste.
**What to build:**
1. A **`taste_judge`** reward model: start prompted (a generative judge that reasons then picks the higher-impact idea, with position-swap consistency), then optionally fine-tune later using **citation-matched preference pairs** (field- and time-matched, per the paper) mined from Paradigm's corpus + external literature, *and* from Paradigm's own published-vs-rejected outcomes.
2. Make it the **match adjudicator** in `hypothesis_tournament.py`: comparison-based **win-rate-in-group** reward, Elo over the pool starting at 1200, with **tiered debate cost** — multi-turn `debate.py` only for top contenders, single-turn for the rest (big token-waste win), bigger Elo swings on upsets.
3. Use **Elo stabilization as a stopping signal** (justified by the GPQA concordance result): stop generating once top-Elo plateaus.
**Where:** new `knowledge/taste.py`; integrate into `knowledge/hypothesis_tournament.py` + `tournament_handler.py`; `orchestrator/debate.py` provides the arguments.
**Effort:** M (prompted judge) → L (fine-tuned). **Risks:** citations are a lagging/noisy proxy ("sleeping beauties"); never use taste as the *sole* gate — pair with falsifiability (D1) and human selection (D9).

#### D6. A diversity/proximity agent before the tournament
**Why:** Theme B (Co-Scientist's Proximity agent prevents the pool collapsing to near-duplicates; without it, ranking just amplifies one idea family).
**What to build:** A clustering step over generated hypotheses (reuse `literature/embeddings.py` / ChromaDB) that dedups and enforces coverage across distinct idea families before the tournament; feed cluster representatives, not raw candidates, into ranking.
**Where:** new step in IDEATION inside `orchestrator/engine.py`; embeddings from `literature/embeddings.py`.
**Effort:** S. **Risks:** clustering granularity tuning.

#### D7. Reproducible self-improvement: gated skill optimization + self-evolving skill library
**Why:** Theme C (SkillOpt; ARIS anti-repetition memory). Converts Paradigm's ungated reflection into monotonic, auditable improvement.
**What to build:**
1. Upgrade end-of-cycle **reflection → propose-and-test optimizer**: a *separate optimizer Claude call* turns scored thread outcomes into **bounded add/delete/replace edits** to each agent's prompt/skill doc, **accepted only if they beat the D3 held-out score** (ties rejected). Keep edits compact (a "learning rate" cap, cosine-decayed).
2. Add a **rejected-edit buffer** (the edit tried + the score drop it caused), fed back into the next optimizer call → stops re-proposing known-bad changes at zero deployment cost. Add an epoch-wise **meta-skill** (teacher-only, not shipped) summarizing which edit patterns help/fail across cycles.
3. Make the **142-skill library self-evolving**: track each skill's invocation success rate; run the bounded-edit optimizer on high-traffic skills; **demote/archive skills** whose edits keep getting rejected or whose success stays below threshold (combine SkillOpt's edit-gate with library pruning — tie to the reputation system).
4. Turn the **graveyard into anti-repetition memory**: feed dead hypotheses into ideation so tournaments don't re-propose them.
**Where:** `agents/memory.py` + `orchestrator/memory.py` (reflection → optimizer); `agents/skills.py` (skill metrics + pruning); `storage/graveyard.py` → ideation context in `orchestrator/engine.py`; selection metric from D3.
**Effort:** L. **Risks:** needs the D3 scorer first (hard dependency); rejected-buffer can narrow exploration — keep a small exploration quota.

#### D8. VLM figure-and-format reflection + length-aware writing pass
**Why:** Theme E (v2's VLM checks killed duplicate-appendix-figure, caption↔figure mismatch, over-length defects).
**What to build:** A vision-model pass over generated figures (clear labels/legends, caption↔figure alignment, no duplicate figures between body and appendix); a reflection stage fed the **target length + current compiled length** so the writer self-enforces format; the placeholder lint from D1.
**Where:** `orchestrator/writing.py` reflection stage; figures come from `experimentation`; uses a vision-capable model via `agents/providers.py`.
**Effort:** S–M. **Risks:** vision-model cost (only at submission stage).

---

### TIER 3 — Interop, reach, and capability expansion

#### D9. Expose Paradigm as an MCP server
**Why:** Theme F (alphaXiv + Paperclip converged on hosted MCP as the agent-native interface; competitive analysis flags Paradigm's visibility gap).
**What to build:** An MCP server exposing Paradigm's unique assets so Claude Desktop/Claude Code/other agents can query them: `paradigm_search_corpus`, `paradigm_novelty_check`, `paradigm_citation_chain`, `paradigm_get_paper_content` (serve a **pre-digested LLM-optimized breakdown by default, raw text as fallback** — steal alphaXiv's default), `paradigm_get_thread` / `paradigm_thread_checkpoint` (research threads — unique to Paradigm), `paradigm_bibliography_export` (BibTeX/RIS — steal Paperclip's export).
**Where:** new `backend/mcp/` (the FastAPI backend already exists); wraps `literature/` + `storage/`.
**Effort:** M. **Tension to flag for a human:** CLAUDE.md says "don't add a web server/API until the CLI works end-to-end." An MCP server is arguably the *agent-native* interface and a lighter lift than a full web API — but this is a deliberate decision for the operator, not an autonomous one.

#### D10. Consume external MCP literature servers + paper→repo reproduction
**Why:** Theme F (alphaXiv paper-linked-repo reading is the missing paper→code bridge; Paperclip's biomedical full-text + map/reduce + stateful `--from`).
**What to build:**
1. An **MCP-client adapter** so the orchestrator can route a `[SEARCH: ...]` tag to an external MCP tool (alphaXiv for CS/ML/physics; Paperclip for biomedical/clinical/regulatory) — modeled as **two more providers behind the existing abstraction**, routed by `domain_router.py`. Keep in-house providers as the substrate (don't break offline/single-node posture); results normalized into Paradigm's paper model.
2. **Paper-linked GitHub-repo reading** for the experimentalist agent (alphaXiv's `/`=tree, dir=parallel-fetch, file=contents convention) → pull reference implementations into the sandbox. This is the bridge between `literature/` and `sandbox/`.
3. Structure ingested papers as **line-numbered, section-split text** (Paperclip's `content.lines` + `sections/`) so agents grep/cite by stable `L<n>` anchors (improves `citation_handler.py` grounding); adopt **`map`/`reduce`** (parallel per-paper reads → synthesis) for the novelty/literature stage and **stateful `--from`** for iterative narrowing.
**Where:** new `literature/mcp_provider.py` behind `provider_factory.py`; `literature/domain_router.py` routing; new `sandbox/` repo-ingest path; `citations.py` line-anchor model.
**Effort:** M–L. **Risks:** external servers are hosted/auth-gated/closed — keep them optional/additive so Paradigm stays runnable offline.

#### D11. Falsifiability + pre-registration in ideation/planning (the statement-vs-intent fix)
**Why:** Themes A & B (Gauss statement-vs-intent gap; math essay; reward clean negative results — the accepted v2 paper *was* a negative result).
**What to build:** Before EXECUTION, freeze a machine-readable hypothesis + its **exact falsifiable prediction and decision rule** ("claim holds iff metric X ∈ [a,b] with p<…; else refuted"). Reject (in ideation) any hypothesis lacking a refutation condition. Re-execution (D1) then verifies the *registered* claim; post-hoc redefinition is blocked. **Reward clean negative/refuted results as publishable** — this both raises pass-rate cheaply and kills late-stage wasted runs.
**Where:** `orchestrator/phases.py` PLANNING gate; pre-registration stored in `storage/`; consumed by D1's verification gate; affects `journal/` acceptance criteria.
**Effort:** S–M. **Risks:** rigid decision rules can be gamed — pair with the cross-model reviewer (D4).

#### D12. Safe unattended overnight runs (autonomy guardrails)
**Why:** Theme D (ARIS guardrails; the platform's overnight-run use case already drove the WebSocket keepalive work in Prompt 65).
**What to build:** **Bounded internal rounds** (not wall-clock cron — "a timer produces no new signal"); **recovery checkpoints** recording round/status/timestamp with resume-within-24h (extend existing checkpoint system); an **edit-whitelist** (allowed/forbidden paths, forbidden ops like new-citation/new-number, max-edits-per-round) so unattended runs can't fabricate or run away; **rejections logged, not fatal** (graceful degradation); **GAP_REPORT / `DATA_NEEDED` markers instead of fabrication**.
**Where:** `orchestrator/engine.py` run loop + `storage/checkpoints`; guardrails as config in `configs/`.
**Effort:** M. **Risks:** over-restrictive whitelists block legitimate edits — make them configurable per assurance level.

---

## 4. Phased Roadmap

**Phase A — "Stop the bleeding" (reliability + measurement).** D3 (eval harness) → D1 (verification kernel, incremental) → D2 (tree-search execution) → D8 (figure/format pass). *Outcome:* no-paper rate down, every change measurable, no more fabricated/placeholder output.

**Phase B — "Pick better, judge harder" (quality).** D4 (cross-model review + kill-argument) → D11 (falsifiability/pre-registration) → D5 (taste judge in tournament) → D6 (diversity agent). *Outcome:* fewer-but-better ideas, hardened review, honest negative results count.

**Phase C — "Learn over time" (compounding).** D7 (gated skill optimization + self-evolving library + anti-repetition graveyard) → D12 (safe overnight autonomy). *Outcome:* the system measurably improves cycle-over-cycle.

**Phase D — "Reach & interop."** D9 (expose MCP) → D10 (consume MCP + paper→repo reproduction). *Outcome:* external visibility + a real paper→code capability.

Dependency notes: **D3 is a prerequisite** for D5 and D7 (both need the held-out scorer). D1 underpins D11. D4 strengthens D5/D11.

---

## 5. Strategic Positioning (Theme G — read before building autonomy features)

The strongest cross-source conclusion is a *strategic* one, and it should constrain the build:

- **Make a few human gates mandatory, not optional.** Nature's irreplaceable roles map onto hard gates in the phase machine: (1) **problem selection/framing** as a required human input at SEEDING (not an agent-autonomous step); (2) **hypothesis prioritization** before resource commitment; (3) **output verification** for fabrication/misinterpretation; plus (4) **data-use appropriateness** and (5) **ethics** checks. Paradigm's `InterventionHook` is the right primitive — promote these specific transitions to mandatory hard gates.
- **Do not optimize for paper throughput.** Imas's economics predicts AI-reproducible output is *intrinsically non-scarce and devalued*. Reframe the headline success metric from volume/efficiency to **insight per cycle** and **verified reproducibility**. The internal journal should reward novelty/insight and clean negative results, not count.
- **Make provenance & accountability first-class, legible artifacts.** Every published paper should carry a visible chain: which human framed the problem, which human verified outputs, which agents/skills contributed (with versions), and the full verification report. This satisfies Nature's accountability requirement *and* manufactures the Imas-style provenance value that pure-AI output structurally lacks — turning Paradigm's git-based threads from an implementation detail into the moat.
- **Operator UX = "research assistant, not supervisor"** (Bilal; Operon). Lean toward a persistent project workspace: durable per-project context (a `CLAUDE.md`-style role/standards/critique-style file), inspectable agent memory, reusable skills, literature screening with table outputs + explicit inclusion/exclusion criteria, evidence cross-referencing ("which sources disagree with claim X"), and durable saved artifacts. Operon's **Plan vs Auto** modes map cleanly onto Paradigm's `directed` vs `explore` + the intervention hook.
- **What's defensible:** Anthropic (Operon), Google (Co-Scientist in Gemini Enterprise), and the literature-MCP vendors are *not* building the autonomous research→write→peer-review→reputation loop over git-versioned, verifiable research threads. That loop — **made trustworthy by a verification kernel and legible by provenance** — is Paradigm's differentiation. Build the trust layer (Tier 1) before the autonomy layer (D12).

---

## 6. Provenance Caveats

- **arXiv:2602.03837 is *not* the Google AI Co-Scientist paper.** It is "Accelerating Scientific Research with Gemini: Case Studies and Common Techniques" (human + Gemini-Deep-Think collaborations). The Elo-tournament / generate-debate-evolve design referenced throughout §2–3 is **arXiv:2502.18864** (DeepMind, lab-validated in *Nature*, May 2026). 2602.03837's reusable ideas are its **adversarial-reviewer pass** and a **neuro-symbolic write-and-execute-code verification loop** — both fold into D1/D4.
- **ARIS (source 1)** is a well-engineered community repo (~11k★, active CI) but has **no peer review or empirical eval** — treat its *patterns* as credible, its *efficacy claims* as anecdotal.
- **SkillOpt's results** (source 8) are from the paper itself; not independently corroborated here. The arXiv ID (2605.x) and ARIS run logs reference 2026 events — consistent with the current date.
- **Operon (source 2)** is a pre-release leak (medium credibility) — directionally consistent with Anthropic's public science trajectory but not officially documented.
- **Sources 10, 13, 14** (Bilal X thread, Paperclip site/blog) were access-blocked (402/403) and **reconstructed** from authoritative secondary sources (the project's GitHub README; Bilal's long-form LinkedIn version) — high-fidelity but secondhand.
- **The taste paper's signal is citation-proxied** and its ideas are never experimentally run; never let a taste score be a sole gate.

---

*Compiled 2026-06-03. Sources and access status in §1. This synthesis is intended to feed `.planning/ROADMAP.md` updates and the next development cycle.*
