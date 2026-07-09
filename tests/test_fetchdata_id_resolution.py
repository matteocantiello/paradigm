"""Robust [FETCHDATA:] id resolution — repair mangled ids against search hits.

A live run found a real catalog via DATASEARCH but emitted
[FETCHDATA: vizier:J/MNRAS/506/150/` (or similar)] and fetched nothing.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from paradigm.orchestrator.literature import LiteratureHandler


@pytest.fixture
def handler():
    eng = MagicMock()
    eng._config.literature.data_providers = ["vizier", "zenodo"]
    h = LiteratureHandler(eng)
    h.seen_dataset_ids = [
        "vizier:J/MNRAS/506/150",
        "vizier:III/284",
        "zenodo:999271",
    ]
    return h


def test_strips_parenthetical_and_trailing_junk(handler):
    rid, corrected = handler._resolve_fetchdata_id("vizier:J/MNRAS/506/150/` (or similar)")
    assert rid == "vizier:J/MNRAS/506/150" and corrected


def test_strips_backticks_and_quotes(handler):
    assert handler._resolve_fetchdata_id("`vizier:III/284`")[0] == "vizier:III/284"
    assert handler._resolve_fetchdata_id("'zenodo:999271'")[0] == "zenodo:999271"


def test_well_formed_owned_id_trusted_verbatim(handler):
    # A bare, provider-recognized id (VizieR accepts the J/... tail) is used as-is.
    rid, corrected = handler._resolve_fetchdata_id("J/MNRAS/506/150")
    assert rid == "J/MNRAS/506/150" and not corrected


def test_missing_prefix_snaps_to_seen_id(handler):
    # "J/MNRAS/506/150" is VizieR-owned, but an id the provider does NOT own
    # (wrong/absent prefix) snaps to the closest search hit by tail.
    rid, corrected = handler._resolve_fetchdata_id("catalog:III/284")
    assert rid == "vizier:III/284" and corrected


def test_owned_id_trusted_even_if_typo(handler):
    # Design boundary: a provider-OWNED id is trusted verbatim (the agent may
    # know a real id that was never searched). A typo here fails at fetch time
    # with a clear error rather than being silently rewritten. Only NON-owned
    # ids are snapped (see test_missing_prefix_snaps_to_seen_id).
    rid, corrected = handler._resolve_fetchdata_id("zenodo:99927")
    assert rid == "zenodo:99927" and not corrected


def test_unrecognized_prose_id_is_rejected(handler):
    assert handler._resolve_fetchdata_id("the GALAH main catalog please")[0] is None


def test_empty_after_cleanup_is_none(handler):
    assert handler._resolve_fetchdata_id("`` ( )")[0] is None


def test_no_search_context_trusts_owned_only():
    eng = MagicMock()
    eng._config.literature.data_providers = ["vizier"]
    h = LiteratureHandler(eng)  # seen_dataset_ids empty
    assert h._resolve_fetchdata_id("vizier:III/284")[0] == "vizier:III/284"
    assert h._resolve_fetchdata_id("mystery:xyz")[0] is None
