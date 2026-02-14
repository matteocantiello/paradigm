"""Literature search, retrieval, and citation tracking for Paradigm."""

from paradigm.literature.arxiv import ArxivClient, ArxivPaper
from paradigm.literature.citations import CitationTracker
from paradigm.literature.corpus import Corpus
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.literature.resources import (
    ResolvedResource,
    ResourceType,
    classify_resource,
    resolve_resource,
)

__all__ = [
    "ArxivClient",
    "ArxivPaper",
    "CitationTracker",
    "Corpus",
    "EmbeddingStore",
    "ResolvedResource",
    "ResourceType",
    "classify_resource",
    "resolve_resource",
]
