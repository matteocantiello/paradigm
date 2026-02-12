# GitHub Configuration

This directory contains GitHub-specific configuration files for the Paradigm project.

## Workflows

### CI (`workflows/ci.yml`)

Runs on every push and pull request to `main`. Tests the codebase across multiple Python versions.

**Jobs:**
- **Test Python 3.11**: Run tests on Python 3.11
- **Test Python 3.12**: Run tests on Python 3.12 with coverage reporting

**Steps:**
1. Checkout code
2. Set up Python with pip caching
3. Install dependencies
4. Verify setup with `verify_setup.py`
5. Run ruff linting
6. Check code formatting
7. Run pytest test suite
8. Generate coverage report (Python 3.12 only)
9. Upload to Codecov (Python 3.12 only)

**Environment Variables:**
- `ANTHROPIC_API_KEY`: Set as a GitHub secret for actual API testing, or uses a test key for basic validation

### Lint (`workflows/lint.yml`)

Dedicated linting workflow that runs ruff checks and format validation.

**Jobs:**
- **Ruff Linting**: Check code quality and formatting

**Steps:**
1. Checkout code
2. Set up Python 3.12
3. Install ruff
4. Run `ruff check` with GitHub annotations
5. Run `ruff format --check`

## Dependabot (`dependabot.yml`)

Automatically creates pull requests to update dependencies.

**Update schedules:**
- **GitHub Actions**: Weekly updates for workflow dependencies
- **Python packages**: Weekly updates for pip dependencies

## Setting Up Secrets

To enable full CI functionality, add the following secrets to your GitHub repository:

1. Go to Settings → Secrets and variables → Actions
2. Add new repository secret:
   - Name: `ANTHROPIC_API_KEY`
   - Value: Your Anthropic API key

**Note:** The CI will run with a test key if this secret is not set, but some tests that require actual API calls may be skipped.

## Local Testing

Before pushing, you can run the same checks locally:

```bash
# Run linting
ruff check src/ tests/

# Check formatting
ruff format --check src/ tests/

# Auto-format code
ruff format src/ tests/

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=paradigm --cov-report=html
```

## Badge Status

The README includes badges that show:
- ✅ **CI**: Whether tests are passing
- ✅ **Lint**: Whether linting is passing
- ℹ️ **Python Version**: Minimum Python version required
- ℹ️ **License**: Project license (MIT)

Badges automatically update based on the latest workflow runs.
