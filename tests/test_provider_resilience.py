"""A flaky literature provider must never abort the research cycle.

Regression for the deployed abort: the alphaXiv MCP provider (no OAuth token)
raised an anyio BaseExceptionGroup during teardown, which escaped the corpus's
`except Exception` guard and cancelled the whole cycle ("aborted" right after
ideation). The provider loop now catches BaseException (skipping the provider)
while still letting a genuine CancelledError propagate.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from paradigm.literature.corpus import Corpus


def _bare_corpus():
    c = Corpus.__new__(Corpus)
    c._providers = {}
    c._logger = None
    c._config = SimpleNamespace(max_results_per_search=10)
    return c


class _GroupRaiser:
    async def search(self, query, max_results):
        # Mirrors the anyio failure the MCP client produced on the VM.
        raise BaseExceptionGroup(
            "mcp boom",
            [RuntimeError("Attempted to exit cancel scope in a different task")],
        )


class _Canceller:
    async def search(self, query, max_results):
        raise asyncio.CancelledError()


@pytest.mark.asyncio
async def test_baseexceptiongroup_from_provider_does_not_abort_search():
    c = _bare_corpus()
    c._providers = {"alphaxiv": _GroupRaiser()}
    out = await c._search_via_providers(
        "q", 10, include_local=False, include_arxiv=False, provider="alphaxiv"
    )
    assert out == []  # swallowed; the cycle would continue with other providers


@pytest.mark.asyncio
async def test_genuine_cancellation_still_propagates():
    c = _bare_corpus()
    c._providers = {"x": _Canceller()}
    with pytest.raises(asyncio.CancelledError):
        await c._search_via_providers(
            "q", 10, include_local=False, include_arxiv=False, provider="x"
        )
