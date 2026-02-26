<p align="center">
  <h1 align="center">Paradigm</h1>
  <p align="center">
    <strong>An agentic science platform where AI agents collaborate to do research, write papers, and submit them to peer review.</strong>
  </p>
  <p align="center">
    <a href="https://github.com/matteocantiello/paradigm/actions/workflows/ci.yml"><img src="https://github.com/matteocantiello/paradigm/workflows/CI/badge.svg" alt="CI"></a>
    <a href="https://github.com/matteocantiello/paradigm/actions/workflows/lint.yml"><img src="https://github.com/matteocantiello/paradigm/workflows/Lint/badge.svg" alt="Lint"></a>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  </p>
</p>

---

Give Paradigm a research question and it assembles a team of AI agents --- theorist, analyst, experimentalist, skeptic, synthesizer, writer --- that debate hypotheses, search the literature, run computational experiments in a sandboxed environment, draft a paper, and submit it to AI peer review. It can also produce comprehensive literature reviews that survey and synthesize existing work without running experiments. Published papers enter an internal corpus that future research cycles can cite and build upon.

Named after Thomas Kuhn --- paradigm shifts emerge from communities of researchers, not individuals.

## The Research Loop

```
                    +-----------+
                    |   Seed    |  You provide a research question,
                    |  Prompt   |  topic, or hypothesis
                    +-----+-----+
                          |
                    +-----v-----+
                    |  IDEATION  |  Agents debate hypotheses,
                    |            |  challenge each other [CHALLENGE: ...]
                    +-----+-----+
                          |
                    +-----v-----+
                    |  PLANNING  |  Concrete research plan:
                    |            |  experiments, data needs, success criteria
                    +-----+-----+
                          |
               +----------+----------+
               |                     |
         +-----v-----+        +-----v-----+
         | EXECUTION  |        | LITERATURE |  Agents search arXiv,
         | Sandboxed  |        |  Review    |  fetch PDFs, build
         | Docker     |        |            |  citation context
         | experiments|        +-----+------+
         +-----+-----+              |
               |          +----------+
               |          |
         +-----v----------v+
         |    WRITING       |  Section drafting (each agent writes
         |                  |  to their expertise), assembly, figures
         +--------+---------+
                  |
         +--------v---------+
         | INTERNAL REVIEW   |  Editor reviews, requests revisions
         +--------+---------+
                  |
         +--------v---------+
         |   PEER REVIEW     |  Independent reviewer agents score
         |                   |  novelty, rigor, clarity, significance
         +---+--------+-----+
             |        |
      +------v--+  +--v-------+
      |PUBLISHED|  | REVISION |---> resubmit
      |         |  +----------+
      +---------+
```

## Quick Start

```bash
# Clone and install
git clone https://github.com/matteocantiello/paradigm.git
cd paradigm
pip install -e ".[dev]"

# Set your API keys
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="..."

# Run a research cycle
paradigm run --mode directed \
  --prompt "Explain the period-luminosity relation for Cepheids" \
  --rounds 2

# Run a literature review
paradigm run --mode review \
  --prompt "Survey recent advances in asteroseismology of red giants"

# Use a detailed prompt from a file
paradigm run --mode directed --prompt-file prompt.md

# Start fresh (ignore previously published Paradigm papers)
paradigm run --mode directed --prompt "New topic" --fresh-corpus

# List produced papers
paradigm papers

# View a paper
paradigm paper <paper-id>
```

For detailed setup (Docker sandbox, multi-provider config, etc.), see [`INSTALL.md`](INSTALL.md).

## Operating Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `directed` | Full team investigates a specific question | "Explain the period-luminosity relation for Cepheids" |
| `explore` | Broad exploration of a topic area | "massive star variability" |
| `hypothesis` | Focused team tests a specific hypothesis | "Convective overshooting extends MS lifetime by >20%" |
| `experimental` | Includes experimentalist + Docker sandbox | Computationally-driven research |
| `replication` | Attempts to reproduce a known result | Verification and extension |
| `review` | Comprehensive literature review and field synthesis | "Survey recent advances in asteroseismology" |

## Agent Team

Each research cycle assembles a team of specialized agents. Every agent has a distinct system prompt, scientific skills, and episodic memory across cycles.

| Agent | Role |
|-------|------|
| **Theorist** | Proposes hypotheses, builds theoretical frameworks |
| **Analyst** | Designs methodology, analyzes data, statistical rigor |
| **Experimentalist** | Writes and runs code in the sandboxed environment |
| **Skeptic** | Challenges assumptions, identifies weaknesses, triggers debates |
| **Synthesizer** | Connects ideas across domains, resolves conflicts |
| **Writer** | Drafts and assembles the paper |
| **Editor** | Internal quality review before submission |
| **Reviewer** | Independent peer review with structured scoring |

Agents can challenge each other mid-discussion using `[CHALLENGE: agent-id: reason]` tags, triggering structured debates with synthesis.

## Multi-Provider LLM Support

Paradigm supports multiple LLM backends. Assign different models to different agent roles for cost savings or epistemic diversity:

```yaml
# configs/default.yaml
providers:
  anthropic:
    type: anthropic
    api_key_env: ANTHROPIC_API_KEY
  together:
    type: openai_compatible
    api_key_env: TOGETHER_API_KEY
    base_url: https://api.together.xyz/v1
    default_model: deepseek-ai/DeepSeek-R1

agent:
  default_provider: anthropic
  default_model: claude-sonnet-4-5-20250929
  overrides:
    skeptic:
      provider: together
      model: deepseek-ai/DeepSeek-R1
```

Install optional OpenAI-compatible provider support with:

```bash
pip install -e ".[openai]"
```

## Key Features

**Domain Profiles** --- Pluggable domain system adapts agent roles, document templates, literature sources, and review criteria to different fields. Built-in domains: science (arXiv, Semantic Scholar) and finance (SSRN, SEC EDGAR, FRED).

**Multi-Source Literature** --- Agents drive their own literature searches via `[SEARCH: query]`, `[FOLLOW: arxiv_id]`, `[CITED_BY: arxiv_id]`, and `[READ: arxiv_id]` tags. Sources include arXiv, Semantic Scholar, PubMed, bioRxiv, NASA ADS, and Google Scholar, with budget-constrained deduplication and stall detection that nudges agents from keyword search toward citation graph traversal.

**Computational Sandbox** --- Experimentalist agents write Python code that runs in isolated Docker containers (`--network=none` by default). Results, figures, and stdout feed back into the paper. Use `--network-access` to allow containers to reach the internet when experiments need external data or APIs.

**Literature Review Mode** --- The `review` mode produces comprehensive field surveys without running experiments. A dedicated document template (literature landscape, thematic analysis, critical assessment, future directions) and review-specific prompts guide systematic synthesis.

**Structured Peer Review** --- Independent reviewer agents score papers on novelty, rigor, clarity, and significance (1--10). Papers can be accepted, revised, or rejected. Rejected papers go to the "graveyard" where future cycles learn from past failures.

**Agent Memory** --- Agents build episodic memory across research cycles. Lessons, discoveries, and methodological insights persist and are retrieved via semantic search with recency decay.

**Citation Grounding** --- Optional Perplexity-based pipeline inserts real arXiv references into paper drafts and appends a bibliography. A separate seed discovery step pre-populates the corpus with foundational papers before agents begin.

**Focused Debates** --- When agents disagree, structured debates resolve conflicts through back-and-forth exchanges with synthesis, rather than averaging over disagreement.

**Intervention Hooks** --- Run in `--interactive` mode to approve or pause at each phase transition. Or provide a custom hook function for programmatic control.

## Architecture

```
Human Operator
      |
  Orchestrator (deterministic Python state machine)
      |
      |-- Research Agents (LLM API x N)
      |       |-- Claude (Anthropic)
      |       |-- Gemini (Google)
      |       |-- DeepSeek, Llama, Qwen, etc. (OpenAI-compatible)
      |       |
      |       +-- Sandbox (Docker containers, --network=none)
      |
      |-- Literature Service
      |       |-- arXiv, PubMed, bioRxiv, NASA ADS, Google Scholar
      |       |-- Semantic Scholar (citation graph traversal)
      |       |-- Perplexity (citation grounding + seed discovery)
      |       +-- ChromaDB (semantic search + internal corpus)
      |
      +-- Journal Pipeline
              |-- Editor (internal review)
              |-- Reviewers (structured peer review)
              +-- Publication / Graveyard
```

No frameworks (no LangChain, no CrewAI). The orchestrator is plain Python with explicit phase transitions, full token tracking, and structured JSON event logging.

## CLI Reference

| Command | Description |
|---------|-------------|
| `paradigm run` | Run a research cycle (`--mode`, `--prompt`, `--prompt-file`, `--rounds`, `--interactive`, `--network-access`, `--fresh-corpus`) |
| `paradigm status` | System statistics and token usage |
| `paradigm papers` | List papers (filter by `--status`) |
| `paradigm paper ID` | View or export a paper (`--export path.md`) |
| `paradigm inspect --thread ID` | Inspect a research thread checkpoint |
| `paradigm memory list --agent ID` | List episodic memories for an agent |
| `paradigm memory search --query Q` | Semantic search across agent memories |
| `paradigm memory clear --older-than 90d` | Prune old memories |

## Project Structure

```
src/paradigm/
  main.py              CLI entry point
  config.py            YAML config + provider registry
  orchestrator/        Phase state machine + engine
  agents/              Base agent, factory, prompts, skills, memory
    providers.py       Multi-backend LLM abstraction
  domains/             Pluggable domain profiles (science, finance)
    science/           Science domain: roles, modes, templates, prompts
    finance/           Finance domain: roles, modes, templates, prompts
  literature/          Multi-source search, embeddings, corpus, citations
  display/             Rich terminal UI (live layout, components, theme)
  sandbox/             Docker-based code execution
  journal/             Peer review + publication pipeline
  storage/             SQLite database, checkpoints, graveyard
  logging/             Structured JSON event logging
configs/               YAML configuration files
tests/                 pytest + pytest-asyncio
```

## Documentation

| Document | Description |
|----------|-------------|
| [`INSTALL.md`](INSTALL.md) | Installation guide (Python, Docker, API keys) |
| [`docs/MANUAL.md`](docs/MANUAL.md) | Operations manual (comprehensive usage guide) |
| [`ROADMAP.md`](ROADMAP.md) | Implementation roadmap and phase status |
| [`HISTORY.md`](HISTORY.md) | Complete development history |

## Status

**Alpha** --- The full research loop works end-to-end: seed question to published, peer-reviewed paper.

All major subsystems are implemented: multi-agent orchestration, multi-source literature search (arXiv, Semantic Scholar, PubMed, bioRxiv, NASA ADS), computational sandbox, paper writing, literature review mode, peer review with revision loops, citation grounding, agent episodic memory, focused debates, multi-provider LLM support, domain profiles, and intervention hooks.

## License

MIT
