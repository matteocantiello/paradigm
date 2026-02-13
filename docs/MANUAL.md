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
9. [Configuration Reference](#9-configuration-reference)
10. [Data and Storage](#10-data-and-storage)
11. [Cost Management](#11-cost-management)
12. [Docker Sandbox](#12-docker-sandbox)
13. [Troubleshooting](#13-troubleshooting)
14. [Recipes](#14-recipes)

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
- Anthropic API key
- Docker (optional, for computational sandbox)

### From zero to first paper in 5 commands

```bash
# 1. Clone and install
git clone https://github.com/matteocantiello/paradigm.git
cd paradigm
pip install -e ".[dev]"

# 2. Set your API key (or create a .env file with ANTHROPIC_API_KEY=sk-ant-...)
export ANTHROPIC_API_KEY="sk-ant-..."

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

The orchestrator initializes a research thread, creates a unique thread ID, registers the agent team, and optionally searches the literature for relevant context. It also searches the graveyard for lessons from past failed or rejected research related to the seed prompt.

**Input:** Seed prompt + mode
**Output:** Thread ID, initial literature context, graveyard context (if any)
**Agents:** None (orchestrator-only)

#### IDEATION

Agents propose and debate hypotheses through structured discussion rounds. In round 1, each agent proposes 1-2 concrete, testable hypotheses. If lessons from past failed research were found during seeding, they are also included in the round 1 prompt, clearly marked as non-citable context. In later rounds, agents critique, build on, and prioritize ideas.

**Input:** Seed prompt + literature context + graveyard lessons (if any)
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
3. Each code block is safety-scanned, then executed in Docker. If the code is rejected by the safety scanner or fails at runtime, the agent receives error feedback and can retry (up to 2 retries per experiment).

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
3. **Refinement** (optional) --- Additional rounds of polishing.

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

## 9. Configuration Reference

Configuration is loaded from a YAML file (default: `configs/default.yaml`). Override with `--config` or the `PARADIGM_CONFIG` environment variable.

### `agent` --- Agent Behavior

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_model` | string | `claude-sonnet-4-5-20250929` | Claude model for all agents |
| `opus_model` | string | `claude-opus-4-6-20250514` | Higher-capability model (available for special tasks) |
| `max_tokens` | int | `4096` | Default max output tokens per API call |
| `temperature` | float | `1.0` | Sampling temperature for agent responses |
| `token_budget_per_thread` | int | `1000000` | Max tokens allowed per research thread |
| `token_budget_per_agent` | int | `100000` | Max tokens allowed per individual agent |

### `orchestrator` --- Orchestration Behavior

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_rounds_per_phase` | int | `10` | Rounds of agent discussion per phase (IDEATION, PLANNING) |
| `enable_checkpointing` | bool | `true` | Save checkpoint summaries during phases |
| `checkpoint_interval` | int | `5` | Save checkpoint every N rounds |
| `enable_writing` | bool | `true` | Enable the WRITING phase (set `false` to stop after PLANNING) |
| `max_review_iterations` | int | `1` | Max internal review-revision loops |
| `enable_peer_review` | bool | `true` | Enable the peer review pipeline after internal review |
| `num_reviewers` | int | `2` | Number of independent peer reviewers |
| `max_revision_rounds` | int | `2` | Max peer-review revision loops before final decision |
| `enable_experimentation` | bool | `true` | Enable EXECUTION phase for modes with an experimentalist |
| `max_experiment_rounds` | int | `3` | Max rounds of experiment proposal/execution in EXECUTION phase |

### `literature` --- Literature Search

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `arxiv_rate_limit` | float | `3.0` | Seconds between arXiv API requests |
| `max_results_per_search` | int | `20` | Maximum papers returned per search |
| `enable_pdf_fetch` | bool | `true` | Fetch and extract PDF text from arXiv |
| `embedding_model` | string | `sentence-transformers/all-MiniLM-L6-v2` | Model for paper embeddings in ChromaDB |

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
| `ANTHROPIC_API_KEY` | Claude API key (**required**) | --- |
| `PARADIGM_CONFIG` | Path to config YAML file | `configs/default.yaml` |
| `PARADIGM_DATA_DIR` | Override data directory | `./data` |
| `PARADIGM_LOG_LEVEL` | Logging level | `INFO` |

You can also place your API key in a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 10. Data and Storage

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

## 11. Cost Management

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

## 12. Docker Sandbox

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

## 13. Troubleshooting

### Common Errors

#### `ANTHROPIC_API_KEY must be set in environment or config file`

Your API key is not configured. Either:
- Set the environment variable: `export ANTHROPIC_API_KEY="sk-ant-..."`
- Create a `.env` file in the project root with `ANTHROPIC_API_KEY=sk-ant-...`

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

## 14. Recipes

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
