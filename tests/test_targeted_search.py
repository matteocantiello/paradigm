"""Tests for provider-targeted search: [SEARCH:provider: query] syntax."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from paradigm.literature.prompt_utils import (
    KNOWN_SEARCH_PROVIDERS,
    parse_search_requests,
)

# ---------------------------------------------------------------------------
# parse_search_requests — provider-targeted parsing
# ---------------------------------------------------------------------------


class TestParseSearchRequestsTargeted:
    """Tests for the [SEARCH:provider: query] extension."""

    def test_plain_search_returns_none_provider(self):
        result = parse_search_requests("[SEARCH: stellar evolution]")
        assert result == [("stellar evolution", None)]

    def test_known_provider_pubmed(self):
        result = parse_search_requests("[SEARCH:pubmed: gene expression]")
        assert result == [("gene expression", "pubmed")]

    def test_known_provider_arxiv(self):
        result = parse_search_requests("[SEARCH:arxiv: cepheid]")
        assert result == [("cepheid", "arxiv")]

    def test_known_provider_nasa_ads(self):
        result = parse_search_requests("[SEARCH:nasa_ads: stellar evolution]")
        assert result == [("stellar evolution", "nasa_ads")]

    def test_known_provider_biorxiv(self):
        result = parse_search_requests("[SEARCH:biorxiv: protein folding]")
        assert result == [("protein folding", "biorxiv")]

    def test_known_provider_semantic_scholar(self):
        result = parse_search_requests("[SEARCH:semantic_scholar: deep learning]")
        assert result == [("deep learning", "semantic_scholar")]

    def test_known_provider_google_scholar(self):
        result = parse_search_requests("[SEARCH:google_scholar: climate models]")
        assert result == [("climate models", "google_scholar")]

    def test_unknown_provider_fallback(self):
        """Unknown provider name is folded back into the query string."""
        result = parse_search_requests("[SEARCH:foo: bar]")
        assert result == [("foo: bar", None)]

    def test_case_insensitive_provider(self):
        """Provider names are lowercased before matching."""
        result = parse_search_requests("[SEARCH:PubMed: gene expression]")
        assert result == [("gene expression", "pubmed")]

    def test_case_insensitive_search_prefix(self):
        result = parse_search_requests("[search:arxiv: neutron stars]")
        assert result == [("neutron stars", "arxiv")]

    def test_mixed_targeted_and_untargeted(self):
        text = (
            "[SEARCH: general query] and "
            "[SEARCH:pubmed: specific query] and "
            "[SEARCH:arxiv: another specific]"
        )
        result = parse_search_requests(text)
        assert len(result) == 3
        assert result[0] == ("general query", None)
        assert result[1] == ("specific query", "pubmed")
        assert result[2] == ("another specific", "arxiv")

    def test_spaced_provider_routes(self):
        """Agents write '[SEARCH: pubmed: q]' (space after SEARCH:) — must still route.

        Regression: before the leading \\s* in the regex, the spaced form failed
        to match the provider group, so the provider was dropped AND its name
        leaked into the query as noise ('pubmed: gene expression').
        """
        result = parse_search_requests("[SEARCH: pubmed: gene expression]")
        assert result == [("gene expression", "pubmed")]

    def test_spaced_provider_semantic_scholar(self):
        result = parse_search_requests("[SEARCH: semantic_scholar: melanopic equivalent]")
        assert result == [("melanopic equivalent", "semantic_scholar")]

    def test_spaced_provider_does_not_leak_into_query(self):
        """The provider token must not survive in the query string."""
        ((query, provider),) = parse_search_requests("[SEARCH: arxiv: cepheid period]")
        assert provider == "arxiv"
        assert "arxiv" not in query.lower()

    def test_spaced_plain_query_no_false_provider(self):
        """A spaced plain query whose first word lacks a colon stays untargeted."""
        result = parse_search_requests("[SEARCH: eye strain late night]")
        assert result == [("eye strain late night", None)]

    def test_deduplication_across_providers(self):
        """Same query text with different providers should NOT be deduped."""
        text = "[SEARCH:arxiv: cepheid] and [SEARCH:pubmed: cepheid]"
        result = parse_search_requests(text)
        # Both have query "cepheid" so they ARE deduped (same query key)
        assert len(result) == 1

    def test_deduplication_same_provider(self):
        text = "[SEARCH:arxiv: cepheid] and [SEARCH:arxiv: cepheid]"
        result = parse_search_requests(text)
        assert len(result) == 1

    def test_whitespace_handling_in_provider(self):
        """Provider name should be stripped."""
        result = parse_search_requests("[SEARCH:pubmed:   lots of space  ]")
        assert result == [("lots of space", "pubmed")]

    def test_empty_query_with_provider_ignored(self):
        result = parse_search_requests("[SEARCH:arxiv:   ]")
        assert result == []

    def test_known_providers_frozenset(self):
        """Verify the set of known providers."""
        assert KNOWN_SEARCH_PROVIDERS == frozenset(
            {
                "arxiv",
                "pubmed",
                "biorxiv",
                "nasa_ads",
                "semantic_scholar",
                "google_scholar",
            }
        )


# ---------------------------------------------------------------------------
# Corpus.search — provider parameter routing
# ---------------------------------------------------------------------------


def _make_corpus(source_providers: dict, topic: str = "test"):
    """Helper to create a Corpus with mocked internals."""
    from paradigm.literature.corpus import Corpus

    mock_db = MagicMock()
    mock_config = MagicMock()
    mock_config.max_results_per_search = 10
    mock_config.arxiv_rate_limit = 1.0
    mock_config.enable_pdf_fetch = False

    mock_embeddings = MagicMock()
    mock_arxiv = MagicMock()
    mock_s2 = MagicMock()

    return Corpus(
        database=mock_db,
        literature_config=mock_config,
        storage_config=MagicMock(),
        source_providers=source_providers,
        topic=topic,
        embedding_store=mock_embeddings,
        arxiv_client=mock_arxiv,
        semantic_scholar_client=mock_s2,
    )


class TestCorpusProviderRouting:
    """Tests that Corpus.search(provider=...) skips domain routing."""

    @pytest.mark.asyncio
    async def test_targeted_provider_skips_domain_routing(self):
        """When provider is set, domain routing functions are not called."""
        mock_provider = MagicMock()
        mock_provider.search = AsyncMock(return_value=[])

        corpus = _make_corpus(
            {"pubmed": mock_provider, "arxiv": mock_provider},
            topic="stellar evolution",
        )

        await corpus.search("test query", max_results=5, provider="pubmed")

        # The targeted provider should have been called
        mock_provider.search.assert_called_once_with("test query", max_results=5)

    @pytest.mark.asyncio
    async def test_no_provider_uses_domain_routing(self):
        """When provider is None, domain routing is used (default path)."""
        from unittest.mock import patch

        mock_provider = MagicMock()
        mock_provider.search = AsyncMock(return_value=[])

        corpus = _make_corpus(
            {"arxiv": mock_provider},
            topic="stellar evolution",
        )

        with (
            patch("paradigm.literature.domain_router.compute_result_allocation") as mock_alloc,
            patch("paradigm.literature.domain_router.rank_providers") as mock_rank,
        ):
            mock_alloc.return_value = {"arxiv": 10}
            mock_rank.return_value = [("arxiv", 1.0)]

            await corpus.search("test query", max_results=5, provider=None)

            # Domain routing should have been called
            mock_alloc.assert_called_once()
            mock_rank.assert_called_once()

    @pytest.mark.asyncio
    async def test_targeted_provider_includes_local(self):
        """Targeted search still queries internal_corpus when include_local=True."""
        mock_external = MagicMock()
        mock_external.search = AsyncMock(return_value=[])

        mock_local = MagicMock()
        mock_local.search = AsyncMock(return_value=[])

        corpus = _make_corpus(
            {"pubmed": mock_external, "internal_corpus": mock_local},
        )

        await corpus.search("query", max_results=5, provider="pubmed", include_local=True)

        # Both local and targeted provider should be called
        mock_local.search.assert_called_once()
        mock_external.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_targeted_unknown_provider_falls_through(self):
        """When targeted provider is not in the providers dict, falls to domain routing."""
        from unittest.mock import patch

        mock_provider = MagicMock()
        mock_provider.search = AsyncMock(return_value=[])

        corpus = _make_corpus({"arxiv": mock_provider})

        with (
            patch("paradigm.literature.domain_router.compute_result_allocation") as mock_alloc,
            patch("paradigm.literature.domain_router.rank_providers") as mock_rank,
        ):
            mock_alloc.return_value = {"arxiv": 10}
            mock_rank.return_value = [("arxiv", 1.0)]

            await corpus.search("query", max_results=5, provider="pubmed")

            # Falls through to domain routing since pubmed isn't available
            mock_alloc.assert_called_once()
