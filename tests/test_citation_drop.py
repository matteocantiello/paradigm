"""Tests for Phase 2 — resolve-or-drop citation finalize (bibliography helpers)."""

from __future__ import annotations

from paradigm.literature.bibliography import BibliographyBuilder, Reference


def _ref(index: int, *, title: str = "") -> Reference:
    return Reference(index=index, url=f"https://arxiv.org/abs/{index}.00000", title=title)


class TestDropUnresolvedReferences:
    def test_drops_unresolved_and_renumbers(self):
        refs = [
            _ref(1, title="Resolved A"),
            _ref(2),  # unresolved (no title)
            _ref(3, title="Resolved B"),
        ]
        kept, remap = BibliographyBuilder.drop_unresolved_references(refs)
        assert [r.index for r in kept] == [1, 2]
        assert [r.title for r in kept] == ["Resolved A", "Resolved B"]
        assert remap == {1: 1, 2: None, 3: 2}

    def test_all_resolved_unchanged_mapping(self):
        refs = [_ref(1, title="A"), _ref(2, title="B")]
        kept, remap = BibliographyBuilder.drop_unresolved_references(refs)
        assert len(kept) == 2
        assert remap == {1: 1, 2: 2}

    def test_all_dropped(self):
        refs = [_ref(1), _ref(2)]
        kept, remap = BibliographyBuilder.drop_unresolved_references(refs)
        assert kept == []
        assert remap == {1: None, 2: None}


class TestRemapCitationMarkers:
    def test_rewrites_and_removes(self):
        # [1]->[1]; original [2] dropped (removed); [3]->[2].
        text = "Foo [1] bar [2] baz [3]."
        remap = {1: 1, 2: None, 3: 2}
        out = BibliographyBuilder.remap_citation_markers(text, remap)
        assert out == "Foo [1] bar  baz [2]."
        assert "[3]" not in out  # no dangling original marker

    def test_unknown_markers_unchanged(self):
        out = BibliographyBuilder.remap_citation_markers("see [9]", {1: 1})
        assert "[9]" in out

    def test_consecutive_markers(self):
        # [1][2][3] with 2 dropped -> [1][2] (3->2)
        out = BibliographyBuilder.remap_citation_markers("[1][2][3]", {1: 1, 2: None, 3: 2})
        assert out == "[1][2]"
