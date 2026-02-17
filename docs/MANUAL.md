# Paradigm Operations Manual

A comprehensive guide for scientist-operators running Paradigm, the agentic science platform.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Quick Start](#2-quick-start)
3. [CLI Reference](#3-cli-reference)
4. [Operating Modes](#4-operating-modes)
5. [The Research Cycle](#5-the-research-cycle)
6. [The Agent Team](#6-the-agent-team)
7. [Interactive Mode](#7-interactive-mode)
8. [Multi-Cycle Research](#8-multi-cycle-research)
9. [Literature Search System](#9-literature-search-system)
10. [Configuration Reference](#10-configuration-reference)
11. [Data and Storage](#11-data-and-storage)
12. [Cost Management](#12-cost-management)
13. [Docker Sandbox](#13-docker-sandbox)
14. [Troubleshooting](#14-troubleshooting)
15. [Recipes](#15-recipes)
16. [Terminal Display System](#16-terminal-display-system)
17. [Citation Grounding & Seed Discovery](#17-citation-grounding--seed-discovery)
18. [Novelty Checking](#18-novelty-checking)
19. [Agent Memory & Reflection](#19-agent-memory--reflection)

---

## 1. Overview

Paradigm is an agentic science platform where teams of AI agents collaborate to perform research, write papers, and submit them to peer review. Named after Thomas Kuhn, it implements the insight that paradigm shifts emerge from communities of researchers, not individuals.

**The core loop:**
You provide a research question or topic. A team of specialized AI agents (theorist, analyst, synthesizer, experimentalist, writer, skeptic) discuss the topic, search the literature, form a research plan, draft a paper, and submit it to independent peer reviewers (editor, reviewers). Published papers enter an internal corpus where future research cycles can discover and cite them, building an interconnected body of knowledge over time.

**Key properties:**
- **Domain-agnostic** --- no hardcoded scientific assumptions. Works for astrophysics, biology, economics, or any field.
- **Full pipeline** --- from seed question to published, peer-reviewed paper in the internal corpus.
- **Transparent** --- every agent message, token cost, and phase transition is logged. You can inspect, pause, and steer at any point.
- **Composable** --- agents are equipped with scientific skills from a library of 142 skill definitions that shape their expertise.

---

## 2. Quick Start

### Prerequisites

- Python 3.11+ (3.12+ recommended)
- Anthropic API key (for default mode)
- Google Gemini API key (for default mode)
- Together.ai API key (for testing mode)
- Docker (optional, for computational sandbox)

### From zero to first paper in 5 commands

```bash
# 1. Clone and install
git clone https://github.com/matteocantiello/paradigm.git
cd paradigm
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
| `--mode` | Choice | `directed` | Operating mode: `directed`, `explore`, `hypothesis`, `experimental`, `replication` |
| `--prompt` | Text | --- | Research prompt or question. **Required** for `directed` mode (unless `--prompt-file` is used). |
| `--prompt-file` | Path | --- | Read research prompt from a file (e.g., `prompt.md`). Mutually exclusive with `--prompt`. |
| `--topic` | Text | --- | Research topic. **Required** for `explore` mode. |
| `--rounds` | Integer | config value (10) | Rounds per phase. Overrides `orchestrator.max_rounds_per_phase`. |
| `--interactive` | Flag | off | Pause for confirmation before each major phase transition. |

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

## 4. Operating Modes

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

---

## 5. The Research Cycle

Every research cycle progresses through a series of phases. The orchestrator manages transitions, and each phase has specific agents, prompts, and outputs.

### Phase Flow

```
SEEDING
   |
IDEATION  (N rounds of structured agent discussion)
   |
PLANNING  (N rounds of research plan development)
   |
   +--[experimentalist on team + sandbox enabled]--+
   |                                               |
   |                                         EXECUTION
   |                                         (propose code, run in Docker,
   |                                          retry on failure, collect results)
   |                                               |
   +-----------------------------------------------+
   |
WRITING   (section drafting -> assembly -> optional refinement)
   |        (execution results injected into RESULTS/METHODS sections)
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

If **Perplexity seed discovery** is enabled (`citation.enable_seed_discovery: true`), the orchestrator queries the Perplexity API to discover foundational papers on the seed topic and pre-populates the literature corpus before agents begin. This gives agents a head start on relevant literature without consuming their search budgets. See [Citation Grounding & Seed Discovery](#17-citation-grounding--seed-discovery) for details.

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
**Rounds:** Configurable via `max_experiment_rounds` (default: 3)

#### WRITING

Three-step process:

1. **Section Drafting** --- Each agent drafts their assigned sections:
   - **Writer:** Abstract, Introduction, Conclusion
   - **Theorist:** Methods (with experiment descriptions if EXECUTION ran)
   - **Analyst:** Results (with computational results if EXECUTION ran)
   - **Synthesizer:** Discussion
2. **Assembly** --- The writer agent combines all sections into a coherent paper, harmonizing style and adding transitions. If figures were generated during EXECUTION, they are referenced as `![Figure N](figures/filename.png)`.
3. **LaTeX Math Enforcement** --- A post-processing pass converts any remaining Unicode math characters (Greek letters, subscripts, superscripts, operators) to LaTeX notation, preserving existing `$...$` delimiters. See [Terminal Display System](#16-terminal-display-system) section note.
4. **Citation Grounding** (if enabled) --- The Perplexity API inserts arXiv reference markers (`[1]`, `[2]`, ...) into citable sections (default: Introduction, Methods) and appends a bibliography. See [Citation Grounding & Seed Discovery](#17-citation-grounding--seed-discovery).
5. **Refinement** (optional) --- Additional rounds of polishing.

**Output:** Complete paper draft saved as `paper-<id>` in the database and as a `.md` file in `data/papers/`. Papers with figures use a subdirectory layout: `data/papers/<paper-id>/<paper-id>.md` with a `figures/` subdirectory.

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

#### REJECTED

The paper is rejected. The orchestrator:
- Sets paper status to `rejected`
- Stores the paper in the graveyard with failure reasons and lessons learned
- Lessons are available for future research cycles to learn from

---

## 6. The Agent Team

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

## 7. Interactive Mode

Run with `--interactive` to pause for confirmation before major phase transitions.

```bash
paradigm run --mode directed --prompt "Your question" --interactive
```

### Intervention Points

The system pauses at these transition points:
1. **IDEATION -> PLANNING** --- After ideation completes, before planning begins
2. **PLANNING -> EXECUTION** --- (experimental/replication modes only) After the research plan is finalized, before computational experiments
3. **EXECUTION -> WRITING** or **PLANNING -> WRITING** --- Before paper drafting begins
4. **INTERNAL_REVIEW -> SUBMITTED** --- After internal review, before submission to peer review

### At Each Pause

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

### Keyboard Interrupt

You can press `Ctrl+C` at any time to interrupt a running cycle. The thread will be left in whatever state it was in at the time of interruption.

---

## 8. Multi-Cycle Research

Paradigm's internal corpus grows over time. Published papers are indexed in ChromaDB and become discoverable by future research cycles.

### How It Works

1. **Cycle 1** runs and publishes a paper (e.g., `paper-abc123def456`)
2. The paper is embedded in ChromaDB with its title and abstract
3. **Cycle 2** starts. During the SEEDING phase, the orchestrator searches the corpus for literature relevant to the new seed prompt
4. If cycle 1's paper is relevant, it appears in the literature context provided to agents
5. Agents can cite it (using its internal ID `paper-abc123def456` or arXiv IDs)
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

## 9. Literature Search System

Paradigm implements a multi-backend, budget-constrained literature search system that agents drive through action tags in their responses. Rather than the orchestrator searching upfront, agents decide what to search for and when, guided by stall detection and budget enforcement.

### Action Tags

Agents embed these tags in their natural-language responses:

| Tag | Purpose | Example |
|-----|---------|---------|
| `[SEARCH: query]` | Keyword search across arXiv + local corpus | `[SEARCH: Cepheid period-luminosity metallicity]` |
| `[FOLLOW: arxiv_id]` | Get papers cited by this paper (references) | `[FOLLOW: 2301.12345]` |
| `[CITED_BY: arxiv_id]` | Get papers that cite this paper | `[CITED_BY: 1903.09534]` |
| `[READ: arxiv_id]` | Deep-read key sections of a paper | `[READ: 2301.12345]` |

After every agent response, the orchestrator parses these tags and executes the corresponding actions. Results are appended to the literature context and included in subsequent agent prompts.

**Search-enabled phases:** IDEATION, PLANNING, EXECUTION. Other phases (WRITING, PEER_REVIEW, etc.) disable literature actions.

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

---

## 10. Configuration Reference

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

**Default mode:**

| Role | Provider | Model |
|------|----------|-------|
| Theorist, Experimentalist, Analyst, Synthesizer, Writer | Anthropic | `claude-opus-4-6` |
| Skeptic, Editor | Google | `gemini-3-pro-preview` |

**Testing mode** (`--testing` flag) --- eliminates Anthropic and Google API calls for cost-free iteration:

| Role | Provider | Model |
|------|----------|-------|
| Theorist, Experimentalist, Analyst, Synthesizer, Writer, Editor | Together | `deepseek-ai/DeepSeek-V3.1` |
| Skeptic | Together | `Qwen/Qwen3-235B-A22B-Thinking-2507` |

Overrides are configured in the `agent.overrides` section of the YAML config. Testing overrides are in the `testing_overrides` section and are applied when the `--testing` CLI flag is passed.

### `orchestrator` --- Orchestration Behavior

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_rounds_per_phase` | int | `10` | Rounds of agent discussion per phase (IDEATION, PLANNING) |
| `enable_checkpointing` | bool | `true` | Save checkpoint summaries during phases |
| `checkpoint_interval` | int | `5` | Save checkpoint every N rounds |
| `enable_writing` | bool | `true` | Enable the WRITING phase (set `false` to stop after PLANNING) |
| `max_review_iterations` | int | `3` | Max internal review-revision loops |
| `enable_peer_review` | bool | `true` | Enable the peer review pipeline after internal review |
| `num_reviewers` | int | `2` | Number of independent peer reviewers |
| `max_revision_rounds` | int | `2` | Max peer-review revision loops before final decision |
| `enable_experimentation` | bool | `true` | Enable EXECUTION phase for modes with an experimentalist |
| `max_experiment_rounds` | int | `3` | Max rounds of experiment proposal/execution in EXECUTION phase |
| `max_searches_per_round` | int | `3` | Max `[SEARCH: ...]` requests processed per round (resets each round) |

### `literature` --- Literature Search

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `arxiv_rate_limit` | float | `3.0` | Seconds between arXiv API requests |
| `max_results_per_search` | int | `50` | Maximum papers returned per search |
| `enable_pdf_fetch` | bool | `true` | Fetch and extract PDF text from arXiv |
| `embedding_model` | string | `sentence-transformers/all-MiniLM-L6-v2` | Model for paper embeddings in ChromaDB |
| `follow_budget_per_round` | int | `3` | Max `[FOLLOW:]` requests per round |
| `cited_by_budget_per_round` | int | `2` | Max `[CITED_BY:]` requests per round |
| `read_budget_per_round` | int | `5` | Max `[READ:]` requests per round |
| `max_read_chars` | int | `8000` | Character limit for deep-read extraction |
| `max_citation_results` | int | `10` | Papers returned per `[CITED_BY:]` |
| `max_reference_results` | int | `20` | Papers returned per `[FOLLOW:]` |

### `sandbox` --- Docker Sandbox

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable Docker sandbox for code execution |
| `image_name` | string | `paradigm-sandbox:latest` | Docker image name |
| `network_mode` | string | `none` | Docker network mode (`none` = no network access) |
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
| `enable_novelty_check` | bool | `false` | Enable novelty assessment during ideation |
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

## 11. Data and Storage

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

---

## 12. Cost Management

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

## 13. Docker Sandbox

The computational sandbox executes Python code in isolated Docker containers with no network access.

### Building the Image

```bash
# Build from the project root
docker build -t paradigm-sandbox:latest -f docker/Dockerfile.sandbox .
```

The sandbox image includes: Python 3.12, NumPy, SciPy, Matplotlib, Pandas, scikit-learn, SymPy, Astropy.

### Security Model

- **No network access:** Containers run with `--network=none`
- **Resource limits:** CPU (2 cores), memory (2 GB), execution timeout (300s)
- **Non-root user:** Code runs as an unprivileged user
- **Pre-execution safety scan:** AST-based code scanner rejects patterns like `os.system()`, `subprocess`, network calls, and sandbox escape attempts
- **Output size limits:** Max 10 MB of output per execution

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
  network_mode: "none"
  cpu_limit: 2.0           # CPU cores
  memory_limit: "2g"       # Container memory limit
  execution_timeout: 300   # Seconds before timeout
  max_output_size: 10485760  # 10 MB max output
```

---

## 14. Troubleshooting

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

## 15. Recipes

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

### Recipe 8: Computational Experiments with Prompt File

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

## 16. Terminal Display System

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

## 17. Citation Grounding & Seed Discovery

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

## 18. Novelty Checking

Paradigm can assess the novelty of research ideas before committing to a full research cycle. Two backends are supported.

### Semantic Scholar Mode (Default)

The default novelty checker uses a multi-step process:

1. **Query extraction** --- An LLM extracts 3-5 search queries from the idea text.
2. **Literature search** --- Each query is searched on Semantic Scholar (limit 10 results per query, up to 5 iterations).
3. **Deduplication** --- Results are deduplicated by paper ID.
4. **Novelty assessment** --- An LLM evaluates the idea against the discovered related work and returns a verdict (`NOVEL: yes/no`), confidence score (0.0-1.0), and reasoning.

**Configuration:**

```yaml
citation:
  enable_novelty_check: true       # default: false
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

## 19. Agent Memory & Reflection

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
