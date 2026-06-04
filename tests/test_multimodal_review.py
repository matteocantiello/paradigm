"""Tests for Phase 2 P2-VLM — figure-aware multimodal review."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from paradigm.agents.providers import AnthropicProvider, OpenAICompatibleProvider
from paradigm.journal.review import encode_figures_for_review
from paradigm.orchestrator.review import ReviewHandler

# ---------------------------------------------------------------------------
# Provider multimodal message builders
# ---------------------------------------------------------------------------


class TestBuildImageMessage:
    def test_anthropic_format(self):
        msg = AnthropicProvider.build_image_message("look", [("image/png", b"abc")])
        assert msg["role"] == "user"
        assert msg["content"][0] == {"type": "text", "text": "look"}
        img = msg["content"][1]
        assert img["type"] == "image"
        assert img["source"]["type"] == "base64"
        assert img["source"]["media_type"] == "image/png"
        assert img["source"]["data"] == "YWJj"  # base64("abc")

    def test_openai_format(self):
        msg = OpenAICompatibleProvider.build_image_message("look", [("image/jpeg", b"abc")])
        assert msg["content"][0]["type"] == "text"
        img = msg["content"][1]
        assert img["type"] == "image_url"
        assert img["image_url"]["url"] == "data:image/jpeg;base64,YWJj"

    def test_multiple_images(self):
        msg = AnthropicProvider.build_image_message("x", [("image/png", b"a"), ("image/png", b"b")])
        assert sum(1 for b in msg["content"] if b["type"] == "image") == 2


# ---------------------------------------------------------------------------
# encode_figures_for_review
# ---------------------------------------------------------------------------


class TestEncodeFigures:
    def test_reads_supported_images(self, tmp_path):
        p = tmp_path / "fig.png"
        p.write_bytes(b"\x89PNG fake data")
        out = encode_figures_for_review([("exp1", p)])
        assert out == [("exp1", "image/png", b"\x89PNG fake data")]

    def test_skips_unsupported_and_missing(self, tmp_path):
        pdf = tmp_path / "fig.pdf"
        pdf.write_bytes(b"%PDF")
        missing = tmp_path / "nope.png"
        out = encode_figures_for_review([("a", pdf), ("b", missing)])
        assert out == []

    def test_respects_max_figures(self, tmp_path):
        figs = []
        for i in range(5):
            p = tmp_path / f"f{i}.png"
            p.write_bytes(b"img")
            figs.append((f"f{i}", p))
        out = encode_figures_for_review(figs, max_figures=2)
        assert len(out) == 2

    def test_skips_oversized(self, tmp_path):
        p = tmp_path / "big.png"
        p.write_bytes(b"x" * 100)
        assert encode_figures_for_review([("big", p)], max_bytes=10) == []


# ---------------------------------------------------------------------------
# _run_figure_review
# ---------------------------------------------------------------------------


class _FakeProvider:
    def __init__(self, response="Figure 1: missing axis labels."):
        self._response = response
        self.last_images = None

    def build_image_message(self, text, images):
        self.last_images = images
        return {"role": "user", "content": [{"type": "text", "text": text}]}

    def complete(self, *, model, system, messages, max_tokens, extra_body=None):
        return (self._response, 12, 7)


def _engine(*, enabled=True, figures=None, provider=None, role="editor"):
    orch = SimpleNamespace(
        enable_multimodal_review=enabled,
        multimodal_review_role=role,
        max_review_figures=6,
    )
    cfg = SimpleNamespace(
        orchestrator=orch,
        get_provider_and_model_for_role=MagicMock(return_value=(provider, "model-x", None)),
    )
    return SimpleNamespace(
        _config=cfg,
        _db=MagicMock(),
        _logger=MagicMock(),
        state=SimpleNamespace(execution_figures=figures or [], thread_id="t1"),
    )


class TestRunFigureReview:
    async def test_disabled_returns_empty(self, tmp_path):
        eng = _engine(enabled=False)
        assert await ReviewHandler(eng)._run_figure_review() == ""

    async def test_no_figures_returns_empty(self):
        eng = _engine(figures=[])
        assert await ReviewHandler(eng)._run_figure_review() == ""

    async def test_runs_and_returns_findings(self, tmp_path):
        p = tmp_path / "fig.png"
        p.write_bytes(b"img")
        provider = _FakeProvider()
        eng = _engine(figures=[("scaling", p)], provider=provider)
        out = await ReviewHandler(eng)._run_figure_review()
        assert "missing axis labels" in out
        assert provider.last_images == [("image/png", b"img")]
        eng._db.record_token_usage.assert_called_once()

    async def test_provider_without_vision_returns_empty(self, tmp_path):
        p = tmp_path / "fig.png"
        p.write_bytes(b"img")
        eng = _engine(figures=[("a", p)], provider=SimpleNamespace())  # no build_image_message
        assert await ReviewHandler(eng)._run_figure_review() == ""

    async def test_complete_error_is_non_fatal(self, tmp_path):
        p = tmp_path / "fig.png"
        p.write_bytes(b"img")

        class _Boom(_FakeProvider):
            def complete(self, **kwargs):
                raise RuntimeError("not vision-capable")

        eng = _engine(figures=[("a", p)], provider=_Boom())
        assert await ReviewHandler(eng)._run_figure_review() == ""
        eng._logger.log_error.assert_called_once()
