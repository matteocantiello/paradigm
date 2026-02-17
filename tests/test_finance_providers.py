"""Tests for finance source providers (SSRN, SEC EDGAR, FRED)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradigm.domains.base import SourceProviderConfig, SourceResult
from paradigm.literature.providers import (
    FREDSourceProvider,
    SECEdgarSourceProvider,
    SSRNSourceProvider,
)

# ---------------------------------------------------------------------------
# SSRN Provider Tests
# ---------------------------------------------------------------------------


class TestSSRNSourceProvider:
    @pytest.fixture
    def provider(self):
        return SSRNSourceProvider(rate_limit=1.0)

    @pytest.mark.asyncio
    async def test_search_returns_list(self, provider):
        """Search returns a list of SourceResult objects."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = (
            '<a href="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1234567">'
            "Test Paper Title</a>"
        )
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            provider._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            results = await provider.search("financial markets", max_results=5)
            assert isinstance(results, list)
            for r in results:
                assert isinstance(r, SourceResult)

    @pytest.mark.asyncio
    async def test_search_handles_error(self, provider):
        """Search returns empty list on HTTP error."""
        import httpx

        with patch.object(
            provider._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("Connection error"),
        ):
            results = await provider.search("test query")
            assert results == []

    @pytest.mark.asyncio
    async def test_fetch_returns_document(self, provider):
        """Fetch returns a SourceDocument for a valid ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Paper content</html>"
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            provider._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            doc = await provider.fetch("1234567")
            assert doc is not None
            assert doc.id == "1234567"
            assert doc.source_type == "ssrn"

    def test_parse_search_results(self):
        """Parse SSRN search HTML extracts paper IDs and titles."""
        html = (
            '<a class="title" href="/sol3/papers.cfm?abstract_id=1111111">First Paper</a>'
            '<a class="title" href="/sol3/papers.cfm?abstract_id=2222222">Second Paper</a>'
        )
        results = SSRNSourceProvider._parse_search_results(html, max_results=10)
        assert len(results) == 2
        assert results[0].id == "1111111"
        assert results[1].id == "2222222"


# ---------------------------------------------------------------------------
# SEC EDGAR Provider Tests
# ---------------------------------------------------------------------------


class TestSECEdgarSourceProvider:
    @pytest.fixture
    def provider(self):
        return SECEdgarSourceProvider()

    @pytest.mark.asyncio
    async def test_search_handles_error(self, provider):
        """Search returns empty list on HTTP error."""
        import httpx

        with patch.object(
            provider._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("Connection error"),
        ):
            results = await provider.search("Apple 10-K")
            assert results == []

    @pytest.mark.asyncio
    async def test_search_parses_response(self, provider):
        """Search parses SEC EDGAR API response correctly."""
        mock_data = {
            "hits": {
                "hits": [
                    {
                        "_id": "doc1",
                        "_source": {
                            "file_num": "001-12345",
                            "form_type": "10-K",
                            "entity_name": "Apple Inc.",
                            "file_date": "2024-01-15",
                        },
                    }
                ]
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            provider._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            results = await provider.search("Apple annual report")
            assert len(results) == 1
            assert results[0].source_type == "sec_edgar"
            assert "Apple Inc." in results[0].title
            assert results[0].metadata["form_type"] == "10-K"

    def test_parse_results_static(self):
        """Static parse method extracts filing metadata."""
        data = {
            "hits": {
                "hits": [
                    {
                        "_id": "doc1",
                        "_source": {
                            "file_num": "001-99999",
                            "form_type": "8-K",
                            "entity_name": "Tesla Inc.",
                            "file_date": "2024-06-01",
                        },
                    }
                ]
            }
        }
        results = SECEdgarSourceProvider._parse_results(data, max_results=10)
        assert len(results) == 1
        assert results[0].id == "001-99999"
        assert results[0].metadata["form_type"] == "8-K"


# ---------------------------------------------------------------------------
# FRED Provider Tests
# ---------------------------------------------------------------------------


class TestFREDSourceProvider:
    @pytest.fixture
    def provider(self):
        return FREDSourceProvider(api_key="test-api-key")

    @pytest.fixture
    def provider_no_key(self):
        return FREDSourceProvider(api_key="")

    @pytest.mark.asyncio
    async def test_search_without_api_key(self, provider_no_key):
        """Search returns empty list when no API key is set."""
        results = await provider_no_key.search("GDP")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_without_api_key(self, provider_no_key):
        """Fetch returns None when no API key is set."""
        doc = await provider_no_key.fetch("GDP")
        assert doc is None

    @pytest.mark.asyncio
    async def test_search_parses_response(self, provider):
        """Search parses FRED series search response correctly."""
        mock_data = {
            "seriess": [
                {
                    "id": "GDP",
                    "title": "Gross Domestic Product",
                    "frequency": "Quarterly",
                    "units": "Billions of Dollars",
                    "observation_start": "1947-01-01",
                    "observation_end": "2024-01-01",
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            provider._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            results = await provider.search("GDP")
            assert len(results) == 1
            assert results[0].id == "GDP"
            assert results[0].source_type == "fred"
            assert "Quarterly" in results[0].summary

    @pytest.mark.asyncio
    async def test_fetch_returns_document(self, provider):
        """Fetch returns a SourceDocument for a valid series ID."""
        mock_data = {
            "seriess": [
                {
                    "id": "UNRATE",
                    "title": "Unemployment Rate",
                    "frequency": "Monthly",
                    "units": "Percent",
                    "seasonal_adjustment": "Seasonally Adjusted",
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            provider._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            doc = await provider.fetch("UNRATE")
            assert doc is not None
            assert doc.id == "UNRATE"
            assert doc.source_type == "fred"
            assert doc.title == "Unemployment Rate"
            assert doc.metadata["frequency"] == "Monthly"

    @pytest.mark.asyncio
    async def test_search_handles_error(self, provider):
        """Search returns empty list on HTTP error."""
        import httpx

        with patch.object(
            provider._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("Connection error"),
        ):
            results = await provider.search("test query")
            assert results == []

    def test_parse_results_static(self):
        """Static parse method extracts series metadata."""
        data = {
            "seriess": [
                {
                    "id": "FEDFUNDS",
                    "title": "Federal Funds Effective Rate",
                    "frequency": "Daily",
                    "units": "Percent",
                    "observation_start": "1954-07-01",
                    "observation_end": "2024-12-31",
                },
                {
                    "id": "DFF",
                    "title": "Federal Funds Rate (Daily)",
                    "frequency": "Daily",
                    "units": "Percent",
                    "observation_start": "1954-07-01",
                    "observation_end": "2024-12-31",
                },
            ]
        }
        results = FREDSourceProvider._parse_results(data, max_results=10)
        assert len(results) == 2
        assert results[0].id == "FEDFUNDS"
        assert results[1].id == "DFF"


# ---------------------------------------------------------------------------
# Provider Factory Tests (finance providers)
# ---------------------------------------------------------------------------


class TestFinanceProviderFactory:
    def test_creates_ssrn_provider(self):
        """Factory creates SSRN provider."""
        # Minimal config — only SSRN
        from paradigm.config import LiteratureConfig, StorageConfig
        from paradigm.literature.provider_factory import create_source_providers
        from paradigm.storage.database import Database

        with pytest.importorskip("tempfile").TemporaryDirectory() as tmpdir:
            from pathlib import Path

            db = Database(Path(tmpdir) / "test.db")
            try:
                configs = [SourceProviderConfig(name="ssrn", enabled=True)]
                lit_config = LiteratureConfig()
                storage_config = StorageConfig(data_dir=tmpdir)
                providers = create_source_providers(configs, lit_config, storage_config, db)
                assert "ssrn" in providers
                assert isinstance(providers["ssrn"], SSRNSourceProvider)
            finally:
                db.close()

    def test_creates_fred_provider(self):
        """Factory creates FRED provider."""
        from paradigm.config import LiteratureConfig, StorageConfig
        from paradigm.literature.provider_factory import create_source_providers
        from paradigm.storage.database import Database

        with pytest.importorskip("tempfile").TemporaryDirectory() as tmpdir:
            from pathlib import Path

            db = Database(Path(tmpdir) / "test.db")
            try:
                configs = [SourceProviderConfig(name="fred", enabled=True)]
                lit_config = LiteratureConfig()
                storage_config = StorageConfig(data_dir=tmpdir)
                providers = create_source_providers(configs, lit_config, storage_config, db)
                assert "fred" in providers
                assert isinstance(providers["fred"], FREDSourceProvider)
            finally:
                db.close()

    def test_creates_sec_edgar_provider(self):
        """Factory creates SEC EDGAR provider."""
        from paradigm.config import LiteratureConfig, StorageConfig
        from paradigm.literature.provider_factory import create_source_providers
        from paradigm.storage.database import Database

        with pytest.importorskip("tempfile").TemporaryDirectory() as tmpdir:
            from pathlib import Path

            db = Database(Path(tmpdir) / "test.db")
            try:
                configs = [SourceProviderConfig(name="sec_edgar", enabled=True)]
                lit_config = LiteratureConfig()
                storage_config = StorageConfig(data_dir=tmpdir)
                providers = create_source_providers(configs, lit_config, storage_config, db)
                assert "sec_edgar" in providers
                assert isinstance(providers["sec_edgar"], SECEdgarSourceProvider)
            finally:
                db.close()
