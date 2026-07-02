"""Deterministic citation grounding + an always-on fabricated-citation safety net.

These are **pure functions** (no engine / IO) so they're trivially unit-testable. They
implement the "corpus-grounded citations" invariant (see
``CitationConfig.corpus_grounded_citations``): the writer is shown a numbered allow-list
built from the cycle's *discovered* papers and told to cite ONLY ``[N]`` markers from it;
the bibliography is then compiled deterministically from that same set, so an inline
citation cannot reference a paper the cycle never retrieved.

``validate_and_strip_citations`` is the always-on net (independent of the flag): it removes
fabricated inline arXiv identifiers (ids not in the cycle's corpus) and counts unverifiable
``(Author, Year)`` cites for telemetry.

The allow-list source is ``LiteratureHandler.discovered_papers`` — a list of
``(arxiv_id, title, first_author)`` tuples — and the valid-id set is
``LiteratureHandler.seen_paper_ids``.
"""

from __future__ import annotations

import re

# A bracketed citation marker, e.g. ``[1]`` / ``[12]``.
_MARKER_RE = re.compile(r"\[(\d+)\]")

# An inline arXiv identifier in prose (new ``YYMM.NNNNN`` or old ``cat/NNNNNNN`` style).
# Deliberately does NOT consume surrounding whitespace/brackets (that merged adjacent
# words); ``_tidy`` cleans up the empty parens / double spaces left behind.
_ARXIV_INLINE_RE = re.compile(
    r"arXiv:\s*(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?",
    re.IGNORECASE,
)

# An "(Author, Year)" style inline citation — unverifiable without the allow-list, so it is
# COUNTED for telemetry, never auto-deleted (removing it mid-sentence would break prose).
_AUTHOR_YEAR_RE = re.compile(
    r"\([A-Z][A-Za-z.'’\-]+"
    r"(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][A-Za-z.'’\-]+)?"
    r",?\s+(?:18|19|20)\d{2}[a-z]?\)"
)

# A trailing References / Bibliography / Works Cited section (everything to EOF).
_REFS_SECTION_RE = re.compile(
    r"\n#{1,3}\s*(references|bibliography|works\s+cited)\b.*\Z",
    re.IGNORECASE | re.DOTALL,
)

_TITLE_CAP = 110

# A REAL arXiv identifier form (new ``YYMM.NNNNN`` or old ``cat/NNNNNNN``). Discovered
# papers can carry synthetic/provider ids (seed-discovered journal PDFs get ``ext-<hash>``)
# — rendering those as ``arXiv:ext-…`` + a dead arxiv.org link would fabricate a reference.
_ARXIV_ID_FORM_RE = re.compile(
    r"^(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.IGNORECASE
)


def _is_arxiv_id(paper_id: str) -> bool:
    return bool(_ARXIV_ID_FORM_RE.match(paper_id or ""))


def _arxiv_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}"


def _norm_arxiv(s: str) -> str:
    """Strip a trailing version (``v2``) and surrounding whitespace so ids compare equal."""
    return re.sub(r"v\d+$", "", (s or "").strip())


def _tidy(text: str) -> str:
    """Clean up artifacts left by removing an inline token: empty ``()``/``[]`` pairs and
    runs of interior spaces. Collapses ``2+`` spaces only when followed by a non-space, so
    trailing ``"  \\n"`` markdown hard-breaks survive."""
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\[\s*\]", "", text)
    text = re.sub(r"[ \t]{2,}(?=\S)", " ", text)
    return text


def build_citation_allowlist(
    papers: list[tuple[str, str, str]],
    max_n: int,
    urls: dict[str, str] | None = None,
) -> tuple[str, list[tuple[str, str, str]]]:
    """Build the writer-facing allow-list block from discovered papers.

    Args:
        papers: ``(arxiv_id, title, first_author)`` tuples (e.g.
            ``LiteratureHandler.discovered_papers``).
        max_n: Cap on the number of papers exposed.
        urls: Optional ``paper_id -> source url`` map for NON-arXiv entries (synthetic
            ``ext-…`` ids from seed-discovered journal PDFs), so they render with their
            real link instead of a fabricated ``arXiv:`` form.

    Returns:
        ``(instruction_block, entries)`` where ``entries`` is the capped list the
        bibliography must be compiled from (same order ⇒ stable ``[N]`` numbering).
        ``("", [])`` when there are no papers.
    """
    entries = [p for p in papers if p and p[0]][:max_n]
    if not entries:
        return "", []

    lines = [
        "\n\n## Citation Allow-List (cite ONLY from this list)",
        "You may cite ONLY the papers below, using bracketed numbers like [1] or [2][5]. "
        "Strict rules:",
        "- Cite a source as [N], where N is its number in this list.",
        '- Do NOT write inline citations as "(Author, Year)" — use [N] only.',
        "- Do NOT invent arXiv IDs, DOIs, authors, titles, or any paper not listed here.",
        "- Do NOT write your own References/Bibliography section — it is generated "
        "automatically from the [N] markers you use.",
        "- This SUPERSEDES any earlier instruction to author references or aim for a "
        "reference count: cite only [N] markers and write no bibliography.",
        "",
    ]
    for i, (arxiv_id, title, first_author) in enumerate(entries, 1):
        short = title if len(title) <= _TITLE_CAP else title[:_TITLE_CAP] + "..."
        if _is_arxiv_id(arxiv_id):
            source = f"arXiv:{arxiv_id}"
        else:
            source = (urls or {}).get(arxiv_id) or "journal/external paper"
        lines.append(f"[{i}] {first_author or 'Unknown'}: {short} ({source})")
    lines.append("")
    return "\n".join(lines), entries


def compile_allowlist_citations(
    body: str,
    entries: list[tuple[str, str, str]],
    urls: dict[str, str] | None = None,
) -> tuple[str, str, list[tuple[str, str, str]]]:
    """Compile the deterministic bibliography for a corpus-grounded paper.

    Strips any writer-authored References section, keeps only in-range ``[N]`` markers
    (dropping fabricated/out-of-range ones), renumbers the survivors contiguously by first
    appearance, and appends a ``## References`` section built from ``entries`` — so every
    reference is a real discovered paper.

    Returns ``(new_body, references_markdown, cited_entries)`` where ``cited_entries`` is
    the list of ``(arxiv_id, title, first_author)`` actually cited, in final ``[N]`` order.
    """
    n = len(entries)
    # Strip a writer-authored references section FIRST so its markers aren't counted.
    core = _REFS_SECTION_RE.sub("", body).rstrip()

    used_order: list[int] = []
    seen: set[int] = set()
    for m in _MARKER_RE.finditer(core):
        k = int(m.group(1))
        if 1 <= k <= n and k not in seen:
            seen.add(k)
            used_order.append(k)

    remap = {old: i + 1 for i, old in enumerate(used_order)}
    dropped = 0

    def _sub(m: re.Match) -> str:
        nonlocal dropped
        k = int(m.group(1))
        if k in remap:
            return f"[{remap[k]}]"
        dropped += 1  # out-of-range ⇒ fabricated ⇒ drop
        return ""

    new_core = _MARKER_RE.sub(_sub, core).rstrip()
    if dropped:
        new_core = _tidy(new_core)

    if not used_order:
        return new_core, "", []

    cited_entries = [entries[old - 1] for old in used_order]
    refs_lines = ["## References", ""]
    for new_idx, (arxiv_id, title, first_author) in enumerate(cited_entries, 1):
        if _is_arxiv_id(arxiv_id):
            refs_lines.append(
                f'[{new_idx}] {first_author or "Unknown"}. "{title}". '
                f"arXiv:{arxiv_id}. {_arxiv_url(arxiv_id)}"
            )
        else:
            # Synthetic ``ext-…`` / provider id: cite by source URL — never a
            # fabricated arXiv form. Omit an unknown author rather than print it.
            author_part = (
                f"{first_author}. " if first_author and first_author != "Unknown" else ""
            )
            url = (urls or {}).get(arxiv_id) or ""
            refs_lines.append(f'[{new_idx}] {author_part}"{title}".{f" {url}" if url else ""}')
    references_md = "\n".join(refs_lines)
    return f"{new_core}\n\n{references_md}", references_md, cited_entries


def validate_and_strip_citations(
    body: str, valid_arxiv_ids: set[str] | frozenset[str], *, strip: bool = True
) -> tuple[str, dict[str, int]]:
    """Always-on safety net: remove fabricated inline arXiv ids; count author-year cites.

    Operates on the PROSE only (a trailing References section is left untouched so a
    writer-authored bibliography isn't mangled). An ``arXiv:<id>`` whose id is not in
    ``valid_arxiv_ids`` is fabricated and removed (``strip=True``) or just counted
    (``strip=False``). DOIs are intentionally NOT stripped — the cycle rarely has the full
    corpus DOI set, so stripping would risk false positives.

    Returns ``(new_body, stats)`` with ``stats`` keys ``fabricated_arxiv_stripped`` and
    ``unverifiable_author_year``.
    """
    valid = {_norm_arxiv(x) for x in valid_arxiv_ids}

    m = _REFS_SECTION_RE.search(body)
    prose, refs = (body[: m.start()], body[m.start() :]) if m else (body, "")

    stats = {
        "fabricated_arxiv_stripped": 0,
        "unverifiable_author_year": len(_AUTHOR_YEAR_RE.findall(prose)),
    }

    def _sub(match: re.Match) -> str:
        if _norm_arxiv(match.group(1)) in valid:
            return match.group(0)
        stats["fabricated_arxiv_stripped"] += 1
        return "" if strip else match.group(0)

    new_prose = _ARXIV_INLINE_RE.sub(_sub, prose)
    if strip and stats["fabricated_arxiv_stripped"]:
        new_prose = _tidy(new_prose)
    return new_prose + refs, stats
