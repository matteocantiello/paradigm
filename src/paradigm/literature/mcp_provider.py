"""MCP-client ``SourceProvider`` — consume an external literature MCP server.

Orchestrator-as-MCP-client (deterministic, per ``DECISIONS.md``): the orchestrator
connects to a remote MCP server over streamable HTTP, **discovers** its tools at
runtime, and exposes search/fetch behind the existing ``SourceProvider``
abstraction. It is **optional + additive** — when unconfigured, the ``mcp``
package is absent, or the server is unreachable, it yields no results and the
in-house providers carry the cycle, so the offline single-node posture holds.

Default target: **alphaXiv** (``https://api.alphaxiv.org/mcp/v1``). Its
``get_paper_content`` tool returns an LLM-optimized report rather than raw PDF
text — far cheaper to inject than a scraped, pymupdf-extracted PDF, which is the
whole point of routing literature through MCP.

The server's exact tool names / argument keys / result shapes vary, so we don't
hardcode them. Tools are matched by name heuristics (with config overrides),
**search arguments are built from each tool's JSON Schema** (alphaXiv's
``discover_papers`` requires a ``keywords`` array, a ``question`` string and a
``difficulty`` number — not a single query), and results are parsed defensively:
``structuredContent`` → JSON-in-text → a numbered-listing text parser (alphaXiv
returns ``N. [ID=<id>] **title**. Published <date> [by <affils>]: <abstract>``).

alphaXiv is OAuth-gated (Clerk) — there is no static API key. Run ``paradigm
mcp-login`` once; the token is cached and auto-refreshed for headless runs.
"""

from __future__ import annotations

import json
import logging
import re
from contextlib import AsyncExitStack
from typing import Any

from paradigm.domains.base import SourceDocument, SourceProvider, SourceResult

_logger = logging.getLogger(__name__)

# Heuristics for matching the server's machine tool-names (lowercased substring).
_SEARCH_HINTS = (
    "search_papers",
    "discover_papers",
    "discover",
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
# ``url`` is last so a dedicated id arg wins; alphaXiv's get_paper_content takes a url.
_ID_ARG_HINTS = ("paper_id", "arxiv_id", "id", "arxiv", "paper", "universal_id", "doi", "url")
_LIMIT_ARG_HINTS = ("limit", "max_results", "top_k", "n", "num_results", "count")
# Roles used when building search args from a tool's JSON Schema.
_KEYWORD_NAME_HINTS = ("keyword", "term", "tag")
_QUESTION_NAME_HINTS = ("question", "query", "search_query", "q", "text", "prompt", "description")
_DIFFICULTY_NAME_HINTS = ("difficulty", "effort", "depth", "rounds", "detail")
_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "with",
     "via", "using", "from", "about", "is", "are", "its", "their"}
)


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


def _clean_ws(s: str) -> str:
    """Strip C0/C1 control chars and collapse whitespace (PDF-extraction noise)."""
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def _arxiv_url(pid: str) -> str:
    pid = (pid or "").strip()
    if not pid:
        return ""
    if pid.startswith("http"):
        return pid
    return f"https://arxiv.org/abs/{pid}"


def _result_text(result: Any) -> str:
    """Join the text of all TextContent blocks in an MCP CallToolResult."""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


# alphaXiv discover_papers listing: ``N. [ID=<id>] **title**. Published <date>
# [by <affils>]: <abstract>``. Abstracts may span lines (truncated with "…").
_LISTING_ENTRY = re.compile(
    r"(?ms)^\s*\d+\.\s*\[ID=(?P<id>[^\]]+)\]\s*"
    r"\*\*(?P<title>.+?)\*\*\.?\s*"
    r"(?:Published\s*(?P<date>\d{4}-\d{2}-\d{2})\s*)?"
    r"(?:by\s+(?P<authors>.+?)\s*)?"
    r":\s*(?P<summary>.*?)\s*"
    r"(?=^\s*\d+\.\s*\[ID=|\Z)"
)


def _parse_text_listing(text: str) -> list[dict]:
    """Parse a numbered ``[ID=..] **title** … : abstract`` listing into dicts.

    Strict by design (requires the enumerator + ``[ID=…]`` marker) so it never
    matches free-form paper body text passed through ``fetch``.
    """
    items: list[dict] = []
    for m in _LISTING_ENTRY.finditer(text or ""):
        pid = (m.group("id") or "").strip()
        if not pid:
            continue
        item: dict[str, Any] = {
            "id": pid,
            "title": _clean_ws(m.group("title") or ""),
            "summary": _clean_ws(m.group("summary") or "").rstrip("… ."),
            "url": _arxiv_url(pid),
        }
        # The "by …" clause in alphaXiv listings is *affiliations*, not author
        # names — keep them separate so we never mislabel institutions as authors.
        affils_raw = _clean_ws(m.group("authors") or "")
        affils = [a.strip() for a in re.split(r"[;,/]", affils_raw) if a.strip()]
        if affils:
            item["affiliations"] = affils
        if m.group("date"):
            item["published"] = m.group("date")
        items.append(item)
    return items


def _extract_items(result: Any) -> list[dict]:
    """Pull a list of paper dicts out of an MCP tool result.

    Prefers ``structuredContent`` (machine-readable), then JSON parsed from text
    blocks, then a numbered-listing text parser (alphaXiv). Tolerates
    {results:[...]} / {papers:[...]} / a bare list / a single object.
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
            coerced = _coerce(json.loads(text))
            if coerced:
                return coerced
        except (json.JSONDecodeError, ValueError):
            pass
        listed = _parse_text_listing(text)
        if listed:
            return listed
    return []


class MCPSourceProvider(SourceProvider):
    """A literature ``SourceProvider`` backed by a remote MCP server."""

    name = "mcp"

    def __init__(
        self,
        *,
        server_url: str,
        auth_mode: str = "oauth",  # "oauth" | "bearer" | "none"
        auth_token: str | None = None,  # for auth_mode="bearer"
        oauth_scope: str = "openid profile email offline_access",
        name: str = "mcp",
        search_tool: str | None = None,
        content_tool: str | None = None,
        search_difficulty: int = 3,
        timeout: float = 30.0,
        source_type: str = "mcp",
        logger: logging.Logger | None = None,
    ) -> None:
        self.name = name
        self._url = server_url
        self._auth_mode = auth_mode
        self._auth = auth_token
        self._oauth_scope = oauth_scope
        self._search_override = search_tool
        self._content_override = content_tool
        self._difficulty = search_difficulty
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

        # Resolve auth. OAuth-gated servers (alphaXiv) use a cached token from a
        # prior `paradigm mcp-login`; a static Bearer token is also supported.
        headers = None
        auth = None
        if self._auth_mode == "oauth":
            from paradigm.literature.mcp_auth import build_oauth_provider

            auth, _ = build_oauth_provider(
                server_url=self._url, name=self.name, scope=self._oauth_scope, interactive=False
            )
        elif self._auth_mode == "bearer" and self._auth:
            headers = {"Authorization": f"Bearer {self._auth}"}

        stack = AsyncExitStack()
        try:
            transport = await stack.enter_async_context(
                streamablehttp_client(self._url, headers=headers, auth=auth)
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

    def _schema(self, tool_name: str) -> dict:
        tool = next((t for t in self._tools if t.name == tool_name), None)
        return getattr(tool, "inputSchema", None) or {}

    def _input_key(self, tool_name: str, hints: tuple[str, ...], default: str | None) -> str | None:
        props = self._schema(tool_name).get("properties", {})
        for h in hints:
            if h in props:
                return h
        return default

    # -- search-argument construction (schema-driven) ---------------------
    def _as_keywords(self, query: str, limit: int = 4) -> list[str]:
        toks = [t for t in re.split(r"[\s,;]+", (query or "").strip()) if t]
        kept = [t for t in toks if t.lower() not in _STOPWORDS and len(t) >= 2]
        kept = kept or toks
        return (kept or [query or ""])[:limit]

    @staticmethod
    def _name_matches(key: str, hints: tuple[str, ...]) -> bool:
        """Match an arg name to a role: exact, or substring for longer hints.

        The substring guard (len >= 5) keeps short hints like ``q``/``n`` from
        matching unrelated names (``frequency``), while still letting ``keyword``
        match ``keywords`` and ``query`` match ``search_query``.
        """
        low = key.lower()
        return any(low == h or (len(h) >= 5 and h in low) for h in hints)

    def _clamp_difficulty(self, spec: dict) -> int | float:
        d: int | float = self._difficulty
        lo, hi = spec.get("minimum"), spec.get("maximum")
        if isinstance(lo, (int, float)):
            d = max(d, lo)
        if isinstance(hi, (int, float)):
            d = min(d, hi)
        return d

    def _build_search_args(self, tool_name: str, query: str, max_results: int) -> dict[str, Any]:
        """Fill a search tool's arguments from its JSON Schema by role+type.

        Handles both simple ``search(query, limit)`` servers and richer ones like
        alphaXiv's ``discover_papers(keywords: array, question, difficulty)``.
        """
        schema = self._schema(tool_name)
        props: dict[str, dict] = schema.get("properties", {}) or {}
        required: list[str] = list(schema.get("required", []) or [])
        args: dict[str, Any] = {}

        for key, spec in props.items():
            typ = (spec or {}).get("type")
            numeric = typ in (None, "number", "integer")
            if typ in (None, "array") and self._name_matches(key, _KEYWORD_NAME_HINTS):
                # Only emit a list when the schema says array (or is silent and a
                # list is acceptable); a string-typed "keywords" stays a string.
                args[key] = self._as_keywords(query) if typ == "array" else query
            elif typ in (None, "string") and self._name_matches(key, _QUESTION_NAME_HINTS):
                args[key] = query
            elif numeric and self._name_matches(key, _LIMIT_ARG_HINTS):
                args[key] = max_results
            elif numeric and self._name_matches(key, _DIFFICULTY_NAME_HINTS):
                args[key] = self._clamp_difficulty(spec or {})

        # Guarantee every required arg has a value (fill leftovers by type).
        for key in required:
            if key in args:
                continue
            spec = props.get(key) or {}
            typ = spec.get("type")
            if typ == "array":
                args[key] = self._as_keywords(query)
            elif typ in ("number", "integer"):
                args[key] = self._clamp_difficulty(spec)
            elif typ == "boolean":
                args[key] = spec.get("default", False)
            else:
                args[key] = query

        # Fallback for servers that expose no usable schema.
        if not args:
            qkey = self._input_key(tool_name, _QUERY_ARG_HINTS, "query")
            args[qkey or "query"] = query
            lim = self._input_key(tool_name, _LIMIT_ARG_HINTS, None)
            if lim:
                args[lim] = max_results
        return args

    def _coerce_id_value(self, tool_name: str, idkey: str, source_id: str) -> str:
        """If the content tool wants a URL (alphaXiv), turn a bare id into one."""
        spec = (self._schema(tool_name).get("properties", {}) or {}).get(idkey, {}) or {}
        wants_url = idkey == "url" or "url" in idkey.lower() or spec.get("format") == "uri"
        if wants_url and not str(source_id).startswith("http"):
            return _arxiv_url(source_id)
        return source_id

    # -- SourceProvider API ----------------------------------------------
    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        session = await self._ensure_session()
        tool = self._pick_tool(self._search_override, _SEARCH_HINTS, avoid=_EMBED_HINTS)
        if tool is None:
            return []
        args = self._build_search_args(tool, query, max_results)
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
        value = self._coerce_id_value(tool, idkey, source_id)
        result = await session.call_tool(tool, {idkey: value})
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
