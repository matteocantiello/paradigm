# Domain Profiles — Extending Paradigm Beyond Academic Research

## Motivation

Paradigm's core orchestration engine (phase machine, agents, sandbox, memory, display, storage) is domain-agnostic, but the literature access, paper format, agent prompts, and review criteria are hardwired to academic science (arXiv, Semantic Scholar, LaTeX papers, novelty/rigor scoring).

To support general-purpose research — financial reports, technical analyses, investigative journalism, policy briefs — we need a clean abstraction that separates *what you research* from *how you research it*.

## Domain Coupling Audit

| Layer | Generic | Science-coupled |
|-------|---------|-----------------|
| Core infra (orchestrator, agents, config, sandbox, storage, display, logging) | ~70% | ~30% |
| Literature (`literature/`) | 1/9 files | 8/9 files |
| Journal (`journal/`) | 0/3 | 3/3 |
| Agent prompts | 1/8 | 7/8 |

The science-specific code clusters into five separable concerns:

1. **Source providers** — ArXiv API, Semantic Scholar API, arXiv ID patterns
2. **Document template** — Academic paper sections (Abstract, Introduction, Methods, Results, Discussion, Conclusion)
3. **Role prompts** — Science-flavored language in 7/8 YAML prompt templates
4. **Review criteria** — Hardcoded novelty/rigor/clarity/significance scoring
5. **Post-processing** — LaTeX math enforcement, arXiv citation grounding

## Design Decision: Profiles, Not Forks

A fork would duplicate ~70% of the codebase. Every orchestrator improvement, display feature, or bug fix would need applying twice. Instead, we introduce **domain profiles** — pluggable bundles that configure the domain-specific 30% while sharing the generic 70%.

```yaml
# Switch domain with one config key
domain: science       # current behavior (default)
domain: research      # generic web-based research
domain: financial     # SEC filings, earnings, market data
```

---

## Architecture

### Source Provider Interface

Replaces the hardwired arXiv/Semantic Scholar integration with a pluggable provider system.

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from datetime import datetime


class SourceResult(BaseModel):
    """Unified search result from any knowledge source."""
    id: str                        # provider-specific ID (arXiv ID, URL hash, etc.)
    source_type: str               # "arxiv", "web", "sec_filing", "news", etc.
    title: str
    authors: list[str]
    summary: str                   # abstract, snippet, or executive summary
    url: str
    date: datetime | None = None
    content: str | None = None     # full text if fetched
    metadata: dict = {}            # provider-specific extras


class SourceDocument(BaseModel):
    """Full document content from a source."""
    id: str
    source_type: str
    title: str
    authors: list[str]
    full_text: str
    sections: dict[str, str] = {}  # section_name -> content (if parseable)
    url: str
    metadata: dict = {}


class SourceProvider(ABC):
    """Any searchable knowledge source."""
    name: str

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        """Search for documents matching a query."""
        ...

    @abstractmethod
    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Fetch the full content of a document by ID."""
        ...

    async def get_references(self, source_id: str) -> list[SourceResult]:
        """Get documents referenced by this document (optional)."""
        return []

    async def get_citing(self, source_id: str) -> list[SourceResult]:
        """Get documents that cite this document (optional)."""
        return []
```

### Document Template

Replaces the hardcoded `PaperSection` enum with a configurable section structure.

```python
class SectionDef(BaseModel):
    """A section in the output document."""
    name: str                      # "introduction", "executive_summary", etc.
    display_name: str              # "Introduction", "Executive Summary"
    description: str               # guidance for the writing agent
    assigned_roles: list[str]      # which agent roles draft this section
    required: bool = True


class CriterionDef(BaseModel):
    """A review criterion."""
    name: str                      # "novelty", "accuracy", etc.
    display_name: str              # "Novelty", "Accuracy"
    description: str               # what the reviewer should evaluate
    weight: float = 1.0            # relative importance in scoring


class DocumentTemplate(BaseModel):
    """Defines the structure of the output document and how it's reviewed."""
    name: str                      # "academic_paper", "research_report", etc.
    sections: list[SectionDef]
    review_criteria: list[CriterionDef]
    citation_style: str = "numbered"  # "arxiv", "url", "numbered", "footnote"
    postprocessors: list[str] = []    # registered postprocessor names (e.g., "latex_math")
```

### Domain Profile

Bundles everything together.

```python
class SandboxProfile(BaseModel):
    """Sandbox configuration for a domain."""
    docker_image: str = "paradigm-sandbox:latest"
    preamble: str = ""                        # import block prepended to every script
    available_libraries: list[str] = []       # for prompt context, not pip install


class DomainProfile(BaseModel):
    """A complete domain configuration."""
    name: str
    description: str
    source_providers: list[SourceProviderConfig]  # which providers to register
    document_template: DocumentTemplate
    prompts_dir: Path                             # path to YAML prompt directory
    default_roles: dict[str, list[str]]           # mode -> list of agent roles
    role_search_strategies: dict[str, str] = {}   # role -> search specialization
    role_later_round_reinforcements: dict[str, str] = {}  # role -> reinforcement prompt
    literature_instruction: str = ""              # how to use literature context
    phase_active_roles: dict[str, set[str]] = {}  # phase -> active roles (Phase 2)
    sandbox: SandboxProfile = SandboxProfile()    # sandbox config (Phase 2)
    corpus_namespace: str = ""                    # ChromaDB collection prefix (Phase 2)
    skills_dir: Path | None = None                # domain-specific skill library (Phase 2)
    skills_header: str = "Skills Reference"       # header for skill-augmented prompts (Phase 2)
```

---

## Built-in Domains

### `science` (current behavior, extracted)

**Source providers:** ArxivProvider, SemanticScholarProvider, InternalCorpusProvider
**Document template:** Abstract, Introduction, Methods, Results, Discussion, Conclusion, References
**Review criteria:** Novelty, Rigor, Clarity, Significance
**Role prompts:** theorist, analyst, experimentalist, synthesizer, skeptic, writer, editor, reviewer
**Post-processing:** LaTeX math enforcement, arXiv citation grounding
**Citation style:** arXiv IDs + numbered references

### `research` (new generic domain)

**Source providers:** WebSearchProvider (Perplexity/Google/Brave), URLFetchProvider, InternalCorpusProvider
**Document template:** Executive Summary, Background, Analysis, Findings, Recommendations, Sources
**Review criteria:** Accuracy, Thoroughness, Clarity, Actionability
**Role prompts:** strategist, investigator, analyst, skeptic, synthesizer, writer, editor, reviewer
**Post-processing:** URL citation formatting
**Citation style:** Numbered URLs with titles

### `financial` (example future domain)

**Source providers:** SECEdgarProvider, WebSearchProvider, NewsAPIProvider, InternalCorpusProvider
**Document template:** Executive Summary, Company Overview, Financial Analysis, Risk Assessment, Outlook, Appendix
**Review criteria:** Accuracy, Completeness, Timeliness, Objectivity
**Role prompts:** financial_analyst, industry_specialist, risk_assessor, skeptic, writer, editor, reviewer
**Post-processing:** Table/chart formatting
**Citation style:** Footnotes with filing references

---

## Directory Structure

```
src/paradigm/
  domains/
    base.py                 ← ABC interfaces (SourceProvider, DocumentTemplate, DomainProfile)
    registry.py             ← Domain registration, loading, and validation
    science/
      __init__.py           ← Registers the science domain profile
      providers.py          ← ArxivProvider, SemanticScholarProvider (extracted from literature/)
      template.py           ← Academic paper template + LaTeX postprocessing
      prompts/              ← Current 8 YAML prompts, moved from agents/prompts/
        theorist.yaml
        analyst.yaml
        experimentalist.yaml
        synthesizer.yaml
        skeptic.yaml
        writer.yaml
        editor.yaml
        reviewer.yaml
      review.py             ← Novelty/rigor/clarity/significance criteria
    research/
      __init__.py           ← Registers the research domain profile
      providers.py          ← WebSearchProvider, URLFetchProvider
      template.py           ← Report template
      prompts/              ← Generic role prompts
        strategist.yaml
        investigator.yaml
        analyst.yaml
        skeptic.yaml
        synthesizer.yaml
        writer.yaml
        editor.yaml
        reviewer.yaml
      review.py             ← Accuracy/thoroughness/clarity/actionability criteria
  literature/
    embeddings.py           ← Stays (generic ChromaDB wrapper)
    corpus.py               ← Refactored to use SourceProvider interface
    prompt_utils.py         ← Stays (generic formatting)
  journal/
    paper.py                ← Refactored to use DocumentTemplate
    review.py               ← Refactored to use CriterionDef from profile
    publication.py          ← Minor changes (generic metadata)
```

### What was modified in Phase 1

- `config.py` — Added `domain: str` field and `get_domain_profile()` method
- `main.py` — Loads domain profile, passes `prompts_dir` to factory, `domain_profile` to engine
- `orchestrator/engine.py` — Accepts `domain_profile`, uses it for roles/strategies/reinforcements/literature
- `orchestrator/constants.py` — Domain-specific constants removed (moved to `domains/science/constants.py`)
- `agents/factory.py` — Accepts `prompts_dir: Path` parameter
- `journal/paper.py` — `PaperDraft.sections` uses `dict[str, SectionDraft]`, added `section_assignments_from_template()`
- `journal/review.py` — Added `score_categories_from_criteria()` helper

### What stays untouched

- `orchestrator/phases.py` — Phase enum and transitions
- `agents/base.py` — Agent class, message protocol
- `agents/memory.py` — Episodic memory and reflection
- `sandbox/` — Docker execution (generic, but will accept preamble from profile in Phase 2)
- `storage/` — SQLite, ChromaDB, checkpoints (corpus namespace in Phase 2)
- `display/` — Rich terminal UI
- `logging/` — Event logging

---

## Migration Path

### Phase 1: Define interfaces & extract science domain (COMPLETED)

Implemented across 8 commits on `feature/domain-profiles`:

1. **Commit 1** — Defined `domains/base.py`: SourceResult, SourceDocument, SourceProvider (ABC), SectionDef, CriterionDef, DocumentTemplate, SourceProviderConfig, DomainProfile
2. **Commit 2** — Domain registry (`domains/registry.py`): register/get/list/load with lazy importlib loading
3. **Commit 3** — Science domain profile: template, constants, 8 YAML prompts
4. **Commit 4** — Config wiring: `domain: str` field, `get_domain_profile()`, profile passed to engine
5. **Commit 5** — Factory wiring: `prompts_dir` parameter, profile's prompts used for agent creation
6. **Commit 6** — Engine wiring: default_roles, search strategies, reinforcements, literature instruction from profile
7. **Commit 7** — Template wiring: section assignments and review criteria from profile, string-keyed PaperDraft
8. **Commit 8** — Cleanup: removed duplicated constants/prompts, 814 tests passing

All existing tests pass. `domain: science` (default) produces identical behavior.

### Phase 2: Wire remaining domain-specific components

See "Resolved Design Decisions (Phase 2)" section above for implementation details.

1. **Sandbox preamble** — Add `SandboxProfile` to DomainProfile, wire into CodeExecutor
2. **Corpus isolation** — Namespace ChromaDB collections by domain
3. **Citation grounding** — Implement ReferenceFormatter postprocessor registry
4. **Skills wiring** — Domain-specific skill directories and configurable headers
5. **Phase active roles** — Move `_PHASE_ACTIVE_ROLES` to profile

### Phase 3: New domains & source providers

1. **SourceProvider adapters** — ArxivClient → ArxivProvider, SemanticScholarClient → SemanticScholarProvider
2. **Corpus refactor** — Use pluggable providers instead of direct client calls
3. **`research` domain** — WebSearchProvider (Perplexity), URLFetchProvider, report template, generic role prompts
4. **Domain-specific Docker images** — Built from shared base with domain-specific packages
5. **End-to-end testing** — Full cycle with `domain: research` producing reports from web sources

---

## Configuration Examples

### Science mode (current behavior)

```yaml
domain: science

# Override specific providers if needed
sources:
  arxiv:
    enabled: true
  semantic_scholar:
    enabled: true
```

### Generic research mode

```yaml
domain: research

sources:
  web_search:
    engine: perplexity
    api_key_env: PERPLEXITY_API_KEY
  url_fetch:
    enabled: true
```

### Financial analysis mode

```yaml
domain: financial

sources:
  sec_edgar:
    enabled: true
  web_search:
    engine: perplexity
    api_key_env: PERPLEXITY_API_KEY
  news:
    api_key_env: NEWS_API_KEY
```

---

## Resolved Design Decisions (Phase 2)

These questions were raised during the Phase 1 implementation and resolved through design discussion.

### 1. Role Mapping Across Modes — Shared modes, domain-specific roles

**Decision:** The `--mode` options (directed, explore, hypothesis, experimental, replication) remain shared across all domains. The orchestration modes are domain-agnostic patterns — "hypothesis mode" means structured conjecture→test regardless of subject matter. Domains control role *composition* and *prompts* per mode, not the modes themselves.

**Implementation:**
- Add `phase_active_roles: dict[str, set[str]]` to `DomainProfile` (currently `_PHASE_ACTIVE_ROLES` in `orchestrator/constants.py`)
- Engine reads phase→active-roles mapping from profile instead of hardcoded dict
- Each domain defines which of its roles participate in each phase
- Mode prompt overrides (`_MODE_PROMPT_OVERRIDES`) stay in `orchestrator/constants.py` since they're structural, not domain-specific

### 2. Sandbox Configuration — Domain-specific sandbox profiles

**Decision:** Domains declare their own sandbox requirements via a nested `SandboxProfile` model. The CodeExecutor reads the preamble and library list from the active domain profile. Different domains can use different Docker images.

**Implementation:**
```python
class SandboxProfile(BaseModel):
    """Sandbox configuration for a domain."""
    docker_image: str = "paradigm-sandbox:latest"
    preamble: str = ""                    # import block prepended to every script
    available_libraries: list[str] = []   # for prompt context, not pip install
```

- Add `sandbox: SandboxProfile` field to `DomainProfile`
- Science domain: preamble imports numpy/scipy/astropy; libraries list shows what's available
- Research domain: preamble imports pandas/requests; lighter library set
- `EXECUTION` prompt uses `{available_libraries}` placeholder instead of hardcoded list
- `CodeExecutor` prepends `sandbox.preamble` to user scripts
- Domain-specific Docker images built from a shared base (Phase 2+)

### 3. Corpus Isolation — Domain-namespaced collections

**Decision:** ChromaDB collections are prefixed with the domain name (`f"{domain}_papers"`). Papers from different domains live in separate vector spaces. Agent episodic memory remains shared across domains (an agent's reflection history is domain-independent).

**Implementation:**
- Add `corpus_namespace: str` to `DomainProfile` (defaults to profile name)
- `Corpus.__init__` accepts `namespace` parameter, uses `f"{namespace}_papers"` as collection name
- Engine passes `profile.corpus_namespace` to Corpus at construction
- Agent memory collections stay as-is (no namespace prefix)
- Migration: existing `papers` collection stays accessible as `science_papers` via alias or rename

### 4. Skill Libraries — Domain-specific skill directories

**Decision:** Add `skills_dir: Path | None` to `DomainProfile`. Science domain points to `vendor/claude-scientific-skills`. Other domains can set `None` to rely on LLM base knowledge, or point to their own curated skill libraries.

**Implementation:**
- Add `skills_dir: Path | None = None` to `DomainProfile`
- Add `skills_header: str = "Skills Reference"` to `DomainProfile` (replaces hardcoded `"Scientific Skills Reference"`)
- `SkillRegistry` accepts optional `base_dir` from profile's `skills_dir`
- `AgentFactory` uses `profile.skills_header` when building skill-augmented prompts
- If `skills_dir` is None, skill injection is skipped entirely (equivalent to `skill_mode="none"`)
- Future: curated skill libraries for financial, policy, etc. domains

### 5. Citation Grounding — Postprocessor registry with ReferenceFormatter

**Decision:** Citation grounding uses the postprocessor registry pattern. `DocumentTemplate.postprocessors` already exists as `list[str]`. Each domain registers named postprocessors that transform the final document.

**Implementation:**
```python
class ReferenceFormatter(ABC):
    """Formats and grounds citations in the final document."""

    @abstractmethod
    def format_references(self, text: str, sources: list[SourceResult]) -> str:
        """Replace citation markers with properly formatted references."""
        ...

    @abstractmethod
    def validate_citations(self, text: str, sources: list[SourceResult]) -> list[str]:
        """Return list of citation issues (unresolved refs, broken links, etc.)."""
        ...
```

- `ArxivReferenceFormatter`: Grounds `[Author et al., YYYY]` patterns to arXiv IDs, formats bibliography
- `URLReferenceFormatter`: Grounds inline citations to numbered URL references
- Novelty checking stays as a **pre-writing hook** (it gates whether to write, not how to format)
- Postprocessors run after assembly, before final review
- Registry pattern: `register_postprocessor("arxiv_citations", ArxivReferenceFormatter())`

---

## Phase 2 Implementation Plan

Phase 1 (completed) defined interfaces and extracted the science domain. Phase 2 wires the remaining domain-specific components.

### Priority order (by impact and coupling)

| Priority | Item | Rationale |
|----------|------|-----------|
| P1 | Sandbox preamble | Simplest change, immediate value for non-science domains |
| P2 | Corpus isolation | Required before multi-domain runs; data integrity |
| P3 | Citation grounding | Enables correct references in non-arXiv domains |
| P4 | Skills wiring | Nice-to-have; LLM base knowledge is a fine fallback |
| P5 | Phase active roles | Low urgency; current science roles work for all modes |

### Deferred to Phase 3

- `SourceProvider` implementations (ArxivClient → ArxivProvider adapter)
- Corpus refactor to use pluggable providers
- `research` domain implementation
- Domain-specific Docker images
- Domain-specific skill library curation
