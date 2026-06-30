"""Markdown -> LaTeX conversion + optional PDF compile (Phase 2 P2-LaTeX).

Toggleable, default-off output format. The conversion is deterministic plain
Python (no LLM, no external Python deps) and preserves ``$...$`` math. PDF
compilation is best-effort: it shells out to a LaTeX engine (tectonic / xelatex /
pdflatex) only if one is installed; otherwise the ``.tex`` is still written.

Markdown paper bodies are produced by the writing phase (headings, ``$math$``,
``![alt](figures/..)`` images, ``[N]`` citation markers + a ``## References``
section). This module renders them into a compilable ``article``-style document.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Journal presets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LatexPreset:
    """A LaTeX output style: document class + preamble packages."""

    name: str
    documentclass: str = r"\documentclass[11pt]{article}"
    # Essentials are unconditional (present in every TeX install). The
    # quality-of-life packages are wrapped in \IfFileExists so a *minimal* TeX
    # install (or a partial texlive) still compiles — missing cosmetic packages
    # are skipped, and missing booktabs falls back to \hline rules so tables
    # still render. (Full installs / tectonic get the nice versions.)
    packages: tuple[str, ...] = (
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath,amssymb}",
        # Best-effort fallbacks for common scientific-notation macros that LLM writers
        # emit (inside $...$) but base LaTeX/amssymb doesn't define — e.g. $M_\sun$,
        # $L_\Lsun$, \degree. Each is the classic "Undefined control sequence" that
        # aborts the whole PDF. \providecommand only defines a macro if it's absent, so
        # a real package (siunitx, aastex, …) still wins. Together with the lenient
        # compile fallback in compile_pdf(), a stray undefined macro no longer kills the PDF.
        (
            r"\providecommand{\sun}{\ensuremath{\odot}}"
            r"\providecommand{\Sun}{\ensuremath{\odot}}"
            r"\providecommand{\Msun}{\ensuremath{M_{\odot}}}"
            r"\providecommand{\msun}{\ensuremath{M_{\odot}}}"
            r"\providecommand{\Lsun}{\ensuremath{L_{\odot}}}"
            r"\providecommand{\lsun}{\ensuremath{L_{\odot}}}"
            r"\providecommand{\Rsun}{\ensuremath{R_{\odot}}}"
            r"\providecommand{\rsun}{\ensuremath{R_{\odot}}}"
            r"\providecommand{\Zsun}{\ensuremath{Z_{\odot}}}"
            r"\providecommand{\zsun}{\ensuremath{Z_{\odot}}}"
            r"\providecommand{\Mdot}{\ensuremath{\dot{M}}}"
            r"\providecommand{\Teff}{\ensuremath{T_{\mathrm{eff}}}}"
            r"\providecommand{\logg}{\ensuremath{\log g}}"
            r"\providecommand{\degree}{\ensuremath{^{\circ}}}"
            r"\providecommand{\degr}{\ensuremath{^{\circ}}}"
            r"\providecommand{\arcsec}{\ensuremath{^{\prime\prime}}}"
            r"\providecommand{\arcmin}{\ensuremath{^{\prime}}}"
            r"\providecommand{\micron}{\ensuremath{\mu\mathrm{m}}}"
            r"\providecommand{\kms}{\ensuremath{\mathrm{km\,s^{-1}}}}"
        ),
        r"\usepackage{graphicx}",
        r"\usepackage[margin=1in]{geometry}",
        # Tables: booktabs if available, else emulate its rules with \hline.
        (
            r"\IfFileExists{booktabs.sty}{\usepackage{booktabs}}{"
            r"\providecommand{\toprule}{\hline}"
            r"\providecommand{\midrule}{\hline}"
            r"\providecommand{\bottomrule}{\hline}}"
        ),
        # Cosmetic-only — load if present, skip silently otherwise.
        r"\IfFileExists{microtype.sty}{\usepackage{microtype}}{}",
        r"\IfFileExists{caption.sty}{\usepackage{caption}}{}",
        r"\IfFileExists{float.sty}{\usepackage{float}}{}",
        r"\IfFileExists{enumitem.sty}{\usepackage{enumitem}}{}",
        r"\IfFileExists{xcolor.sty}{\usepackage{xcolor}}{}",
        r"\usepackage{hyperref}",  # keep last; present in every install
    )


# Article-compatible presets. Journal-specific classes (revtex/aastex) that need
# bundled .cls files and different title/abstract macros are a follow-up.
JOURNAL_PRESETS: dict[str, LatexPreset] = {
    "none": LatexPreset(name="none"),
    "arxiv": LatexPreset(
        name="arxiv",
        documentclass=r"\documentclass[11pt]{article}",
        # Base-only packages so it compiles on a minimal TeX install (no authblk etc.).
    ),
    "neurips": LatexPreset(
        name="neurips",
        documentclass=r"\documentclass[10pt]{article}",
    ),
}


def get_preset(journal: str) -> LatexPreset:
    """Return the preset for a journal key (case-insensitive), defaulting to 'none'."""
    return JOURNAL_PRESETS.get((journal or "none").lower(), JOURNAL_PRESETS["none"])


# ---------------------------------------------------------------------------
# Markdown -> LaTeX conversion (deterministic, math-preserving)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MATH_RE = re.compile(r"\$\$.+?\$\$|\$[^$]+?\$", re.DOTALL)
# LaTeX special characters that must be escaped in prose (backslash handled first).
_SPECIAL = {
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


# Unicode punctuation that has no glyph in the default (T1/Computer Modern) font under
# XeTeX/tectonic — a raw "—" triggers a "could not represent character" warning and can
# render as a blank. Map to LaTeX equivalents. (Unicode *math* symbols are handled
# upstream by sanitize_unicode_math; this covers prose punctuation it doesn't.)
_UNICODE_PUNCT = {
    "—": "---",  # em dash
    "–": "--",  # en dash
    "‒": "--",  # figure dash
    "―": "---",  # horizontal bar
    "‘": "`",  # left single quote
    "’": "'",  # right single quote / apostrophe
    "“": "``",  # left double quote
    "”": "''",  # right double quote
    "…": r"\ldots{}",  # ellipsis
    "−": "$-$",  # minus sign
    " ": "~",  # non-breaking space
    " ": r"\,",  # thin space
    " ": r"\,",  # narrow no-break space
    "•": r"\textbullet{}",  # bullet
}


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in plain prose (not math, not generated TeX)."""
    text = text.replace("\\", r"\textbackslash{}")
    for ch, rep in _SPECIAL.items():
        text = text.replace(ch, rep)
    # Map unfont-able Unicode punctuation last (its replacements add $/\ that must NOT
    # be re-escaped).
    for ch, rep in _UNICODE_PUNCT.items():
        text = text.replace(ch, rep)
    return text


def _sanitize_math_span(span: str) -> str:
    """Convert Unicode math symbols INSIDE a ``$...$`` span to LaTeX commands.

    ``sanitize_unicode_math`` only fixes Unicode *outside* math; a literal ``$β$``
    (common in arXiv reference titles) reaches XeTeX/tectonic as a raw char with no glyph
    in the math font ("Missing character: There is no β in font cmmi10"). Map it to
    ``\\beta``. Commands get a trailing space so ``$βCep$`` -> ``\\beta Cep`` (not the
    undefined ``\\betaCep``)."""
    from paradigm.journal.paper import _UNICODE_TO_LATEX

    for ch, rep in _UNICODE_TO_LATEX.items():
        if ch in span:
            span = span.replace(ch, rep + (" " if rep.startswith("\\") else ""))
    return span


def _convert_inline(text: str) -> str:
    """Convert inline markdown to LaTeX, preserving ``$...$`` math spans verbatim."""
    # Protect math spans with placeholders so escaping doesn't touch them.
    math_spans: list[str] = []

    def _stash(m: re.Match) -> str:
        math_spans.append(_sanitize_math_span(m.group(0)))
        return f"\x00MATH{len(math_spans) - 1}\x00"

    protected = _MATH_RE.sub(_stash, text)
    protected = _escape_latex(protected)
    # Markdown emphasis -> LaTeX (operates on escaped, math-free text).
    protected = _BOLD_RE.sub(lambda m: rf"\textbf{{{m.group(1)}}}", protected)
    protected = _ITALIC_RE.sub(lambda m: rf"\textit{{{m.group(1)}}}", protected)
    # Restore math verbatim.
    for i, span in enumerate(math_spans):
        protected = protected.replace(f"\x00MATH{i}\x00", span)
    return protected


def _heading_command(level: int, title: str) -> str:
    cmd = {1: "section", 2: "section", 3: "subsection", 4: "subsubsection"}.get(level, "subsection")
    return rf"\{cmd}{{{_convert_inline(title)}}}"


def _convert_body_block(lines: list[str]) -> str:
    """Convert a block of non-heading markdown lines (paragraphs, lists, figures)."""
    out: list[str] = []
    in_itemize = False
    in_enumerate = False

    def _close_lists() -> None:
        nonlocal in_itemize, in_enumerate
        if in_itemize:
            out.append(r"\end{itemize}")
            in_itemize = False
        if in_enumerate:
            out.append(r"\end{enumerate}")
            in_enumerate = False

    n = len(lines)
    i = 0
    while i < n:
        stripped = lines[i].rstrip().strip()

        # Table: a `| ... |` row followed by a `|---|` separator line.
        if (
            _looks_like_table_row(stripped)
            and i + 1 < n
            and _TABLE_SEP_RE.match(lines[i + 1].strip())
        ):
            _close_lists()
            header = _split_table_row(stripped)
            sep_cells = _split_table_row(lines[i + 1].strip())
            body_rows: list[list[str]] = []
            j = i + 2
            while j < n and _looks_like_table_row(lines[j].strip()):
                body_rows.append(_split_table_row(lines[j].strip()))
                j += 1
            out.append(_convert_table(header, sep_cells, body_rows))
            i = j
            continue

        img = _IMAGE_RE.search(stripped)
        if img:
            _close_lists()
            alt, path = img.group(1), img.group(2).split()[0].strip('"')
            caption = _FIG_LABEL_RE.sub("", alt).strip()  # drop redundant "Figure N:"
            out.append(r"\begin{figure}[htbp]")
            out.append(r"\centering")
            # Guard against a referenced-but-MISSING image (e.g. a writer-hallucinated
            # "graphical abstract" that was never generated). A bare \includegraphics
            # on a missing file aborts the ENTIRE PDF compile; \IfFileExists degrades
            # it to a placeholder so the rest of the paper still renders.
            out.append(
                rf"\IfFileExists{{{path}}}"
                rf"{{\includegraphics[width=0.8\linewidth]{{{path}}}}}"
                rf"{{\textit{{[Figure unavailable]}}}}"
            )
            # Always emit \caption (keeps the auto-numbered "Figure N" label that
            # the prose refers to); include the description when one survives.
            out.append(rf"\caption{{{_convert_inline(caption)}}}" if caption else r"\caption{}")
            out.append(r"\end{figure}")
            i += 1
            continue

        bullet = _BULLET_RE.match(stripped)
        number = _NUMBER_RE.match(stripped)
        if bullet:
            if not in_itemize:
                _close_lists()
                out.append(r"\begin{itemize}")
                in_itemize = True
            out.append(rf"\item {_convert_inline(bullet.group(1))}")
            i += 1
            continue
        if number:
            if not in_enumerate:
                _close_lists()
                out.append(r"\begin{enumerate}")
                in_enumerate = True
            out.append(rf"\item {_convert_inline(number.group(1))}")
            i += 1
            continue

        if not stripped:
            # A blank line inside a list does NOT end it if the next content line is
            # another list item — markdown "loose lists" stay one list, so numbering
            # keeps counting (1,2,3) instead of resetting (1,1,1).
            if in_itemize or in_enumerate:
                k = i + 1
                while k < n and not lines[k].strip():
                    k += 1
                nxt = lines[k].strip() if k < n else ""
                if _BULLET_RE.match(nxt) or _NUMBER_RE.match(nxt):
                    i += 1
                    continue
            _close_lists()
            out.append("")
            i += 1
            continue

        _close_lists()
        out.append(_convert_inline(stripped))
        i += 1

    _close_lists()
    return "\n".join(out)


# --- Markdown tables -------------------------------------------------------
# A GitHub-flavored table is a row of ``| a | b |`` immediately followed by a
# separator ``|---|:--:|`` line. Without this, a table fell through to prose and
# rendered as literal pipe-garbage (the "bad table formatting" symptom).
_BULLET_RE = re.compile(r"^[-*+]\s+(.*)$")
_NUMBER_RE = re.compile(r"^\d+[.)]\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")
# A leading "Figure N:" / "Fig. N." in alt text is redundant — LaTeX's \caption
# adds its own "Figure N:" label, so strip it to avoid "Figure 1: Figure 1: ...".
_FIG_LABEL_RE = re.compile(r"^(?:figure|fig\.?)\s*\d+\s*[:.—-]?\s*", re.IGNORECASE)


def _looks_like_table_row(stripped: str) -> bool:
    return stripped.startswith("|") and stripped.count("|") >= 2


def _split_table_row(stripped: str) -> list[str]:
    s = stripped.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _column_spec(sep_cells: list[str], ncols: int) -> str:
    """Map markdown alignment cells (``:--``/``:-:``/``--:``) to an l/c/r spec."""
    spec = []
    for c in sep_cells:
        c = c.strip()
        left, right = c.startswith(":"), c.endswith(":")
        spec.append("c" if left and right else "r" if right else "l")
    spec += ["l"] * (ncols - len(spec))
    return "".join(spec[:ncols]) or "l"


def _convert_table(header: list[str], sep_cells: list[str], body_rows: list[list[str]]) -> str:
    """Render a parsed markdown table as a booktabs ``tabular`` inside a ``table``."""
    ncols = len(header)
    for r in body_rows:
        ncols = max(ncols, len(r))
    ncols = max(ncols, 1)
    spec = _column_spec(sep_cells, ncols)

    def _row(cells: list[str]) -> str:
        padded = cells + [""] * (ncols - len(cells))
        return " & ".join(_convert_inline(c) for c in padded[:ncols]) + r" \\"

    out = [
        r"\begin{table}[htbp]",
        r"\centering",
        rf"\begin{{tabular}}{{{spec}}}",
        r"\toprule",
        _row(header),
        r"\midrule",
    ]
    out.extend(_row(r) for r in body_rows)
    out.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(out)


@dataclass
class _Section:
    title: str
    level: int
    lines: list[str] = field(default_factory=list)


def _split_sections(body: str) -> tuple[str, list[_Section]]:
    """Split a markdown body into a leading title (first '# ') and sections."""
    title = ""
    sections: list[_Section] = []
    current: _Section | None = None
    for raw in body.splitlines():
        m = _HEADING_RE.match(raw)
        if m:
            level = len(m.group(1))
            heading = m.group(2).strip()
            if level == 1 and not title and current is None:
                title = heading
                continue
            current = _Section(title=heading, level=level)
            sections.append(current)
        elif current is not None:
            current.lines.append(raw)
        elif raw.strip():
            # Preamble prose before any section -> an untitled lead section.
            current = _Section(title="", level=2)
            sections.append(current)
            current.lines.append(raw)
    return title, sections


def markdown_to_latex(body: str, preset: LatexPreset, title: str | None = None) -> str:
    """Convert a markdown paper body into a compilable LaTeX document.

    Args:
        body: Paper markdown (headings, ``$math$``, ``![](figures/..)``, ``[N]`` + References).
        preset: Journal/style preset (document class + packages).
        title: Optional explicit title; otherwise the body's first ``# Title`` is used.

    Returns:
        A full ``\\documentclass ... \\end{document}`` LaTeX string.
    """
    parsed_title, sections = _split_sections(body)
    doc_title = title or parsed_title or "Untitled"

    parts: list[str] = [preset.documentclass, *preset.packages, ""]
    parts.append(rf"\title{{{_convert_inline(doc_title)}}}")
    parts.append(r"\author{Paradigm}")
    parts.append(r"\date{}")
    parts.append(r"\begin{document}")
    parts.append(r"\maketitle")

    for sec in sections:
        key = sec.title.strip().lower()
        if key == "abstract":
            parts.append(r"\begin{abstract}")
            parts.append(_convert_body_block(sec.lines))
            parts.append(r"\end{abstract}")
        elif key in ("references", "bibliography", "works cited"):
            parts.append(r"\section*{References}")
            parts.append(r"\begingroup")
            parts.append(r"\small")
            # Flush-left, hanging-indent entries (every reference starts at the
            # margin; continuation lines indent under it). Without this, the 2nd+
            # references picked up a stray paragraph indent and looked ragged.
            parts.append(r"\setlength{\parindent}{0pt}")
            parts.append(r"\setlength{\parskip}{3pt}")
            for raw in sec.lines:
                if raw.strip():
                    parts.append(r"\hangindent=1.5em\hangafter=1")
                    parts.append(_convert_inline(raw.strip()) + r"\par")
            parts.append(r"\endgroup")
        else:
            if sec.title:
                parts.append(_heading_command(sec.level, sec.title))
            parts.append(_convert_body_block(sec.lines))

    parts.append(r"\end{document}")
    return "\n".join(p for p in parts if p is not None)


# ---------------------------------------------------------------------------
# Optional PDF compilation (best-effort)
# ---------------------------------------------------------------------------

_ENGINES = ("tectonic", "xelatex", "pdflatex")


def find_latex_engine() -> str | None:
    """Return the first available LaTeX engine on PATH, or None."""
    for engine in _ENGINES:
        if shutil.which(engine):
            return engine
    return None


def compile_pdf(tex_path: Path, timeout: int = 120) -> tuple[bool, str]:
    """Best-effort compile ``tex_path`` to PDF in its directory.

    Returns ``(produced, message)``. If no LaTeX engine is installed, returns
    ``(False, "no LaTeX engine ...")`` without raising — the .tex is unaffected.
    """
    engine = find_latex_engine()
    if engine is None:
        return False, f"no LaTeX engine found (looked for: {', '.join(_ENGINES)})"

    workdir = tex_path.parent
    pdf_path = tex_path.with_suffix(".pdf")
    name = str(tex_path.name)

    # Try a STRICT compile first (clean output); if it fails to produce a PDF, retry in a
    # LENIENT mode that continues past a recoverable error (e.g. one writer-emitted
    # undefined macro) so a single bad token can't deny the whole paper a PDF.
    if engine == "tectonic":
        attempts = [([engine, name], 1), ([engine, "-Z", "continue-on-errors", name], 1)]
    else:
        attempts = [
            ([engine, "-interaction=nonstopmode", "-halt-on-error", name], 2),  # resolve refs
            ([engine, "-interaction=nonstopmode", name], 2),  # no halt → skip & continue
        ]

    last_output = ""
    for idx, (cmd, passes) in enumerate(attempts):
        for _ in range(passes):
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                last_output = (proc.stdout or "") + (proc.stderr or "")
            except (subprocess.TimeoutExpired, OSError) as e:
                return False, f"{engine} failed: {e}"
        if pdf_path.exists():
            note = "" if idx == 0 else " (lenient: skipped unrenderable markup)"
            return True, f"compiled with {engine}{note}"
    return False, _extract_tex_errors(last_output)


def _extract_tex_errors(log: str) -> str:
    """Pull the most useful error lines from a LaTeX log for diagnostics."""
    errors = [ln for ln in log.splitlines() if ln.startswith("!") or "Error" in ln]
    tail = "\n".join(errors[-8:]) if errors else log[-500:]
    return f"PDF not produced. {tail}".strip()


def write_paper_latex(
    paper_dir: Path,
    paper_id: str,
    body: str,
    *,
    journal: str = "none",
    title: str | None = None,
    compile_to_pdf: bool = False,
) -> dict[str, object]:
    """Render ``body`` to ``paper_dir/paper_id.tex`` (+ optional PDF). Best-effort.

    Returns a dict with the tex path and, when requested, the PDF status.
    """
    paper_dir.mkdir(parents=True, exist_ok=True)
    tex = markdown_to_latex(body, get_preset(journal), title=title)
    tex_path = paper_dir / f"{paper_id}.tex"
    tex_path.write_text(tex)
    result: dict[str, object] = {"tex_path": str(tex_path)}
    if compile_to_pdf:
        produced, message = compile_pdf(tex_path)
        result["pdf"] = produced
        result["pdf_message"] = message
        if produced:
            result["pdf_path"] = str(tex_path.with_suffix(".pdf"))
    return result
