# Installation Guide

## System Requirements

- **Python**: 3.11 or higher (3.12+ recommended)
- **Operating System**: Linux, macOS, or Windows with WSL2
- **Docker**: Required for Phase 3 (computational sandbox)
- **API Access**: Anthropic API key with Claude access

## Step-by-Step Installation

### 1. Check Python Version

```bash
python3 --version
```

If you have Python 3.11+, you're good. If not, install Python 3.12:

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev
```

**macOS (with Homebrew):**
```bash
brew install python@3.12
```

### 2. Create Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Paradigm

```bash
pip install -e ".[dev]"
```

This installs Paradigm in editable mode with all development dependencies.

### 4. Verify Installation

Run the verification script:

```bash
python verify_setup.py
```

You should see:
```
🎉 Phase 0 setup is complete!
```

### 5. Set API Key

Get your Anthropic API key from https://console.anthropic.com/

**Linux/macOS:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Add to ~/.bashrc or ~/.zshrc to persist
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
```

**Windows:**
```cmd
set ANTHROPIC_API_KEY=sk-ant-...
# Or use System Properties > Environment Variables for persistence
```

### 6. Test the CLI

```bash
python -m paradigm --help
```

You should see the Paradigm CLI help message.

### 7. Run Tests

```bash
pytest tests/
```

All tests should pass (requires dependencies installed).

## Configuration

Paradigm uses a YAML configuration file. The default config is at `configs/default.yaml`.

To use a custom config:

```bash
export PARADIGM_CONFIG=/path/to/your/config.yaml
# Or
python -m paradigm --config /path/to/your/config.yaml run ...
```

### Configuration Options

See `configs/default.yaml` for all available options. Key settings:

- **Agent**: Model selection, token budgets, temperature
- **Sandbox**: Docker settings, resource limits
- **Literature**: arXiv rate limits, embedding model
- **Storage**: Data directory, database paths
- **Orchestrator**: Max rounds per phase, checkpointing
- **Memory**: Agent episodic memory (enable/disable, recency half-life, max memories per prompt)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | **Required** |
| `PARADIGM_CONFIG` | Path to config YAML | `configs/default.yaml` |
| `PARADIGM_DATA_DIR` | Data storage directory | `./data` |
| `PARADIGM_LOG_LEVEL` | Logging level | `INFO` |

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError`, ensure you've installed the package:

```bash
pip install -e ".[dev]"
```

### Database Errors

If the database fails to initialize, check that the data directory is writable:

```bash
mkdir -p data
chmod 755 data
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
    model="claude-sonnet-4-5-20250929",
    max_tokens=100,
    messages=[{"role": "user", "content": "Hi"}]
)
print(response.content[0].text)
```

### Permission Errors

If you get permission errors during installation, use:

```bash
pip install --user -e ".[dev]"
```

Or use a virtual environment (recommended).

## Web API (Optional)

To run the web API backend:

```bash
# Install API dependencies
pip install -e ".[api]"

# Start the development server
uvicorn backend.api.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive API documentation.

For authentication, set an API key:

```bash
export PARADIGM_API_KEY="your-secret-key"
```

See [`docs/API.md`](docs/API.md) for full API reference and [`backend/README.md`](backend/README.md) for backend architecture details.

## Development Setup

For development work:

1. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
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

## Next Steps

Once installed:

1. Read `SPEC.md` to understand the architecture
2. Read `ROADMAP.md` to see the implementation plan
3. Check `HISTORY.md` to see the development history
4. Explore the codebase in `src/paradigm/`

The system implements the full research cycle: literature search, multi-agent orchestration, sandbox code execution, paper writing, peer review, and agent episodic memory.
