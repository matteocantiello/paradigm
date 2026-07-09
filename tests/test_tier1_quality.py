"""Overnight Tier 1: reference integrity, revision-block strip, stats directive,
CDS ReadMe data cards."""

from __future__ import annotations

from paradigm.journal.paper import _strip_revision_blocks, strip_agent_scaffolding
from paradigm.literature.citation_validation import enforce_reference_integrity
from paradigm.literature.resources import cds_read_fwf_recipe, parse_cds_readme
from paradigm.orchestrator.constants import _STATS_RIGOR_DIRECTIVE

# --- T1a: dangling-reference invariant ---------------------------------------

_BODY = (
    "Intro cites [1] and [2].\n\nResults rely on [3] and the dangling [20], "
    'twice [20].\n\n## References\n\n[1] A. "P1". arXiv:1\n[2] B. "P2". arXiv:2\n'
    '[3] C. "P3". arXiv:3\n'
)


def test_dangling_reference_stripped():
    body, n = enforce_reference_integrity(_BODY)
    assert n == 2
    assert "[20]" not in body.split("## References")[0]
    # In-range markers and the References section itself are untouched.
    assert "[1]" in body and "[3] C." in body


def test_in_range_body_unchanged():
    body, n = enforce_reference_integrity(_BODY.replace("[20]", "[2]"))
    assert n == 0


def test_no_references_section_unchanged():
    body, n = enforce_reference_integrity("Prose citing [5] with no bibliography.")
    assert n == 0 and "[5]" in body


# --- T1b: revision-correspondence block removal -------------------------------

_LEAKED = (
    "# Title\n\n## Results\nScience text.\n\n"
    "**Summary of revisions addressing reviewer feedback**\n\n"
    "Required Change 1: fixed figure numbering.\nRequired Change 2: rounding.\n\n"
    "## Discussion\nMore science.\n"
)


def test_revision_summary_block_removed():
    out = _strip_revision_blocks(_LEAKED)
    assert "Summary of revisions" not in out
    assert "Required Change 1" not in out
    assert "## Discussion" in out and "Science text." in out


def test_markdown_heading_variant_removed():
    text = "# T\n\n### Response to Reviewers\n- point\n\n## Conclusions\nDone.\n"
    out = _strip_revision_blocks(text)
    assert "Response to Reviewers" not in out and "## Conclusions" in out


def test_legit_sections_survive():
    text = "# T\n\n## Discussion\nWe revise our estimate of X upward.\n"
    assert _strip_revision_blocks(text) == text


def test_strip_agent_scaffolding_applies_block_removal():
    out = strip_agent_scaffolding(_LEAKED)
    assert "Required Change" not in out


# --- T1c: stats directive ------------------------------------------------------


def test_stats_directive_content():
    d = _STATS_RIGOR_DIRECTIVE
    assert "RANK-BASED" in d and "Spearman" in d
    assert "permutation" in d and "effect sizes" in d.lower()
    assert "exclude" in d.lower()


# --- T1d: CDS ReadMe parsing ----------------------------------------------------

_README = """Byte-by-byte Description of file: tablee1.dat
--------------------------------------------------------------------------------
   Bytes Format Units   Label     Explanations
--------------------------------------------------------------------------------
   1- 11  A11   ---     ID        Star name
  14- 18  F5.2  kK      Teff      Effective temperature
  21- 24  F4.2  [cm/s2] logg      Log gravity
      26  A1    ---     Flag      Quality flag
--------------------------------------------------------------------------------
"""


def test_parse_cds_readme_ranges_and_single_byte():
    specs = parse_cds_readme(_README)
    cols = specs["tablee1.dat"]
    assert [c["label"] for c in cols] == ["ID", "Teff", "logg", "Flag"]
    assert cols[0]["bytes"] == "1-11" and cols[3]["bytes"] == "26"
    assert cols[1]["unit"] == "kK"


def test_read_fwf_recipe_is_zero_based_half_open():
    specs = parse_cds_readme(_README)
    recipe = cds_read_fwf_recipe("tablee1.dat", specs["tablee1.dat"])
    assert "(0,11)" in recipe and "(13,18)" in recipe and "(25,26)" in recipe
    assert "names=['ID', 'Teff', 'logg', 'Flag']" in recipe
    assert "read_fwf" in recipe


def test_parse_cds_readme_empty_on_garbage():
    assert parse_cds_readme("no byte tables here") == {}
