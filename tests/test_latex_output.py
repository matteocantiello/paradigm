"""Tests for Phase 2 P2-LaTeX — markdown->LaTeX conversion + optional PDF compile."""

from __future__ import annotations

import pytest

from paradigm.journal.latex import (
    compile_pdf,
    find_latex_engine,
    get_preset,
    markdown_to_latex,
    write_paper_latex,
)

_PRESET = get_preset("none")


def _tex(md: str) -> str:
    return markdown_to_latex(md, _PRESET)


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


class TestMarkdownToLatex:
    def test_document_skeleton(self):
        out = _tex("# Title\n\n## Intro\nHello.")
        assert out.startswith(r"\documentclass")
        assert r"\begin{document}" in out
        assert out.strip().endswith(r"\end{document}")
        assert r"\maketitle" in out

    def test_title_extraction(self):
        out = _tex("# My Great Paper\n\n## S\nx")
        assert r"\title{My Great Paper}" in out

    def test_explicit_title_overrides(self):
        out = markdown_to_latex("# In-body\n\n## S\nx", _PRESET, title="Override")
        assert r"\title{Override}" in out

    def test_sections_and_subsections(self):
        out = _tex("# T\n\n## Methods\na\n\n### Detail\nb")
        assert r"\section{Methods}" in out
        assert r"\subsection{Detail}" in out

    def test_abstract_environment(self):
        out = _tex("# T\n\n## Abstract\nWe summarize.")
        assert r"\begin{abstract}" in out and r"\end{abstract}" in out
        assert "We summarize." in out

    def test_inline_math_preserved(self):
        out = _tex(r"# T" + "\n\n## S\n" + r"the value $x_i^2$ holds")
        assert r"$x_i^2$" in out  # math passes through untouched (not escaped)

    def test_display_math_preserved(self):
        out = _tex("# T\n\n## S\n$$E = mc^2$$")
        assert r"$$E = mc^2$$" in out

    def test_special_chars_escaped_outside_math(self):
        out = _tex("# T\n\n## S\n50% of data & more_stuff")
        assert r"50\%" in out
        assert r"\&" in out
        assert r"more\_stuff" in out

    def test_special_chars_not_escaped_inside_math(self):
        out = _tex("# T\n\n## S\n" + r"ratio $a_b$ and 50\%")
        assert r"$a_b$" in out  # underscore inside math untouched

    def test_bold_and_italic(self):
        out = _tex("# T\n\n## S\nthis is **bold** and *italic*")
        assert r"\textbf{bold}" in out
        assert r"\textit{italic}" in out

    def test_figure_conversion(self):
        out = _tex("# T\n\n## Results\n![SEM plot](figures/sem.png)")
        assert r"\includegraphics[width=0.8\linewidth]{figures/sem.png}" in out
        assert r"\caption{SEM plot}" in out
        assert r"\begin{figure}" in out

    def test_figure_caption_strips_redundant_label(self):
        # "![Figure 1: desc]" must not become "Figure 1: Figure 1: desc" (LaTeX
        # already adds the "Figure N:" label).
        out = _tex("# T\n\n## R\n![Figure 1: Mass-luminosity relation](figures/ml.png)")
        assert r"\caption{Mass-luminosity relation}" in out
        assert "Figure 1: Mass" not in out  # no doubled label

    def test_figure_bare_label_yields_empty_caption(self):
        # "![Figure 1]" (no description) -> empty caption keeps the auto "Figure 1:" label.
        out = _tex("# T\n\n## R\n![Figure 1](figures/x.png)")
        assert r"\caption{}" in out

    def test_itemize_and_enumerate(self):
        out = _tex("# T\n\n## S\n- a\n- b\n\n1. one\n2. two")
        assert r"\begin{itemize}" in out and r"\end{itemize}" in out
        assert r"\begin{enumerate}" in out and r"\end{enumerate}" in out
        assert out.count(r"\item") == 4

    def test_references_section(self):
        out = _tex('# T\n\n## References\n[1] Smith (2020). "X". arXiv:2001.1')
        assert r"\section*{References}" in out
        assert "[1] Smith" in out

    # --- tables (A1) -------------------------------------------------------
    def test_markdown_table_becomes_booktabs_tabular(self):
        md = (
            "# T\n\n## Results\n"
            "| Mass | Luminosity |\n"
            "|------|-----------:|\n"
            "| 1.0  | 1.0        |\n"
            "| 2.0  | 11.0       |\n"
        )
        out = _tex(md)
        assert r"\begin{table}" in out and r"\end{table}" in out
        assert r"\begin{tabular}{lr}" in out  # 2nd col right-aligned (`---:`)
        assert r"\toprule" in out and r"\midrule" in out and r"\bottomrule" in out
        assert r"Mass & Luminosity \\" in out
        assert r"1.0 & 1.0 \\" in out
        # no raw pipe-garbage leaked into prose
        assert "|------" not in out

    def test_table_alignment_spec(self):
        md = "# T\n\n## S\n| a | b | c |\n|:--|:-:|--:|\n| 1 | 2 | 3 |\n"
        assert r"\begin{tabular}{lcr}" in _tex(md)

    def test_table_cell_escaping_and_math(self):
        md = "# T\n\n## S\n| q | v |\n|---|---|\n| 50% rise | $x^2$ |\n"
        out = _tex(md)
        assert r"50\% rise & $x^2$ \\" in out

    # --- loose-list numbering (A2) ----------------------------------------
    def test_blank_separated_numbered_list_is_one_enumerate(self):
        # Items separated by blank lines must stay ONE enumerate (1,2,3),
        # not three enumerates each restarting at 1.
        md = "# T\n\n## S\n1. first\n\n2. second\n\n3. third\n"
        out = _tex(md)
        assert out.count(r"\begin{enumerate}") == 1
        assert out.count(r"\end{enumerate}") == 1
        assert out.count(r"\item") == 3

    def test_blank_separated_bullets_stay_one_itemize(self):
        md = "# T\n\n## S\n- a\n\n- b\n\n- c\n"
        out = _tex(md)
        assert out.count(r"\begin{itemize}") == 1
        assert out.count(r"\item") == 3

    def test_list_closes_before_following_paragraph(self):
        md = "# T\n\n## S\n1. one\n2. two\n\nA new paragraph.\n"
        out = _tex(md)
        assert out.count(r"\begin{enumerate}") == 1
        assert r"\end{enumerate}" in out
        assert "A new paragraph." in out


class TestPresets:
    def test_known_preset(self):
        assert get_preset("neurips").name == "neurips"

    def test_unknown_defaults_to_none(self):
        assert get_preset("does-not-exist").name == "none"

    def test_case_insensitive(self):
        assert get_preset("ARXIV").name == "arxiv"


# ---------------------------------------------------------------------------
# write_paper_latex + compile
# ---------------------------------------------------------------------------


class TestWritePaperLatex:
    def test_writes_tex_file(self, tmp_path):
        result = write_paper_latex(tmp_path, "paper-1", "# T\n\n## S\nbody")
        tex_path = tmp_path / "paper-1.tex"
        assert tex_path.exists()
        assert result["tex_path"] == str(tex_path)
        assert r"\documentclass" in tex_path.read_text()
        assert "pdf" not in result  # not compiled unless requested

    def test_no_engine_returns_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.setattr("paradigm.journal.latex.find_latex_engine", lambda: None)
        (tmp_path / "p.tex").write_text(r"\documentclass{article}\begin{document}x\end{document}")
        ok, msg = compile_pdf(tmp_path / "p.tex")
        assert ok is False
        assert "no LaTeX engine" in msg


@pytest.mark.skipif(find_latex_engine() is None, reason="no LaTeX engine installed")
class TestRealCompile:
    def test_compiles_minimal_pdf(self, tmp_path):
        result = write_paper_latex(
            tmp_path, "paper-c", "# Compile Test\n\n## Body\nHello $x^2$.", compile_to_pdf=True
        )
        assert result.get("pdf") is True, result.get("pdf_message")
        assert (tmp_path / "paper-c.pdf").exists()
