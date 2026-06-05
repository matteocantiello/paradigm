"""MCP-client ``SourceProvider`` — consume an external literature MCP server.

Orchestrator-as-MCP-client (deterministic, per ``DECISIONS.md``): the orchestrator
connects to a remote MCP server over streamable HTTP, **discovers** its tools at
runtime, and exposes search/fetch behind the existing ``SourceProvider``
abstraction. It is **optional + additive** — when unconfigured, the ``mcp``
package is absent, or the server is unreachable, it yields no results and the
in-house providers carry the cycle, so the offline single-node posture holds.

Default target: **alphaXiv** (``https://api.alphaxiv.org/mcp/v1``). Its
``get_paper_content`` tool returns an LLM-optimized *structured breakdown* rather
than raw PDF text — far cheaper to inject than a scraped, pymupdf-extracted PDF,
which is the whole point of routing literature through MCP.

The server's exact tool names / argument keys vary, so we don't hardcode them:
tools are matched by name heuristics (with config overrides) and results are
parsed defensively. alphaXiv requires an API key (``Authorization: Bearer``);
supply it via the configured env var.
"""

from __future__ import annotations

import json
import logging
from contextlib import AsyncExitStack
from typing import Any

from paradigm.domains.base import SourceDocument, SourceProvider, SourceResult

_logger = logging.getLogger(__name__)

# Heuristics for matching the server's machine tool-names (lowercased substring).
_SEARCH_HINTS = (
    "search_papers",
    "full_text",
    "fulltext",
    "keyword",
    "search",
    "find_papers",
    "retrieval",
    "retrieve",
    "find",
)
_EMBED_HINTS = ("embed", "similar", "vector")  # avoid these for plain search
_CONTENT_HINTS = (
    "get_paper_content",
    "paper_content",
    "read_paper",
    "get_paper",
    "content",
    "fetch_paper",
)
_QUERY_ARG_HINTS = ("query", "q", "search_query", "keywords", "text", "prompt", "question")
_ID_ARG_HINTS = ("paper_id", "arxiv_id", "id", "arxiv", "paper", "universal_id", "doi")
_LIMIT_ARG_HINTS = ("limit", "max_results", "top_k", "n", "num_results", "count")


# ---------------------------------------------------------------------------
# Defensive parsing helpers (the upstream result schema is not guaranteed)
# ---------------------------------------------------------------------------
def _first(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, (int, float)):
            return str(v)
    return ""


def _authors(d: dict) -> list[str]:
    raw = d.get("authors") or d.get("author") or d.get("creators")
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    out: list[str] = []
    if isinstance(raw, list):
        for a in raw:
            if isinstance(a, str) and a.strip():
                out.append(a.strip())
            elif isinstance(a, dict):
                name = _first(a, "name", "full_name", "display_name")
                if name:
                    out.append(name)
    return out


def _result_text(result: Any) -> str:
    """Join the text of all TextContent blocks in an MCP CallToolResult."""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


def _extract_items(result: Any) -> list[dict]:
    """Pull a list of paper dicts out of an MCP tool result.

    Prefers ``structuredContent`` (machine-readable), falls back to JSON parsed
    from text blocks. Tolerates {results:[...]} / {papers:[...]} / a bare list /
    a single object.
    """

    def _coerce(obj: Any) -> list[dict]:
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            for key in ("results", "papers", "items", "data", "matches", "hits"):
                v = obj.get(key)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
            return [obj]
        return []

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        items = _coerce(structured)
        if items:
            return items

    text = _result_text(result)
    if text:
        try:
            return _coerce(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            pass
    return []


class MCPSourceProvider(SourceProvider):
    """A literature ``SourceProvider`` backed by a remote MCP server."""

    name = "mcp"

    def __init__(
        self,
        *,
        server_url: str,
        auth_token: str | None = None,
        name: str = "mcp",
        search_tool: str | None = None,
        content_tool: str | None = None,
        timeout: float = 30.0,
        source_type: str = "mcp",
        logger: logging.Logger | None = None,
    ) -> None:
        self.name = name
        self._url = server_url
        self._auth = auth_token
        self._search_override = search_tool
        self._content_override = content_tool
        self._timeout = timeout
        self._source_type = source_type
        self._log = logger or _logger
        self._stack: AsyncExitStack | None = None
        self._session: Any | None = None
        self._tools: list[Any] = []
        self._connect_failed = False

    # -- connection -------------------------------------------------------
    async def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session
        if self._connect_failed:
            raise RuntimeError(f"MCP server {self.name!r} unavailable (prior connect failed)")
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as e:  # optional dependency
            self._connect_failed = True
            raise RuntimeError(
                "The 'mcp' package is required for the MCP literature provider — "
                "install it with: pip install paradigm[mcp]"
            ) from e

        headers = {"Authorization": f"Bearer {self._auth}"} if self._auth else None
        stack = AsyncExitStack()
        try:
            transport = await stack.enter_async_context(
                streamablehttp_client(self._url, headers=headers)
            )
            read, write = transport[0], transport[1]
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
        except Exception:
            await stack.aclose()
            self._connect_failed = True
            self._log.warning(
                "MCP literature provider %r could not connect to %s (check auth/URL)",
                self.name,
                self._url,
            )
            raise
        self._stack = stack
        self._session = session
        self._tools = list(listed.tools)
        return session

    # -- tool discovery ---------------------------------------------------
    def _pick_tool(self, override: str | None, hints: tuple[str, ...], *, avoid=()) -> str | None:
        names = {t.name for t in self._tools}
        if override and override in names:
            return override
        for hint in hints:
            for tool in self._tools:
                low = tool.name.lower()
                if hint in low and not any(a in low for a in avoid):
                    return tool.name
        return None

    def _input_key(self, tool_name: str, hints: tuple[str, ...], default: str | None) -> str | None:
        tool = next((t for t in self._tools if t.name == tool_name), None)
        props = (getattr(tool, "inputSchema", None) or {}).get("properties", {}) if tool else {}
        for h in hints:
            if h in props:
                return h
        return default

    # -- SourceProvider API ----------------------------------------------
    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        session = await self._ensure_session()
        tool = self._pick_tool(self._search_override, _SEARCH_HINTS, avoid=_EMBED_HINTS)
        if tool is None:
            return []
        args: dict[str, Any] = {self._input_key(tool, _QUERY_ARG_HINTS, "query"): query}
        limit_key = self._input_key(tool, _LIMIT_ARG_HINTS, None)
        if limit_key:
            args[limit_key] = max_results
        result = await session.call_tool(tool, args)
        out: list[SourceResult] = []
        for item in _extract_items(result)[:max_results]:
            sr = self._to_source_result(item)
            if sr is not None:
                out.append(sr)
        return out

    async def fetch(self, source_id: str) -> SourceDocument | None:
        session = await self._ensure_session()
        tool = self._pick_tool(self._content_override, _CONTENT_HINTS)
        if tool is None:
            return None
        idkey = self._input_key(tool, _ID_ARG_HINTS, "paper_id")
        result = await session.call_tool(tool, {idkey: source_id})
        return self._to_source_document(source_id, result)

    # -- normalization ----------------------------------------------------
    def _to_source_result(self, item: dict) -> SourceResult | None:
        if not isinstance(item, dict):
            return None
        return SourceResult(
            id=_first(item, "id", "paper_id", "arxiv_id", "paperId", "universal_id", "doi"),
            source_type=self._source_type,
            title=_first(item, "title", "name"),
            authors=_authors(item),
            # alphaXiv-style: prefer the pre-digested breakdown/tldr over abstract.
            summary=_first(item, "tldr", "breakdown", "summary", "abstract", "description"),
            url=_first(item, "url", "link", "pdf_url", "abs_url"),
        )

    def _to_source_document(self, source_id: str, result: Any) -> SourceDocument | None:
        items = _extract_items(result)
        obj = items[0] if items else {}
        breakdown = _first(obj, "breakdown", "content", "structured_content", "summary") if obj else ""
        full = breakdown or _result_text(result)
        if not full:
            return None
        return SourceDocument(
            id=source_id,
            source_type=self._source_type,
            title=(_first(obj, "title", "name") or source_id) if obj else source_id,
            authors=_authors(obj) if obj else [],
            full_text=full,
            sections={"breakdown": breakdown} if breakdown else {},
            url=_first(obj, "url", "link") if obj else "",
        )

    async def close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception as e:  # best-effort teardown
                self._log.debug("MCP provider %r close failed: %s", self.name, e)
            finally:
                self._stack = None
                self._session = None
