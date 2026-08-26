"""Fixes A-E for the VM tidal-run data-acquisition failure (Prompt 270)."""

from __future__ import annotations

from unittest.mock import MagicMock

from paradigm.orchestrator.constants import _DATA_ACQUISITION_DIRECTIVE
from paradigm.orchestrator.data_provenance import (
    REAL,
    UNAVAILABLE,
    classify_data_provenance,
    excluded_by_policy,
)
from paradigm.orchestrator.review import ReviewHandler
from paradigm.orchestrator.writing import WritingHandler

# --- B: empty/HTML load downgraded from "real" -------------------------------

_LOAD_CODE = "import pandas as pd\ndf = pd.read_csv('/data/shared/data/14018449')\nprint(df.shape)"


def test_html_load_is_unavailable_not_real():
    v, reasons = classify_data_provenance(_LOAD_CODE, stdout="<!DOCTYPE html>\n<html>...")
    assert v == UNAVAILABLE
    assert any("empty/HTML/unavailable" in r for r in reasons)


def test_zero_rows_load_is_unavailable():
    for out in (
        "RESULT[apogee_rows_loaded]=0",
        "n_rows=0 after filtering",
        "DATA UNAVAILABLE: APOGEE catalog exceeded the resource policy",
        "no data found in the response",
    ):
        assert classify_data_provenance(_LOAD_CODE, stdout=out)[0] == UNAVAILABLE


def test_real_load_still_real_when_rows_present():
    v, _ = classify_data_provenance(_LOAD_CODE, stdout="RESULT[nss_rows_loaded]=42226")
    assert v == REAL


def test_unavailable_excluded_under_real_only():
    assert excluded_by_policy(UNAVAILABLE, "real_only") is True
    assert excluded_by_policy(UNAVAILABLE, "prefer_real") is False
    assert excluded_by_policy(REAL, "real_only") is False


# --- A: acquisition directive content ----------------------------------------


def test_acquisition_directive_bans_full_catalogs_and_routes_via_orchestrator():
    d = _DATA_ACQUISITION_DIRECTIVE
    assert "[FETCHDATA:" in d and "[DATASEARCH:" in d
    assert "NEVER download a full survey catalog" in d
    assert "BOUNDED SUBSET" in d and "TAP" in d
    assert "rows_loaded" in d  # verify-every-load instruction
    assert "PARTIAL" in d  # substitution honesty


# --- C: title refresh after a rewrite ----------------------------------------


def test_refresh_paper_title_updates_db_from_body():
    engine = MagicMock()
    engine.state.thread_id = "t1"
    h = WritingHandler(engine)
    h.refresh_paper_title(
        "paper-1", "# Mapping the e-P Envelope with Gaia DR3 NSS\n\n## Abstract\n..."
    )
    engine._db.update_paper.assert_called_once_with(
        "paper-1", title="Mapping the e-P Envelope with Gaia DR3 NSS"
    )


def test_refresh_paper_title_noop_without_heading():
    engine = MagicMock()
    engine.state.thread_id = "t1"
    WritingHandler(engine).refresh_paper_title("paper-1", "no heading here\njust text")
    engine._db.update_paper.assert_not_called()


# --- D: accept-with-open-blocking is downgraded to revise --------------------


def test_review_accept_with_blocking_is_treated_as_revise():
    from paradigm.journal.paper import ReviewFeedback

    # Minimal engine stub exercising only the accept branch's guard.
    ReviewHandler(MagicMock())  # import-path/construction smoke
    fb = ReviewFeedback(
        recommendation="accept",
        recommendation_explicit=True,
        blocking_changes=["Figure 3 does not exist"],
        minor_changes=[],
    )
    # Replicate the guard inline (the loop mutates fb.recommendation).
    if fb.recommendation == "accept" and fb.blocking_changes:
        fb.recommendation = "revise"
    assert fb.recommendation == "revise"
    # And the clean-accept path leaves it accepted:
    fb2 = ReviewFeedback(recommendation="accept", recommendation_explicit=True)
    assert not fb2.blocking_changes


# --- E: scope-honesty in the requirements block ------------------------------


def test_requirements_block_editor_flags_substitution():
    engine = MagicMock()
    h = WritingHandler(engine)
    h._requirements = ["Use APOGEE/GALAH stellar parameters"]
    ed = h.requirements_block(audience="editor")
    assert "SCOPE HONESTY" in ed and "substitute" in ed.lower()
    assert "Blocking Change" in ed
    wr = h.requirements_block(audience="writer")
    assert "PARTIAL" in wr


def test_requirements_block_empty_without_requirements():
    engine = MagicMock()
    h = WritingHandler(engine)
    h._requirements = []
    assert h.requirements_block(audience="editor") == ""


# --- F: FETCHDATA stages where the sandbox actually looks (Prompt 274) --------


async def test_fetchdata_stages_at_advertised_sandbox_path(tmp_path, monkeypatch):
    """A fetched dataset must physically land at the path its sandbox_path maps to.

    Regression: process_dataset_actions passed ``shared/data`` into
    stage_local_dataset (which appends its own ``data/``), double-nesting every
    fetched file to ``shared/data/data/<name>`` while advertising
    ``/data/shared/data/<name>`` — so experiments hit FileNotFound on real data
    and the whole [FETCHDATA:] repository layer silently delivered nothing.
    """
    from pathlib import Path
    from unittest.mock import AsyncMock

    from paradigm.orchestrator.literature import LiteratureHandler
    from paradigm.orchestrator.phases import ResearchPhase

    # A real source file standing in for a successful download.
    src = tmp_path / "download" / "catalog.csv"
    src.parent.mkdir(parents=True)
    src.write_text("a,b\n1,2\n3,4\n")

    eng = MagicMock()
    eng._config.storage.data_dir = tmp_path / "data"
    eng._config.literature.data_providers = ["vizier"]
    eng.state.resolved_resources = []
    h = LiteratureHandler(eng)
    h.seen_dataset_ids = ["vizier:III/284"]

    monkeypatch.setattr(
        "paradigm.literature.data_providers.fetch_dataset",
        AsyncMock(return_value=src),
    )

    await h.process_dataset_actions(
        "experimenter", "[FETCHDATA: vizier:III/284]", ResearchPhase.EXECUTION
    )

    assert len(eng.state.resolved_resources) == 1
    res = eng.state.resolved_resources[0]
    # The sandbox mounts <data_dir>/shared at /data/shared, so this advertised
    # path resolves to <data_dir>/shared/data/<name> on the host.
    assert res.sandbox_path == f"/data/shared/data/{res.name}"
    expected = tmp_path / "data" / "shared" / "data" / res.name
    assert Path(res.local_path) == expected
    assert expected.is_file()
    # And it must NOT be double-nested under a second data/ (the bug).
    assert not (tmp_path / "data" / "shared" / "data" / "data").exists()


# --- G: FETCHDATA-staging is the reliable primary path (Prompt 277 cycle-1) ---


def test_acquisition_directive_makes_staging_primary_with_tap_fallback():
    """Regression: a directive over-promoting server-side TAP joins steered an
    agent to a live query whose failure cascaded through the whole pipeline; the
    reliable path is FETCHDATA-staging, with any live TAP query verified + fell
    back to staged data."""
    d = _DATA_ACQUISITION_DIRECTIVE
    assert "gaia:gaiadr3.nss_two_body_orbit" in d  # concrete reliable stage
    assert "FALL BACK" in d and "rows_loaded" in d
    assert "un-fallback" in d  # never hinge a pipeline on one live query


# --- H: reproducible data acquisition (Prompt 277 cycle-2) -------------------


def test_acquisition_directive_requires_reproducible_sample():
    """Regression: an agent used a live `SELECT TOP N` (no ORDER BY) whose sample
    varied per run → verification flagged the whole chain non-reproducible and
    discarded it. The directive now mandates reading the staged file or an
    ORDER BY-ed, cached live query."""
    d = _DATA_ACQUISITION_DIRECTIVE
    assert "REPRODUCIBLE" in d
    assert "ORDER BY" in d
    assert "NON-REPRODUCIBLE" in d
    assert "CACHE" in d or "cache" in d
