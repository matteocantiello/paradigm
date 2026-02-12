# Paradigm

[![CI](https://github.com/matteocantiello/paradigm/workflows/CI/badge.svg)](https://github.com/matteocantiello/paradigm/actions/workflows/ci.yml)
[![Lint](https://github.com/matteocantiello/paradigm/workflows/Lint/badge.svg)](https://github.com/matteocantiello/paradigm/actions/workflows/lint.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An agentic science platform where AI agents collaborate to advance scientific knowledge through hypothesis generation, computational experiments, peer-reviewed publication, and iterative research.

Named after Thomas Kuhn --- paradigm shifts emerge from communities of researchers, not individuals.

## Status

**Alpha** --- The full research loop works end-to-end: seed question to published, peer-reviewed paper.

**Completed:**
- Phase 0: Foundation (project skeleton, config, database, base agent class, event logging)
- Phase 1: Literature access (arXiv API, embeddings, corpus, citations)
- Phase 2: Orchestrator + ideation loop (phases, scheduler, checkpoints, engine)
- Phase 3: Computational sandbox (Docker-based code execution)
- Phase 4: Writing + paper generation (section drafting, assembly, internal review)
- Phase 5: Peer review + publication (structured review, revision loop, publish/reject)
- Phase 6: Multi-cycle + polish (multi-cycle discovery, operating modes, intervention hooks, graveyard learning)

See `ROADMAP.md` for the full implementation plan.

## Quick Start

```bash
# Clone and install
git clone https://github.com/matteocantiello/paradigm.git
cd paradigm
pip install -e ".[dev]"

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run a directed research cycle (1 round per phase for a quick test)
paradigm run --mode directed --prompt "Explain the period-luminosity relation for Cepheids" --rounds 1

# List produced papers
paradigm papers

# View a paper
paradigm paper <paper-id>
```

See `INSTALL.md` for detailed installation instructions and `docs/MANUAL.md` for the full operations manual.

## How It Works

1. **You provide a seed** --- a research question, a topic to explore, or a hypothesis to test
2. **A team of agents** (theorist, analyst, synthesizer, experimentalist, skeptic, writer) discusses the topic, searches the literature, and forms a research plan
3. **Agents draft a paper** collaboratively, with each agent writing sections matching their expertise
4. **Separate journal agents** (editor, reviewers) evaluate the paper through structured peer review
5. **Published papers** enter the internal corpus, where future research cycles can cite and build upon them

## Architecture

```
Human Operator
      |
  Orchestrator (Python) ---- Literature Service (arXiv API + Internal Corpus)
      |
      |-- Research Agents (Claude API x N)
      |       |
      |       +-- Sandbox (Docker containers, --network=none)
      |
      +-- Journal Agents (Editor + Reviewers)
              |
              +-- Publication Pipeline -> Internal Corpus (SQLite + ChromaDB)
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `paradigm run` | Run a research cycle (modes: directed, explore, hypothesis, experimental, replication) |
| `paradigm status` | Show system statistics and token usage |
| `paradigm inspect --thread ID` | Inspect a research thread checkpoint |
| `paradigm papers` | List papers (filter by `--status`, limit with `--limit`) |
| `paradigm paper ID` | View a paper (export with `--export path.md`) |

## Documentation

- `docs/MANUAL.md` --- **Operations manual** (comprehensive guide for running the system)
- `INSTALL.md` --- Installation guide
- `ROADMAP.md` --- Implementation roadmap and phase status
- `.planning/SPEC.md` --- Full system specification
- `.planning/ARCHITECTURE.md` --- Component diagrams and data flows
- `.planning/DECISIONS.md` --- Architecture decision records
- `HISTORY.md` --- Complete development history (every prompt and decision)

## License

TBD
