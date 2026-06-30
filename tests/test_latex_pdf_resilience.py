"""LaTeX/PDF resilience: undefined-macro fallbacks, Unicode handling, lenient compile.

Guards the fix for the production PDF failure where a writer-emitted ``$M_\\sun$`` (an
undefined control sequence) plus Unicode em/en-dashes aborted the whole compile.
"""

from __future__ import annotations

import pytest

from paradigm.journal.latex import (
    _escape_latex,
    _sanitize_math_span,
    compile_pdf,
    find_latex_engine,
    get_preset,
    markdown_to_latex,
)
from paradigm.journal.paper import sanitize_unicode_math


def test_preamble_defines_common_macro_fallbacks():
    tex = markdown_to_latex("# T\n\n## Abstract\nx\n", get_preset("none"))
    for macro in (r"\providecommand{\sun}", r"\providecommand{\Msun}", r"\providecommand{\degree}"):
        assert macro in tex


def test_escape_converts_unicode_dashes():
    out = _escape_latex("a — b – c")
    assert "—" not in out and "–" not in out
    assert "---" in out and "--" in out


def test_escape_converts_curly_quotes_and_ellipsis():
    out = _escape_latex("“quote” ‘x’ …")
    assert "“" not in out and "”" not in out and "‘" not in out
    assert r"\ldots" in out


def test_sanitize_math_span_converts_unicode_greek_with_separator():
    # Command gets a trailing space so it doesn't merge with a following letter.
    assert _sanitize_math_span("$β$") == r"$\beta $"
    assert _sanitize_math_span("$βCep$") == r"$\beta Cep$"


def test_markdown_to_latex_reference_beta_becomes_command():
    md = '## References\n[1] X. "Hybrid $β$ Cep". arXiv:1. https://arxiv.org/abs/1\n'
    tex = markdown_to_latex(md, get_preset("none"))
    assert "β" not in tex
    assert r"\beta" in tex


@pytest.mark.skipif(find_latex_engine() is None, reason="no LaTeX engine installed")
def test_paper_with_undefined_macro_and_dashes_compiles(tmp_path):
    # Realistic writer output: an undefined \sun macro, a standalone \Msun, Unicode
    # em/en-dashes, and a reference title with literal $β$ — previously aborted the PDF.
    md = sanitize_unicode_math(
        "# Cepheids — A Study\n\n"
        "## Abstract\nWe find $M_\\sun$ near $5\\,\\Msun$ — across a 10–20% range.\n\n"
        "## References\n"
        '[1] X. "Hybrid $β$ Cep/SPB". arXiv:1806.02996. https://arxiv.org/abs/1806.02996\n'
    )
    tex = markdown_to_latex(md, get_preset("none"))
    tex_path = tmp_path / "paper.tex"
    tex_path.write_text(tex)
    produced, msg = compile_pdf(tex_path, timeout=90)
    assert produced, msg
