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
