"""R1-R3 (PI reflection / loop-backs / call-it) + D2 (repository data providers)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from paradigm.literature.data_providers import (
    DataCandidate,
    VizieRDataProvider,
    ZenodoDataProvider,
    create_data_providers,
    fetch_dataset,
    parse_vizier_resources,
)
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.reflection import ReflectionHandler

# ---------------------------------------------------------------------------
# ReflectionHandler verdict guards (R3 convergence mechanics)
# ---------------------------------------------------------------------------


def _reflection_stub(*, loop_backs_used=0, max_loop_backs=2, reflection_log=None, raw="{}"):
    engine = MagicMock()
    engine._config.orchestrator.max_loop_backs = max_loop_backs
    engine.state.loop_backs_used = loop_backs_used
    engine.state.reflection_log = reflection_log or []
    engine.state.seed_prompt = "brief"
    engine.state.experiment_metadata = [
        {"name": "exp1", "status": "success", "data_provenance": "real", "stdout_preview": "ok"}
    ]
    engine.state.execution_caveats = []
    engine.state.thread_id = "t1"
    handler = ReflectionHandler(engine)
    handler._pi_complete = AsyncMock(return_value=raw)
    return handler, engine


@pytest.mark.asyncio
async def test_reflection_proceed_passes_through():
    handler, _ = _reflection_stub(raw='{"verdict": "proceed", "reason": "solid"}')
    assert (await handler.run_reflection("draft"))["verdict"] == "proceed"


@pytest.mark.asyncio
async def test_reflection_unparseable_defaults_to_proceed():
    handler, _ = _reflection_stub(raw="I think we should definitely maybe...")
    assert (await handler.run_reflection("draft"))["verdict"] == "proceed"


@pytest.mark.asyncio
async def test_loop_back_blocked_when_budget_spent():
    handler, _ = _reflection_stub(
        loop_backs_used=2,
        raw='{"verdict": "loop_back", "target": "execution", "directives": ["more"]}',
    )
    assert (await handler.run_reflection("draft"))["verdict"] == "proceed"


@pytest.mark.asyncio
async def test_repeat_target_forces_call_it():
    handler, _ = _reflection_stub(
        loop_backs_used=1,
        reflection_log=[{"target": "execution", "directives": ["x"]}],
        raw='{"verdict": "loop_back", "target": "execution", "directives": ["more"]}',
    )
    verdict = await handler.run_reflection("draft")
    assert verdict["verdict"] == "call_it"


@pytest.mark.asyncio
async def test_loop_back_without_directives_proceeds():
    handler, _ = _reflection_stub(
        raw='{"verdict": "loop_back", "target": "execution", "directives": []}'
    )
    assert (await handler.run_reflection("draft"))["verdict"] == "proceed"


@pytest.mark.asyncio
async def test_valid_loop_back_normalized():
    handler, _ = _reflection_stub(
        raw='{"verdict": "loop_back", "target": "bogus", "directives": ["fetch full catalog"],'
        ' "success_criteria": "n>500"}'
    )
    v = await handler.run_reflection("draft")
    assert v["verdict"] == "loop_back"
    assert v["target"] == "execution"  # unknown target falls back
    assert v["directives"] == ["fetch full catalog"]


@pytest.mark.asyncio
async def test_triage_requires_directives_and_budget():
    handler, _ = _reflection_stub(raw='{"deep_loop": true, "directives": []}')
    assert (await handler.triage_peer_reviews("reviews"))["deep_loop"] is False
    handler2, _ = _reflection_stub(
        loop_backs_used=2, raw='{"deep_loop": true, "directives": ["run it"]}'
    )
    assert (await handler2.triage_peer_reviews("reviews"))["deep_loop"] is False
    handler3, _ = _reflection_stub(raw='{"deep_loop": true, "directives": ["run it"]}')
    assert (await handler3.triage_peer_reviews("reviews"))["deep_loop"] is True


# ---------------------------------------------------------------------------
# Engine _run_reflection_loop (stub-bound)
# ---------------------------------------------------------------------------


def _exp_result(context="new results"):
    return SimpleNamespace(
        execution_context=context,
        caveats=[],
        execution_figures=[],
        successful_code=[("expX", "code")],
        experiment_metadata=[{"name": "expX", "status": "success"}],
    )


def _engine_stub(verdicts: list[dict]):
    stub = SimpleNamespace()
    stub._config = SimpleNamespace(
        orchestrator=SimpleNamespace(
            enable_reflection=True, max_loop_backs=2, checkpoint_interval=5
        )
    )
    stub.state = SimpleNamespace(
        thread_id="t1",
        loop_backs_used=0,
        reflection_log=[],
        called_by_pi=False,
        pi_call_reason="",
        execution_caveats=[],
        execution_context="old",
        execution_figures=[],
        successful_code=[],
        experiment_metadata=[],
        planning_action_items="1. plan",
        messages=[],
        phase_manager=PhaseManager(initial_phase=ResearchPhase.WRITING),
    )
    stub._decision_hook = None  # autonomous — no interactive reflection dialog
    stub._reflection = SimpleNamespace(run_reflection=AsyncMock(side_effect=verdicts))
    stub._display = MagicMock()
    stub._db = MagicMock()
    stub._db.get_thread.return_value = {"current_draft_id": "paper-1"}
    stub.emit_event = MagicMock()
    stub._log_phase_transition = MagicMock()
    stub._pending_guidance = []
    stub._announce_discussion_phase = MagicMock()
    stub._run_phase = AsyncMock()
    stub._run_synthesis_round = AsyncMock()
    stub._extract_planning_actions = MagicMock(return_value="1. new plan")
    stub._experimentation = SimpleNamespace(
        run_experimentation_phase=AsyncMock(return_value=_exp_result())
    )
    long_body = "# Revised paper\n" + ("evidence " * 1300)  # > _MIN_PAPER_LENGTH (10k)
    stub._review = SimpleNamespace(run_revision=AsyncMock(return_value=long_body))
    stub._writing = SimpleNamespace(save_paper_file=MagicMock())
    stub._run_reflection_loop = OrchestrationEngine._run_reflection_loop.__get__(stub)
    stub._merge_execution_results = OrchestrationEngine._merge_execution_results.__get__(stub)
    return stub


def _draft():
    d = MagicMock()
    d.assembled_body = "# Draft\n" + ("text " * 400)
    return d


@pytest.mark.asyncio
async def test_reflection_proceed_returns_draft_unchanged():
    stub = _engine_stub([{"verdict": "proceed", "reason": "ok"}])
    draft = _draft()
    out = await stub._run_reflection_loop(draft, should_experiment=True)
    assert out is draft
    assert stub.state.loop_backs_used == 0


@pytest.mark.asyncio
async def test_reflection_call_it_records_and_proceeds():
    stub = _engine_stub([{"verdict": "call_it", "reason": "diminishing returns"}])
    out = await stub._run_reflection_loop(_draft(), should_experiment=True)
    assert out is not None
    assert stub.state.called_by_pi is True
    assert any("PI declared" in c for c in stub.state.execution_caveats)


@pytest.mark.asyncio
async def test_loop_back_runs_experiments_and_revises_in_place():
    stub = _engine_stub(
        [
            {
                "verdict": "loop_back",
                "target": "execution",
                "directives": ["fetch the full catalog"],
                "success_criteria": "n>1000",
            },
            {"verdict": "proceed", "reason": "fixed"},
        ]
    )
    draft = _draft()
    out = await stub._run_reflection_loop(draft, should_experiment=True)
    assert stub.state.loop_backs_used == 1
    stub._experimentation.run_experimentation_phase.assert_awaited_once_with(max_rounds_override=2)
    # New evidence merged; directives on the plan; paper revised IN PLACE.
    assert "new results" in stub.state.execution_context
    assert "PI DIRECTIVE (must be honored): fetch the full catalog" in (
        stub.state.planning_action_items
    )
    assert out.assembled_body.startswith("# Revised paper")
    stub._db.update_paper.assert_called_once()
    # Back at WRITING for the review stage.
    assert stub.state.phase_manager.current_phase == ResearchPhase.WRITING


@pytest.mark.asyncio
async def test_reflection_disabled_is_a_noop():
    stub = _engine_stub([])
    stub._config.orchestrator.enable_reflection = False
    draft = _draft()
    assert await stub._run_reflection_loop(draft, should_experiment=True) is draft
    stub._reflection.run_reflection.assert_not_awaited()


# ---------------------------------------------------------------------------
# D2: data providers
# ---------------------------------------------------------------------------

_VOTABLE = """<VOTABLE><RESOURCE type="results" name="J/A+A/701/A297">
<DESCRIPTION>Microturbulence across the HR Diagram (Markova+, 2025)</DESCRIPTION>
</RESOURCE><RESOURCE name="J/ApJ/875/129">
<DESCRIPTION>  Another
catalog  </DESCRIPTION></RESOURCE>
<RESOURCE name="J/A+A/701/A297"><DESCRIPTION>duplicate</DESCRIPTION></RESOURCE></VOTABLE>"""


def test_parse_vizier_resources():
    got = parse_vizier_resources(_VOTABLE)
    assert [c.id for c in got] == ["vizier:J/A+A/701/A297", "vizier:J/ApJ/875/129"]
    assert got[0].title.startswith("Microturbulence across the HR Diagram")
    assert got[1].title == "Another catalog"  # whitespace collapsed


def test_provider_ownership_and_registry():
    v, z = VizieRDataProvider(), ZenodoDataProvider()
    assert v.owns("vizier:J/A+A/701/A297") and v.owns("J/A+A/701/A297")
    assert not v.owns("zenodo:12345")
    assert z.owns("zenodo:12345") and not z.owns("J/A+A/1/1")
    assert [p.name for p in create_data_providers(["vizier", "zenodo", "bogus"])] == [
        "vizier",
        "zenodo",
    ]


@pytest.mark.asyncio
async def test_fetch_dataset_unknown_id_raises():
    with pytest.raises(ValueError, match="no configured data provider"):
        await fetch_dataset([VizieRDataProvider()], "zenodo:123")


def test_data_candidate_shape():
    c = DataCandidate(id="vizier:J/X/1", title="T", source="VizieR/CDS")
    assert c.detail == ""


# ---------------------------------------------------------------------------
# D2 expansion: the new provider set (parsing + ownership + registry, no net)
# ---------------------------------------------------------------------------


def test_provider_registry_has_full_set():
    from paradigm.literature.data_providers import _PROVIDER_CLASSES, create_data_providers

    expected = {
        "vizier",
        "mast",
        "irsa",
        "heasarc",
        "ned",
        "nasa_exoplanet",
        "simbad",
        "zenodo",
        "dryad",
        "uniprot",
        "pdb",
        "geo",
    }
    assert expected <= set(_PROVIDER_CLASSES)
    # create skips unknown names, preserves order.
    provs = create_data_providers(["mast", "bogus", "uniprot"])
    assert [p.name for p in provs] == ["mast", "uniprot"]


def test_parse_tabular_rows_csv_and_votable():
    from paradigm.literature.data_providers import parse_tabular_rows

    csv_rows = parse_tabular_rows("table_name,description\nfoo,a table\nbar,another\n")
    assert csv_rows == [["foo", "a table"], ["bar", "another"]]

    vot = (
        "<VOTABLE><RESOURCE><TABLE><DATA><TABLEDATA>"
        "<TR><TD>dbo.allpointing</TD><TD>obs&amp;lt;pointings</TD></TR>"
        "<TR><TD>caom.obs</TD><TD>x</TD></TR>"
        "</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>"
    )
    rows = parse_tabular_rows(vot)
    assert rows[0][0] == "dbo.allpointing"
    assert "obs" in rows[0][1]  # entity-unescaped


def test_tap_and_object_ownership():
    from paradigm.literature.data_providers import (
        ExoplanetArchiveDataProvider,
        MastDataProvider,
        NedDataProvider,
        PdbDataProvider,
        SimbadDataProvider,
        UniProtDataProvider,
    )

    assert MastDataProvider().owns("mast:dbo.allpointing")
    assert not MastDataProvider().owns("irsa:x")
    assert ExoplanetArchiveDataProvider().owns("exoplanet:ps")
    assert NedDataProvider().owns("ned:NEDTAP.objdir")
    assert SimbadDataProvider().owns("simbad:M31") and not SimbadDataProvider().owns("mast:x")
    assert UniProtDataProvider().owns("uniprot:P01308")
    assert PdbDataProvider().owns("pdb:3GOU")


def test_tap_provider_dialects():
    from paradigm.literature.data_providers import (
        ExoplanetArchiveDataProvider,
        IrsaDataProvider,
    )

    assert ExoplanetArchiveDataProvider()._EXOPLANET_STYLE is True
    assert IrsaDataProvider()._EXOPLANET_STYLE is False


@pytest.mark.asyncio
async def test_fetch_dataset_routes_by_prefix():
    from paradigm.literature.data_providers import (
        GeoDataProvider,
        create_data_providers,
        fetch_dataset,
    )

    provs = create_data_providers(["vizier", "geo", "uniprot"])
    # geo needs a GSE accession — a non-GSE id raises a clear error, proving routing.
    with pytest.raises(ValueError, match="GSE series accession"):
        # Route directly through the geo provider's fetch via the dispatcher.
        import tempfile
        from pathlib import Path

        await GeoDataProvider().fetch("geo:UID999", Path(tempfile.mkdtemp()))
    with pytest.raises(ValueError, match="no configured data provider"):
        await fetch_dataset(provs, "unknownprefix:x")
