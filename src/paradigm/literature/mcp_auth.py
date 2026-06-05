"""OAuth 2.1 plumbing for OAuth-gated literature MCP servers (e.g. alphaXiv).

alphaXiv's MCP server is protected by Clerk OAuth — there is **no static API key**.
This implements the MCP-spec OAuth flow:

  * a one-time interactive browser login (``paradigm mcp-login``) populates a
    local token cache under ``~/.paradigm/mcp/<name>/``;
  * thereafter the headless orchestrator reuses + auto-refreshes the cached
    token with NO browser (the provider builds a non-interactive
    ``OAuthClientProvider`` whose redirect handler refuses to pop a browser).

All ``mcp`` imports are lazy so the package stays an optional dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_DEFAULT_CALLBACK_PORT = 41789
_CALLBACK_PATH = "/callback"


def token_dir(name: str) -> Path:
    d = Path.home() / ".paradigm" / "mcp" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


class FileTokenStorage:
    """On-disk ``TokenStorage`` — persists OAuth tokens + client registration.

    Implements the (async) ``mcp.client.auth.TokenStorage`` protocol structurally.
    """

    def __init__(self, name: str) -> None:
        d = token_dir(name)
        self._tokens_path = d / "tokens.json"
        self._client_path = d / "client.json"

    async def get_tokens(self) -> Any | None:
        from mcp.shared.auth import OAuthToken

        if self._tokens_path.exists():
            try:
                return OAuthToken.model_validate_json(self._tokens_path.read_text())
            except Exception:
                return None
        return None

    async def set_tokens(self, tokens: Any) -> None:
        self._tokens_path.write_text(tokens.model_dump_json())
        self._tokens_path.chmod(0o600)

    async def get_client_info(self) -> Any | None:
        from mcp.shared.auth import OAuthClientInformationFull

        if self._client_path.exists():
            try:
                return OAuthClientInformationFull.model_validate_json(self._client_path.read_text())
            except Exception:
                return None
        return None

    async def set_client_info(self, client_info: Any) -> None:
        self._client_path.write_text(client_info.model_dump_json())
        self._client_path.chmod(0o600)

    def has_tokens(self) -> bool:
        return self._tokens_path.exists()


async def _browser_redirect(authorization_url: str) -> None:
    import webbrowser

    print(
        "\nOpening your browser to log in to the literature MCP server…\n"
        f"If it doesn't open, paste this URL into a browser:\n  {authorization_url}\n"
    )
    webbrowser.open(authorization_url)


def _make_callback_handler(port: int):
    async def _callback() -> tuple[str, str | None]:
        import asyncio
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import parse_qs, urlparse

        captured: dict[str, str | None] = {}

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (http.server API)
                q = parse_qs(urlparse(self.path).query)
                captured["code"] = (q.get("code") or [None])[0]
                captured["state"] = (q.get("state") or [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h2>Paradigm: login complete.</h2><p>You can close this tab.</p>"
                )

            def log_message(self, *args: Any) -> None:  # silence the default logging
                return

        def _serve_once() -> None:
            server = HTTPServer(("localhost", port), _Handler)
            server.handle_request()  # block for a single request
            server.server_close()

        await asyncio.to_thread(_serve_once)
        code = captured.get("code")
        if not code:
            raise RuntimeError("OAuth callback received no authorization code")
        return code, captured.get("state")

    return _callback


def _headless_redirect(name: str):
    async def _redirect(authorization_url: str) -> None:
        raise RuntimeError(
            f"MCP server {name!r} needs a one-time interactive login. "
            f"Run:  paradigm mcp-login"
        )

    return _redirect


async def _headless_callback() -> tuple[str, str | None]:
    raise RuntimeError("Interactive login required — run `paradigm mcp-login`")


def build_oauth_provider(
    *,
    server_url: str,
    name: str,
    scope: str,
    interactive: bool = False,
    port: int = _DEFAULT_CALLBACK_PORT,
) -> tuple[Any, FileTokenStorage]:
    """Build an ``OAuthClientProvider`` backed by the on-disk token cache.

    ``interactive=False`` (the headless orchestrator): never opens a browser —
    if there's no usable cached/refreshable token, connect fails and the provider
    degrades gracefully. ``interactive=True`` (the ``mcp-login`` command): opens a
    browser and runs a one-shot local callback server to complete the flow.

    Returns ``(auth_provider, storage)``.
    """
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    storage = FileTokenStorage(name)
    redirect_uri = f"http://localhost:{port}{_CALLBACK_PATH}"
    metadata = OAuthClientMetadata(
        client_name="Paradigm",
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=scope,
        token_endpoint_auth_method="none",
    )
    if interactive:
        redirect_handler = _browser_redirect
        callback_handler = _make_callback_handler(port)
    else:
        redirect_handler = _headless_redirect(name)
        callback_handler = _headless_callback

    provider = OAuthClientProvider(
        server_url=server_url,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )
    return provider, storage


async def interactive_login(
    *, server_url: str, name: str, scope: str, port: int = _DEFAULT_CALLBACK_PORT
) -> list[str]:
    """Run the one-time interactive OAuth login and cache the token.

    Opens a browser, completes the flow, then verifies by listing the server's
    tools. Returns the discovered tool names. Raises with a clear message on
    failure (e.g. the server doesn't support dynamic client registration).
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    auth, storage = build_oauth_provider(
        server_url=server_url, name=name, scope=scope, interactive=True, port=port
    )
    async with streamablehttp_client(server_url, auth=auth) as transport:
        read, write = transport[0], transport[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    names = [t.name for t in listed.tools]
    _logger.info("MCP login OK for %s — token cached at %s", name, token_dir(name))
    return names
