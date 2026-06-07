"""Deterministic tests for the MCP-client literature provider (no network).

The provider discovers tools at runtime and parses results defensively, so we
inject a fake MCP session + tool list and exercise tool-matching + normalization.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from paradigm.literature.mcp_provider import (
    MCPSourceProvider,
    _authors,
    _extract_items,
    _first,
    _parse_text_listing,
    _summarize_exc,
)


class TestConnectFailureDegradesCleanly:
    """An OAuth/connect failure (e.g. an expired token) must mark the provider
    failed so it skips cleanly and arXiv carries — not retry on every search."""

    @pytest.mark.asyncio
    async def test_base_exception_group_sets_connect_failed(self, monkeypatch):
        import mcp.client.streamable_http as sh

        def _boom(*_a, **_k):
            # What anyio raises when the OAuth flow needs interactive re-login —
            # a BaseExceptionGroup, which is NOT an Exception.
            raise BaseExceptionGroup("oauth", [RuntimeError("needs interactive login")])

        monkeypatch.setattr(sh, "streamablehttp_client", _boom)
        p = MCPSourceProvider(
            server_url="https://x/mcp", auth_mode="bearer", auth_token="t", name="alphaxiv"
        )

        # First call: fails, but cleanly (RuntimeError, not the raw group) and flags it.
        with pytest.raises(RuntimeError):
            await p._ensure_session()
        assert p._connect_failed is True

        # Second call: fast-fails on the flag — does NOT reconnect (no retry spam).
        monkeypatch.setattr(
            sh, "streamablehttp_client", lambda *a, **k: pytest.fail("should not reconnect")
        )
        with pytest.raises(RuntimeError, match="unavailable"):
            await p._ensure_session()

    def test_parse_date_for_year_display(self):
        """alphaXiv listings carry a published date but no author names; capture the
        date so the UI shows a year instead of '(?)'."""
        from paradigm.literature.mcp_provider import _parse_date

        assert _parse_date({"published": "2024-03-05"}).year == 2024
        assert _parse_date({"year": "2019"}).year == 2019
        assert _parse_date({}) is None

    def test_summarize_exc_unwraps_group(self):
        grp = BaseExceptionGroup("g", [RuntimeError("needs login")])
        assert "needs login" in _summarize_exc(grp)


def _tool(name: str, props: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, inputSchema={"properties": props or {}})


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def _result(content=None, structured=None) -> SimpleNamespace:
    return SimpleNamespace(content=content or [], structuredContent=structured)


class FakeSession:
    def __init__(self, result):
        self._result = result
        self.calls: list[tuple] = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return self._result


def _provider(tools, result, **kw) -> MCPSourceProvider:
    p = MCPSourceProvider(server_url="http://x", source_type="alphaxiv", **kw)
    p._tools = tools
    p._session = FakeSession(result)  # bypass network connect
    return p


# --- helpers ---------------------------------------------------------------
def test_first_and_authors_helpers():
    assert _first({"a": "", "b": "x"}, "a", "b") == "x"
    assert _first({"n": 3}, "n") == "3"
    assert _authors({"authors": ["A", "B"]}) == ["A", "B"]
    assert _authors({"authors": [{"name": "Jane Doe"}, {"full_name": "J. R."}]}) == [
        "Jane Doe",
        "J. R.",
    ]
    assert _authors({"author": "Solo"}) == ["Solo"]


def test_extract_items_prefers_structured_then_text():
    r = _result(structured={"results": [{"id": "1"}, {"id": "2"}]})
    assert [i["id"] for i in _extract_items(r)] == ["1", "2"]
    r2 = _result(content=[_text(json.dumps([{"id": "9"}]))])
    assert _extract_items(r2) == [{"id": "9"}]
    r3 = _result(content=[_text(json.dumps({"papers": [{"id": "7"}]}))])
    assert _extract_items(r3) == [{"id": "7"}]


# --- tool discovery --------------------------------------------------------
def test_picks_fulltext_search_over_embedding_and_content_tool():
    p = _provider(
        [
            _tool("embedding_similarity_search"),
            _tool("full_text_search"),
            _tool("get_paper_content"),
        ],
        _result(),
    )
    from paradigm.literature.mcp_provider import _CONTENT_HINTS, _EMBED_HINTS, _SEARCH_HINTS

    assert p._pick_tool(None, _SEARCH_HINTS, avoid=_EMBED_HINTS) == "full_text_search"
    assert p._pick_tool(None, _CONTENT_HINTS) == "get_paper_content"


def test_search_override_wins():
    p = _provider([_tool("full_text_search"), _tool("agentic_retrieval")], _result())
    from paradigm.literature.mcp_provider import _SEARCH_HINTS

    p._search_override = "agentic_retrieval"
    assert p._pick_tool(p._search_override, _SEARCH_HINTS) == "agentic_retrieval"


# --- search ----------------------------------------------------------------
async def test_search_normalizes_structured_results():
    tools = [_tool("full_text_search", {"query": {}, "limit": {}}), _tool("get_paper_content")]
    result = _result(
        structured={
            "results": [
                {
                    "paper_id": "2509.12411",
                    "title": "Cepheid P-L Relation",
                    "authors": [{"name": "A. Star"}],
                    "tldr": "A tight period-luminosity law.",
                    "url": "https://arxiv.org/abs/2509.12411",
                }
            ]
        }
    )
    p = _provider(tools, result)
    out = await p.search("cepheid period luminosity", max_results=5)
    assert len(out) == 1
    sr = out[0]
    assert sr.id == "2509.12411"
    assert sr.source_type == "alphaxiv"
    assert sr.title == "Cepheid P-L Relation"
    assert sr.authors == ["A. Star"]
    assert sr.summary == "A tight period-luminosity law."  # tldr preferred
    # The query + limit args were routed by the discovered schema keys.
    assert p._session.calls == [
        ("full_text_search", {"query": "cepheid period luminosity", "limit": 5})
    ]


async def test_search_from_text_json_and_synthesized_id():
    tools = [_tool("search_papers", {"query": {}})]
    result = _result(content=[_text(json.dumps([{"title": "No ID Paper", "abstract": "x"}]))])
    p = _provider(tools, result)
    out = await p.search("q")
    assert len(out) == 1
    assert out[0].title == "No ID Paper"
    assert out[0].id.startswith("src-")  # _ensure_id synthesized from title
    assert out[0].summary == "x"  # falls back to abstract when no tldr/breakdown


async def test_search_empty_when_no_search_tool():
    p = _provider([_tool("get_paper_content")], _result())
    assert await p.search("q") == []


# --- fetch -----------------------------------------------------------------
async def test_fetch_returns_structured_breakdown():
    tools = [_tool("get_paper_content", {"paper_id": {}})]
    result = _result(
        structured={"breakdown": "## Summary\nKey claim ...", "title": "Cepheids", "url": "u"}
    )
    p = _provider(tools, result)
    doc = await p.fetch("2509.12411")
    assert doc is not None
    assert doc.id == "2509.12411"
    assert doc.source_type == "alphaxiv"
    assert doc.full_text.startswith("## Summary")
    assert doc.sections == {"breakdown": "## Summary\nKey claim ..."}
    assert p._session.calls == [("get_paper_content", {"paper_id": "2509.12411"})]


async def test_fetch_none_when_no_content():
    p = _provider([_tool("get_paper_content", {"paper_id": {}})], _result())
    assert await p.fetch("x") is None


async def test_close_is_safe_when_unconnected():
    p = MCPSourceProvider(server_url="http://x")
    await p.close()  # must not raise (never connected)


# --- alphaXiv text listing (discover_papers returns plain text, not JSON) ---
_ALPHAXIV_LISTING = (
    "1. [ID=2502.17438] **The Legacy of Henrietta Leavitt: A Re-analysis**. "
    "Published 2025-02-24 by Space Telescope Science Institute, Johns Hopkins "
    "University: Henrietta Swan Leavitt's discovery revolutionized astronomy...\n"
    "2. [ID=astro-ph/9907236] **OGLE Cepheids in the Magellanic Clouds**. "
    "Published 1999-07-16: We present Period-Luminosity relations for 1280 Cepheids."
)


def test_parse_text_listing_alphaxiv():
    items = _parse_text_listing(_ALPHAXIV_LISTING)
    assert len(items) == 2
    a, b = items
    assert a["id"] == "2502.17438"
    assert a["title"] == "The Legacy of Henrietta Leavitt: A Re-analysis"
    assert a["url"] == "https://arxiv.org/abs/2502.17438"
    assert a["summary"].startswith("Henrietta Swan Leavitt")
    # The "by …" clause is affiliations — never mislabeled as authors.
    assert a["affiliations"] == ["Space Telescope Science Institute", "Johns Hopkins University"]
    assert "authors" not in a
    assert a["published"] == "2025-02-24"
    # Old-style arXiv id → abs URL; no "by" clause → no affiliations.
    assert b["id"] == "astro-ph/9907236"
    assert b["url"] == "https://arxiv.org/abs/astro-ph/9907236"
    assert "affiliations" not in b


def test_parse_text_listing_strips_control_chars():
    items = _parse_text_listing("1. [ID=1.1] **A\x08B Title**. Published 2020-01-01: ok")
    # Control char → space (safe: never merges words across a mangled separator).
    assert items[0]["title"] == "A B Title"


def test_parse_text_listing_ignores_non_listing_text():
    # Free-form paper body text must never be parsed as a listing.
    assert _parse_text_listing("arXiv:1103.0275v1 [astro-ph.SR]\nABSTRACT\n1. Introduction") == []


async def test_search_parses_text_listing_results():
    tools = [
        _tool(
            "discover_papers",
            {
                "keywords": {"type": "array"},
                "question": {"type": "string"},
                "difficulty": {"type": "number", "minimum": 1, "maximum": 10},
            },
        ),
        _tool("get_paper_content", {"url": {"type": "string", "format": "uri"}}),
    ]
    p = _provider(tools, _result(content=[_text(_ALPHAXIV_LISTING)]))
    out = await p.search("period-luminosity relation Cepheids", max_results=5)
    assert [r.id for r in out] == ["2502.17438", "astro-ph/9907236"]
    assert out[0].url == "https://arxiv.org/abs/2502.17438"
    assert out[0].authors == []  # affiliations are not authors
    assert out[0].summary.startswith("Henrietta Swan Leavitt")


def test_build_search_args_discover_shape():
    tools = [
        _tool(
            "discover_papers",
            {
                "keywords": {"type": "array"},
                "question": {"type": "string"},
                "difficulty": {"type": "number", "minimum": 1, "maximum": 10},
            },
        )
    ]
    p = _provider(tools, _result(), search_difficulty=2)
    args = p._build_search_args("discover_papers", "period-luminosity relation for Cepheids", 5)
    assert isinstance(args["keywords"], list) and args["keywords"]  # array of terms
    assert "for" not in args["keywords"]  # stopword dropped
    assert args["question"] == "period-luminosity relation for Cepheids"
    assert args["difficulty"] == 2  # configured, within [1, 10]


def test_build_search_args_clamps_difficulty_to_schema():
    tools = [
        _tool(
            "discover_papers",
            {
                "keywords": {"type": "array"},
                "question": {"type": "string"},
                "difficulty": {"type": "number", "minimum": 1, "maximum": 3},
            },
        )
    ]
    p = _provider(tools, _result(), search_difficulty=9)
    args = p._build_search_args("discover_papers", "q", 5)
    assert args["difficulty"] == 3  # clamped to schema maximum


def test_pick_tool_matches_discover_papers():
    from paradigm.literature.mcp_provider import _EMBED_HINTS, _SEARCH_HINTS

    p = _provider([_tool("discover_papers"), _tool("get_paper_content")], _result())
    assert p._pick_tool(None, _SEARCH_HINTS, avoid=_EMBED_HINTS) == "discover_papers"


async def test_fetch_coerces_bare_id_to_url_arg():
    tools = [_tool("get_paper_content", {"url": {"type": "string", "format": "uri"}})]
    result = _result(content=[_text("Full paper text body ...")])
    p = _provider(tools, result)
    doc = await p.fetch("1103.0275")
    assert doc is not None and doc.full_text.startswith("Full paper text")
    # Bare arXiv id was promoted to a URL for the url-typed arg.
    assert p._session.calls == [("get_paper_content", {"url": "https://arxiv.org/abs/1103.0275"})]


async def test_fetch_passes_url_through_when_already_url():
    tools = [_tool("get_paper_content", {"url": {"type": "string", "format": "uri"}})]
    p = _provider(tools, _result(content=[_text("body")]))
    await p.fetch("https://alphaxiv.org/overview/2307.12307")
    assert p._session.calls[0][1] == {"url": "https://alphaxiv.org/overview/2307.12307"}


# --- degradation: a flaky / expired-token MCP server must never crash a run ---


class _RaisingSession:
    """A session whose tool call blows up — simulating an OAuth/expiry failure
    mid-session (which surfaces as a raw RuntimeError or anyio BaseExceptionGroup)."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
        self.calls: list = []

    async def call_tool(self, name, args):
        raise self._exc


async def test_search_degrades_on_base_exception_group():
    # An expired alphaXiv token surfaces from anyio as a BaseExceptionGroup (NOT an
    # Exception) wrapping the raw "needs interactive login" error. It must degrade
    # to no results so arXiv + the other providers carry the run.
    p = _provider([_tool("full_text_search", {"query": {}})], _result())
    p._session = _RaisingSession(
        BaseExceptionGroup("oauth", [RuntimeError("needs a one-time interactive login")])
    )
    assert await p.search("q") == []


async def test_fetch_degrades_on_raw_login_runtimeerror():
    p = _provider([_tool("get_paper_content", {"paper_id": {}})], _result())
    p._session = _RaisingSession(RuntimeError("needs a one-time interactive login"))
    assert await p.fetch("2501.00001") is None


async def test_search_and_fetch_degrade_when_connect_already_failed():
    # No live session + a prior connect failure -> _ensure_session raises; both
    # public methods must swallow it into empty results, not propagate.
    p = MCPSourceProvider(server_url="http://x", source_type="alphaxiv", name="alphaxiv")
    p._connect_failed = True
    assert await p.search("q") == []
    assert await p.fetch("x") is None


async def test_cancellation_still_propagates():
    # A genuine cycle cancellation must NOT be swallowed by the degrade guard.
    p = _provider([_tool("full_text_search", {"query": {}})], _result())
    p._session = _RaisingSession(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await p.search("q")
