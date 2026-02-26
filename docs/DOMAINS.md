# Domain Profiles Reference

Paradigm uses a pluggable **domain profile** system to adapt the entire research pipeline to different fields. Each domain defines its own agent roles, research modes, document template, review criteria, literature sources, and sandbox environment.

---

## Table of Contents

1. [How Domains Work](#how-domains-work)
2. [Science Domain](#science-domain)
3. [Finance Domain](#finance-domain)
4. [Creating a New Domain](#creating-a-new-domain)

---

## How Domains Work

A domain profile is a `DomainProfile` Pydantic model (defined in `src/paradigm/domains/base.py`) that bundles everything the orchestrator needs to run research in a particular field:

| Component | Purpose |
|-----------|---------|
| **Agent roles** | YAML prompt files defining each agent's persona and expertise |
| **Research modes** | Named team configurations (e.g., `directed`, `explore`) |
| **Document template** | Output format --- sections, section assignments, citation style |
| **Review criteria** | Scoring dimensions for peer review |
| **Source providers** | Literature and data sources (arXiv, SSRN, FRED, etc.) |
| **Phase-active roles** | Which roles participate in each orchestration phase |
| **Search strategies** | Per-role literature search guidance |
| **Later-round reinforcements** | Prompts injected in later discussion rounds to keep agents on track |

Domains are registered at import time via `register_domain()` in `src/paradigm/domains/registry.py`. When a config file sets `domain: finance`, the registry lazy-loads the `paradigm.domains.finance` package.

---

## Science Domain

**Package:** `src/paradigm/domains/science/`
**Config:** `configs/default.yaml` (science is the default when no `domain:` key is set)

### Agent Roles (7)

| Role | Persona | Section Assignment |
|------|---------|--------------------|
| `theorist` | Theoretical modeling, mathematical frameworks | Methods |
| `analyst` | Data analysis, statistical methods | Results |
| `synthesizer` | Cross-disciplinary connections, literature integration | Discussion |
| `experimentalist` | Computational experiments, simulation design | --- |
| `skeptic` | Critical analysis, identifying flaws | --- |
| `writer` | Scientific writing, narrative coherence | Abstract, Introduction, Conclusion |
| `editor` | Peer review, structured feedback | --- |

### Research Modes (6)

| Mode | Team | Description |
|------|------|-------------|
| `directed` | theorist, analyst, experimentalist, synthesizer, skeptic, writer, editor | Focused investigation of a specific question |
| `explore` | theorist, analyst, experimentalist, synthesizer, skeptic, writer, editor | Open-ended exploration of a broad topic |
| `hypothesis` | theorist, skeptic, experimentalist, analyst, writer, editor | Formulate and test precise hypotheses |
| `experimental` | experimentalist, analyst, theorist, writer, editor | Design and execute computational experiments |
| `replication` | analyst, experimentalist, skeptic, writer, editor | Reproduce and verify existing results |
| `review` | theorist, synthesizer, skeptic, writer, editor | Comprehensive literature review and field synthesis (no experiments) |

### Document Templates

#### `academic_paper` (default)

**Sections:** abstract, introduction, methods, results, discussion, conclusion
**Citation style:** `arxiv`
**Postprocessors:** `latex_math`

#### `literature_review` (review mode)

**Sections:** abstract, introduction, literature_landscape, thematic_analysis, critical_assessment, future_directions, conclusion
**Citation style:** `numbered`
**Postprocessors:** `latex_math`

### Review Criteria (4)

| Criterion | Description |
|-----------|-------------|
| `novelty` | Does the work present new ideas, methods, or findings? |
| `rigor` | Are the methods sound, analysis correct, and conclusions justified? |
| `clarity` | Is the paper well-written, well-organized, and easy to follow? |
| `significance` | Does the work make a meaningful contribution to the field? |

### Source Providers

| Provider | Description |
|----------|-------------|
| `arxiv` | arXiv preprint server (search + PDF full-text fetch) |
| `semantic_scholar` | Semantic Scholar API (citation graph traversal) |
| `internal_corpus` | Local ChromaDB vector store (previously ingested papers) |

### Sandbox

**Docker image:** `paradigm-sandbox:latest`
**Pre-installed:** NumPy, SciPy, Matplotlib, Pandas, scikit-learn, SymPy, Astropy

---

## Finance Domain

**Package:** `src/paradigm/domains/finance/`
**Config:** `configs/finance.yaml`

### Agent Roles (8)

| Role | Persona | Section Assignment |
|------|---------|--------------------|
| `economist` | Macroeconomic theory, policy analysis, causal inference | Background, Literature Review |
| `quant` | Quantitative modeling, derivatives, time series, risk metrics | Methodology, Results |
| `strategist` | Market strategy, portfolio construction, asset allocation | Analysis |
| `risk_analyst` | Risk assessment, stress testing, tail risk, regulatory | Risk Assessment |
| `experimentalist` | Econometrics + quantitative finance experiments | --- |
| `writer` | Research report drafting with executive summaries | Executive Summary, Recommendations |
| `editor` | Reviews structure, clarity, actionability | --- |
| `reviewer` | Independent peer review against finance research standards | --- |

### Research Modes (5)

| Mode | Team | Description |
|------|------|-------------|
| `directed` | economist, quant, strategist, risk_analyst, experimentalist, writer, editor, reviewer | Focused investigation of a specific financial question |
| `explore` | economist, quant, strategist, risk_analyst | Open-ended exploration of a financial topic |
| `empirical` | quant, economist, experimentalist, risk_analyst | Data-driven analysis with heavy experimentation |
| `strategy` | quant, strategist, risk_analyst, experimentalist | Investment/trading strategy research |
| `policy` | economist, strategist, risk_analyst | Economic policy analysis |

### Document Template: `research_report`

**Sections:** executive_summary, background, literature_review, methodology, results, analysis, risk_assessment, recommendations
**Citation style:** `numbered`
**Postprocessors:** `latex_math`

### Review Criteria (5)

| Criterion | Description |
|-----------|-------------|
| `rigor` | Statistical methodology, data quality, and robustness checks |
| `novelty` | New insights, models, or approaches vs existing literature |
| `relevance` | Practical applicability to current market conditions |
| `actionability` | Clear, implementable recommendations |
| `risk_awareness` | Adequate treatment of uncertainties and downside scenarios |

### Source Providers

| Provider | Description |
|----------|-------------|
| `ssrn` | SSRN (Social Science Research Network) --- working papers and preprints |
| `sec_edgar` | SEC EDGAR --- 10-K, 10-Q, 8-K filings |
| `fred` | FRED (Federal Reserve Economic Data) --- economic data series. Requires `FRED_API_KEY` env var |
| `semantic_scholar` | Semantic Scholar API (citation graph traversal) |
| `internal_corpus` | Local ChromaDB vector store (previously ingested papers) |

### Phase-Active Roles

The finance domain explicitly defines which roles participate in deliberation phases:

| Phase | Active Roles |
|-------|-------------|
| IDEATION | economist, quant, strategist, risk_analyst |
| PLANNING | economist, quant, strategist, risk_analyst |
| POST_EXECUTION | economist, quant, strategist, risk_analyst |

Writer, editor, and reviewer activate only during their respective phases (WRITING, INTERNAL_REVIEW, PEER_REVIEW).

### Sandbox

**Docker image:** `paradigm-finance-sandbox:latest`
**Pre-installed:**
- Core scientific: NumPy, SciPy, Matplotlib, Pandas, scikit-learn
- Econometrics: statsmodels, linearmodels, arch
- Quantitative finance: quantlib-python, pyfolio-reloaded, zipline-reloaded
- Data access: fredapi, pandas-datareader, yfinance

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FRED_API_KEY` | For FRED provider | Federal Reserve Economic Data API key |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `GEMINI_API_KEY` | Yes | Google Gemini API key |

---

## Creating a New Domain

To add a new domain (e.g., `law`, `medicine`, `engineering`):

### 1. Create the domain package

```
src/paradigm/domains/yourname/
    __init__.py        # Register DomainProfile
    constants.py       # MODE_TEAM_ROLES, ROLE_SEARCH_STRATEGIES, etc.
    template.py        # DocumentTemplate with sections and review criteria
    prompts/           # One YAML file per agent role
        role1.yaml
        role2.yaml
        ...
```

### 2. Define agent prompts

Each YAML file follows this schema:

```yaml
name: role_name
description: One-line description
system_prompt: |
  Multi-line system prompt defining the agent's persona,
  expertise, and behavioral constraints.
default_skills:
  - relevant_skill_1
  - relevant_skill_2
```

### 3. Define the document template

In `template.py`, create a `DocumentTemplate` with:
- Named sections (each with a `name`, `description`, and `assigned_to` list)
- Review criteria (each with a `name`, `description`, and `weight`)
- Citation style (`arxiv`, `numbered`, etc.)

### 4. Define research modes

In `constants.py`, create `MODE_TEAM_ROLES` mapping mode names to role lists. Also define `ROLE_SEARCH_STRATEGIES` and `ROLE_LATER_ROUND_REINFORCEMENTS`.

### 5. Register the domain

In `__init__.py`:

```python
from paradigm.domains.base import DomainProfile, SourceProviderConfig
from paradigm.domains.registry import register_domain

_PROFILE = DomainProfile(
    name="yourname",
    description="...",
    source_providers=[...],
    document_template=YOUR_TEMPLATE,
    prompts_dir=Path(__file__).parent / "prompts",
    default_roles=MODE_TEAM_ROLES,
    # ... other fields
)
register_domain(_PROFILE)
```

### 6. Add source providers (if needed)

If your domain needs data sources beyond arXiv and Semantic Scholar:
1. Implement a new `SourceProvider` subclass in `src/paradigm/literature/providers.py`
2. Register it in `src/paradigm/literature/provider_factory.py`

### 7. Create a config file

Create `configs/yourname.yaml` with `domain: yourname` and any domain-specific overrides.

### 8. Create a sandbox Dockerfile (if needed)

If your domain requires specialized Python packages for experiments, create `docker/Dockerfile.yourname`.

### 9. Add tests

Create `tests/test_yourname_domain.py` to verify profile loading, template structure, and mode definitions. See `tests/test_finance_domain.py` for a complete example.
