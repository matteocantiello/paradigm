"""Tests for the LiteratureHandler._append_to_context helper."""

from unittest.mock import MagicMock

from paradigm.orchestrator.constants import _LITERATURE_CONTEXT_LIMIT
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
