"""Tests for calm, deduped handling of best-effort literature-source failures."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from paradigm.display.fallback import PlainTextFallback
from paradigm.display.manager import DisplayManager
from paradigm.orchestrator.literature import (
    LiteratureHandler,
    _is_transient_source_error,
)


def _handler():
    engine = SimpleNamespace(
        _config=SimpleNamespace(literature=SimpleNamespace(max_read_chars=8000)),
        _corpus=SimpleNamespace(),
        _logger=MagicMock(),
        _display=MagicMock(),
        state=SimpleNamespace(thread_id="t1"),
    )
    return LiteratureHandler(engine), engine


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://export.arxiv.org/api/query")
    return httpx.HTTPStatusError("err", request=req, response=httpx.Response(code, request=req))


class TestIsTransientSourceError:
    @pytest.mark.parametrize(
        "err",
        [
            httpx.ReadTimeout("slow"),
            httpx.ConnectError("no route"),
            httpx.RemoteProtocolError("peer closed"),
            httpx.PoolTimeout("pool"),
            _status_error(429),
            _status_error(503),
            Exception("Semantic Scholar API returned 429"),
            Exception("connection timed out"),
        ],
    )
    def test_transient(self, err):
        assert _is_transient_source_error(err) is True

    @pytest.mark.parametrize(
        "err",
        [
            ValueError("bad value"),
            TypeError("unexpected keyword argument 'system_prompt'"),
            KeyError("id"),
            RuntimeError("boom"),
        ],
    )
    def test_not_transient(self, err):
        assert _is_transient_source_error(err) is False


class TestHandleSourceFailure:
    def test_transient_emits_one_deduped_notice(self):
        handler, engine = _handler()
        err = httpx.ReadTimeout("slow")
        # Every failure is handled calmly (True), but only the FIRST per source
        # this cycle surfaces a display notice.
        assert handler._handle_source_failure("arXiv", "analyst-1", err) is True
        assert handler._handle_source_failure("arXiv", "analyst-1", err) is True
        assert handler._handle_source_failure("arXiv", "theorist-1", err) is True
        engine._display.source_degraded.assert_called_once_with("arXiv")
        # All three are still recorded in the structured log for forensics.
        assert engine._logger.log_error.call_count == 3

    def test_distinct_sources_each_notify_once(self):
        handler, engine = _handler()
        err = httpx.ConnectError("down")
        handler._handle_source_failure("arXiv", "a", err)
        handler._handle_source_failure("Semantic Scholar", "a", err)
        assert engine._display.source_degraded.call_count == 2

    def test_non_transient_surfaced_loudly(self):
        handler, engine = _handler()
        assert handler._handle_source_failure("arXiv", "a", TypeError("real bug")) is False
        engine._display.source_degraded.assert_not_called()
        engine._logger.log_error.assert_called_once()

    def test_reset_cycle_reallows_notice(self):
        handler, engine = _handler()
        err = httpx.ReadTimeout("slow")
        handler._handle_source_failure("arXiv", "a", err)
        handler.reset_cycle()
        handler._handle_source_failure("arXiv", "a", err)
        assert engine._display.source_degraded.call_count == 2


class TestDisplaySourceDegraded:
    def test_manager_adds_warning_event(self):
        mgr = DisplayManager(verbose=True)  # non-rich path → no TTY needed
        mgr.source_degraded("arXiv")
        events = mgr.state.recent_events
        assert events[-1]["type"] == "warning"
        assert "arXiv" in events[-1]["message"]
        assert "rate-limited" in events[-1]["message"]

    def test_fallback_echoes_calm_line(self, capsys):
        PlainTextFallback().source_degraded("arXiv")
        out = capsys.readouterr().out
        assert "arXiv" in out
        assert "rate-limited" in out
        assert "[!]" not in out  # calm marker, not an error marker
