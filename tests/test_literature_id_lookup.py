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


def _read_handler(read_paper_return):
    """Handler wired for the [READ:] path (no-full-text sources return None)."""
    corpus = SimpleNamespace(read_paper=AsyncMock(return_value=read_paper_return))
    lit = SimpleNamespace(
        max_read_chars=8000,
        read_budget_per_round=5,
        follow_budget_per_round=3,
        cited_by_budget_per_round=2,
        max_reference_results=10,
        max_citation_results=10,
    )
    engine = SimpleNamespace(
        _config=SimpleNamespace(literature=lit),
        _corpus=corpus,
        _logger=MagicMock(),
        _display=MagicMock(),
        state=SimpleNamespace(thread_id="t1"),
        emit_event=MagicMock(),
    )
    return LiteratureHandler(engine), engine


class TestReadAbstractFallback:
    """A [READ:] on a source with no full text (Semantic Scholar / PubMed) falls
    back to the abstract captured at discovery — instead of silently failing."""

    async def test_track_paper_caches_abstract(self):
        handler, _ = _read_handler(None)
        handler._track_paper("36588717", "BPC-157 review", "Smith", "The abstract text.")
        assert handler.discovered_abstracts["36588717"] == ("BPC-157 review", "The abstract text.")
        # empty summary is not cached, but the paper is still indexed
        handler._track_paper("99999999", "No abstract", "Doe", "")
        assert "99999999" not in handler.discovered_abstracts
        assert ("99999999", "No abstract", "Doe") in handler.discovered_papers

    async def test_read_falls_back_to_cached_abstract(self):
        handler, engine = _read_handler(None)  # corpus.read_paper -> None (no full text)
        handler.seen_paper_ids.add("36588717")
        handler.discovered_abstracts["36588717"] = ("BPC-157 review", "Promotes healing via …")
        await handler.process_literature_actions(
            "agent-1", "[READ: 36588717]", ResearchPhase.IDEATION
        )
        assert "36588717" in handler.read_paper_ids
        assert "Abstract only" in handler.literature_context
        kinds = [c.args[0] for c in engine.emit_event.call_args_list]
        assert "paper.read" in kinds

    async def test_read_with_no_text_and_no_abstract_warns(self):
        handler, engine = _read_handler(None)
        handler.seen_paper_ids.add("36588717")  # discovered but no cached abstract
        await handler.process_literature_actions(
            "agent-1", "[READ: 36588717]", ResearchPhase.IDEATION
        )
        assert "36588717" not in handler.read_paper_ids
        events = [(c.args[0], c.args[1]) for c in engine.emit_event.call_args_list]
        assert any(t == "warning.emitted" and p.get("kind") == "read_failed" for t, p in events)


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
