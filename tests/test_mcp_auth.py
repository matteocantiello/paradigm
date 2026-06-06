"""Tests for the MCP OAuth plumbing (token cache + provider build). No network."""

from __future__ import annotations

import pytest

from paradigm.literature.mcp_auth import (
    FileTokenStorage,
    _headless_redirect,
    build_oauth_provider,
    token_dir,
)


@pytest.fixture
def _home(tmp_path, monkeypatch):
    """Redirect ~/.paradigm to a temp dir for the test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_token_dir_under_home(_home):
    d = token_dir("alphaxiv")
    assert d == _home / ".paradigm" / "mcp" / "alphaxiv"
    assert d.is_dir()


async def test_file_token_storage_roundtrip(_home):
    from mcp.shared.auth import OAuthToken

    store = FileTokenStorage("alphaxiv")
    assert await store.get_tokens() is None
    assert not store.has_tokens()

    tok = OAuthToken(access_token="abc123", token_type="Bearer", refresh_token="r1")
    await store.set_tokens(tok)

    assert store.has_tokens()
    loaded = await store.get_tokens()
    assert loaded is not None
    assert loaded.access_token == "abc123"
    assert loaded.refresh_token == "r1"
    # Token file is written with restrictive perms.
    assert (
        oct((_home / ".paradigm" / "mcp" / "alphaxiv" / "tokens.json").stat().st_mode)[-3:] == "600"
    )


async def test_corrupt_token_file_returns_none(_home):
    store = FileTokenStorage("alphaxiv")
    (token_dir("alphaxiv") / "tokens.json").write_text("not json{")
    assert await store.get_tokens() is None


def test_build_oauth_provider_headless(_home):
    provider, storage = build_oauth_provider(
        server_url="https://api.alphaxiv.org/mcp/v1",
        name="alphaxiv",
        scope="email profile",
        interactive=False,
    )
    assert isinstance(storage, FileTokenStorage)
    # It's an httpx-compatible auth object from the mcp SDK.
    from mcp.client.auth import OAuthClientProvider

    assert isinstance(provider, OAuthClientProvider)


async def test_headless_redirect_refuses_browser():
    redirect = _headless_redirect("alphaxiv")
    with pytest.raises(RuntimeError, match="mcp-login"):
        await redirect("https://clerk.alphaxiv.org/authorize?...")


def test_mcp_login_command_registered():
    from paradigm.main import cli

    assert "mcp-login" in cli.commands
