# Installation Guide

## System Requirements

- **Python**: 3.12+ (via conda/mamba recommended)
- **Node.js**: 20+ (for the web frontend)
- **Operating System**: Linux, macOS, or Windows with WSL2
- **Docker**: Required for the computational sandbox (experiments)
- **API Access**: Anthropic API key (required); OpenAI, Gemini, and Together keys unlock the full model tiers

## Step-by-Step Installation

### 1. Create a Conda Environment (Recommended)

Using conda or mamba ensures the correct Python version and isolates dependencies:

```bash
# Using mamba (faster) or conda
mamba create -n paradigm python=3.12 -y   # or: conda create -n paradigm python=3.12 -y
conda activate paradigm
```

**Alternative (if you already have Python 3.12+):**

```bash
python3 --version  # must be 3.12+
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Paradigm

```bash
pip install -e ".[api,dev]"
```

This installs Paradigm in editable mode with the web API and development dependencies. For a CLI-only install, `pip install -e ".[dev]"` is enough.

### 3. Set API Keys

Get your Anthropic API key from https://console.anthropic.com/

**Linux/macOS:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Add to ~/.bashrc or ~/.zshrc to persist, or put keys in a .env file
```

**Windows:**
```cmd
set ANTHROPIC_API_KEY=sk-ant-...
# Or use System Properties > Environment Variables for persistence
```

See [Environment Variables](#environment-variables) below for the optional provider keys and what each unlocks.

### 4. Build the Sandbox Image (for experiments)

Experiments run in a hardened Docker container. Build the image once:

```bash
docker build -t paradigm-sandbox:latest docker/
```

Without Docker, set `orchestrator.enable_experimentation: false` in your config — literature-driven cycles still work.

### 5. Start the Backend

```bash
uvicorn backend.api.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive API documentation.

Optional API authentication:

```bash
export PARADIGM_API_KEY="your-secret-key"
```

See [`docs/API.md`](docs/API.md) for the full API reference and [`backend/README.md`](backend/README.md) for backend architecture.

### 6. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The Vite dev server proxies `/api` and `/health` to the backend on port 8000. For production, `npm run build` emits static files to `frontend/dist/` (see [`frontend/README.md`](frontend/README.md)).

### 7. Test the CLI (optional)

```bash
paradigm --help
paradigm run --mode directed --prompt "Explain the period-luminosity relation for Cepheids"
```

### 8. Run Tests

```bash
pytest tests/
```

All tests should pass (requires dev dependencies installed).

## Configuration

Paradigm uses a YAML configuration file. The default config is at `configs/default.yaml`, which is production-parity (2 rounds per phase, verification kernel, quality ledger, and reflection all on) with a `testing_overrides` block that the `--testing` flag / GUI testing toggle uses to swap every role to cheap open models.

Other profiles: `configs/production.yaml` (the premium "Top models" tier) and `configs/open.yaml` (the open-weights tier on Together serverless). The web wizard selects between tiers per cycle.

To use a custom config:

```bash
export PARADIGM_CONFIG=/path/to/your/config.yaml
# Or
paradigm --config /path/to/your/config.yaml run ...
```

### Configuration Options

See `configs/default.yaml` for all available options. Key settings:

- **Agent**: Per-role model overrides, token budgets, temperature
- **Sandbox**: Docker settings, network mode (`bridge` by default), resource limits
- **Literature**: Search sources, data providers (VizieR, Zenodo), rate limits
- **Orchestrator**: Rounds per phase, verification kernel, quality ledger, reflection, data policy
- **Storage**: Data directory, database paths
- **Memory**: Agent episodic memory (enable/disable, recency half-life, max memories per prompt)

## Environment Variables

### Provider keys

| Variable | Description | Required? |
|----------|-------------|-----------|
| `ANTHROPIC_API_KEY` | Claude models (analyst, skeptic, writer, editor, PI, synthesizer in the premium tier) | **Required** |
| `OPENAI_API_KEY` | GPT models (theorist + experimentalist in the premium tier) | Optional — needed for the full premium mapping |
| `GEMINI_API_KEY` | Gemini models (peer reviewers + the quality-ledger judge in both tiers) | Optional — needed for the full premium mapping |
| `TOGETHER_API_KEY` | Open-weights models on Together serverless | Optional — needed for the open tier and `--testing` |
| `PERPLEXITY_API_KEY` | Seed literature discovery + fallback citation grounding | Optional — degrades cleanly without it |
| `NASA_ADS_API_KEY` | NASA ADS literature search (important for astronomy topics) | Optional |

Roles whose provider key is missing fall back per config; unset providers are simply hidden in the GUI model picker.

### Runtime

| Variable | Description | Default |
|----------|-------------|---------|
| `PARADIGM_CONFIG` | Path to config YAML | `configs/default.yaml` |
| `PARADIGM_DATA_DIR` | Data storage directory | `./data` |
| `PARADIGM_LOG_LEVEL` | Logging level | `INFO` |
| `PARADIGM_API_KEY` | Web API auth key (auth disabled if unset) | — |
| `PARADIGM_MAX_CONCURRENT_SESSIONS` | Backend concurrency bound | `4` |

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError`, ensure you've installed the package:

```bash
pip install -e ".[api,dev]"
```

### Database Errors

If the database fails to initialize, check that the data directory is writable:

```bash
mkdir -p data
chmod 755 data
```

### Sandbox Errors

If experiments fail to start, check that Docker is running and the image exists:

```bash
docker info
docker image inspect paradigm-sandbox:latest
```

### API Key Issues

Verify your API key is set:

```bash
echo $ANTHROPIC_API_KEY
```

Test it with a simple API call (requires `anthropic` package):

```python
from anthropic import Anthropic
client = Anthropic()  # Uses ANTHROPIC_API_KEY from environment
response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=100,
    messages=[{"role": "user", "content": "Hi"}]
)
print(response.content[0].text)
```

### Permission Errors

If you get permission errors during installation, use:

```bash
pip install --user -e ".[api,dev]"
```

Or use a virtual environment (recommended).

## Development Setup

For development work:

1. Install development dependencies:
   ```bash
   pip install -e ".[api,dev]"
   ```

2. Install pre-commit hooks (optional):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

3. Run linting:
   ```bash
   ruff check src/ tests/
   ruff format src/ tests/
   ```

4. Run tests with coverage:
   ```bash
   pytest tests/ --cov=paradigm --cov-report=html
   ```

5. Frontend linting:
   ```bash
   cd frontend && npm run lint
   ```

## Next Steps

Once installed:

1. Read [`README.md`](README.md) for the platform overview, model tiers, and the research loop
2. Read [`docs/MANUAL.md`](docs/MANUAL.md) for the comprehensive operations manual
3. Open http://localhost:3000 and launch your first research cycle
