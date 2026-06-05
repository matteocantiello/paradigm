"""Tests for the resilient arXiv request path: global rate gate, transient
retries, and Retry-After-aware 429 backoff."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from paradigm.literature.arxiv import ArxivClient, _arxiv_rate_gate

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>0</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>0</opensearch:itemsPerPage>
</feed>"""


def _resp(status: int = 200, *, text: str = _FEED, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        text=text,
        headers=headers or {},
        request=httpx.Request("GET", "https://export.arxiv.org/api/query"),
    )


def _client_with_gets(*side_effect) -> ArxivClient:
    """ArxivClient (no spacing) whose underlying httpx client is fully mocked."""
    client = ArxivClient(rate_limit=0.0)
    client._client = MagicMock()
    client._client.get = AsyncMock(side_effect=list(side_effect))
    return client


@patch("paradigm.literature.arxiv.asyncio.sleep", new_callable=AsyncMock)
async def test_429_retries_then_succeeds(mock_sleep):
    client = _client_with_gets(_resp(429), _resp(429), _resp(200))
    resp = await client._rate_limited_get("https://x")
    assert resp.status_code == 200
    assert client._client.get.await_count == 3
    assert mock_sleep.await_count == 2  # two backoffs between three attempts


@patch("paradigm.literature.arxiv.asyncio.sleep", new_callable=AsyncMock)
async def test_transient_timeout_retries_then_succeeds(mock_sleep):
    client = _client_with_gets(httpx.ReadTimeout("slow"), _resp(200))
    resp = await client._rate_limited_get("https://x")
    assert resp.status_code == 200
    assert client._client.get.await_count == 2
    assert mock_sleep.await_count == 1


@patch("paradigm.literature.arxiv.asyncio.sleep", new_callable=AsyncMock)
async def test_transient_error_exhausted_reraises(mock_sleep):
    client = _client_with_gets(*([httpx.ReadTimeout("slow")] * 5))
    with pytest.raises(httpx.ReadTimeout):
        await client._rate_limited_get("https://x", max_retries=2)
    assert client._client.get.await_count == 3  # initial + 2 retries


@patch("paradigm.literature.arxiv.asyncio.sleep", new_callable=AsyncMock)
async def test_429_exhausted_raises_status_error(mock_sleep):
    client = _client_with_gets(*([_resp(429)] * 5))
    with pytest.raises(httpx.HTTPStatusError):
        await client._rate_limited_get("https://x", max_retries=2)


@patch("paradigm.literature.arxiv.asyncio.sleep", new_callable=AsyncMock)
async def test_429_honors_retry_after_header(mock_sleep):
    client = _client_with_gets(_resp(429, headers={"Retry-After": "5"}), _resp(200))
    resp = await client._rate_limited_get("https://x")
    assert resp.status_code == 200
    mock_sleep.assert_awaited_once_with(5.0)  # honored verbatim, no jitter


@patch("paradigm.literature.arxiv.asyncio.sleep", new_callable=AsyncMock)
async def test_retry_after_capped_at_60s(mock_sleep):
    client = _client_with_gets(_resp(429, headers={"Retry-After": "9999"}), _resp(200))
    await client._rate_limited_get("https://x")
    mock_sleep.assert_awaited_once_with(60.0)


async def test_rate_gate_is_process_global():
    """All ArxivClient instances must share one rate-limit lock per loop, so
    arXiv sees a single global cadence regardless of how many clients exist."""
    gate_a = _arxiv_rate_gate()
    gate_b = _arxiv_rate_gate()
    assert gate_a is gate_b
