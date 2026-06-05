"""Literature relevance gate: aggregated results are re-ranked by semantic
similarity to the query and off-topic papers are dropped (prompt 112).
"""

from __future__ import annotations

from types import SimpleNamespace

from paradigm.domains.base import SourceResult
from paradigm.literature.corpus import Corpus


def _bare_corpus(threshold=0.25, min_keep=1):
    """A Corpus with only the attrs _rerank_by_relevance needs (skip heavy init)."""
    c = Corpus.__new__(Corpus)
    c._embed_fn = None
    c._logger = None
    c._config = SimpleNamespace(relevance_threshold=threshold, relevance_min_keep=min_keep)
    return c


def _sr(rid, title):
    return SourceResult(id=rid, source_type="x", title=title, authors=[], summary="", url="")


def test_rerank_drops_offtopic_and_orders_by_relevance():
    c = _bare_corpus()
    results = [
        _sr("off", "CRISPR gene editing in maize for drought resistance"),
        _sr("rel", "Measuring the chirp mass of binary black hole mergers with LIGO"),
        _sr("loose", "Numerical methods for solving partial differential equations"),
        _sr("rel2", "Gravitational waveforms of inspiralling compact binaries"),
    ]
    out = c._rerank_by_relevance(
        "chirp mass gravitational waves from compact binary mergers", results, 10
    )
    ids = [r.id for r in out]
    assert "off" not in ids and "loose" not in ids  # off-topic + loosely-related dropped
    assert set(ids) == {"rel", "rel2"}
    assert ids[0] in {"rel", "rel2"}  # most relevant first


def test_rerank_fails_open_on_empty_query():
    c = _bare_corpus()
    results = [_sr("a", "Anything"), _sr("b", "Something else")]
    assert c._rerank_by_relevance("", results, 5) == results  # unchanged


def test_rerank_min_keep_avoids_starving():
    # Even if everything is below threshold, keep at least min_keep (sorted best-first).
    c = _bare_corpus(threshold=0.99, min_keep=2)
    results = [
        _sr("a", "quantum chromodynamics lattice gauge theory"),
        _sr("b", "ocean acidification coral reef ecosystems"),
        _sr("c", "medieval european trade routes history"),
    ]
    out = c._rerank_by_relevance("gravitational waves", results, 10)
    assert len(out) == 2  # min_keep, not zero
