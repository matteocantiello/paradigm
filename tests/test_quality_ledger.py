"""Tier 2: quality ledger (auto-judge) + front-loaded novelty."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.api.routes.papers import _json_obj
from paradigm.eval.models import JudgeScores
from paradigm.literature.novelty import NoveltyResult
from paradigm.orchestrator.engine import OrchestrationEngine


def _ledger_stub(*, enabled=True, judge_result=None):
    stub = SimpleNamespace()
    stub._config = MagicMock()
    stub._config.orchestrator.enable_quality_ledger = enabled
    stub._config.get_provider_and_model_for_role.return_value = (MagicMock(), "judge-model", None)
    stub._db = MagicMock()
    stub._db.get_paper.return_value = {"title": "T", "body": "B" * 500}
    stub._display = MagicMock()
    stub._logger = MagicMock()
    stub.state = SimpleNamespace(thread_id="t1")
    stub.emit_event = MagicMock()
    stub._run_quality_judge = OrchestrationEngine._run_quality_judge.__get__(stub)
    return stub


@pytest.mark.asyncio
async def test_quality_judge_persists_scores(monkeypatch):
    scores = JudgeScores(novelty=6, rigor=7, clarity=8, significance=5, honesty=9)
    monkeypatch.setattr("paradigm.eval.judge.judge_paper", lambda *a, **k: scores)
    stub = _ledger_stub()
    await stub._run_quality_judge("paper-1")
    kwargs = stub._db.update_paper.call_args.kwargs
    js = kwargs["judge_scores"]
    assert js["composite"] == 7.0  # (6+7+8+5+9)/50*10
    assert js["judge_model"] == "judge-model"
    events = [c.args[0] for c in stub.emit_event.call_args_list]
    assert "paper.judged" in events


@pytest.mark.asyncio
async def test_quality_judge_disabled_is_noop(monkeypatch):
    called = []
    monkeypatch.setattr("paradigm.eval.judge.judge_paper", lambda *a, **k: called.append(1))
    stub = _ledger_stub(enabled=False)
    await stub._run_quality_judge("paper-1")
    assert not called
    stub._db.update_paper.assert_not_called()


@pytest.mark.asyncio
async def test_quality_judge_none_scores_skips(monkeypatch):
    monkeypatch.setattr("paradigm.eval.judge.judge_paper", lambda *a, **k: None)
    stub = _ledger_stub()
    await stub._run_quality_judge("paper-1")
    stub._db.update_paper.assert_not_called()


# --- novelty front-load --------------------------------------------------------


def _novelty_stub(result: NoveltyResult | None, enabled=True):
    stub = SimpleNamespace()
    stub._config = MagicMock()
    stub._config.citation.enable_novelty_check = enabled
    stub._config.citation.novelty_mode = "semantic_scholar"
    stub._citation_handler = SimpleNamespace(
        check_novelty=AsyncMock(return_value=result)
        if result is not None
        else AsyncMock(side_effect=RuntimeError("api down"))
    )
    stub._display = MagicMock()
    stub._logger = MagicMock()
    stub.state = SimpleNamespace(thread_id="t1")
    stub.emit_event = MagicMock()
    stub._pending_guidance = []
    stub._assess_novelty = OrchestrationEngine._assess_novelty.__get__(stub)
    return stub


@pytest.mark.asyncio
async def test_weak_novelty_queues_differentiation_guidance():
    res = NoveltyResult(
        is_novel=False, confidence=0.8, related_work=["Smith 2024: same topic"], papers_found=12
    )
    stub = _novelty_stub(res)
    note = await stub._assess_novelty("prompt")
    assert "WEAK" in note and "12" in note
    assert len(stub._pending_guidance) == 1
    assert "position this work against it" in stub._pending_guidance[0][0]
    events = [c.args[0] for c in stub.emit_event.call_args_list]
    assert "novelty.assessed" in events


@pytest.mark.asyncio
async def test_novel_verdict_notes_without_guidance():
    res = NoveltyResult(is_novel=True, confidence=0.7, papers_found=3)
    stub = _novelty_stub(res)
    note = await stub._assess_novelty("prompt")
    assert "looks novel" in note
    assert stub._pending_guidance == []


@pytest.mark.asyncio
async def test_novelty_failure_is_silent():
    stub = _novelty_stub(None)  # check_novelty raises
    assert await stub._assess_novelty("prompt") == ""


@pytest.mark.asyncio
async def test_novelty_disabled_returns_empty():
    stub = _novelty_stub(NoveltyResult(is_novel=True, confidence=1.0), enabled=False)
    assert await stub._assess_novelty("prompt") == ""


# --- API helper -----------------------------------------------------------------


def test_json_obj_parses_and_rejects():
    assert _json_obj('{"composite": 7.0}') == {"composite": 7.0}
    assert _json_obj({"a": 1}) == {"a": 1}
    assert _json_obj("[1,2]") is None
    assert _json_obj("") is None
    assert _json_obj(None) is None
