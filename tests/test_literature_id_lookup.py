"""Tests for the fetch-by-id interop slice — routing `id:<arxiv-id>` queries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from paradigm.orchestrator.literature import LiteratureHandler, _extract_arxiv_id_query
from paradigm.orchestrator.phases import ResearchPhase

# ---------------------------------------------------------------------------
# _extract_arxiv_id_query
# ---------------------------------------------------------------------------


class TestExtractArxivIdQuery:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("id:2509.12411", "2509.12411"),
            ("id: 2509.12411v2", "2509.12411v2"),
            ("2509.12411", "2509.12411"),
            ("arxiv:2301.00001", "2301.00001"),
            ("astro-ph/0601001", "astro-ph/0601001"),
            ("id:astro-ph/0601001", "astro-ph/0601001"),
            ("  ID:2509.12411  ", "2509.12411"),
        ],
    )
    def test_matches_ids(self, query, expected):
        assert _extract_arxiv_id_query(query) == expected

    @pytest.mark.parametrize(
        "query",
        [
            "massive star variability",
            "effect of id: on stars",
            "period-luminosity relation",
            "",
            "id:",
            "2509",  # too short to be an arxiv id
        ],
    )
    def test_rejects_keyword_queries(self, query):
        assert _extract_arxiv_id_query(query) is None


# ---------------------------------------------------------------------------
# _resolve_id_query
# ---------------------------------------------------------------------------


def _handler(read_paper_return):
    corpus = SimpleNamespace(read_paper=AsyncMock(return_value=read_paper_return))
    engine = SimpleNamespace(
        _config=SimpleNamespace(literature=SimpleNamespace(max_read_chars=8000)),
        _corpus=corpus,
        _logger=MagicMock(),
        _display=MagicMock(),
        state=SimpleNamespace(thread_id="t1"),
        emit_event=MagicMock(),
    )
    return LiteratureHandler(engine), corpus, engine


class TestResolveIdQuery:
    async def test_found_appends_context_and_tracks(self):
        handler, corpus, engine = _handler(("A Great Paper", "full text body"))
        await handler._resolve_id_query(
            "agent-1",
            "id:2509.12411",
            "id:2509.12411",
            "2509.12411",
            frozenset(),
            ResearchPhase.IDEATION,
        )
        corpus.read_paper.assert_awaited_once()
        assert "A Great Paper" in handler.literature_context
        assert "2509.12411" in handler.seen_paper_ids
        assert handler.search_count_this_round == 1
        assert handler.agent_search_count["agent-1"] == 1
        # Precise id lookup must NOT count as a stale keyword search.
        assert handler.total_stale_keyword_searches == 0
        engine._display.read_result.assert_called_once()

    async def test_not_found_no_context_no_stale(self):
        handler, corpus, engine = _handler(None)
        await handler._resolve_id_query(
            "agent-1",
            "id:9999.99999",
            "id:9999.99999",
            "9999.99999",
            frozenset(),
            ResearchPhase.IDEATION,
        )
        assert handler.literature_context == ""
        assert handler.total_stale_keyword_searches == 0
        assert handler.search_count_this_round == 1
        engine._display.read_not_found.assert_called_once_with("9999.99999")

    async def test_read_error_is_non_fatal(self):
        handler, corpus, engine = _handler(("t", "x"))
        corpus.read_paper = AsyncMock(side_effect=RuntimeError("boom"))
        await handler._resolve_id_query(
            "agent-1",
            "id:2509.12411",
            "id:2509.12411",
            "2509.12411",
            frozenset(),
            ResearchPhase.IDEATION,
        )
        engine._logger.log_error.assert_called_once()
        engine._display.read_error.assert_called_once()

    async def test_routing_uses_fetch_not_keyword_search(self):
        """An `id:` SEARCH request must hit read_paper, never corpus.search."""
        handler, corpus, engine = _handler(("Paper", "body"))
        corpus.search = AsyncMock(return_value=[])
        engine._config = SimpleNamespace(
            literature=SimpleNamespace(max_read_chars=8000, max_results_per_search=50),
            orchestrator=SimpleNamespace(max_searches_per_round=3, search_relevance_threshold=0.15),
        )
        await handler.process_search_requests(
            "agent-1", "[SEARCH: id:2509.12411]", ResearchPhase.IDEATION
        )
        corpus.read_paper.assert_awaited_once()
        corpus.search.assert_not_called()
