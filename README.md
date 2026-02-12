# Paradigm

An agentic science platform where AI agents collaborate to advance scientific knowledge through hypothesis generation, computational experiments, peer-reviewed publication, and iterative research.

Named after Thomas Kuhn — paradigm shifts emerge from communities of researchers, not individuals.

## Status

🚧 **Pre-alpha** — Phase 0 complete. Core infrastructure and database ready.

**Completed:**
- ✅ Phase 0: Project skeleton, configuration, database, base agent class, event logging

**In Progress:**
- 🔄 Phase 1: Literature access (arXiv API, embeddings, corpus)

See `ROADMAP.md` for the full implementation plan.

## Quick Start

```bash
# Clone and install
cd paradigm

# Verify Phase 0 setup
python3 verify_setup.py

# Install dependencies (requires Python 3.11+)
pip install -e ".[dev]"

# Set your API key
export ANTHROPIC_API_KEY="your-key-here"

# Verify installation
python -m paradigm --help

# Run tests
pytest tests/

# (Future) Run a directed research session
paradigm run --mode directed --prompt "Develop a model to explain long-range dependence in stellar variability"
```

## Installation

### Requirements

- Python 3.11 or higher (3.12+ recommended)
- Docker (for computational sandbox in Phase 3)
- Anthropic API key

### Dependencies

Core dependencies:
- `anthropic` — Claude API SDK
- `chromadb` — Vector search for literature
- `pydantic` — Data validation
- `pyyaml` — Configuration files
- `docker` — Container management (Phase 3)
- `httpx` — HTTP client for arXiv API
- `pymupdf` — PDF text extraction
- `click` — CLI framework

Development dependencies:
- `pytest`, `pytest-asyncio` — Testing
- `ruff` — Linting and formatting

### Verify Setup

After installation, run the verification script:

```bash
python3 verify_setup.py
```

This checks that all directories, files, and basic imports are working correctly.

## How It Works

1. **You provide a seed** — a research question, a topic to explore, or a hypothesis to test
2. **A team of agents** (theorist, data analyst, literature synthesizer, experimentalist, skeptic, writer) discusses the topic, searches the literature, and forms a research plan
3. **Agents execute the plan** — running computational experiments in sandboxed Docker containers, analyzing results, and building arguments
4. **A paper is drafted** collaboratively by the team
5. **Separate journal agents** (editor, reviewers) evaluate the paper through peer review
6. **Published papers** enter the internal corpus, where future research cycles can cite and build upon them

## Architecture

See `.planning/SPEC.md` for the full specification.

```
Human Operator
      │
      ▼
  Orchestrator (Python) ──── Literature Service (arXiv API + Internal Corpus)
      │
      ├── Research Agents (Claude API × N)
      │       │
      │       └── Sandbox (Docker containers, --network=none)
      │
      └── Journal Agents (Editor + Reviewers)
              │
              └── Publication Pipeline → Internal Corpus (SQLite + ChromaDB)
```

## Documentation

- `.planning/SPEC.md` — Full system specification
- `.planning/ROADMAP.md` — Phased implementation plan with milestones
- `.planning/DECISIONS.md` — Architecture decision log
- `CLAUDE.md` — Instructions for Claude Code

## License

TBD
