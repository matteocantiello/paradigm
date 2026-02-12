# Paradigm Project History

## 2026-02-11

### Prompt 1: Debug CI Failure
> we just implemented CI, but I received a notification from github actions that something didn't work

**Key decisions:** Investigating and fixing CI failures in `.github/workflows/ci.yml`
**Artifacts modified:**
- `src/paradigm/agents/prompts/.gitkeep` — created (missing dir caused verify_setup.py to fail)
- `tests/test_database.py` — removed spurious f-string prefix (F541)
- `src/paradigm/agents/base.py` — migrated Pydantic v1 `class Config` to v2 `model_config`

### Prompt 2: CI Error Log Analysis
> (User shared CI error log showing `src/paradigm/agents/prompts` directory missing)

**Root cause:** The `prompts/` directory was empty and had no `.gitkeep`, so git didn't track it. The `verify_setup.py` script checks for it and exits with code 1.
**Fix:** Added `.gitkeep` to `src/paradigm/agents/prompts/`

### Prompt 3: Move to Phase 1
> CI passed. We can move to phase 1

**Key decisions:** Begin Phase 1 implementation per ROADMAP.md
**Artifacts created:**
- `src/paradigm/literature/arxiv.py` — ArxivClient + ArxivPaper model (async, rate-limited, XML parsing)
- `src/paradigm/literature/embeddings.py` — EmbeddingStore (ChromaDB wrapper, semantic search)
- `src/paradigm/literature/citations.py` — CitationTracker (SQLite-based citation graph)
- `src/paradigm/literature/corpus.py` — Corpus (unified search combining arXiv + local + citations)
- `src/paradigm/literature/__init__.py` — Public exports
- `tests/test_arxiv.py` — 11 tests for arXiv client
- `tests/test_embeddings.py` — 9 tests for embeddings
- `tests/test_citations.py` — 9 tests for citations
- `tests/test_corpus.py` — 13 tests for corpus
**Artifacts modified:**
- `src/paradigm/config.py` — Fixed Pydantic v2 `validate_default=True` for api_key validator
- `tests/test_config.py` — Fixed macOS path resolution in tests
