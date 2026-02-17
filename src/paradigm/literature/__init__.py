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
    "BibliographyBuilder",
    "CitationTracker",
    "CitedParagraph",
    "Corpus",
    "EmbeddingStore",
    "NoveltyResult",
    "PerplexityClient",
    "Reference",
    "ResolvedResource",
    "ResourceType",
    "SemanticPaper",
    "SemanticScholarClient",
    "check_novelty_futurehouse",
    "check_novelty_semantic_scholar",
    "classify_resource",
    "resolve_resource",
]
