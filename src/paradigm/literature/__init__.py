"""Literature search, retrieval, and citation tracking for Paradigm."""

from paradigm.literature.arxiv import ArxivClient, ArxivPaper
from paradigm.literature.bibliography import BibliographyBuilder, Reference
from paradigm.literature.citations import CitationTracker
from paradigm.literature.corpus import Corpus
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.literature.novelty import (
    NoveltyResult,
    check_novelty_futurehouse,
    check_novelty_semantic_scholar,
)
from paradigm.literature.perplexity import CitedParagraph, PerplexityClient
from paradigm.literature.provider_factory import create_source_providers
from paradigm.literature.providers import (
    ArxivSourceProvider,
    InternalCorpusProvider,
    SemanticScholarSourceProvider,
)
from paradigm.literature.resources import (
    ResolvedResource,
    ResourceType,
    classify_resource,
    resolve_resource,
)
from paradigm.literature.semantic_scholar import SemanticPaper, SemanticScholarClient

__all__ = [
    "ArxivClient",
    "ArxivPaper",
    "ArxivSourceProvider",
    "BibliographyBuilder",
    "CitationTracker",
    "CitedParagraph",
    "Corpus",
    "EmbeddingStore",
    "InternalCorpusProvider",
    "NoveltyResult",
    "PerplexityClient",
    "Reference",
    "ResolvedResource",
    "ResourceType",
    "SemanticPaper",
    "SemanticScholarClient",
    "SemanticScholarSourceProvider",
    "check_novelty_futurehouse",
    "check_novelty_semantic_scholar",
    "classify_resource",
    "create_source_providers",
    "resolve_resource",
]
