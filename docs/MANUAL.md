# Paradigm Operations Manual

A comprehensive guide for scientist-operators running Paradigm, the agentic science platform.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Quick Start](#2-quick-start)
3. [CLI Reference](#3-cli-reference)
4. [Domain Profiles](#4-domain-profiles)
5. [Operating Modes](#5-operating-modes)
6. [The Research Cycle](#6-the-research-cycle)
7. [The Agent Team](#7-the-agent-team)
8. [Interactive Mode](#8-interactive-mode)
9. [Multi-Cycle Research](#9-multi-cycle-research)
10. [Literature Search System](#10-literature-search-system)
11. [Configuration Reference](#11-configuration-reference)
12. [Data and Storage](#12-data-and-storage)
13. [Cost Management](#13-cost-management)
14. [Docker Sandbox](#14-docker-sandbox)
15. [Troubleshooting](#15-troubleshooting)
16. [Recipes](#16-recipes)
17. [Terminal Display System](#17-terminal-display-system)
18. [Citation Grounding & Seed Discovery](#18-citation-grounding--seed-discovery)
19. [Novelty Checking](#19-novelty-checking)
20. [Agent Memory & Reflection](#20-agent-memory--reflection)
21. [Web API](#21-web-api)
22. [Correctness Kernel & Output Formats](#22-correctness-kernel--output-formats)

---

## 1. Overview

Paradigm is an agentic science platform where teams of AI agents collaborate to perform research, write papers, and submit them to peer review. Named after Thomas Kuhn, it implements the insight that paradigm shifts emerge from communities of researchers, not individuals.

**The core loop:**
You provide a research question or topic. A team of specialized AI agents (theorist, analyst, synthesizer, experimentalist, writer, skeptic) discuss the topic, search the literature, form a research plan, draft a paper, and submit it to independent peer reviewers (editor, reviewers). Published papers enter an internal corpus where future research cycles can discover and cite them, building an interconnected body of knowledge over time.

**Key properties:**
- **Domain-agnostic** --- pluggable domain profiles adapt agent roles, data sources, and output formats to any field. Built-in domains: science and finance. See [Domain Profiles](#4-domain-profiles).
- **Full pipeline** --- from seed question to published, peer-reviewed paper in the internal corpus.
- **Transparent** --- every agent message, token cost, and phase transition is logged. You can inspect, pause, and steer at any point.
- **Composable** --- agents are equipped with scientific skills from a library of 142 skill definitions that shape their expertise.

---

## 2. Quick Start

### Prerequisites

- Python 3.12+ (via conda/mamba recommended)
- Anthropic API key (for default mode)
- Google Gemini API key (for default mode)
- Together.ai API key (for testing mode)
- Docker (optional, for computational sandbox)

### From zero to first paper in 5 commands

```bash
# 1. Clone and set up environment
git clone https://github.com/matteocantiello/paradigm.git
cd paradigm
conda create -n paradigm python=3.12 -y
conda activate paradigm
pip install -e ".[dev]"

# 2. Set your API keys (or create a .env file)
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="..."

# 3. Run a quick directed research cycle (1 round per phase to minimize cost)
paradigm run --mode directed --prompt "Explain the period-luminosity relation for Cepheids" --rounds 1

# 4. List the papers produced
paradigm papers

# 5. View the paper
paradigm paper <paper-id>
```

The paper is also saved as a markdown file in `data/papers/`.

---

## 3. CLI Reference

All commands are invoked via `paradigm` (or `python -m paradigm`).

### Global Options

```
paradigm [OPTIONS] COMMAND [ARGS]
```

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to configuration YAML file |
| `--version` | Show version and exit |
| `--help` | Show help and exit |

### `paradigm run`

Run a research cycle from seed to (optionally) published paper.

```
paradigm run [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--mode` | Choice | `directed` | Operating mode: `directed`, `explore`, `hypothesis`, `experimental`, `replication`, `review` |
| `--prompt` | Text | --- | Research prompt or question. **Required** for `directed` and `review` modes (unless `--prompt-file` is used). |
| `--prompt-file` | Path | --- | Read research prompt from a file (e.g., `prompt.md`). Mutually exclusive with `--prompt`. |
| `--topic` | Text | --- | Research topic. **Required** for `explore` mode. |
| `--rounds` | Integer | config value (10) | Rounds per phase. Overrides `orchestrator.max_rounds_per_phase`. |
| `--interactive` | Flag | off | Pause for confirmation before each major phase transition. |
| `--network-access` | Flag | off | Allow sandbox containers to access the network (sets `network_mode="bridge"`). See [Network Access Mode](#network-access-mode). |
| `--fresh-corpus` | Flag | off | Start with an empty internal corpus (avoids cross-domain contamination). |
| `--verbose` | Flag | off | Enable verbose logging output. |

**Examples:**

```bash
# Directed research with specific question
paradigm run --mode directed --prompt "What causes the Blazhko effect in RR Lyrae stars?"

# Read a detailed prompt from a file
paradigm run --mode directed --prompt-file prompt.md

# Experimental mode with prompt file
paradigm run --mode experimental --prompt-file prompt.md --rounds 2

# Open-ended exploration
paradigm run --mode explore --topic "massive star variability"

# Hypothesis testing
paradigm run --mode hypothesis --prompt "Period-luminosity relation breaks down for overtone pulsators"

# Quick test (1 round per phase, minimal cost)
paradigm run --mode directed --prompt "Explain stellar convection" --rounds 1

# Interactive mode with human oversight
paradigm run --mode directed --prompt "Dark matter distribution in dwarf galaxies" --interactive

# Fresh corpus (ignore previously published Paradigm papers)
paradigm run --mode directed --prompt "Protein folding mechanisms" --fresh-corpus
```

#### Prompt Files

For complex research prompts that include detailed instructions, paper references, or multi-paragraph descriptions, use `--prompt-file` to read the prompt from a markdown file:

```bash
paradigm run --mode experimental --prompt-file prompt.md --rounds 1
```

The entire file content is used as the seed prompt. This is especially useful for prompts that include URLs to papers, structured instructions, or multi-step research plans that would be unwieldy as a command-line argument.

**PDF ingestion from URLs:** Any URLs in the prompt pointing to PDF files are automatically fetched, extracted, and ingested into the local corpus during the SEEDING phase. Supported sources include arXiv, A&A (aanda.org), Nature, IOP Science (ApJ, ApJS, MNRAS), and most other journal sites that serve direct PDF links. Sites with aggressive bot protection (e.g., TLS fingerprinting) are handled via a curl fallback.

### `paradigm status`

Show system statistics (total token usage).

```bash
paradigm status
```

Output:
```
System Status:
  Total tokens used: 380,412
  Input tokens: 312,100
  Output tokens: 68,312
```

### `paradigm inspect`

Inspect a research thread's checkpoint (state, participants, findings, next steps).

```
paradigm inspect --thread THREAD_ID
```

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `--thread` | Text | Yes | Thread ID to inspect (e.g., `thread-9a80e2395c85`) |

**Example:**

```bash
paradigm inspect --thread thread-9a80e2395c85
```

### `paradigm papers`

List papers in the system.

```
paradigm papers [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--status` | Choice | all | Filter: `draft`, `submitted`, `in_review`, `published`, `rejected` |
| `--limit` | Integer | 10 | Maximum papers to show |

**Examples:**

```bash
# List all papers
paradigm papers

# Show only published papers
paradigm papers --status published

# Show last 5 papers
paradigm papers --limit 5
```

Output:
```
ID                        Status       Title
--------------------------------------------------------------------------------
paper-cfda5f7cd61b        published    Enhanced Convective Overshooting in Ma...
paper-a1b2c3d4e5f6        rejected     Preliminary Study of Variable Stars...
```

### `paradigm paper`

View or export a specific paper.

```
paradigm paper PAPER_ID [OPTIONS]
```

| Option | Type | Description |
|--------|------|-------------|
| `--export PATH` | Path | Export paper to a markdown file |

**Examples:**

```bash
# View paper in terminal
paradigm paper paper-cfda5f7cd61b

# Export to file
paradigm paper paper-cfda5f7cd61b --export my-paper.md
```

Output:
```
Title:    Enhanced Convective Overshooting in Massive Stars
Status:   published
Authors:  theorist-0, analyst-1, synthesizer-2, skeptic-3, writer-4, editor-5
Created:  2026-02-12T15:30:00
--------------------------------------------------------------------------------
# Enhanced Convective Overshooting in Massive Stars
...
```

---

## 4. Domain Profiles

Paradigm uses a pluggable **domain profile** system that adapts the entire research pipeline --- agent roles, research modes, document template, review criteria, and literature sources --- to different fields.

### Available Domains

| Domain | Config File | Description |
|--------|-------------|-------------|
| **science** (default) | `configs/default.yaml` | Academic science research with arXiv and Semantic Scholar. Agents: theorist, analyst, synthesizer, skeptic, experimentalist, writer, editor. Output: academic paper. |
| **finance** | `configs/finance.yaml` | Financial research with SSRN, SEC EDGAR, FRED, and Semantic Scholar. Agents: economist, quant, strategist, risk_analyst, experimentalist, writer, editor, reviewer. Output: research report. |

### Switching Domains

Set the `domain` key in your config file:

```yaml
# configs/finance.yaml
domain: finance
mode: directed
```

Then pass the config to the CLI:

```bash
paradigm run --config configs/finance.yaml --prompt "Analyze the yield curve inversion as a recession predictor"
```

If no `domain` key is set, Paradigm defaults to `science`.

### What Changes Per Domain

Each domain defines its own:

- **Agent roles** --- different personas with domain-specific expertise
- **Research modes** --- different team compositions for different investigation styles
- **Document template** --- different output sections (e.g., "executive summary" vs "abstract")
- **Review criteria** --- different scoring dimensions for peer review
- **Source providers** --- different literature and data sources
- **Sandbox environment** --- different pre-installed Python packages

For full details on each domain's configuration, see [docs/DOMAINS.md](DOMAINS.md).

---

## 5. Operating Modes

Each mode assembles a different team and provides mode-specific prompts that shape how agents approach the research.

### `directed` (default)

**Purpose:** Answer a specific research question.

**Team:** theorist, analyst, synthesizer, skeptic, writer, editor

**When to use:** You have a clear question and want a focused investigation with a definitive answer or model.

```bash
paradigm run --mode directed --prompt "What is the mass-loss rate for Wolf-Rayet stars?"
```

### `explore`

**Purpose:** Survey a broad topic, identify open questions and unexplored connections.

**Team:** theorist, analyst, synthesizer, skeptic, writer, editor

**When to use:** You want to understand the landscape of a field, find research gaps, or generate ideas for future work.

**Special behavior:** The ideation prompt instructs agents to survey broadly, identify open questions, unexplored connections between subfields, and propose 2-3 diverse research directions.

```bash
paradigm run --mode explore --topic "massive star variability"
```

### `hypothesis`

**Purpose:** Formulate and test precise, falsifiable hypotheses.

**Team:** theorist, skeptic, analyst, writer, editor

**When to use:** You have a specific claim to evaluate rigorously. The skeptic plays a prominent role.

**Special behavior:** Agents focus on stating hypotheses clearly, describing confirming/refuting evidence, identifying confounders, and proposing the simplest possible tests.

```bash
paradigm run --mode hypothesis --prompt "Convective overshooting extends main sequence lifetime by >15%"
```

### `experimental`

**Purpose:** Design and execute computational experiments.

**Team:** experimentalist, analyst, theorist, writer, editor

**When to use:** The research question is best answered by running simulations or data analysis in the Docker sandbox.

```bash
paradigm run --mode experimental --prompt "Simulate p-mode oscillations in a 1.5 solar mass star"
```

### `replication`

**Purpose:** Reproduce and verify existing results.

**Team:** analyst, experimentalist, skeptic, writer, editor

**When to use:** You want to independently verify a published claim.

```bash
paradigm run --mode replication --prompt "Replicate the period-luminosity relation from Leavitt 1912"
```

### `review`

**Purpose:** Produce a comprehensive literature review and field synthesis.

**Team:** theorist, synthesizer, skeptic, writer, editor

**When to use:** You want to survey and synthesize existing work on a topic without running computational experiments. The output is a literature review paper with sections for landscape overview, thematic analysis, critical assessment, and future directions.

**Special behavior:** The team has no experimentalist or analyst — the EXECUTION phase is skipped entirely. Prompts are tailored for systematic literature gathering, thematic organization, and critical synthesis. The document template uses literature-review-specific sections instead of methods/results.

```bash
paradigm run --mode review --prompt "Survey recent advances in asteroseismology of red giants"
```

---

## 6. The Research Cycle

Every research cycle progresses through a series of phases. The orchestrator manages transitions, and each phase has specific agents, prompts, and outputs.

### Phase Flow

```
SEEDING
   |
IDEATION  (N rounds of structured agent discussion)
   |
PLANNING  (N rounds of research plan development)
   |
   +--[experimentalist on team + sandbox enabled]--+   (skipped in review mode)
   |                                               |
   |                                         EXECUTION
   |                                         (propose code, run in Docker,
   |                                          retry on failure, collect results)
   |                                               |
   |                                       POST_EXECUTION
   |                                       (team interprets results, flags
   |                                        limitations, agrees on conclusions)
   |                                               |
   +-----------------------------------------------+
   |
WRITING   (section drafting -> assembly -> optional refinement)
   |        (execution results + caveats injected into RESULTS/METHODS sections)
   |
   +--[enable_reflection]-- PI REFLECTION (verdict on the draft)
   |        |    proceed / call_it -> continue below
   |        |    loop_back -> EXECUTION or PLANNING with directives,
   |        |                 then back through WRITING (max_loop_backs budget)
   |        +---------------------------------------------------+
   |
INTERNAL_REVIEW  (editor reviews, writer revises if needed)
   |
SUBMITTED  (desk review by editor-in-chief)
   |              |
   |         [desk reject] -> REJECTED
   |
PEER_REVIEW  (independent reviewers score and evaluate)
   |              |
   |         [reject] -> REJECTED
   |              |
   |         [revision needed]
   |              |
   |          REVISION -> back to PEER_REVIEW (up to max_revision_rounds)
   |
PUBLISHED  (paper enters internal corpus)
```

### Phase Details

#### SEEDING

The orchestrator initializes a research thread, creates a unique thread ID, and registers the agent team. If the seed prompt contains URLs to papers (e.g., A&A, Nature, IOP Science PDFs), the orchestrator fetches and ingests them into the local corpus as external papers. It also searches the graveyard for lessons from past failed or rejected research related to the seed prompt.

If **Perplexity seed discovery** is enabled (`citation.enable_seed_discovery: true`), the orchestrator queries the Perplexity API to discover foundational papers on the seed topic and pre-populates the literature corpus before agents begin. This gives agents a head start on relevant literature without consuming their search budgets. See [Citation Grounding & Seed Discovery](#18-citation-grounding--seed-discovery) for details.

Literature search is **not** performed during seeding — instead, agents drive their own literature searches during deliberation phases (see [Agent-Driven Literature Search](#agent-driven-literature-search) below).

**Input:** Seed prompt + mode
**Output:** Thread ID, ingested external papers (if URLs present), graveyard context (if any), seed-discovered papers (if Perplexity enabled)
**Agents:** None (orchestrator-only)

#### Agent-Driven Literature Search

Rather than sending the raw prompt to arXiv (which fails on long prompts), agents request literature searches themselves by writing `[SEARCH: query]` markers in their responses — the same text-parsing pattern used for code execution via fenced Python blocks.

The orchestrator parses these markers, executes searches via `corpus.search()` (which queries both the local ChromaDB and arXiv API), formats the results, and appends them to an accumulated literature context. This context is included in all subsequent agent prompts, growing throughout the research cycle.

**Search-enabled phases:** IDEATION, PLANNING, EXECUTION, WRITING, INTERNAL_REVIEW, PEER_REVIEW, REVISION.

**Budget:** Each round allows up to `max_searches_per_round` (default: 3) search requests to prevent runaway API costs. The counter resets at the start of each round.

**Example agent output:**
```
Based on the discussion, I'd like to look into the metallicity dependence:
[SEARCH: Cepheid period-luminosity relation metallicity dependence]

I also want to check recent asteroseismology results:
[SEARCH: delta Scuti asteroseismology mixed modes]
```

#### IDEATION

Agents propose and debate hypotheses through structured discussion rounds. In round 1, each agent proposes 1-2 concrete, testable hypotheses. If lessons from past failed research were found during seeding, they are also included in the round 1 prompt, clearly marked as non-citable context. In later rounds, agents critique, build on, and prioritize ideas. Agents may request literature searches at any time via `[SEARCH: query]` markers.

**Input:** Seed prompt + graveyard lessons (if any) + accumulated literature context
**Output:** Refined set of hypotheses
**Agents:** Full team in round-robin order
**Rounds:** Configurable via `max_rounds_per_phase` (default: 10)

#### PLANNING

Agents develop a concrete research plan: experiments to run, data needs, success criteria, potential pitfalls. In later rounds they refine the plan, challenge assumptions, and identify dependencies.

**Input:** Ideation checkpoint
**Output:** Actionable research plan
**Agents:** Full team
**Rounds:** Same as ideation

#### EXECUTION (conditional)

Runs only when all three conditions are met: `enable_experimentation` is `true`, the Docker sandbox is enabled, and an `experimentalist` agent is on the team (i.e., `experimental` or `replication` mode). Otherwise this phase is skipped automatically.

Agents propose Python code in fenced ` ```python ` blocks with a `# EXPERIMENT: name` header comment. The orchestrator extracts and executes each block in the Docker sandbox.

**Loop** (up to `max_experiment_rounds` rounds):
1. Round 1: the experimentalist proposes initial experiments based on the research plan.
2. Round 2+: the agent reviews previous results and either proposes follow-up experiments or signals completion (by responding without code blocks).
3. Each code block is safety-scanned, then executed in Docker. If the code is rejected by the safety scanner or fails at runtime, the agent receives error feedback and can retry (up to 2 retries per experiment, for a maximum of 3 total attempts).
4. **Vacuous execution detection:** If an experiment exits successfully but produces no meaningful output (no output files AND stdout is empty or dominated by error-like messages such as "file not found" or "no data available"), it is treated as a failure and triggers a retry with error feedback. This prevents experiments that silently do nothing from being accepted as results.

**Available libraries:** NumPy, SciPy, Matplotlib, Pandas, scikit-learn, SymPy, Astropy.

**Safety constraints:** No `os`, `subprocess`, `open()`, network calls, or sandbox escape patterns. Code is scanned via AST analysis before execution.

**Output files:** Figures saved as `.png` or `.pdf` by the experiment code are tracked and later copied to a `figures/` subdirectory alongside the paper markdown.

**Input:** Planning checkpoint
**Output:** Execution context (formatted results + figure paths), injected into WRITING phase
**Agents:** Experimentalist (fallback to analyst)
**Rounds:** Configurable via `max_experiment_rounds` (default: 2 × `max_rounds_per_phase`)

#### POST_EXECUTION (conditional)

Runs automatically after EXECUTION when experiments produced results and `enable_post_execution_discussion` is `true` (default). The research team reconvenes to interpret findings before writing begins.

**Purpose:** Prevent experimental results — especially synthetic data or results with significant limitations — from being presented as authoritative in the paper. The team discusses what the evidence actually shows, flags limitations, and agrees on what claims the paper can support.

**Caveats propagation:** During EXECUTION, structured caveats are automatically collected for conditions like:
- All experiments used synthetic/simulated data (no observational data in sandbox)
- Circuit breaker fired (>70% failure rate)
- Network errors (sandbox has no internet access)
- Experiment timeouts
- Vacuous successes (experiments that produced no meaningful output)

These caveats are injected into both the POST_EXECUTION discussion prompts and the WRITING phase prompts, ensuring writing agents acknowledge limitations.

**Input:** Execution results + caveats + planning checkpoint + literature context
**Output:** Team consensus on what results mean, limitations to acknowledge
**Agents:** Theorist, analyst, synthesizer, skeptic, experimentalist
**Rounds:** Up to 2 (capped)

#### WRITING

Three-step process:

1. **Section Drafting** --- Each agent drafts their assigned sections:
   - **Writer:** Abstract, Introduction, Conclusion
   - **Theorist:** Methods (with experiment descriptions if EXECUTION ran)
   - **Analyst:** Results (with computational results if EXECUTION ran)
   - **Synthesizer:** Discussion
2. **Assembly** --- The writer agent combines all sections into a coherent paper, harmonizing style and adding transitions. If figures were generated during EXECUTION, they are referenced as `![Figure N](figures/filename.png)`.
3. **LaTeX Math Enforcement** --- A post-processing pass converts any remaining Unicode math characters (Greek letters, subscripts, superscripts, operators) to LaTeX notation, preserving existing `$...$` delimiters. See [Terminal Display System](#17-terminal-display-system) section note.
4. **Citation Grounding** (if enabled) --- The Perplexity API inserts arXiv reference markers (`[1]`, `[2]`, ...) into citable sections (default: Introduction, Methods) and appends a bibliography. See [Citation Grounding & Seed Discovery](#18-citation-grounding--seed-discovery).
5. **Refinement** (optional) --- Additional rounds of polishing.

**Output:** Complete paper draft saved as `paper-<id>` in the database and as a `.md` file in `data/papers/`. Papers with figures use a subdirectory layout: `data/papers/<paper-id>/<paper-id>.md` with a `figures/` subdirectory.

#### REFLECTION (PI verdict)

When `orchestrator.enable_reflection` is on (it is in the shipped configs), a **PI agent** (config role `pi` — the strongest model in the tier) judges the assembled draft after WRITING and returns one of three verdicts:

- **`proceed`** — the draft is coherent and the evidence supports its claims; go to review (the default).
- **`loop_back`** — a specific, fixable gap would sink the paper in review. The team is sent back to **EXECUTION** (more experiments) or **PLANNING** (re-plan first), with concrete directives and a MEASURABLE success criterion; the cycle then flows through WRITING again.
- **`call_it`** — more work won't help; finish honestly with what stands.

Loop-backs are hard-budgeted by `orchestrator.max_loop_backs` (default 2): a second loop-back must show the first one's success criteria were met, looping back to the **same target twice forces `call_it`**, and with the budget spent only `proceed`/`call_it` are valid. The verdict is best-effort — an unparseable reflection defaults to `proceed`, never blocking the cycle.

The PI also **triages peer reviews**: if a major revision's demands require genuinely new analysis (not rewording), it can trigger one *deep revision loop* (new experiments feeding the revision) before resubmission.

In interactive mode the PI's verdict becomes a decision dialog — the operator sees the reasoning, directives, and success criteria, and can accept the proposal or pick a different path (see [Interactive Mode](#8-interactive-mode)).

#### INTERNAL_REVIEW

The editor agent reviews the paper with structured feedback: strengths, weaknesses, required changes, and a recommendation (accept or revise). If revision is needed, the writer revises and the editor re-reviews, up to `max_review_iterations` times.

**Output:** Reviewed paper, ready for submission.

#### SUBMITTED (Desk Review)

The editor-in-chief performs a quick quality check. Papers that are incoherent, off-topic, or fundamentally flawed are desk-rejected. Otherwise, they proceed to peer review.

**Output:** Decision: `send_to_review` or `desk_reject`.

#### PEER_REVIEW

Fresh reviewer agents (not reusing team agents) independently evaluate the paper. Each reviewer provides:
- Summary, strengths, weaknesses, questions, suggestions
- Scores: Novelty, Rigor, Clarity, Significance (each out of 10)
- Recommendation: `accept`, `minor_revision`, `major_revision`, or `reject`

The synthesized decision follows majority vote with acceptance threshold.

**Output:** Decision + list of peer reviews.

#### REVISION

If reviewers request revisions, the writer agent revises the paper based on all reviewer feedback, then resubmits for another round of peer review. This loop repeats up to `max_revision_rounds` times (default: 2).

#### PUBLISHED

The paper is accepted. The orchestrator:
- Sets paper status to `published`
- Adds the paper to ChromaDB for semantic search
- Extracts and records citations (both arXiv and internal paper IDs)
- Updates author agent reputation scores
- Scores the paper via the quality ledger, when enabled (see [Quality Ledger](#quality-ledger))

#### REJECTED

The paper is rejected. The orchestrator:
- Sets paper status to `rejected`
- Stores the paper in the graveyard with failure reasons and lessons learned
- Lessons are available for future research cycles to learn from

---

## 7. The Agent Team

### Research Agents

| Role | Expertise | Section Assignments | Description |
|------|-----------|---------------------|-------------|
| **theorist** | Theoretical modeling, mathematical frameworks | Methods | Proposes hypotheses, develops theoretical models, writes the methods section |
| **analyst** | Data analysis, statistical methods | Results | Analyzes data, interprets results, writes the results section |
| **synthesizer** | Cross-disciplinary connections, literature integration | Discussion | Connects findings to broader context, writes the discussion section |
| **experimentalist** | Computational experiments, simulation design | --- | Designs and proposes computational experiments for the sandbox |
| **writer** | Scientific writing, narrative coherence | Abstract, Introduction, Conclusion | Drafts framing sections, assembles the full paper, handles revisions |
| **skeptic** | Critical analysis, identifying flaws | --- | Challenges assumptions, identifies weaknesses, provides internal critique |

### Journal Agents

| Role | Purpose |
|------|---------|
| **editor** | Performs internal review and desk review. Evaluates paper quality, provides structured feedback, decides whether to send to peer review. |
| **reviewer** | Independent peer reviewer. Created fresh for each review round (not shared with the research team). Scores papers on novelty, rigor, clarity, significance. |

### Scientific Skills System

Each agent is equipped with scientific skills from a library of 142 skill definitions (sourced from `vendor/claude-scientific-skills/`). Skills shape an agent's system prompt with domain-specific knowledge and methodology.

**Skill loading modes** (set via `skills.default_mode` in config):

| Mode | Behavior |
|------|----------|
| `default` | Each role loads its own default skills as specified in the role YAML template |
| `all` | Every agent loads all 142 skills |
| `none` | No external skills; agents use only their role prompt |
| `custom` | Explicit list of skill names per agent |

Role prompts are defined in `src/paradigm/agents/prompts/*.yaml` and compose with skills to form the agent's full system prompt.

---

## 8. Interactive Mode

Interactive mode puts a human in the loop at key decisions. In the CLI, run with `--interactive`; in the web UI, it is a **per-cycle flag** — toggle "Interactive" in the Setup Wizard when creating the cycle (`interactive: true` on `POST /api/v1/research`). Other cycles on the same server run autonomously.

```bash
paradigm run --mode directed --prompt "Your question" --interactive
```

### Structured Decision Gates (Web UI)

Beyond plain phase-transition approvals, an interactive cycle surfaces **typed decision points** with selectable choices (each carries `id`, `label`, `detail`, and where relevant a `score`):

1. **Hypothesis selection** (`hypothesis_selection`) --- after the IDEATION tournament, the full Elo-ranked field of hypotheses is offered with the tournament winners preselected (multi-select). Keep, narrow, or broaden the set; free-text notes become guidance for the next discussion round.
2. **Experiment-plan approval** (`experiment_plan`) --- before EXECUTION, the action items extracted from PLANNING are shown. Approve as-is, or add notes that are appended to the plan as `OPERATOR DIRECTIVE` lines every experiment prompt re-reads.
3. **PI reflection** (`pi_reflection`) --- the PI's verdict on the draft (proceed / loop back to execution / loop back to planning / call it) is presented as a decision dialog with the PI's proposal preselected; pick a different path or ride along with notes.

Every decision also offers **pause** and **abort**. Decisions are delivered over the WebSocket as `approval_request` messages with `decision_type`, `choices`, `multi_select`, and `default_ids` fields; respond with `approval_response` (`decision`, optional `notes`, optional `modifications.selected_ids`). See [`docs/API.md`](API.md).

**Auto-continue:** each gate times out after **300 seconds** and defaults to *continue* with the preselected choices, so an unattended interactive run never stalls.

### Classic Phase-Transition Gates

The plain continue/pause/abort confirmations still fire at:
1. **IDEATION -> PLANNING** --- After ideation completes, before planning begins
2. **PLANNING -> EXECUTION** --- Before computational experiments (subsumed by the structured experiment-plan gate when a decision hook is connected)
3. **POST_EXECUTION -> WRITING**, **EXECUTION -> WRITING**, or **PLANNING -> WRITING** --- Before paper drafting begins
4. **INTERNAL_REVIEW -> SUBMITTED** --- After internal review, before submission to peer review

### At Each CLI Pause

You are prompted:

```
Proceed from ideation to planning? [Y/n]:
```

Your options:
- **Yes (Enter/Y)** --- Continue to the next phase
- **No** --- You are then asked:
  ```
  Abort the research cycle entirely? [y/N]:
  ```
  - **Yes** --- The cycle is aborted and the thread status is set to `aborted`
  - **No** --- The cycle is paused and the thread status is set to `paused`

### Steering Between Gates

You don't have to wait for a gate to steer. Messages typed into the web UI land at the **next agent turn** (typically within a minute), not the next round boundary — the engine checks for a pause click and drains fresh guidance before every agent speaks. Guidance drained mid-round reaches the remaining speakers immediately and stays visible through the next full round.

This works **during EXECUTION too**, which runs no discussion rounds: between experiments, steering is converted into `OPERATOR DIRECTIVE` lines on the planning action items, which every experiment prompt re-reads.

### Keyboard Interrupt

You can press `Ctrl+C` at any time to interrupt a running cycle. The thread will be left in whatever state it was in at the time of interruption.

---

## 9. Multi-Cycle Research

Paradigm's internal corpus grows over time. Published papers are indexed in ChromaDB and become discoverable by future research cycles.

### Per-Cycle Collection Isolation

Each research cycle gets its own ChromaDB collection (`paradigm_papers_{cycle_id}`) so that literature embeddings from one cycle don't leak into another. In the CLI, the cycle ID is a random short UUID; in the backend, it's the session ID. This prevents unrelated papers (e.g., Cepheid papers from cycle 1) from polluting search results in a different-topic cycle 2.

Agent memories, by contrast, use a shared `agent_memories` collection that persists across cycles — this is intentional so agents can learn from past experience.

### How It Works

1. **Cycle 1** runs and publishes a paper (e.g., `paper-abc123def456`)
2. The paper is embedded in its cycle-specific ChromaDB collection with its title and abstract
3. **Cycle 2** starts with a fresh, empty collection. During the SEEDING phase, the orchestrator searches arXiv and other external sources for literature relevant to the new seed prompt
4. If cycle 1's paper was also stored in SQLite (which is shared), it can still be found via direct DB lookups, but it won't pollute semantic search results
5. Agents can cite papers (using internal ID `paper-abc123def456` or arXiv IDs)
6. On publication, citations are extracted from the paper body and recorded in the citation graph

### Citation Tracking

Citations are extracted automatically from published paper text:

- **arXiv citations:** Matched by pattern `arXiv:XXXX.XXXXX` (e.g., `arXiv:2301.12345`)
- **Internal citations:** Matched by pattern `paper-XXXXXXXXXXXX` (e.g., `paper-abc123def456`)

The citation graph is stored in SQLite and can be queried to find:
- Papers cited by a given paper
- Papers that cite a given paper
- Most-cited papers in the corpus

### Learning from Failures

Paradigm learns from its own failures. When a paper is rejected (either at desk review or after peer review), it is stored in the **graveyard** table with:
- The original content
- The failure reason (e.g., "desk_reject", "peer_review_reject")
- Lessons learned extracted from reviewer feedback

During the **SEEDING** phase, the orchestrator searches the graveyard for past failures related to the current seed prompt. If relevant entries are found, these lessons are injected into the **IDEATION** round 1 prompt as non-citable context, helping agents avoid repeating past mistakes.

**Corpus status filtering:** Only papers with status `published` or `external` appear in corpus search results. Draft, submitted, revised, and rejected papers are automatically filtered out, ensuring agents only cite finalized, peer-reviewed work.

**Fresh corpus mode:** If you want to start a cycle without any previously published Paradigm papers in the corpus (e.g., to avoid cross-domain contamination when switching topics), use the `--fresh-corpus` flag. This creates an isolated temporary vector DB so the internal corpus starts empty. External papers ingested from URLs in the seed prompt are still included.

```bash
paradigm run --mode directed --prompt "Your new topic" --fresh-corpus
```

### Example Multi-Cycle Workflow

```bash
# Cycle 1: Establish foundational result
paradigm run --mode directed \
  --prompt "Derive the period-luminosity relation for classical Cepheids"

# Cycle 2: Build on cycle 1
paradigm run --mode directed \
  --prompt "How does metallicity affect the Cepheid period-luminosity relation?"

# Cycle 3: Challenge the results
paradigm run --mode hypothesis \
  --prompt "The Cepheid period-luminosity relation has a non-linear break at 10 days"

# Check what was produced
paradigm papers --status published
```

---

## 10. Literature Search System

Paradigm implements a multi-backend, budget-constrained literature search system that agents drive through action tags in their responses. Rather than the orchestrator searching upfront, agents decide what to search for and when, guided by stall detection and budget enforcement.

### Action Tags

Agents embed these tags in their natural-language responses:

| Tag | Purpose | Example |
|-----|---------|---------|
| `[SEARCH: query]` | Keyword search across arXiv + local corpus | `[SEARCH: Cepheid period-luminosity metallicity]` |
| `[FOLLOW: arxiv_id]` | Get papers cited by this paper (references) | `[FOLLOW: 2301.12345]` |
| `[CITED_BY: arxiv_id]` | Get papers that cite this paper | `[CITED_BY: 1903.09534]` |
| `[READ: arxiv_id]` | Deep-read key sections of a paper | `[READ: 2301.12345]` |
| `[CHAIN: id depth=N direction=refs\|cites\|both]` | Multi-hop BFS through the citation graph from one seed | `[CHAIN: 2301.12345 depth=2 direction=both]` |
| `[DATA: url]` | Stage a dataset for use in experiments | `[DATA: https://example.com/catalog.csv]` |
| `[DATASEARCH: query]` | Search wired data repositories (VizieR/CDS, Zenodo) for datasets | `[DATASEARCH: OB star TESS photometry catalog]` |
| `[FETCHDATA: id]` | Fetch a repository dataset by ID and stage it into the sandbox | `[FETCHDATA: vizier:J/A+A/701/A297]` |

`[FOLLOW:]`, `[CITED_BY:]`, `[READ:]`, and `[CHAIN:]` only operate on arXiv IDs that
actually appeared in a real search result — an invented/hallucinated ID is rejected
(it would otherwise pull in unrelated papers). `[CHAIN:]` walks references and/or
citations breadth-first up to `depth` (capped at 3) from a discovered seed; it's
budgeted at `chain_budget_per_round` (default 1) since it fans out fast.

After every agent response, the orchestrator parses these tags and executes the corresponding actions. Results are appended to the literature context and included in subsequent agent prompts.

**Search-enabled phases:** IDEATION, PLANNING, EXECUTION. Other phases (WRITING, PEER_REVIEW, etc.) disable literature actions. Data staging (`[DATA:]`) is only processed during IDEATION and PLANNING.

### Search Pipeline (SEARCH)

When an agent issues `[SEARCH: query]`, the request passes through several gates before execution:

**1. Deduplication.** Two layers prevent redundant searches:
- *Exact match:* The query string (lowercased) is checked against all previous queries in this cycle.
- *Fuzzy keyword match:* Keywords are extracted (stop words removed), and Jaccard similarity is computed against all previous keyword sets. Queries with similarity >= 0.7 are skipped.

**2. Budget enforcement.** Three levels of budget control:
- *Per-round global:* `max_searches_per_round` (default: 3). Hard cap on total keyword searches per round. Resets each round.
- *Per-agent cap:* Computed as `max * 2/5` (default: 2). Prevents a single agent from monopolizing the search budget.
- *Cross-round stall throttle:* After 5 cumulative zero-result searches, the global keyword budget is reduced to 1 per round.

**3. Dual-backend query.** Two independent sources are queried in parallel:
- *ChromaDB (local):* Semantic similarity search using sentence-transformers embeddings. Returns papers with status `published` or `external` only. Paradigm-internal draft/rejected papers are filtered out.
- *arXiv API:* Keyword search via `http://export.arxiv.org/api/query`. Rate-limited to one request per `arxiv_rate_limit` seconds (default: 3.0). Results sorted by relevance.

**4. Merge and filter.** Local results are ranked first, then arXiv-only results (deduplicated by ID). The merged list is capped at `max_results_per_search` (default: 50). Papers already seen in this cycle (`seen_paper_ids`) are filtered out --- agents never see the same paper twice.

**5. Context injection.** Formatted results are appended to the accumulated `literature_context`. This context is truncated to 15,000 characters, trimming from the beginning (oldest results first) so the most recent searches are always visible.

### Graph Traversal (FOLLOW / CITED_BY)

Graph traversal uses the **Semantic Scholar API** to walk the citation graph:

- **FOLLOW** queries `GET /paper/ArXiv:{id}/references` --- returns up to `max_reference_results` (default: 20) papers cited by the target.
- **CITED_BY** queries `GET /paper/ArXiv:{id}/citations` --- returns up to `max_citation_results` (default: 10) papers citing the target, filtered to arXiv papers only and sorted by year descending (most recent first).

**Budgets per round:** `follow_budget_per_round` (default: 3), `cited_by_budget_per_round` (default: 2). Each paper's references and citations are traversed at most once per cycle.

### Deep Read (READ)

`[READ: arxiv_id]` fetches the full PDF text (cached in SQLite after first fetch), extracts key sections (Abstract, Introduction, Conclusion --- up to `max_read_chars`, default: 8,000 characters), and injects the content into the literature context.

**Budget:** `read_budget_per_round` (default: 5). Each paper is read at most once per cycle.

### Discovered Papers Index

Separately from the truncated literature context, the orchestrator maintains a compact **discovered papers index** --- a list of `[arxiv_id] Author: Title` entries for every paper encountered during the cycle. This index is never truncated, ensuring agents always have paper IDs available for `[FOLLOW:]` and `[CITED_BY:]` commands even after the detailed search results have been trimmed.

### Stall Detection

The system detects when keyword searches stop finding new papers and nudges agents toward graph traversal:

1. **Per-agent stall (2 consecutive zero-result searches):** A warning is injected into the literature context with specific `[FOLLOW:]` and `[CITED_BY:]` suggestions using discovered paper IDs.
2. **Global exhaustion (5+ cumulative zero-result searches):** The keyword search budget is hard-capped to 1 per round, and a persistent warning tells all agents to use graph traversal exclusively.

### Intended Search Strategy

The system is designed to guide agents through a natural progression:

- **Round 1:** Agents use `[SEARCH:]` to build an initial corpus of relevant papers.
- **Round 2+:** As keyword searches return diminishing results, agents shift to `[FOLLOW:]` and `[CITED_BY:]` to explore the citation graph. Stall detection enforces this transition.
- **Throughout:** Agents use `[READ:]` to deep-dive into the most relevant papers.

### State and Reset

All literature state --- query history, seen papers, stall counters, discovered paper index, dedup sets --- is scoped to a single research cycle. The `reset_cycle()` method clears everything at the start of each new cycle, so literature discovery starts fresh.

### Data Pre-staging (DATA)

Agents can request external datasets during IDEATION and PLANNING by embedding `[DATA: url]` tags in their responses. The orchestrator downloads the file outside the sandbox and mounts it into the shared data directory so it is available during EXECUTION.

```
[DATA: https://example.com/catalog.csv]
```

The sandbox default is `network_mode: "bridge"` (see [Docker Sandbox](#14-docker-sandbox)), so experiments *can* fetch public data at runtime — but pre-staging with `[DATA:]` is still the preferred route: the download is deterministic, happens outside the sandbox, produces a data card, and survives into the paper's provenance trail. The test-harness configs (`selftest-exp.yaml`, `validate.yaml`, `verify-*.yaml`) pin `network_mode: "none"`, and there pre-staging is the only way to get external data into experiments.

**How it works:**

1. The orchestrator parses `[DATA: url]` tags from agent responses (IDEATION and PLANNING phases only).
2. The URL is validated (must be `http://` or `https://`) and classified via the resource classifier (must be a `DATA` type resource).
3. The file is downloaded using the existing resource resolver, which handles streaming, size limits, and format detection.
4. The downloaded file is placed in `data/shared/data/` and automatically appears in the experiment file listing during EXECUTION.
5. A confirmation message is injected into the literature context (e.g., "Downloaded dataset: catalog.csv (1.2 MB)").

**Budget:** Maximum 3 data requests per round (`_DATA_REQUESTS_PER_ROUND`). URLs are deduplicated across the entire cycle --- requesting the same URL twice is silently skipped.

**Intended usage:** Use `[DATA:]` during PLANNING to request specific datasets you'll need in EXECUTION. Combine with `[SEARCH:]` to find papers that reference datasets, then stage the data with `[DATA:]`.

### Repository Data Acquisition (DATASEARCH / FETCHDATA)

`[DATA:]` requires the agent to already know a URL. The repository tags close the loop when it doesn't: agents can *search* wired data repositories and stage what they find.

```
[DATASEARCH: OB star TESS photometry catalog]
...results injected into context as provider-prefixed IDs...
[FETCHDATA: vizier:J/A+A/701/A297]
```

**Providers** are configured via `literature.data_providers` (implementations in `src/paradigm/literature/data_providers.py`):

| Provider | ID format | Description |
|----------|-----------|-------------|
| `vizier` | `vizier:J/A+A/701/A297` | VizieR/CDS astronomical catalogs (VOTable resource search, TSV table fetch) |
| `mast` | `mast:dbo.allpointing` | MAST — Hubble/Webb/TESS/Kepler/Roman archive (IVOA TAP catalog) |
| `irsa` | `irsa:twomass.allsky_images` | IRSA — NASA/IPAC infrared archive: WISE, 2MASS, Spitzer (TAP) |
| `ned` | `ned:NEDTAP.objdir` | NED — NASA/IPAC Extragalactic Database (TAP) |
| `nasa_exoplanet` | `exoplanet:ps` | NASA Exoplanet Archive — confirmed planets, KOIs, time series (TAP) |
| `simbad` | `simbad:M31` | SIMBAD object cross-match — resolve a name to coordinates/type/basic params |
| `heasarc` | `heasarc:swiftmastr` | HEASARC high-energy archive (TAP; fetch-by-known-id — its schema search is finicky, so not in the default lists) |
| `zenodo` | `zenodo:999271` | Zenodo research-data records (domain-agnostic) |
| `dryad` | `dryad:doi:10.5061/dryad.xxx` | Dryad curated datasets (search returns DOIs; bulk download is often auth-gated) |
| `uniprot` | `uniprot:P01308` | UniProt — protein sequence/annotation records (TSV) |
| `pdb` | `pdb:3GOU` | RCSB PDB — macromolecular structures (`.pdb`/`.cif`) |
| `geo` | `geo:GSE12345` | NCBI GEO — gene-expression series (SOFT family file) |

The astro-flavored shipped configs (`default.yaml`, `production.yaml`, `open.yaml`, `interactive.yaml`) use `["vizier", "simbad", "ned", "mast", "irsa", "nasa_exoplanet", "zenodo"]`. A biology domain would set e.g. `["uniprot", "pdb", "geo", "zenodo"]`. TAP archives (`mast`/`irsa`/`ned`/`nasa_exoplanet`/`heasarc`) list matching tables on search and stage a bounded TOP-5000 slice on fetch (agents run larger queries themselves in the sandbox). An empty list disables the tags.

**How it works:**

1. `[DATASEARCH: query]` fans the query out to every wired provider (up to 4 candidates each). Results are injected into the literature context as `` `id` — title [source] `` lines with an instruction to stage one via `[FETCHDATA: <id>]`. A `dataset.search` event is emitted.
2. `[FETCHDATA: id]` downloads the dataset outside the sandbox and stages it into `data/shared/data/` (visible to experiments as `/data/shared/data/`), generating a **data card** — a schema preview injected into context and the EXECUTION prompts. A `dataset.fetched` event is emitted.
3. **CDS fixed-width tables get first-class treatment:** a CDS `ReadMe`'s byte-by-byte description is the authoritative schema, and whitespace-splitting the `.dat` silently misparses it. The stager parses the ReadMe's byte-by-byte tables and emits a ready-to-paste `pandas.read_fwf` recipe (exact `colspecs` + column names) into the data card.

**Phases:** the same as literature search actions — IDEATION, PLANNING, EXECUTION, POST_EXECUTION.

**Budgets:** 2 `[DATASEARCH:]` per round; `[FETCHDATA:]` shares the 3-per-round data-staging budget with `[DATA:]`. Fetched dataset IDs are deduplicated across the cycle. Like every literature action, failures degrade to a note in context — they never abort the cycle.

### Real-Data Mandate (data_policy)

`orchestrator.data_policy` governs whether experiments may fabricate their input data:

| Policy | Behavior |
|--------|----------|
| `real_only` | Fabricating datasets is forbidden. Synthetic experiments are **excluded from the paper's evidence base** and raise a blocking editor alert. Default in `default.yaml`, `production.yaml`, and `open.yaml`. |
| `prefer_real` | Synthetic stand-ins are tolerated but must be clearly labeled; they are flagged to reviewers. (Code default when a config sets nothing.) |
| `permissive` | No policy — intended for test harnesses. |

**Provenance classifier.** The policy needs a mechanical answer to "where did this experiment's data come from?", so every executed experiment is classified from its code (and stdout) into one of four verdicts (`src/paradigm/orchestrator/data_provenance.py`):

| Verdict | Meaning |
|---------|---------|
| `real` | Loads data files, no random generation |
| `resampled` | Loads data files AND uses randomness — bootstrap/permutation/Monte-Carlo over real data (legitimate statistics) |
| `derived` | Neither loads files nor generates randomness (pure computation on prior results) |
| `synthetic` | Generates random arrays without loading any data, or self-describes its data as synthetic/mock |

Under `real_only`, a `synthetic` verdict excludes the experiment from the evidence base and the editor receives a blocking alert — the writer cannot cite it.

**DATA UNAVAILABLE descope protocol.** The `real_only` experiment directive instructs agents: if the data an experiment needs cannot be found in `/data/shared` (or downloaded), *descope* the experiment and print `DATA UNAVAILABLE: <what and why>`. An honestly missing analysis is publishable; a fabricated one is fraud. The carve-outs matter — resampling of real data and clearly-labeled analytic computation remain allowed.

**Statistical-standards directive.** Alongside the data policy, every experiment prompt carries a statistical-rigor block: inspect distributions before choosing methods (rank-based statistics for skewed/quantized variables), report effect sizes with bootstrap CIs rather than bare p-values, control for confounds before claiming an association is physical, and document every excluded row. It exists because a live head-to-head run was dinged by reviewers for exactly these omissions.

---

## 11. Configuration Reference

Configuration is loaded from a YAML file (default: `configs/default.yaml`). Override with `--config` or the `PARADIGM_CONFIG` environment variable.

### `providers` --- LLM Providers

Paradigm supports multiple LLM providers for epistemic diversity. Each provider is defined in the `providers` section:

```yaml
providers:
  anthropic:
    type: anthropic
    api_key_env: ANTHROPIC_API_KEY
    default_model: claude-sonnet-4-5-20250929
  together:
    type: openai_compatible
    api_key_env: TOGETHER_API_KEY
    base_url: https://api.together.xyz/v1
    default_model: meta-llama/Llama-3.3-70B-Instruct-Turbo
  google:
    type: openai_compatible
    api_key_env: GEMINI_API_KEY
    base_url: https://generativelanguage.googleapis.com/v1beta/
    default_model: gemini-3-pro-preview
```

Any provider with an OpenAI-compatible chat completions API can be added using `type: openai_compatible`.

### `agent` --- Agent Behavior

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_provider` | string | `together` | Default LLM provider for agents without an explicit override |
| `default_model` | string | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Default model for agents without an explicit override |
| `opus_model` | string | `claude-opus-4-6` | Higher-capability model (available for special tasks) |
| `max_tokens` | int | `4096` | Default max output tokens per API call |
| `temperature` | float | `1.0` | Sampling temperature for agent responses |
| `token_budget_per_thread` | int | `1000000` | Max tokens allowed per research thread |
| `token_budget_per_agent` | int | `100000` | Max tokens allowed per individual agent |

### Model Assignments

Per-role overrides route each agent to a specific provider and model. The default configuration uses three providers for epistemic diversity --- agents from different training lineages are less likely to share the same blind spots.

**Default mode** (`configs/default.yaml` — production-parity premium mapping):

| Role | Provider | Model |
|------|----------|-------|
| Theorist | OpenAI | `gpt-5.4` |
| Experimentalist | OpenAI | `gpt-5.5` |
| Analyst, Skeptic | Anthropic | `claude-sonnet-4-6` |
| Writer, PI, Prompt refiner | Anthropic | `claude-opus-4-8` |
| Editor | Anthropic | `claude-sonnet-5` |
| Synthesizer | Anthropic | `claude-haiku-4-5` |
| Reviewers, Judge | Google | `gemini-3.5-flash` |

**Testing mode** (`--testing` flag / the GUI mode toggle) --- the cheap open-weights mapping for fast trial runs:

| Role | Provider | Model |
|------|----------|-------|
| Theorist, Experimentalist, Writer | Together | `zai-org/GLM-5.2` |
| Skeptic, Editor | Together | `moonshotai/Kimi-K2.6` |
| Analyst, Reviewers | Together | `MiniMaxAI/MiniMax-M3` |
| Synthesizer | Together | `openai/gpt-oss-120b` |

Overrides are configured in the `agent.overrides` section of the YAML config. Testing overrides are in the `testing_overrides` section and are applied when the `--testing` CLI flag is passed.

### Model Tiers

Two shipped configs implement the same pipeline on different model tiers:

| Tier | Config | Models |
|------|--------|--------|
| `premium` | `configs/production.yaml` | Top closed models per role (e.g. GPT-5.4 theorist, Claude Opus 4.8 writer/PI, Claude Sonnet 5 editor, Gemini for utility roles) |
| `open` | `configs/open.yaml` | Open-weights models via Together: GLM-5.2 (theorist/experimentalist/writer/PI), Kimi-K2.6 (skeptic/editor), MiniMax-M3 (analyst/reviewer), gpt-oss-120b (synthesizer) |

In the web UI, the Setup Wizard has a per-cycle **Models** toggle (`model_tier`: `premium` | `open`; `null` = whatever the active config runs) — the tier applies to that cycle only, without switching the server config. `GET /api/v1/config/tiers` reports which tiers are available (key-gated) and which one the active config resembles.

Two role overrides matter beyond the classic team:

- **`pi`** — the PI-reflection gate's model (the strongest model in the tier; see [REFLECTION](#reflection-pi-verdict)).
- **`judge`** — the quality ledger's scorer. Deliberately FIXED across tiers (`gemini-3.5-flash` in both shipped configs), so quality scores stay comparable when you switch tiers.

In `open.yaml` the closed providers stay registered (hidden in the picker without their key), so any role can be flipped back to a frontier model live from the GUI Agents panel.

### `orchestrator` --- Orchestration Behavior

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_rounds_per_phase` | int | `10` | Rounds of agent discussion per phase (IDEATION, PLANNING) |
| `enable_checkpointing` | bool | `true` | Save checkpoint summaries during phases |
| `checkpoint_interval` | int | `5` | Save checkpoint every N rounds |
| `enable_writing` | bool | `true` | Enable the WRITING phase (set `false` to stop after PLANNING) |
| `max_review_iterations` | int | `5` | Max internal review-revision loops |
| `enable_peer_review` | bool | `true` | Enable the peer review pipeline after internal review |
| `num_reviewers` | int | `2` | Number of independent peer reviewers |
| `max_revision_rounds` | int | `4` | Max peer-review revision loops before final decision |
| `enable_experimentation` | bool | `true` | Enable EXECUTION phase for modes with an experimentalist |
| `enable_post_execution_discussion` | bool | `true` | Enable POST_EXECUTION team discussion after experiments complete |
| `max_experiment_rounds` | int or null | `null` (2 × `max_rounds_per_phase`) | Max rounds of experiment proposal/execution in EXECUTION phase. Defaults to twice the discussion rounds. |
| `max_searches_per_round` | int | `3` | Max `[SEARCH: ...]` requests processed per round (resets each round) |
| `enable_convergence_detection` | bool | `true` | Detect when agents converge early in discussion phases and skip remaining rounds |
| `convergence_confidence_threshold` | float | `0.85` | Minimum confidence (0.0–1.0) to accept convergence and skip rounds |
| `data_policy` | string | `prefer_real` | Real-data mandate: `real_only` / `prefer_real` / `permissive`. Shipped configs set `real_only`. See [Real-Data Mandate](#real-data-mandate-data_policy) |
| `enable_reflection` | bool | `false` | PI reflection gate after WRITING (proceed / loop back / call it). ON in shipped configs. See [REFLECTION](#reflection-pi-verdict) |
| `max_loop_backs` | int | `2` | Hard budget on PI loop-backs per cycle |
| `enable_quality_ledger` | bool | `false` | Auto-score every finished paper with the `judge` role. ON in shipped configs. See [Quality Ledger](#quality-ledger) |

### `literature` --- Literature Search

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `arxiv_rate_limit` | float | `3.0` | Seconds between arXiv API requests |
| `max_results_per_search` | int | `50` | Maximum papers returned per search |
| `enable_pdf_fetch` | bool | `true` | Fetch and extract PDF text from arXiv |
| `data_providers` | list | `["zenodo"]` | Repository providers for `[DATASEARCH:]`/`[FETCHDATA:]` (`vizier`, `zenodo`). Shipped configs use `["vizier", "zenodo"]`; empty list disables the tags |
| `embedding_model` | string | `sentence-transformers/all-MiniLM-L6-v2` | Model for paper embeddings in ChromaDB |
| `follow_budget_per_round` | int | `3` | Max `[FOLLOW:]` requests per round |
| `cited_by_budget_per_round` | int | `2` | Max `[CITED_BY:]` requests per round |
| `read_budget_per_round` | int | `5` | Max `[READ:]` requests per round |
| `chain_budget_per_round` | int | `1` | Max `[CHAIN:]` multi-hop walks per round |
| `max_read_chars` | int | `8000` | Character limit for deep-read extraction |
| `max_citation_results` | int | `10` | Papers returned per `[CITED_BY:]` |
| `max_reference_results` | int | `20` | Papers returned per `[FOLLOW:]` |

### `sandbox` --- Docker Sandbox

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable Docker sandbox for code execution |
| `image_name` | string | `paradigm-sandbox:latest` | Docker image name |
| `network_mode` | string | `bridge` | Docker network mode (`bridge` = internet access; `none` = fully isolated — pinned in the test-harness configs) |
| `cpu_limit` | float | `2.0` | CPU core limit per container |
| `memory_limit` | string | `2g` | Memory limit per container |
| `execution_timeout` | int | `300` | Execution timeout in seconds |
| `max_output_size` | int | `10485760` | Max output size in bytes (10 MB) |

### `skills` --- Scientific Skills

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `skills_dir` | path | `vendor/claude-scientific-skills/scientific-skills` | Path to skill definitions directory |
| `default_mode` | string | `default` | Skill loading mode: `default`, `all`, `none` |
| `max_skill_chars` | int or null | `null` | Per-skill character truncation limit (null = no truncation) |

### `citation` --- Citation Grounding & Novelty

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enable_citation_grounding` | bool | `true` | Enable Perplexity-based citation grounding on paper drafts |
| `perplexity_api_key_env` | string | `PERPLEXITY_API_KEY` | Environment variable name for the Perplexity API key |
| `citation_sections` | list | `["introduction", "methods"]` | Which paper sections to process for citation insertion |
| `max_retries_per_paragraph` | int | `2` | Max retries for Perplexity citation calls per paragraph |
| `perplexity_timeout` | float | `120.0` | Timeout in seconds for Perplexity API calls |
| `enable_novelty_check` | bool | `false` | Front-loaded novelty assessment before hypothesis selection. ON in shipped configs |
| `novelty_mode` | string | `semantic_scholar` | Novelty checking backend: `semantic_scholar` or `futurehouse` |
| `novelty_max_iterations` | int | `5` | Max search iterations for Semantic Scholar novelty check |
| `futurehouse_api_key_env` | string | `FUTURE_HOUSE_API_KEY` | Environment variable name for FutureHouse API key |
| `enable_seed_discovery` | bool | `true` | Enable Perplexity-based seed discovery before IDEATION |
| `seed_discovery_max_papers` | int | `10` | Max papers to discover during seed discovery |

### `memory` --- Agent Episodic Memory

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable agent episodic memory across cycles |
| `max_memories_per_prompt` | int | `5` | Max memories injected per agent per prompt |
| `recency_half_life_days` | float | `30.0` | Half-life for recency decay scoring (days) |
| `reflection_model` | string | `claude-sonnet-4-5-20250929` | Model used for end-of-cycle reflection generation |
| `collection_name` | string | `agent_memories` | ChromaDB collection name for memories |
| `max_memory_chars` | int | `2000` | Max characters of memory context per agent prompt |

### `storage` --- Data Storage

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `data_dir` | path | `./data` | Root directory for all data (resolved relative to project root) |
| `db_path` | path or null | `<data_dir>/paradigm.db` | SQLite database path (auto-derived if null) |
| `vector_db_path` | path or null | `<data_dir>/vector_db` | ChromaDB directory (auto-derived if null) |
| `papers_dir` | path or null | `<data_dir>/papers` | Published paper markdown files (auto-derived if null) |
| `log_path` | path or null | `<data_dir>/events.jsonl` | Event log file (auto-derived if null) |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key (**required** for default mode) | --- |
| `GEMINI_API_KEY` | Google Gemini API key (**required** for default mode) | --- |
| `TOGETHER_API_KEY` | Together.ai API key (**required** for testing mode) | --- |
| `PERPLEXITY_API_KEY` | Perplexity API key (for citation grounding and seed discovery) | --- |
| `FUTURE_HOUSE_API_KEY` | FutureHouse API key (for FutureHouse novelty checking mode) | --- |
| `PARADIGM_CONFIG` | Path to config YAML file | `configs/default.yaml` |
| `PARADIGM_DATA_DIR` | Override data directory | `./data` |
| `PARADIGM_LOG_LEVEL` | Logging level | `INFO` |

Place your API keys in a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
TOGETHER_API_KEY=...
PERPLEXITY_API_KEY=pplx-...
```

---

## 12. Data and Storage

### Directory Layout

```
data/
  paradigm.db          # SQLite database (papers, threads, agents, events, token usage)
  events.jsonl         # Structured event log (JSON lines)
  vector_db/           # ChromaDB embeddings for semantic search
  papers/              # Published paper markdown files
    paper-abc123.md              # Papers without figures: flat file
    paper-def456/                # Papers with figures: subdirectory layout
      paper-def456.md            #   Paper markdown
      figures/                   #   Generated figures from EXECUTION phase
        experiment-name_plot.png
        experiment-name_data.png
      experiments/               #   Working experiment code (EXECUTION phase)
        experiment_name.py       #     Code that produced successful results
        README.md                #     Index of experiments
      transcript.md              #   Full conversation transcript
      literature_searches.md     #   Search queries and results log
      reviews.md                 #   Review report with token/time summary
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `papers` | All papers (draft, submitted, published, rejected, external) with title, abstract, authors, body, status, review scores, timestamps |
| `agents` | Agent records with skill profile, personality, reputation metrics |
| `threads` | Research threads with status, mode, participants, hypothesis, findings, current phase, draft ID |
| `graveyard` | Failed/rejected entries with failure reasons and lessons learned; searchable by keyword and type |
| `events` | Structured event log (supplements JSONL) with event type, agent/thread IDs, phase, content |
| `token_usage` | Per-call token tracking with model, input/output tokens, agent/thread IDs |
| `citations` | Citation graph: citing_paper_id -> cited_paper_id with optional context |

### Event Log Format

Events are stored as JSON lines in `data/events.jsonl`. Each line is a JSON object:

```json
{
  "timestamp": "2026-02-12T15:30:00+00:00",
  "event_type": "agent_message",
  "agent_id": "theorist-0",
  "thread_id": "thread-9a80e2395c85",
  "phase": "ideation",
  "content": {"from": "theorist-0", "type": "proposal", "content": "..."},
  "metadata": {}
}
```

**Event types:**

| Type | Description |
|------|-------------|
| `agent_message` | Agent sent a message during a phase |
| `api_call` | Claude API call with token counts |
| `code_execution` | Code executed in Docker sandbox |
| `state_change` | Thread state change |
| `error` | Error occurred |
| `phase_transition` | Research phase changed |
| `literature_search` | Literature corpus search performed |
| `checkpoint_created` | Checkpoint saved |
| `paper_submitted` | Paper submitted, published, or rejected |
| `review_completed` | Review completed |

### Paper Files

Published papers are automatically saved as markdown files in `data/papers/`. Papers without figures are saved as flat files (`<paper-id>.md`). Papers with figures from the EXECUTION phase use a subdirectory layout (`<paper-id>/<paper-id>.md` with a `figures/` subdirectory). Papers are also written to disk when revised, so the file always reflects the latest version.

Each paper folder is a self-contained research artifact. Alongside the paper markdown and figures, the folder includes:
- **`transcript.md`** --- Full conversation transcript organized by phase, showing all agent messages, code executions, literature searches, and debates with timestamps.
- **`experiments/`** --- Working Python code from experiments that produced successful (non-vacuous) results during the EXECUTION phase, with a `README.md` index.
- **`literature_searches.md`** --- Log of all literature search queries, which agent made them, and the papers returned.
- **`reviews.md`** --- Complete review report including internal review, desk review, peer review scores, and a session summary with token usage and elapsed time.
- **`<paper-id>.tex` / `<paper-id>.pdf`** --- Journal-ready LaTeX and (if a LaTeX engine
  such as tectonic is on `PATH`) a typeset PDF, written when `journal.enable_latex_output`
  / `journal.compile_pdf` are on. In the web UI the paper view renders figures inline and
  offers **Copy Markdown**, **Download .md**, and **Download PDF** (compiled on demand if
  not pre-built).

---

## 13. Cost Management

Paradigm uses Claude API calls extensively. A full research cycle with default settings (10 rounds per phase, 6 agents, 2 reviewers) can use 300K-500K+ tokens.

### Estimating Costs

**Approximate token usage per phase** (with 6 agents, 10 rounds):

| Phase | Tokens (rough estimate) |
|-------|------------------------|
| SEEDING | ~5K (literature search only) |
| IDEATION | ~100K-150K |
| PLANNING | ~100K-150K |
| EXECUTION | ~30K-60K (experimental/replication modes only) |
| WRITING | ~50K-80K |
| INTERNAL_REVIEW | ~20K-30K |
| PEER_REVIEW | ~20K-40K |
| REVISION | ~20K-30K |
| **Total (full cycle)** | **~300K-500K** |

Costs depend on the model. Check [Anthropic pricing](https://www.anthropic.com/pricing) for current rates.

### Budget Controls

1. **`--rounds` CLI flag** --- The most effective cost lever. Set `--rounds 1` for cheap test runs:
   ```bash
   paradigm run --mode directed --prompt "Your question" --rounds 1
   ```
   This runs just 1 round of discussion per phase instead of 10, reducing IDEATION and PLANNING costs by ~90%.

2. **Token budgets** in config:
   ```yaml
   agent:
     token_budget_per_thread: 1000000   # Max tokens for entire thread
     token_budget_per_agent: 100000     # Max tokens per individual agent
   ```

3. **Disable optional phases:**
   ```yaml
   orchestrator:
     enable_writing: false          # Stop after PLANNING (no paper generated)
     enable_peer_review: false      # Stop after INTERNAL_REVIEW (no peer review)
     enable_experimentation: false  # Skip EXECUTION phase even in experimental mode
   ```

4. **Reduce reviewers:**
   ```yaml
   orchestrator:
     num_reviewers: 1           # 1 reviewer instead of 2
     max_revision_rounds: 0     # No revision rounds (accept or reject on first review)
   ```

### Monitoring Usage

```bash
# Check total token usage
paradigm status
```

Token usage is tracked per API call in the `token_usage` database table and logged in `events.jsonl` as `api_call` events.

---

## 14. Docker Sandbox

The computational sandbox executes Python code in isolated Docker containers. The default network mode is `"bridge"` (internet access, so experiments can fetch public data); the test-harness configs (`selftest-exp.yaml`, `validate.yaml`, `verify-*.yaml`) pin `network_mode: "none"` for full isolation.

### Building the Image

```bash
# The Dockerfile has no COPY — use docker/ as the build context (not the repo root)
docker build -t paradigm-sandbox:latest -f docker/Dockerfile.sandbox docker/
```

The sandbox image includes Python 3.12 plus: NumPy, SciPy, Matplotlib, Pandas,
scikit-learn, SymPy, Astropy, seaborn, h5py, emcee, corner, lmfit, uncertainties,
statsmodels, tqdm, numba, xarray, joblib, pyyaml, pypdf, pdfminer.six, beautifulsoup4,
and the astro/data extras photutils, specutils, dust_extinction, plotly, bokeh,
tables, netCDF4, pyarrow. Keep this list in sync with `docker/Dockerfile.sandbox`
and the EXECUTION prompt's "Extra packages" line, or agents import something that
isn't there. Each experiment runs as a **fresh process** with `numpy` (np),
`pandas` (pd), `matplotlib.pyplot` (plt), `scipy`, `astropy.units` (u), and
`astropy.constants` (const) **auto-imported**; write intermediate files to
`/data/workspace/` to share data between experiments.

### Security Model

- **Configurable network isolation:** `network_mode: "bridge"` by default; `"none"` for a fully offline container (pinned in the test-harness configs)
- **Resource limits:** CPU (2 cores), memory (2 GB), execution timeout (300s), pids limit (256)
- **Non-root user:** Code runs as an unprivileged user (with `cap_drop=ALL` and `no-new-privileges` by default)
- **Pre-execution safety scan:** AST-based code scanner rejects patterns like `os.system()`, `subprocess`, and sandbox escape attempts (plus network imports when `network_mode` is `"none"`)
- **Output size limits:** Max 10 MB of output per execution

### Network Access Mode

The default is `network_mode: "bridge"`: containers can reach the internet, experiments may download public data at runtime, and agents are told network access is available. The safety scanner keys off this setting — with `"bridge"`, network imports (`requests`, `httpx`, `urllib.request`, etc.) are allowed; other safety checks (`subprocess`, `os.system()`, `exec()`) remain active regardless.

For full isolation, set:

```yaml
sandbox:
  network_mode: "none"   # default: "bridge"
```

With `"none"`, the safety scanner blocks all network-related imports, experiment prompts warn agents that there is NO network access, and external data can only enter via `[DATA:]` / `[FETCHDATA:]` pre-staging or attached datasets. The shipped test-harness configs (`selftest-exp.yaml`, `validate.yaml`, `verify-*.yaml`) pin this mode so harness runs are hermetic.

If your config pins `"none"` but a one-off run needs the network, the CLI flag forces bridge mode for that run:

```bash
paradigm run --network-access --prompt "Your research prompt"
```

**Prefer pre-staging even with the network open:** `[DATA:]` / `[DATASEARCH:]` / `[FETCHDATA:]` downloads are deterministic, produce data cards, and leave a provenance trail; runtime downloads inside experiment code do not.

### Running Without Docker

If Docker is not available, disable the sandbox in config:

```yaml
sandbox:
  enabled: false
```

Research cycles will still run but agents cannot execute computational experiments. The writing pipeline does not require the sandbox.

### Configuration

```yaml
sandbox:
  enabled: true
  image_name: "paradigm-sandbox:latest"
  network_mode: "bridge"   # "none" = fully isolated (test-harness configs)
  cpu_limit: 2.0           # CPU cores
  memory_limit: "2g"       # Container memory limit
  execution_timeout: 300   # Seconds before timeout
  max_output_size: 10485760  # 10 MB max output
```

---

## 15. Troubleshooting

### Common Errors

#### `API key must be set in environment or config file`

A required API key is not configured. Ensure all provider keys are set:
- `export ANTHROPIC_API_KEY="sk-ant-..."` (Anthropic, for default mode)
- `export GEMINI_API_KEY="..."` (Google, for default mode)
- `export TOGETHER_API_KEY="..."` (Together.ai, for testing mode)
- Or create a `.env` file in the project root with all required keys

#### `Error loading configuration`

The config file could not be loaded. Check:
- The file exists at the expected path (`configs/default.yaml` or your `--config` path)
- The YAML is valid (no syntax errors)
- All paths in the config are valid

#### `ModuleNotFoundError: No module named 'paradigm'`

Install the package: `pip install -e ".[dev]"`

#### Agent API call failures (`[!] theorist-0 failed: ...`)

Individual agent failures are caught and logged. The cycle continues with remaining agents. Common causes:
- Rate limiting (too many concurrent requests)
- Token budget exceeded
- Invalid API key
- Network issues

The error is printed to the console and logged in `events.jsonl`.

#### `No checkpoint found for thread: ...`

The thread ID does not exist or no checkpoint was saved. Check:
- The thread ID is correct (look in the console output from the `run` command)
- Checkpointing is enabled (`orchestrator.enable_checkpointing: true`)

#### PDF fetch failures (`[!] Could not extract PDF from: ...`)

The orchestrator could not download or parse a PDF from a URL in your prompt. Common causes:
- **HTML article page instead of PDF link** --- Use the direct PDF URL (e.g., `https://www.nature.com/articles/s41586-020-2649-2.pdf`, not the `.html` article page)
- **Paywall or institutional access required** --- Some journals restrict access. Use the arXiv preprint link instead if available
- **Bot protection (captcha)** --- Some sites use TLS fingerprint detection. Paradigm falls back to `curl` automatically, but if `curl` is also blocked, the fetch will fail
- **Timeout** --- Large PDFs from slow servers may time out (30s limit). Try again or download the PDF manually

#### Docker sandbox errors

- **`docker.errors.ImageNotFound`** --- Build the image: `docker build -t paradigm-sandbox:latest -f docker/Dockerfile.sandbox .`
- **`docker.errors.APIError`** --- Docker Desktop may not be running. Start it and try again.
- **Permission denied** --- Your user may not be in the `docker` group. On Linux: `sudo usermod -aG docker $USER`

### Inspecting Logs

```bash
# View the event log
cat data/events.jsonl | python -m json.tool --no-ensure-ascii | less

# Filter for errors only
grep '"event_type":"error"' data/events.jsonl | python -m json.tool

# Filter for a specific thread
grep 'thread-abc123' data/events.jsonl | python -m json.tool

# Count API calls
grep '"event_type":"api_call"' data/events.jsonl | wc -l

# Inspect the database directly
sqlite3 data/paradigm.db "SELECT id, status, title FROM papers;"
sqlite3 data/paradigm.db "SELECT id, status, mode, current_phase FROM threads;"
sqlite3 data/paradigm.db "SELECT SUM(input_tokens), SUM(output_tokens) FROM token_usage;"
```

### Inspecting the Graveyard

Query the graveyard table to review past failures and the lessons extracted from them:

```bash
# List all graveyard entries
sqlite3 data/paradigm.db "SELECT id, type, failure_reason, substr(lessons_learned, 1, 80) FROM graveyard;"

# Search for entries related to a keyword
sqlite3 data/paradigm.db "SELECT id, type, lessons_learned FROM graveyard WHERE content LIKE '%convection%' OR failure_reason LIKE '%convection%' OR lessons_learned LIKE '%convection%';"

# Filter by type (e.g., only rejected papers)
sqlite3 data/paradigm.db "SELECT id, failure_reason, lessons_learned FROM graveyard WHERE type = 'rejected_paper';"
```

### Resetting State

To start fresh, remove the data directory:

```bash
rm -rf data/
```

The next `paradigm run` will recreate it. The SQLite database, ChromaDB embeddings, event log, and paper files will all be regenerated.

To reset only the database (keep event logs and paper files):

```bash
rm data/paradigm.db
```

---

## 16. Recipes

### Recipe 1: Quick Test Run (Low Cost)

Verify the system works with minimal API spend (~10K-20K tokens):

```bash
paradigm run \
  --mode directed \
  --prompt "Briefly explain stellar nucleosynthesis" \
  --rounds 1
```

### Recipe 2: Full Directed Cycle with Oversight

Run a complete research cycle with interactive checkpoints:

```bash
paradigm run \
  --mode directed \
  --prompt "What physical mechanisms drive the red supergiant problem?" \
  --rounds 3 \
  --interactive
```

You will be prompted before each major phase transition. Use this to:
- Review the ideation discussion before committing to a plan
- Verify the research plan before the writing phase
- Check the paper before submission to peer review

### Recipe 3: Multi-Cycle Discovery Workflow

Run multiple cycles and let papers build on each other:

```bash
# Foundation cycle
paradigm run --mode directed \
  --prompt "Derive the Hertzsprung-Russell diagram from first principles" \
  --rounds 2

# Follow-up cycle (will discover the first paper if relevant)
paradigm run --mode directed \
  --prompt "How do post-main-sequence stars evolve on the HR diagram?" \
  --rounds 2

# Exploratory follow-up
paradigm run --mode explore \
  --topic "gaps in stellar evolution theory" \
  --rounds 2

# Check the growing corpus
paradigm papers --status published
```

### Recipe 4: Custom Configuration

Create a custom config for cost-conscious exploration:

```yaml
# configs/cheap.yaml
agent:
  default_model: "claude-sonnet-4-5-20250929"
  max_tokens: 2048
  temperature: 1.0
  token_budget_per_thread: 200000
  token_budget_per_agent: 50000

orchestrator:
  max_rounds_per_phase: 2
  enable_checkpointing: true
  checkpoint_interval: 2
  enable_writing: true
  max_review_iterations: 1
  enable_peer_review: true
  num_reviewers: 1
  max_revision_rounds: 1

literature:
  max_results_per_search: 10

storage:
  data_dir: "./data"

skills:
  skills_dir: "vendor/claude-scientific-skills/scientific-skills"
  default_mode: "default"
```

Run with:

```bash
paradigm --config configs/cheap.yaml run \
  --mode directed \
  --prompt "Your question here"
```

### Recipe 5: Explore Without Writing

Stop after the planning phase (no paper generated, much cheaper):

```yaml
# In your config:
orchestrator:
  enable_writing: false
```

```bash
paradigm --config configs/ideation-only.yaml run \
  --mode explore \
  --topic "applications of machine learning in asteroseismology"

# Inspect what was discussed
paradigm inspect --thread <thread-id>
```

### Recipe 6: Export All Published Papers

```bash
# List published papers
paradigm papers --status published

# Papers are already in data/papers/ as markdown files
ls data/papers/

# Or export a specific one
paradigm paper paper-abc123 --export ~/Desktop/my-paper.md
```

### Recipe 7: Reviewing Past Failures

Check what the system has learned from rejected papers:

```bash
# See all graveyard entries
sqlite3 data/paradigm.db "SELECT id, type, failure_reason FROM graveyard;"

# Read lessons learned from a specific failure
sqlite3 data/paradigm.db "SELECT lessons_learned FROM graveyard WHERE id = 'graveyard-abc123';"

# Find failures related to a topic you're about to research
sqlite3 data/paradigm.db "SELECT failure_reason, lessons_learned FROM graveyard WHERE content LIKE '%stellar winds%' OR lessons_learned LIKE '%stellar winds%';"
```

These lessons are automatically surfaced during the SEEDING phase of future research cycles. If the new seed prompt is related to a past failure, agents will see the lessons in their first IDEATION round.

### Recipe 8: Literature Review

Produce a comprehensive survey of a research field:

```bash
paradigm run \
  --mode review \
  --prompt "Survey the current state of knowledge on internal gravity waves in massive stars" \
  --rounds 3
```

The review mode assembles a team without experimentalist or analyst, skips the EXECUTION phase, and produces a literature review paper with sections for literature landscape, thematic analysis, critical assessment, and future directions. Prompts are tuned for systematic searching and synthesis rather than hypothesis testing.

### Recipe 9: Computational Experiments with Prompt File

Run an experimental cycle with a detailed prompt from a file:

```bash
# Create a detailed prompt file
cat > prompt.md << 'EOF'
Investigate red noise (stochastic low-frequency variability) in massive stars.

Use the following approach:
1. Generate synthetic light curves with injected red noise following a power-law PSD
2. Analyze the frequency spectra using Lomb-Scargle periodograms
3. Fit power-law models to characterize the noise properties
4. Compare results across different stellar parameters

Reference: Bowman et al. 2019 (arXiv:1903.09534)
EOF

# Run with Docker sandbox enabled
paradigm run --mode experimental --prompt-file prompt.md --rounds 2

# Papers with figures will be in data/papers/<paper-id>/
ls data/papers/
```

The EXECUTION phase will propose and run Python experiments in Docker, and the results (including figures) will be automatically incorporated into the paper's Results and Methods sections.

---

## 17. Terminal Display System

Paradigm includes a Rich-based terminal UI that provides real-time visibility into a running research cycle.

### Live Display Layout

When running in a TTY terminal (and not in `--verbose` mode), Paradigm renders a live 3-column layout that refreshes 4 times per second:

```
┌─────────────────────────────────────────────────────────────────────┐
│  🌱 SEEDING ─── ● IDEATION ─── ○ PLANNING ─── ○ WRITING ─── ...   │  ← Phase bar
│  ⏱ 2m 31s  │  📄 0 papers  │  🔍 4 searches  │  🪙 45.2K tokens  │  ← Stats bar
├──────────────┬────────────────────┬─────────────────────────────────┤
│  Agents      │  Agent Messages    │  Events                         │
│              │                    │                                 │
│  🔭 theorist│  🔭 theorist-0     │  12:30:01 agent_response        │
│     active   │  claude-opus-4-6   │  12:30:05 literature_search     │
│  📊 analyst │  "The period-lum..." │  12:30:08 agent_response        │
│     active   │                    │  12:30:12 literature_search     │
│  ...         │  📊 analyst-1      │  ...                            │
│              │  gemini-3-pro      │                                 │
│              │  "I'd like to..."  │                                 │
└──────────────┴────────────────────┴─────────────────────────────────┘
```

**Columns:**
- **Agents** --- Shows each agent on the team with their role icon and status (active/idle).
- **Agent Messages** --- Displays the most recent agent outputs with role, model name, and a preview of the response (first ~500 characters). Capped at 8 entries.
- **Events** --- Timestamped stream of system events (agent responses, literature searches, phase transitions, etc.). Capped at 50 entries.

**Header:**
- **Phase bar** --- Horizontal progress through the research phases. Completed phases show a checkmark, the current phase is highlighted, and future phases are dimmed.
- **Stats bar** --- Elapsed time, papers produced, literature searches performed, and total token usage.

### Plain-Text Fallback

When the terminal is not a TTY (e.g., piped output, CI environments) or when `--verbose` is passed, the display falls back to plain-text output via `click.echo()`. All the same information is printed as sequential log lines.

### Final Summary

When a research cycle completes, the live display is replaced by a static summary panel showing the final outcome (published/rejected), total tokens used, elapsed time, and paper ID.

### Agent Theme

Each agent role has a distinct color and icon for visual identification:

| Role | Icon | Color |
|------|------|-------|
| Theorist | 🔭 | Blue |
| Analyst | 📊 | Orange |
| Experimentalist | 🧪 | Green |
| Skeptic | 🔍 | Red |
| Synthesizer | 🔗 | Purple |
| Writer | ✍️ | Cyan |
| Editor | 📋 | Yellow |
| Reviewer | ⚖️ | Magenta |

---

## 18. Citation Grounding & Seed Discovery

Paradigm can use the Perplexity API to ground papers in real arXiv literature and to pre-seed the literature corpus before agents begin.

### Citation Grounding

Citation grounding is a post-processing pipeline that runs after the writing phase assembles a paper draft. It uses the Perplexity `sonar-reasoning-pro` model to insert arXiv reference markers into the paper text.

**How it works:**

1. The paper is parsed into sections by `##` headers.
2. Only configured sections are processed (default: Introduction and Methods). Other sections are left untouched.
3. Each section is split into paragraphs. Headers, tables, images, display math (`$$`), and short lines are skipped.
4. For each paragraph, Perplexity is asked to add `[1]`, `[2]`, ... citation markers with corresponding arXiv references.
5. Citations are renumbered globally across all sections.
6. A bibliography section is appended to the paper with full arXiv metadata.

**Configuration:**

```yaml
citation:
  enable_citation_grounding: true
  perplexity_api_key_env: PERPLEXITY_API_KEY
  citation_sections:
    - introduction
    - methods
  max_retries_per_paragraph: 2
  perplexity_timeout: 120.0
```

**Requirements:** Set the `PERPLEXITY_API_KEY` environment variable.

### Seed Discovery

Seed discovery runs during the SEEDING phase, before agents begin ideation. It queries Perplexity to find the most relevant foundational papers for the seed topic and pre-populates the literature corpus.

**How it works:**

1. The seed prompt is sent to Perplexity with a discovery prompt requesting the 10 most relevant arXiv papers.
2. arXiv URLs are extracted from the response (both from API citation metadata and via regex fallback).
3. Discovered papers are fetched and ingested into the local corpus, making them immediately available to agents.

**Configuration:**

```yaml
citation:
  enable_seed_discovery: true
  seed_discovery_max_papers: 10
```

This gives agents a head start on relevant literature without consuming their per-round search budgets during IDEATION.

---

## 19. Novelty Checking

Paradigm can assess the novelty of research ideas before committing to a full research cycle. Two backends are supported. Novelty checking is enabled in the shipped configs (`default.yaml`, `production.yaml`, `open.yaml`).

### Front-Loaded Assessment

The check is **front-loaded**: it runs during IDEATION, *before* hypotheses are locked in — after the tournament produces winners but before hypothesis selection — so a weak verdict can still change the work rather than just annotate the finished paper. The result is emitted as a `novelty.assessed` event and, in interactive mode, shown alongside the hypothesis-selection dialog.

If the verdict is **weak** (confidently NOT novel), a **differentiation directive** is queued as guidance for PLANNING: it names the closely-related prior work and instructs the team to explicitly position against it — state what is NEW (data, method, regime, or claim) and plan at least one analysis the prior work did not do.

### Semantic Scholar Mode (Default)

The default novelty checker uses a multi-step process:

1. **Query extraction** --- An LLM extracts 3-5 search queries from the idea text.
2. **Literature search** --- Each query is searched on Semantic Scholar (limit 10 results per query, up to 5 iterations).
3. **Deduplication** --- Results are deduplicated by paper ID.
4. **Novelty assessment** --- An LLM evaluates the idea against the discovered related work and returns a verdict (`NOVEL: yes/no`), confidence score (0.0-1.0), and reasoning.

**Configuration:**

```yaml
citation:
  enable_novelty_check: true       # code default: false; ON in shipped configs
  novelty_mode: semantic_scholar    # default
  novelty_max_iterations: 5
```

### FutureHouse Mode (Optional)

An alternative that uses the FutureHouse proprietary novelty checking API. Requires the optional `futurehouse_client` package and a FutureHouse API key.

```yaml
citation:
  enable_novelty_check: true
  novelty_mode: futurehouse
  futurehouse_api_key_env: FUTURE_HOUSE_API_KEY
```

### Output

Both modes return a `NoveltyResult` with:
- `is_novel` --- Boolean verdict
- `confidence` --- Confidence score (0.0-1.0)
- `related_work` --- Top 5 related paper titles
- `papers_found` --- Total papers found
- `source` --- Which backend was used

If novelty checking fails, the system defaults to assuming the idea is novel (with low confidence) and proceeds.

---

## 20. Agent Memory & Reflection

Agents build episodic memory across research cycles. Lessons, discoveries, strategies, and collaboration insights persist in ChromaDB and are retrieved via semantic search with recency decay.

### Memory Lifecycle

**End of cycle (reflection):**

After a research cycle completes (whether the paper is published or rejected), each agent that contributed undergoes a reflection step:

1. The agent's messages from the cycle are collected.
2. A reflection prompt (including the seed prompt, outcome summary, and agent role) is sent to an LLM (default: `claude-sonnet-4-5-20250929`, temperature 0.3).
3. The LLM extracts 3-5 episodic memories, each tagged with a type.
4. Memories are stored in ChromaDB with the agent ID and timestamp.

**Start of next cycle (retrieval):**

When building an agent's prompt for a new cycle:

1. The seed prompt is used as a semantic query against the agent's memory collection.
2. Results are re-ranked using a combined score: `similarity x recency_weight`.
3. The recency weight uses exponential decay: `0.5^(age_days / half_life_days)` (default half-life: 30 days).
4. The top 5 memories (by combined score) are formatted and injected into the agent's prompt, up to 2000 characters.

### Memory Types

| Type | Description |
|------|-------------|
| `insight` | A scientific insight or discovery made during research |
| `mistake` | An error or wrong approach that should be avoided |
| `strategy` | A methodological strategy that worked well |
| `collaboration` | An observation about working with other agents |

### Configuration

```yaml
memory:
  enabled: true
  max_memories_per_prompt: 5
  recency_half_life_days: 30.0
  reflection_model: claude-sonnet-4-5-20250929
  collection_name: agent_memories
  max_memory_chars: 2000
```

### CLI Commands

```bash
# List memories for a specific agent
paradigm memory list --agent theorist-0

# Semantic search across all agent memories
paradigm memory search --query "stellar pulsation period-luminosity"

# Prune old memories
paradigm memory clear --older-than 90d
```

### Key Properties

- **Per-agent isolation** --- Each agent sees only their own memories. A theorist's insights are not visible to the analyst.
- **Recency decay** --- Older memories fade: a 30-day-old memory has half the weight of a fresh one.
- **Bounded** --- Max 5 memories and 2000 characters per agent per prompt, preventing memory from dominating the context.
- **Non-fatal** --- Reflection failures (API errors, parsing issues) are logged but do not block the research cycle.

---

## 21. Web API

Paradigm includes an optional FastAPI backend that exposes REST endpoints and a WebSocket interface for building web-based frontends. This allows programmatic access to all Paradigm functionality and real-time monitoring of running research cycles.

### Setup

```bash
# Install API dependencies
pip install -e ".[api]"

# Start the development server
uvicorn backend.api.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive Swagger UI documentation.

### Key Capabilities

- **Create and manage research cycles** via REST endpoints
- **Start sessions** that run research cycles as background tasks
- **Monitor live progress** via WebSocket (agent outputs, phase transitions, round updates)
- **Intervene in real time** --- send messages to agents, redirect research, approve phase transitions
- **Browse results** --- list papers, view outputs, inspect session history
- **Checkpoint and fork** --- save session state and branch from checkpoints

### Core Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/research` | Create research cycle |
| GET | `/api/v1/research` | List cycles (paginated) |
| POST | `/api/v1/research/{id}/sessions` | Start a session |
| GET | `/api/v1/sessions/{id}` | Session state snapshot |
| WS | `/api/v1/sessions/{id}/ws` | Real-time WebSocket |
| GET | `/api/v1/papers` | List papers |
| GET | `/api/v1/agents` | List agent types |

### WebSocket Protocol

Connect to `ws://localhost:8000/api/v1/sessions/{session_id}/ws` to receive real-time updates:

**Server -> Client:**
- `session_state` --- Full state sync (sent on connect)
- `agent_output_stream` --- Streamed agent response chunks
- `agent_step_complete` --- Agent finished a step
- `phase_transition` --- Phase changed (e.g., ideation -> planning)
- `round_update` --- Round progress within a phase
- `approval_request` --- System needs user input (interactive mode)
- `notification` --- Informational events (literature search results, etc.)
- `error` --- Errors and warnings

**Client -> Server:**
- `approval_response` --- Respond to approval requests (continue/pause/abort)
- `session_control` --- Pause, resume, or checkpoint a session
- `user_intervention` --- Redirect, constrain, or inform an agent
- `user_message` --- Send a message to an agent or the orchestrator

### Authentication

By default, authentication is disabled for development. Set the `PARADIGM_API_KEY` environment variable to enable API key authentication via the `X-API-Key` header.

### Architecture

The API wraps existing Paradigm internals without modifying them:

- **SessionManager** manages running sessions as `asyncio.Task` background tasks
- **WebSocketDisplayAdapter** implements the same interface as the terminal `DisplayManager`, bridging all 100+ display methods to WebSocket broadcasts
- **InterventionHook bridge** converts the synchronous intervention callable to an async pattern backed by `asyncio.Event`, enabling frontend approval workflows

For full API reference with request/response examples, see [`docs/API.md`](API.md).

### Web UI (React Frontend)

Paradigm includes an optional React frontend for browser-based monitoring and control.

#### Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server starts on **http://localhost:3000** and proxies API requests to the backend at `localhost:8000`.

#### Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Overview of recent cycles, running sessions, and quick stats |
| `/research` | Research | Create and manage research cycles |
| `/session/:id` | Session | Real-time session monitoring and control |
| `/papers` | Papers | Browse papers with tabbed artifact viewer |
| `/agents` | Agents | View and configure agent models and parameters |
| `/settings` | Settings | Configure orchestrator, sandbox, literature, and other settings |

#### Key Capabilities

- **Live monitoring** --- real-time agent output streaming, phase progression, round counters, and token usage via WebSocket
- **Knowledge panel** --- view the evolving knowledge architecture (entities, hypotheses, evidence, open questions) as agents work
- **Approval workflows** --- approve or reject phase transitions in interactive mode directly from the browser
- **Session control** --- pause, resume, or abort running sessions
- **Paper viewer** --- full Markdown + LaTeX math rendering with table of contents and export
- **Research artifact browser** --- tabbed viewer for all paper artifacts: literature searches (with arXiv links), peer reviews, conversation transcript, experiment code, and generated figures
- **Literature panel** --- clickable papers count in session stats opens a slide-over panel showing papers found during research with arXiv abstract/PDF links
- **Agent configuration** --- change models, providers, and token budgets per agent role
- **Settings page** --- configure orchestrator, sandbox, literature, knowledge, memory, citation, and journal settings (including the correctness-kernel + output-quality toggles below) with per-section auto-save/reset
- **Mode toggle** --- switch between production and testing configurations at runtime

See [`frontend/README.md`](../frontend/README.md) for full setup, directory structure, and architecture details.

---

## 22. Correctness Kernel & Output Formats

Empirical science has no proof checker, so Paradigm provides *proxy* gates that
harden correctness and output quality. Every feature here defaults to off in code, so
the legacy autonomous pipeline is unchanged until a config enables it — but the
**verification kernel is ON in the shipped configs** (`default.yaml`, `production.yaml`,
`open.yaml`; `fast.yaml` keeps it off because re-execution is slow). Toggle them in
`configs/default.yaml`, a custom config (`paradigm --config my.yaml run ...`), or the web
**Settings page** (Orchestrator / Knowledge / Citation / Journal sections). A deep
implementation write-up lives in [`docs/correctness-kernel-implementation.md`](correctness-kernel-implementation.md).

### Pre-registration / falsifiability

Before EXECUTION (a new `PRE_REGISTRATION` phase), the theorist freezes one
machine-readable, falsifiable `PredictionRule` per hypothesis — a metric token, a
direction (`inside`/`outside`/`greater`/`less`) with bounds, and a **required** refutation
condition. Hypotheses with no admissible rule are dropped. After execution the verdict
(`confirmed`/`refuted`/`inconclusive`) is computed *only* from the frozen rule, so results
can't be reinterpreted; refuted/negative results are reported honestly.

| Key (`knowledge.`) | Type | Default | Description |
|---|---|---|---|
| `enable_preregistration` | bool | `false` | Turn on the pre-registration phase |
| `prereg_require_refutation` | bool | `true` | Drop hypotheses lacking a refutation condition |
| `prereg_on_empty` | str | `advisory` | `advisory` (warn + continue) or `blocking` (abort) when no rule survives |

### Verification kernel (re-execution as ground truth)

When enabled, each successful experiment re-runs in a **fresh, seeded sandbox workspace**
(`verify/<thread>`, a new `VERIFICATION` phase, using the configured sandbox settings) and
is accepted only if its `RESULT[label]=value` tokens reproduce within tolerance —
otherwise it is demoted so the writer can't cite it. Enabling verification also activates
the **console-as-data-bus contract**: experiments must print every key number as
`RESULT[label]=value`.

| Key (`orchestrator.`) | Type | Default | Description |
|---|---|---|---|
| `enable_verification` | bool | `false` (ON in shipped configs) | Re-execute results to verify reproducibility |
| `verification_tolerance` | float | `1e-6` | Relative tolerance for reproducing metrics |
| `verification_seed` | int | `12345` | Seed injected before re-execution |
| `verification_reexec_budget` | int | `20` | Cap on re-runs per cycle |
| `abort_on_verification_failure` | bool | `true` | Abort before WRITING if nothing reproduces |

### Tree-search & step-restart

| Key (`orchestrator.`) | Type | Default | Description |
|---|---|---|---|
| `enable_best_first_nodes` | bool | `false` | Prefer non-buggy experiments within a round |
| `enable_step_restart` | bool | `false` | Resume failed multi-step experiments from prior artifacts |
| `debug_buggy_node_prob` | float | `0.3` | Chance a ready buggy node is promoted for a retry |
| `max_step_restarts_per_experiment` | int | `2` | Per-experiment restart budget |

### Hybrid human gates & provenance

`human_gate_mode` adds human checkpoints at `problem_selection`, `pre_registration`, and
`final_verification`. `advisory` surfaces the decision without blocking; `blocking` defers
to the intervention hook (and **continues with a logged warning if no hook is registered**,
so autonomous runs never deadlock). Each paper records an engine-written provenance chain
(`framed_by` / `registered_by` / `verified_by`).

| Key (`orchestrator.`) | Type | Default | Description |
|---|---|---|---|
| `human_gate_mode` | str | `off` | `off` / `advisory` / `blocking` |
| `human_gate_points` | list | all three | Which gates are active |

### Output formats

| Key | Type | Default | Description |
|---|---|---|---|
| `orchestrator.enable_multimodal_review` | bool | `false` | Editor visually inspects the actual figures |
| `orchestrator.multimodal_review_role` | str | `editor` | Role whose model performs the figure review |
| `orchestrator.max_review_figures` | int | `6` | Cap on images sent to the vision model |
| `journal.enable_latex_output` | bool | `false` | Also write a journal-ready `.tex` |
| `journal.latex_journal` | str | `none` | Preset: `none` / `arxiv` / `neurips` |
| `journal.compile_pdf` | bool | `false` | Also compile the `.tex` to PDF (needs a LaTeX engine) |
| `citation.drop_unresolved_citations` | bool | `false` | Drop refs that don't resolve (vs. bare URLs) |

### Quality Ledger

With `orchestrator.enable_quality_ledger: true` (ON in the shipped configs), **every
finished paper is auto-scored** by the config role `judge` on five dimensions —
novelty, rigor, clarity, significance, honesty (each 1–10) — plus a composite
(mean × 10) and a one-sentence justification. The scores are:

- stored on the paper row (`papers.judge_scores`, JSON — includes `composite` and `judge_model`),
- emitted as a `paper.judged` event on the thread's event stream,
- returned by the papers API (`judge_scores` on paper responses) and shown as **badges** in the web UI.

The judge model is deliberately **fixed across model tiers** (`gemini-3.5-flash` in both
shipped configs) so quality is trendable across cycles, configs, and tiers. Scoring is
best-effort: a judge failure is logged and skipped, never breaking a cycle.

| Key (`orchestrator.`) | Type | Default | Description |
|---|---|---|---|
| `enable_quality_ledger` | bool | `false` (ON in shipped configs) | Auto-judge every finished paper |

### Reproducibility evaluation (`paradigm eval`)

Score papers on a deterministic + optional LLM-judge rubric.

```bash
paradigm eval                              # score papers already in the DB (offline)
paradigm eval --judge --limit 20           # add the LLM taste judge
paradigm eval --live 3 --split selection --judge   # run fresh cycles + score them
```

| Option | Description |
|---|---|
| `--judge` / `--judge-role` | Add the LLM taste judge (novelty/rigor/clarity/significance/honesty) |
| `--limit N` | Cap papers scored (offline) |
| `--include-external` | Also score ingested external papers |
| `--live N` | Run N fresh cycles end-to-end and score the output |
| `--split {train,selection,test}` | Seed split to draw `--live` cycles from (hash-fixed; the test split never leaks) |

New metrics include `reproduction_pass_rate` (accepted/total verification records) and the
pre-registration verdict; the judge can be calibrated against the real published/rejected
boundary. Reports are written to `data/eval/`.
