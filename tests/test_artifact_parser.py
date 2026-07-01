"""Tests for paper artifact scanning (figures, pdf, etc.)."""

from __future__ import annotations

from backend.api.services.artifact_parser import scan_paper_artifacts


def test_detects_pdf(tmp_path):
    """A compiled <paper_id>.pdf is reported as has_pdf so the UI can offer it."""
    paper_dir = tmp_path / "paper-xyz"
    paper_dir.mkdir()
    (paper_dir / "paper-xyz.md").write_text("# Title")
    assert scan_paper_artifacts(paper_dir).has_pdf is False

    (paper_dir / "paper-xyz.pdf").write_bytes(b"%PDF-1.5 ...")
    assert scan_paper_artifacts(paper_dir).has_pdf is True


def test_detects_digest(tmp_path):
    """A <paper_id>-digest.md is reported as has_digest so the UI can show the Digest tab."""
    paper_dir = tmp_path / "paper-dig"
    paper_dir.mkdir()
    (paper_dir / "paper-dig.md").write_text("# Title")
    assert scan_paper_artifacts(paper_dir).has_digest is False

    (paper_dir / "paper-dig-digest.md").write_text("A plain-language summary.")
    assert scan_paper_artifacts(paper_dir).has_digest is True


def test_detects_figures(tmp_path):
    """Figures under figures/ are listed and flip has_figures."""
    paper_dir = tmp_path / "paper-abc"
    (paper_dir / "figures").mkdir(parents=True)
    (paper_dir / "figures" / "fig1.png").write_bytes(b"\x89PNG")

    out = scan_paper_artifacts(paper_dir)
    assert out.has_figures is True
    assert out.figure_files == ["fig1.png"]
