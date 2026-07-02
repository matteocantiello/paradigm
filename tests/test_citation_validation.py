"""Tests for the deterministic citation grounding + fabricated-citation safety net.

Covers the pure helpers in ``paradigm.literature.citation_validation`` that implement the
``corpus_grounded_citations`` invariant and the always-on strip pass.
"""

from __future__ import annotations

from paradigm.literature.citation_validation import (
    build_citation_allowlist,
    compile_allowlist_citations,
    validate_and_strip_citations,
)

PAPERS = [
    ("2501.00001", "Deep Learning for Stellar Pulsations", "Smith"),
    ("2502.00002", "Red Noise in Light Curves", "Jones"),
    ("hep-ph/9901001", "An Old-Style Preprint", "Doe"),
]


# --------------------------------------------------------------------------- #
# build_citation_allowlist
# --------------------------------------------------------------------------- #


def test_allowlist_numbers_and_rules():
    block, entries = build_citation_allowlist(PAPERS, 40)
    assert entries == PAPERS
    assert "[1] Smith:" in block
    assert "[2] Jones:" in block
    assert "[3] Doe:" in block
    assert "arXiv:2501.00001" in block
    # The cite-only rules + the supersede line are present.
    assert "cite ONLY" in block
    assert "Do NOT write your own References" in block
    assert "SUPERSEDES" in block


def test_allowlist_respects_cap():
    block, entries = build_citation_allowlist(PAPERS, 2)
    assert len(entries) == 2
    assert "[2] Jones" in block
    assert "Doe" not in block


def test_allowlist_empty_when_no_papers():
    assert build_citation_allowlist([], 40) == ("", [])


def test_allowlist_skips_entries_without_id():
    papers = [("", "No ID Paper", "Ghost"), ("2501.00001", "Real", "Smith")]
    block, entries = build_citation_allowlist(papers, 40)
    assert entries == [("2501.00001", "Real", "Smith")]
    assert "Ghost" not in block


def test_allowlist_truncates_long_titles():
    long_title = "A" * 200
    block, _ = build_citation_allowlist([("2501.00001", long_title, "Smith")], 40)
    assert "..." in block
    assert "A" * 200 not in block


# --------------------------------------------------------------------------- #
# compile_allowlist_citations
# --------------------------------------------------------------------------- #


def test_compile_keeps_in_range_drops_out_of_range():
    body = "Cites [1] and [2]. A fabricated [9] marker."
    new_body, refs_md, cited = compile_allowlist_citations(body, PAPERS)
    assert "[9]" not in new_body
    assert "fabricated  marker" not in new_body  # tidied double space
    assert len(cited) == 2
    assert refs_md.startswith("## References")
    assert "arXiv:2501.00001" in refs_md
    assert "arXiv:2502.00002" in refs_md


def test_compile_strips_writer_authored_references():
    body = "Body cites [1].\n\n## References\n[1] Hallucinated junk the writer invented\n"
    new_body, _refs, cited = compile_allowlist_citations(body, PAPERS)
    assert "Hallucinated junk" not in new_body
    assert len(cited) == 1
    assert cited[0] == PAPERS[0]
    # Exactly one References section, and it is the deterministic one.
    assert new_body.count("## References") == 1
    assert 'Smith. "Deep Learning for Stellar Pulsations"' in new_body


def test_compile_renumbers_by_first_appearance():
    # Writer cites [2] before [1]; final numbering is citation order (IEEE-style).
    body = "First [2] then [1]."
    new_body, _refs, cited = compile_allowlist_citations(body, PAPERS)
    assert "First [1] then [2]." in new_body
    assert cited[0] == PAPERS[1]  # Jones cited first -> reference [1]
    assert cited[1] == PAPERS[0]


def test_compile_no_markers_yields_no_references():
    body = "A paper body with no citations at all."
    new_body, refs_md, cited = compile_allowlist_citations(body, PAPERS)
    assert refs_md == ""
    assert cited == []
    assert "## References" not in new_body


def test_compile_empty_entries_is_safe():
    body = "Body with [1] marker.\n\n## References\nwriter junk\n"
    new_body, refs_md, cited = compile_allowlist_citations(body, [])
    assert cited == []
    assert refs_md == ""
    assert "writer junk" not in new_body  # writer refs still stripped


def test_compile_deduplicates_repeated_marker():
    body = "Cite [1] here and [1] again and [2]."
    _new_body, _refs, cited = compile_allowlist_citations(body, PAPERS)
    assert len(cited) == 2  # [1] counted once


# --------------------------------------------------------------------------- #
# validate_and_strip_citations
# --------------------------------------------------------------------------- #


def test_strip_removes_fabricated_arxiv_keeps_valid():
    body = "See arXiv:9999.88888 and the real arXiv:2501.00001 here."
    out, stats = validate_and_strip_citations(body, {"2501.00001"})
    assert "9999.88888" not in out
    assert "arXiv:2501.00001" in out
    assert stats["fabricated_arxiv_stripped"] == 1
    assert "Seeand" not in out  # no word merge


def test_strip_removes_parenthesized_fabricated_arxiv():
    body = "As shown (arXiv:9999.88888) in prior work."
    out, stats = validate_and_strip_citations(body, set())
    assert "9999.88888" not in out
    assert "()" not in out  # empty parens tidied
    assert stats["fabricated_arxiv_stripped"] == 1


def test_strip_count_only_mode_leaves_body_unchanged():
    body = "Fabricated arXiv:9999.88888 here."
    out, stats = validate_and_strip_citations(body, set(), strip=False)
    assert out == body
    assert stats["fabricated_arxiv_stripped"] == 1


def test_strip_preserves_references_section():
    # A fabricated id inside the trailing References section is left untouched
    # (we don't mangle a writer-authored bibliography).
    body = "Prose with arXiv:9999.88888.\n\n## References\n[1] X. arXiv:7777.66666\n"
    out, stats = validate_and_strip_citations(body, set())
    assert "7777.66666" in out  # in references -> preserved
    assert "9999.88888" not in out  # in prose -> stripped
    assert stats["fabricated_arxiv_stripped"] == 1


def test_strip_counts_author_year_without_deleting():
    body = "Prior work (Smith et al., 2021) and (Jones and Lee, 2019) showed X."
    out, stats = validate_and_strip_citations(body, set())
    assert "(Smith et al., 2021)" in out  # not deleted
    assert stats["unverifiable_author_year"] == 2


def test_strip_matches_old_style_and_versioned_ids():
    body = "Old arXiv:hep-ph/9901001 and versioned arXiv:2501.00001v3 cited."
    out, stats = validate_and_strip_citations(body, {"2501.00001"})
    assert "hep-ph/9901001" not in out  # fabricated old-style stripped
    assert "arXiv:2501.00001v3" in out  # versioned id matches versionless valid id
    assert stats["fabricated_arxiv_stripped"] == 1


# --------------------------------------------------------------------------- #
# Non-arXiv (ext-…) entries: never render a fabricated arXiv form
# --------------------------------------------------------------------------- #

EXT_PAPERS = [
    ("2501.00001", "Deep Learning for Stellar Pulsations", "Smith"),
    ("ext-ab12cd34ef56", "Red Noise in Massive Stars", "Unknown"),
]
EXT_URLS = {"ext-ab12cd34ef56": "https://www.aanda.org/articles/aa/pdf/2019/paper.pdf"}


def test_allowlist_ext_entry_renders_source_url_not_arxiv():
    block, _ = build_citation_allowlist(EXT_PAPERS, 40, EXT_URLS)
    assert "arXiv:ext-" not in block
    assert "https://www.aanda.org/articles/aa/pdf/2019/paper.pdf" in block
    assert "arXiv:2501.00001" in block  # real arXiv entry unchanged


def test_allowlist_ext_entry_without_url_labels_external():
    block, _ = build_citation_allowlist(EXT_PAPERS, 40)
    assert "arXiv:ext-" not in block
    assert "journal/external paper" in block


def test_compile_ext_reference_uses_url_and_omits_unknown_author():
    body = "Result [1] agrees with observations [2]."
    new_body, refs, cited = compile_allowlist_citations(body, EXT_PAPERS, EXT_URLS)
    assert "arXiv:ext-" not in new_body
    assert "arxiv.org/abs/ext-" not in new_body
    assert 'Unknown. "Red Noise' not in new_body
    assert '[2] "Red Noise in Massive Stars". https://www.aanda.org/' in new_body
    # Real arXiv entry keeps the arXiv form.
    assert "arXiv:2501.00001" in new_body
    assert len(cited) == 2


def test_compile_ext_reference_without_url_still_no_fake_arxiv():
    body = "Only the external paper is cited [2]."
    new_body, refs, cited = compile_allowlist_citations(body, EXT_PAPERS)
    assert "arxiv.org/abs/ext-" not in new_body
    assert '[1] "Red Noise in Massive Stars".' in new_body
