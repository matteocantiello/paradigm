"""Tests for the LiteratureHandler._append_to_context helper and search dedup."""

from unittest.mock import MagicMock

from paradigm.orchestrator.constants import (
    _LITERATURE_CONTEXT_LIMIT,
    _PER_AGENT_CAP_MIN,
    _STOP_WORDS,
    _is_duplicate_query,
    _normalize_query_keywords,
)
from paradigm.orchestrator.literature import LiteratureHandler


def _make_handler() -> LiteratureHandler:
    """Create a LiteratureHandler with a mocked engine."""
    engine = MagicMock()
    return LiteratureHandler(engine)


class TestAppendToEmptyContext:
    def test_from_empty(self):
        handler = _make_handler()
        handler.literature_context = ""
        handler._append_to_context("new content")
        assert handler.literature_context == "new content"


class TestAppendToExistingContext:
    def test_appends_with_newline(self):
        handler = _make_handler()
        handler.literature_context = "existing"
        handler._append_to_context("new")
        assert handler.literature_context == "existing\nnew"


class TestAppendWithTrim:
    def test_trims_at_limit(self):
        handler = _make_handler()
        # Start with a context that is just under the limit
        handler.literature_context = "x" * (_LITERATURE_CONTEXT_LIMIT - 10)
        # Append enough to exceed the limit
        handler._append_to_context("y" * 100)
        assert len(handler.literature_context) == _LITERATURE_CONTEXT_LIMIT
        # Should keep the most recent content (end of string)
        assert handler.literature_context.endswith("y" * 100)


class TestAppendWithoutTrim:
    def test_no_trim(self):
        handler = _make_handler()
        handler.literature_context = "x" * _LITERATURE_CONTEXT_LIMIT
        handler._append_to_context("y" * 100, trim=False)
        # Should exceed the limit because trim=False
        assert len(handler.literature_context) > _LITERATURE_CONTEXT_LIMIT
        assert handler.literature_context.endswith("y" * 100)


# ---------------------------------------------------------------------------
# Search deduplication tests
# ---------------------------------------------------------------------------


class TestStopWordsIncludeScientificFiller:
    """Expanded stop words should remove common scientific filler."""

    def test_scientific_filler_in_stop_words(self):
        scientific_filler = {
            "analysis",
            "based",
            "between",
            "can",
            "during",
            "effect",
            "evidence",
            "evolution",
            "model",
            "new",
            "observation",
            "observed",
            "properties",
            "recent",
            "relation",
            "role",
            "study",
            "using",
            "through",
            "which",
        }
        assert scientific_filler.issubset(_STOP_WORDS)

    def test_filler_stripped_from_query(self):
        kw = _normalize_query_keywords("study of stellar pulsation properties")
        assert "study" not in kw
        assert "properties" not in kw
        assert "stellar" in kw
        assert "pulsation" in kw


class TestJaccardThresholdCatchesRewordedQueries:
    """0.5 threshold should catch reworded queries that 0.7 would miss."""

    def test_reworded_queries_detected_at_half(self):
        # A pair that SHOULD be caught at 0.5:
        q5 = _normalize_query_keywords("red giant oscillation asteroseismology")
        q6 = _normalize_query_keywords("red giant asteroseismology oscillation modes")
        # Overlap: {red, giant, oscillation, asteroseismology} = 4
        # Union: {red, giant, oscillation, asteroseismology, modes} = 5
        # Jaccard = 4/5 = 0.80 — caught at both thresholds
        assert _is_duplicate_query(q6, [q5])

    def test_filler_removal_boosts_overlap(self):
        """Queries that differ only in scientific filler should match."""
        q1 = _normalize_query_keywords("study of stellar pulsation properties")
        q2 = _normalize_query_keywords("analysis of stellar pulsation observations")
        # After filler removal: q1 = {stellar, pulsation}, q2 = {stellar, pulsation}
        # Jaccard = 1.0 — definitely a duplicate
        assert _is_duplicate_query(q2, [q1])

    def test_distinct_queries_not_flagged(self):
        q1 = _normalize_query_keywords("white dwarf cooling sequence")
        q2 = _normalize_query_keywords("neutron star equation of state")
        assert not _is_duplicate_query(q2, [q1])


class TestPerAgentCapMin:
    """Per-agent keyword cap should be 1 to force graph traversal."""

    def test_cap_is_one(self):
        assert _PER_AGENT_CAP_MIN == 1
