"""Deterministic tests for the MCP-client literature provider (no network).

The provider discovers tools at runtime and parses results defensively, so we
inject a fake MCP session + tool list and exercise tool-matching + normalization.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from paradigm.literature.mcp_provider import (
    MCPSourceProvider,
    _authors,
    _extract_items,
    _first,
)


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
        [_tool("embedding_similarity_search"), _tool("full_text_search"), _tool("get_paper_content")],
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
    assert p._session.calls == [("full_text_search", {"query": "cepheid period luminosity", "limit": 5})]


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
