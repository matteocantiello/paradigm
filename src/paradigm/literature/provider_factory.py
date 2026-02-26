"""Factory for creating SourceProvider instances from domain profile config."""

from __future__ import annotations

import logging
import os

from paradigm.config import LiteratureConfig, StorageConfig
from paradigm.domains.base import SourceProvider, SourceProviderConfig
from paradigm.literature.arxiv import ArxivClient
from paradigm.literature.biorxiv import BiorxivClient
from paradigm.literature.embeddings import EmbeddingStore
from paradigm.literature.nasa_ads import ADSClient
from paradigm.literature.providers import (
    ArxivSourceProvider,
    BiorxivSourceProvider,
    FREDSourceProvider,
    GoogleScholarSourceProvider,
    InternalCorpusProvider,
    NASAADSSourceProvider,
    PubMedSourceProvider,
    SECEdgarSourceProvider,
    SemanticScholarSourceProvider,
    SSRNSourceProvider,
)
from paradigm.literature.pubmed import PubMedClient
from paradigm.literature.semantic_scholar import SemanticScholarClient
from paradigm.logging.events import EventLogger
from paradigm.storage.database import Database

_logger = logging.getLogger(__name__)


def create_source_providers(
    provider_configs: list[SourceProviderConfig],
    literature_config: LiteratureConfig,
    storage_config: StorageConfig,
    database: Database,
    logger: EventLogger | None = None,
) -> dict[str, SourceProvider]:
    """Create SourceProvider instances from domain profile configuration.

    Maps config names to concrete adapter classes and injects the right
    dependencies. Skips disabled providers. Logs unknown provider names.

    Args:
        provider_configs: List of SourceProviderConfig from the domain profile.
        literature_config: Literature configuration (rate limits, etc.).
        storage_config: Storage configuration (vector DB path, etc.).
        database: SQLite database for paper storage.
        logger: Optional event logger.

    Returns:
        Dict mapping provider name to SourceProvider instance.
    """
    providers: dict[str, SourceProvider] = {}

    for config in provider_configs:
        if not config.enabled:
            continue

        name = config.name.lower()

        if name == "arxiv":
            client = ArxivClient(
                rate_limit=literature_config.arxiv_rate_limit,
                logger=logger,
            )
            providers[name] = ArxivSourceProvider(client)

        elif name == "semantic_scholar":
            client = SemanticScholarClient(
                api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
                logger=logger,
            )
            providers[name] = SemanticScholarSourceProvider(client)

        elif name == "internal_corpus":
            embedding_store = EmbeddingStore(
                vector_db_path=storage_config.vector_db_path,
            )
            providers[name] = InternalCorpusProvider(embedding_store, database)

        elif name == "ssrn":
            providers[name] = SSRNSourceProvider()

        elif name == "sec_edgar":
            providers[name] = SECEdgarSourceProvider()

        elif name == "fred":
            providers[name] = FREDSourceProvider(
                api_key=os.getenv("FRED_API_KEY"),
            )

        elif name == "pubmed":
            client = PubMedClient(
                api_key=os.getenv("NCBI_API_KEY"),
                rate_limit=literature_config.pubmed_rate_limit,
                logger=logger,
            )
            providers[name] = PubMedSourceProvider(client)

        elif name == "biorxiv":
            client = BiorxivClient(
                rate_limit=literature_config.biorxiv_rate_limit,
                logger=logger,
            )
            providers[name] = BiorxivSourceProvider(client)

        elif name == "nasa_ads":
            client = ADSClient(
                api_key=os.getenv("NASA_ADS_API_KEY"),
                rate_limit=literature_config.ads_rate_limit,
                logger=logger,
            )
            providers[name] = NASAADSSourceProvider(client)

        elif name == "google_scholar":
            providers[name] = GoogleScholarSourceProvider(
                api_key=os.getenv("SERPAPI_KEY"),
            )

        else:
            _logger.warning("Unknown source provider: %s — skipping", name)

    return providers
