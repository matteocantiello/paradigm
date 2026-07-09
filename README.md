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

Type a research question into the Paradigm web console and it assembles a team of AI agents --- theorist, analyst, experimentalist, skeptic, synthesizer, writer, editor, PI --- that debate hypotheses, search the literature, acquire real datasets, run computational experiments in a sandboxed environment, draft a paper, reflect on whether the evidence holds up, and submit the result to AI peer review. You watch it happen live, steer it mid-flight, and read the finished paper (with its digest, reviews, code, and figures) in the same interface. Published papers enter an internal corpus that future research cycles can cite and build upon.

Named after Thomas Kuhn --- paradigm shifts emerge from communities of researchers, not individuals.

## Quick Start

Paradigm is a web platform: a FastAPI backend wrapping the research engine, and a React frontend ("Observatory") for launching, steering, and reading research.

```bash
# Clone and set up the environment
git clone https://github.com/matteocantiello/paradigm.git
cd paradigm
conda create -n paradigm python=3.12 -y
conda activate paradigm
pip install -e ".[api,dev]"

# Set API keys (or put them in a .env file)
export ANTHROPIC_API_KEY="sk-ant-..."   # required
export GEMINI_API_KEY="..."             # reviewers + quality judge
export OPENAI_API_KEY="..."             # premium theorist/experimentalist
export TOGETHER_API_KEY="..."           # open-model tier

# Terminal 1: backend (port 8000)
uvicorn backend.api.main:app --reload --port 8000

# Terminal 2: frontend (port 3000)
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. The landing page is a prompt console: type a research question, optionally attach datasets, and hit **Launch** --- or **Configure** to open the setup wizard (supervision mode, model tier, research mode, agent team). The live session view shows a Mission Digest (what the team is doing now, what it has found so far, what comes next), a steering bar for typed guidance (delivered at the next agent turn), pause/resume, and decision dialogs when supervision is on.

The CLI still works as a headless alternative:

```bash
paradigm run --mode directed \
  --prompt "Explain the period-luminosity relation for Cepheids" \
  --data observations.csv

paradigm papers            # list produced papers
paradigm paper <paper-id>  # view one
```

For detailed setup (Docker sandbox, all provider keys, frontend build), see [`INSTALL.md`](INSTALL.md).

## The Research Loop

```
                     +-----------+
                     |   Seed    |  You provide a research question
                     |  Prompt   |  (refined into a research brief by a strong LLM)
                     +-----+-----+
                           |
                     +-----v-----+
                     | IDEATION  |  Agents debate hypotheses,
                     |           |  challenge each other [CHALLENGE: ...]
                     +-----+-----+
                           |        <- novelty check runs BEFORE selection
                     +-----v-----+
                     | PLANNING  |  Concrete research plan:
                     |           |  experiments, data needs, success criteria
                     +-----+-----+
                           |
                +----------+----------+
                |                     |
          +-----v------+       +-----v------+
          | EXECUTION  |       | LITERATURE |  Search arXiv, ADS, Semantic
     +--->| Sandboxed  |       |   Review   |  Scholar; fetch PDFs; acquire
     |    | Docker     |       |            |  datasets (VizieR, Zenodo)
     |    | experiments|       +-----+------+
     |    +-----+------+             |
     |          |                    |
     |   +------v-------+            |
     |   | VERIFICATION |            |  re-execute in a fresh sandbox;
     |   | re-execute   |            |  unreproduced results are demoted
     |   +------+-------+            |
     |          |          +---------+
     |          |          |
     |    +-----v----------v-+
     |    |     WRITING      |  Section drafting, assembly, figures
     |    +--------+---------+
     |             |
     |    +--------v---------+
     +----+  PI REFLECTION   |  proceed / loop back / call it
    loop  +--------+---------+  (loop back: more experiments or
    back           |             a re-plan; budgeted, max 2)
    (max 2)        | proceed
          +--------v---------+
          | INTERNAL REVIEW  |  Editor gates on Blocking vs Minor changes
          +--------+---------+
                   |
          +--------v---------+
          |   PEER REVIEW    |  Independent reviewer agents score
          |                  |  novelty, rigor, clarity, significance
          +----+--------+----+
               |        |
        +------v--+  +--v-------+
        |PUBLISHED|  | REVISION |---> resubmit (major revisions can
        | +judged |  +----------+     trigger new experiments)
        +---------+
```

The loop is deliberately non-linear. After writing, a PI agent (the strongest model in the tier) reads the draft and decides: **proceed** to review, **loop back** for more experiments or a re-plan (budgeted, max 2 loop-backs), or **call it**. Peer-review major revisions can trigger a deep revision that runs new experiments rather than just rewording. Every finished paper is scored by an independent LLM judge and carries its quality badges in the paper library.

## The Web Platform

**Prompt-first landing** --- The dashboard hero console: pose a question, attach data files, Launch. The **Configure** path opens the SetupWizard: prompt + datasets, then Supervision (Autonomous vs Interactive), Model tier (Top models vs Open models), research mode (directed / explore / test), then team selection and a final review step.

**Live session view** --- Mission Digest panel (Now / So far / Ahead), phase tracker, streaming agent output, experiment and draft panels, hypothesis tournament board, literature and knowledge graphs. The steering bar sends typed guidance that lands at the next agent turn; pause/resume works at round boundaries. In interactive mode, decision dialogs surface structured choices: hypothesis selection, experiment-plan approval, and the PI's reflection verdict. Unanswered decisions time out after 5 minutes and fall back to the agents' own choice.

**Papers view** --- Each paper opens with tabs: Paper, Digest (a plain-language summary generated from the final text), Literature, Reviews, Transcript, Code, and Figures. Judge-score badges show the quality ledger's ratings. Export as Markdown or PDF (server-side LaTeX compile).

**Replay** --- Finished runs can be replayed from their per-thread `events.jsonl` stream: scrub through the cycle's phases, decisions, and outputs after the fact.

## Model Tiers

The wizard offers two model tiers per cycle; both run the identical pipeline.

**Top models** (`configs/production.yaml`) --- frontier closed models, deliberately diverse across providers:

| Role | Model |
|------|-------|
| Theorist | `gpt-5.4` |
| Experimentalist | `gpt-5.5` |
| Analyst, Skeptic | `claude-sonnet-4-6` |
| Writer, PI, Prompt refiner | `claude-opus-4-8` |
| Editor | `claude-sonnet-5` |
| Synthesizer | `claude-haiku-4-5` |
| Reviewers, Judge | `gemini-3.5-flash` |

**Open models** (`configs/open.yaml`) --- open-weights models on Together serverless, roughly $3--6 per cycle (vs ~$15--25 on the premium mix): `GLM-5.2` (theorist, experimentalist, writer, PI), `Kimi K2.6` (skeptic, editor), `MiniMax-M3` (analyst, reviewers), `gpt-oss-120b` (synthesizer). Family diversity is deliberate --- the writer's family never grades its own paper.

The judge is pinned to the same model across tiers so quality-ledger scores stay comparable. Any role can be reassigned live from the Agents panel (Anthropic / OpenAI / Gemini / Together catalogs, key-gated).

## Real Data, Verified

Paradigm enforces a real-data mandate end to end:

**Data policy** --- `orchestrator.data_policy: real_only` by default. A provenance classifier labels every dataset an experiment touches (real / derived / resampled / synthetic), and fabricated data is excluded from the paper's evidence base.

**Data acquisition** --- Agents find and fetch real datasets themselves via `[DATASEARCH: query]` and `[FETCHDATA: id]` against wired repositories (VizieR/CDS catalog search, Zenodo records), or pull a specific file with `[DATA: url]`. Users can attach their own files (CLI `--data`, wizard upload); attached datasets get schema data cards --- column names, types, sample rows, and for CDS tables a ReadMe-derived `read_fwf` loading recipe --- so agents load them correctly on the first try.

**Verification kernel** --- On by default. Successful experiments are re-executed in a fresh sandbox; results that don't reproduce are demoted out of the evidence base so the writer can't cite them.

**Quality ledger** --- Every finished paper is automatically scored by an LLM judge on novelty, rigor, clarity, significance, and honesty (plus a composite), stored with the paper and shown as badges in the library.

**Grounded citations** --- The writer cites only from a numbered allow-list of papers the cycle actually discovered; the bibliography is compiled deterministically from that set, and fabricated inline arXiv ids are stripped. A novelty check runs before hypothesis selection, not after the paper is written.

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
| **Editor** | Internal quality gate (Blocking vs Minor changes; accept-with-minor) |
| **PI** | Post-writing reflection: proceed, loop back, or call it |
| **Reviewer** | Independent peer review with structured scoring |
| **Judge** | Scores finished papers for the quality ledger |

Agents can challenge each other mid-discussion using `[CHALLENGE: agent-id: reason]` tags, triggering structured debates with synthesis. Experiment prompts carry a statistical-standards directive (distribution-appropriate methods, effect sizes with bootstrap CIs instead of bare p-values, confound control, documented exclusions).

## Computational Sandbox

Experimentalist agents write Python that runs in isolated Docker containers. The default network mode is **`bridge`** --- experiments may fetch public datasets --- with hardening: dropped capabilities, `no-new-privileges`, pids limit, CPU/memory/timeout caps. This is strong isolation for a trusted group, not a multi-tenant boundary. The self-test configs pin `network_mode: "none"`, and the CLI `--network-access` flag exists for configs that default to `none`. Set `orchestrator.enable_experimentation: false` to disable code execution entirely.

## Key Features

**Domain Profiles** --- Pluggable domain system adapts agent roles, document templates, literature sources, and review criteria to different fields. Built-in domains: science (arXiv, Semantic Scholar) and finance (SSRN, SEC EDGAR, FRED).

**Multi-Source Literature** --- Agents drive their own literature searches via `[SEARCH:]`, `[FOLLOW:]`, `[CITED_BY:]`, and `[READ:]` tags. Sources include arXiv, Semantic Scholar, PubMed, bioRxiv, NASA ADS, and Google Scholar, with budget-constrained deduplication and stall detection that nudges agents from keyword search toward citation-graph traversal. Perplexity powers seed discovery (foundational papers pre-loaded at cycle start) and fallback citation grounding.

**Prompt preprocessing** --- A strong-LLM first pass turns the raw user prompt into a structured research brief (goals, constraints, candidate datasets) before the team sees it; the original prompt is preserved.

**Structured Peer Review** --- Independent reviewer agents score papers on novelty, rigor, clarity, and significance (1--10). Papers can be accepted, revised, or rejected; major revisions can trigger a deep revision with new experiments. Rejected papers go to the "graveyard" where future cycles learn from past failures. For literature-synthesis or theoretical cycles the review bar adapts --- it judges evidence by cited literature and reasoning rather than demanding experimental figures it can't have.

**Hypothesis Tournament + World Model** --- The world model is the single hypothesis ledger: restatements deduplicate at creation (embedding-based), an Elo tournament with Swiss pairing ranks the canonical set, and beliefs move `proposed -> supported / contradicted` through one auditable path as evidence lands.

**Agent Memory** --- Agents build episodic memory across research cycles. Lessons, discoveries, and methodological insights persist and are retrieved via semantic search with recency decay.

**Focused Debates** --- When agents disagree, structured debates resolve conflicts through back-and-forth exchanges with synthesis, rather than averaging over disagreement.

**Pre-registration (opt-in)** --- Freeze a machine-readable, falsifiable prediction per hypothesis before experiments run; the verdict (confirmed / refuted / inconclusive) is computed only against the frozen rule. (`knowledge.enable_preregistration`)

**Journal-ready LaTeX/PDF** --- Papers emit a journal-styled `.tex` alongside the markdown and compile to PDF when a LaTeX engine (tectonic / xelatex / pdflatex) is available; the web UI's PDF export compiles on demand.

**Reproducibility Evaluation** --- `paradigm eval` scores papers on a deterministic + LLM-judge rubric; `--live N --split {train,selection,test}` runs fresh cycles on held-out seed splits and reports reproduction-pass-rate.

## Operating Modes

The web wizard offers three modes per cycle:

| Mode | Description |
|------|-------------|
| `directed` | Full team investigates a specific question |
| `explore` | Open-ended exploration of a topic area |
| `test` | Quick test run with minimal rounds |

The CLI supports additional modes: `hypothesis` (test a specific claim), `experimental` (computation-first), `replication` (reproduce a known result), and `review` (comprehensive literature survey with a dedicated document template, no experiments).

## Architecture

```
Human Operator ──── Web UI "Observatory" (React/Vite, port 3000)
      |                    |
      |              FastAPI Backend (port 8000)
      |              (REST + WebSocket + event streams)
      |                    |
  Orchestrator (deterministic Python state machine)
      |
      |-- Research Agents (LLM API x N)
      |       |-- Claude (Anthropic)
      |       |-- GPT (OpenAI), Gemini (Google)
      |       |-- GLM, Kimi, MiniMax, gpt-oss (Together)
      |       |
      |       +-- Sandbox (hardened Docker, bridge network)
      |
      |-- Literature + Data Service
      |       |-- arXiv, PubMed, bioRxiv, NASA ADS, Google Scholar
      |       |-- Semantic Scholar (citation graph traversal)
      |       |-- VizieR/CDS + Zenodo (dataset acquisition)
      |       |-- Perplexity (seed discovery + citation grounding)
      |       +-- ChromaDB (semantic search + internal corpus)
      |
      +-- Journal Pipeline
              |-- Editor (internal review gate)
              |-- PI (reflection: proceed / loop back / call it)
              |-- Reviewers (structured peer review)
              |-- Judge (quality ledger)
              +-- Publication / Graveyard
```

No frameworks (no LangChain, no CrewAI). The orchestrator is plain Python with explicit phase transitions, full token tracking, and structured JSON event logging (per-thread `events.jsonl` powering the Replay view).

## CLI Reference

| Command | Description |
|---------|-------------|
| `paradigm run` | Run a research cycle (`--mode`, `--prompt`, `--prompt-file`, `--topic`, `--rounds`, `--data <file>` (repeatable), `--interactive`, `--testing`, `--network-access`, `--fresh-corpus`, `--verbose`) |
| `paradigm eval` | Score papers on a deterministic + LLM-judge rubric; `--live N --split {train,selection,test}` runs fresh cycles and reports reproduction-pass-rate |
| `paradigm status` | System statistics and token usage |
| `paradigm papers` | List papers (filter by `--status`) |
| `paradigm paper ID` | View or export a paper (`--export path.md`) |
| `paradigm inspect --thread ID` | Inspect a research thread checkpoint |
| `paradigm agents` | List configured agents and their models |
| `paradigm memory list --agent ID` | List episodic memories for an agent |
| `paradigm memory search --query Q` | Semantic search across agent memories |
| `paradigm memory clear --older-than 90d` | Prune old memories |
| `paradigm mcp-login` | One-time OAuth login for the optional alphaXiv MCP provider |

`--data` attaches a local dataset file or directory: it is staged into the sandbox-visible shared data directory with a schema preview for the agents. `--testing` swaps every role to cheap open models (the same `testing_overrides` behind the GUI's testing toggle). `configs/default.yaml` is production-parity: 2 rounds per phase with all quality features on.

## Project Structure

```
src/paradigm/
  main.py              CLI entry point
  config.py            YAML config + provider registry
  orchestrator/        Phase state machine, engine, reflection, verification
  agents/              Base agent, factory, prompts, skills, memory
    providers.py       Multi-backend LLM abstraction
  domains/             Pluggable domain profiles (science, finance)
  literature/          Multi-source search, data providers, corpus, citations
  display/             Rich terminal UI (CLI runs)
  sandbox/             Docker-based code execution
  journal/             Peer review, publication, LaTeX/PDF
  storage/             SQLite database, checkpoints, graveyard
  logging/             Structured JSON event logging + event streams
backend/
  api/                 FastAPI web API (REST + WebSocket)
    routes/            research, sessions, papers, agents, models, config, settings, ws
    services/          SessionManager, WebSocket display bridge
frontend/              React "Observatory" web UI (Vite + TypeScript)
configs/               YAML configuration files (default, production, open, ...)
tests/                 pytest + pytest-asyncio
```

## Documentation

| Document | Description |
|----------|-------------|
| [`INSTALL.md`](INSTALL.md) | Installation guide (Python, Docker, frontend, API keys) |
| [`docs/MANUAL.md`](docs/MANUAL.md) | Operations manual (comprehensive usage guide) |
| [`docs/API.md`](docs/API.md) | Web API reference (REST endpoints, WebSocket protocol) |
| [`docs/DOMAINS.md`](docs/DOMAINS.md) | Domain profile system (science, finance, custom) |
| [`backend/README.md`](backend/README.md) | Backend setup, architecture, endpoint inventory |
| [`frontend/README.md`](frontend/README.md) | Frontend setup, structure, and architecture |
| [`ROADMAP.md`](ROADMAP.md) | Implementation roadmap and phase status |
| [`HISTORY.md`](HISTORY.md) | Complete development history |

## Status

**Alpha** --- The full platform works end to end: type a question in the web console, watch the team research it live, read the published, peer-reviewed, judge-scored paper.

All major subsystems are implemented: the Observatory web UI (wizard, live steering, decision dialogs, paper library, replay), multi-agent orchestration with PI reflection loop-backs, real-data acquisition with provenance classification, verification kernel, quality ledger, multi-source literature search, hardened computational sandbox, grounded citations, structured peer review with deep revisions, agent episodic memory, model tiers (frontier and open-weights), and a headless CLI.

## License

MIT
