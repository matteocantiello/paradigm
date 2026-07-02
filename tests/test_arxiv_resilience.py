"""Tests for the resilient arXiv request path: global rate gate, transient
retries, and Retry-After-aware 429 backoff."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from paradigm.literature.arxiv import (
    ArxivClient,
    ArxivUnavailable,
    _arxiv_circuit_is_open,
    _arxiv_rate_gate,
    _reset_arxiv_circuit,
)


@pytest.fixture(autouse=True)
def _clean_circuit():
    """Reset the process-global arXiv circuit breaker around every test."""
    _reset_arxiv_circuit()
    yield
    _reset_arxiv_circuit()


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


@patch("paradigm.literature.arxiv.asyncio.sleep", new_callable=AsyncMock)
async def test_circuit_breaker_opens_then_fails_fast(mock_sleep):
    """After repeated failures the breaker opens, so the next call fails INSTANTLY
    (no network) — preventing a hard-down arXiv from making cycles crawl."""
    # Two fully-failed calls (each exhausts retries) → breaker opens at threshold 2.
    c1 = _client_with_gets(*([httpx.ReadTimeout("down")] * 5))
    with pytest.raises(httpx.ReadTimeout):
        await c1._rate_limited_get("https://x")
    c2 = _client_with_gets(*([httpx.ReadTimeout("down")] * 5))
    with pytest.raises(httpx.ReadTimeout):
        await c2._rate_limited_get("https://x")

    assert _arxiv_circuit_is_open()

    # Next call must fast-fail WITHOUT hitting the network.
    c3 = _client_with_gets(_resp(200))  # would succeed if it tried
    with pytest.raises(ArxivUnavailable):
        await c3._rate_limited_get("https://x")
    c3._client.get.assert_not_called()


@patch("paradigm.literature.arxiv.asyncio.sleep", new_callable=AsyncMock)
async def test_circuit_breaker_resets_on_success(mock_sleep):
    """A single failure must NOT open the breaker, and a success keeps it closed."""
    c1 = _client_with_gets(*([httpx.ReadTimeout("blip")] * 5))
    with pytest.raises(httpx.ReadTimeout):
        await c1._rate_limited_get("https://x")
    assert not _arxiv_circuit_is_open()  # 1 failure < threshold

    c2 = _client_with_gets(_resp(200))
    assert (await c2._rate_limited_get("https://x")).status_code == 200
    assert not _arxiv_circuit_is_open()  # success reset the counter


# --------------------------------------------------------------------------- #
# External (non-arXiv) PDF fetches must not touch the arXiv gate or breaker
# --------------------------------------------------------------------------- #


@patch("paradigm.literature.arxiv.subprocess.run")
async def test_external_pdf_failures_do_not_open_arxiv_breaker(mock_run):
    # Seed discovery fetches journal PDFs right before IDEATION's arXiv searches;
    # two paywall 403s must NOT open the arXiv circuit (it would fast-fail those
    # searches for the whole cooldown).
    mock_run.return_value = MagicMock(returncode=1, stdout=b"")
    client = _client_with_gets(_resp(403), _resp(403))
    assert await client.fetch_pdf_bytes("https://academic.oup.com/mnras/x.pdf") is None
    assert await client.fetch_pdf_bytes("https://www.aanda.org/y.pdf") is None
    assert not _arxiv_circuit_is_open()


async def test_arxiv_pdf_fetch_uses_rate_limited_path():
    client = _client_with_gets()
    client._rate_limited_get = AsyncMock(return_value=_resp(200))
    await client.fetch_pdf_bytes("https://arxiv.org/pdf/2501.12345")
    client._rate_limited_get.assert_awaited_once()


async def test_external_pdf_fetch_bypasses_rate_limited_path():
    pdf = httpx.Response(
        status_code=200,
        content=b"%PDF-1.4 fake",
        headers={"content-type": "application/pdf"},
        request=httpx.Request("GET", "https://academic.oup.com/mnras/x.pdf"),
    )
    client = _client_with_gets(pdf)
    client._rate_limited_get = AsyncMock()
    out = await client.fetch_pdf_bytes("https://academic.oup.com/mnras/x.pdf")
    assert out == b"%PDF-1.4 fake"
    client._rate_limited_get.assert_not_awaited()
