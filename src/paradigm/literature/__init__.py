"""Literature search, retrieval, and citation tracking for Paradigm."""

from paradigm.literature.arxiv import ArxivClient, ArxivPaper
from paradigm.literature.bibliography import BibliographyBuilder, Reference
from paradigm.literature.biorxiv import BiorxivClient, BiorxivPaper
from paradigm.literature.citation_chains import follow_citation_chain
from paradigm.literature.citations import CitationTracker
from paradigm.literature.corpus import Corpus
from paradigm.literature.domain_router import (
    classify_topic,
    compute_result_allocation,
    rank_providers,
)
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.literature.nasa_ads import ADSClient, ADSPaper
from paradigm.literature.novelty import (
    NoveltyResult,
    check_novelty_futurehouse,
    check_novelty_semantic_scholar,
)
from paradigm.literature.perplexity import CitedParagraph, PerplexityClient
from paradigm.literature.provider_factory import create_source_providers
from paradigm.literature.providers import (
    ArxivSourceProvider,
    BiorxivSourceProvider,
    GoogleScholarSourceProvider,
    InternalCorpusProvider,
    NASAADSSourceProvider,
    PubMedSourceProvider,
    SemanticScholarSourceProvider,
)
from paradigm.literature.pubmed import PubMedClient, PubMedPaper
from paradigm.literature.resources import (
    ResolvedResource,
    ResourceType,
    classify_resource,
    resolve_resource,
)
from paradigm.literature.search_service import LiteratureSearchService
from paradigm.literature.semantic_scholar import SemanticPaper, SemanticScholarClient

__all__ = [
    "ADSClient",
    "ADSPaper",
    "ArxivClient",
    "ArxivPaper",
    "ArxivSourceProvider",
    "BibliographyBuilder",
    "BiorxivClient",
    "BiorxivPaper",
    "BiorxivSourceProvider",
    "CitationTracker",
    "CitedParagraph",
    "Corpus",
    "EmbeddingStore",
    "GoogleScholarSourceProvider",
    "InternalCorpusProvider",
    "LiteratureSearchService",
    "NASAADSSourceProvider",
    "NoveltyResult",
    "PerplexityClient",
    "PubMedClient",
    "PubMedPaper",
    "PubMedSourceProvider",
    "Reference",
    "ResolvedResource",
    "ResourceType",
    "SemanticPaper",
    "SemanticScholarClient",
    "SemanticScholarSourceProvider",
    "check_novelty_futurehouse",
    "check_novelty_semantic_scholar",
    "classify_resource",
    "classify_topic",
    "compute_result_allocation",
    "create_source_providers",
    "follow_citation_chain",
    "rank_providers",
    "resolve_resource",
]
