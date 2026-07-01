"""Pure-function utilities for parsing paper artifacts from disk."""

from __future__ import annotations

import re
from pathlib import Path

from backend.api.models.papers import (
    LiteratureSearchEntry,
    LiteratureSearchLog,
    LiteratureSearchPaper,
    PaperArtifactList,
)

# Regex for search header: ## Search N — PHASE (agent_id)
_SEARCH_HEADER_RE = re.compile(
    r"^##\s+Search\s+(\d+)\s*[\u2014\u2013-]\s*(\w+)\s*\(([^)]+)\)",
    re.MULTILINE,
)

# Regex for query line: **Query:** "..."
_QUERY_RE = re.compile(r'\*\*Query:\*\*\s*["\u201c]([^"\u201d]+)["\u201d]')

# Regex for paper line: N. **Title** — Authors (Year) [arxiv_id]
_PAPER_LINE_RE = re.compile(
    r"^(\d+)\.\s+\*\*(.+?)\*\*\s*[\u2014\u2013-]\s*(.+?)\s*\((\d{4})\)\s*\[([^\]]+)\]",
    re.MULTILINE,
)


def parse_literature_searches(md_text: str) -> LiteratureSearchLog:
    """Parse a ``literature_searches.md`` file into structured data."""
    searches: list[LiteratureSearchEntry] = []
    seen_arxiv: dict[str, LiteratureSearchPaper] = {}

    # Split by search headers
    headers = list(_SEARCH_HEADER_RE.finditer(md_text))

    for idx, match in enumerate(headers):
        search_num = int(match.group(1))
        phase = match.group(2)
        agent_id = match.group(3)

        # Extract text block for this search
        start = match.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(md_text)
        block = md_text[start:end]

        # Extract query
        query = ""
        query_match = _QUERY_RE.search(block)
        if query_match:
            query = query_match.group(1)

        # Extract papers
        papers: list[LiteratureSearchPaper] = []
        for pm in _PAPER_LINE_RE.finditer(block):
            arxiv_id = pm.group(5).strip()
            paper = LiteratureSearchPaper(
                rank=int(pm.group(1)),
                title=pm.group(2).strip(),
                authors=pm.group(3).strip(),
                year=pm.group(4),
                arxiv_id=arxiv_id,
                arxiv_url=(
                    f"https://arxiv.org/abs/{arxiv_id}"
                    if arxiv_id and not arxiv_id.startswith("ext-")
                    else ""
                ),
            )
            papers.append(paper)
            if arxiv_id not in seen_arxiv:
                seen_arxiv[arxiv_id] = paper

        searches.append(
            LiteratureSearchEntry(
                search_num=search_num,
                phase=phase,
                agent_id=agent_id,
                query=query,
                papers=papers,
            )
        )

    unique = list(seen_arxiv.values())

    return LiteratureSearchLog(
        total_searches=len(searches),
        searches=searches,
        unique_papers=unique,
    )


_ALLOWED_EXPERIMENT_EXT = {".py", ".ipynb", ".r", ".jl", ".sh"}
_ALLOWED_FIGURE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}


def scan_paper_artifacts(paper_dir: Path) -> PaperArtifactList:
    """Check which artifact files/dirs exist for a paper."""
    paper_id = paper_dir.name

    has_paper = (paper_dir / "paper.md").exists() or (paper_dir / f"{paper_id}.md").exists()
    has_literature = (paper_dir / "literature_searches.md").exists()
    has_reviews = (paper_dir / "reviews.md").exists()
    has_transcript = (paper_dir / "transcript.md").exists()

    experiment_files: list[str] = []
    # Check both "experiments" and "code" directories
    experiments_dir = paper_dir / "experiments"
    if not experiments_dir.is_dir():
        experiments_dir = paper_dir / "code"
    if experiments_dir.is_dir():
        experiment_files = sorted(
            f.name
            for f in experiments_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _ALLOWED_EXPERIMENT_EXT
        )

    figure_files: list[str] = []
    figures_dir = paper_dir / "figures"
    if figures_dir.is_dir():
        figure_files = sorted(
            f.name
            for f in figures_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _ALLOWED_FIGURE_EXT
        )

    has_pdf = (paper_dir / f"{paper_id}.pdf").exists() or (paper_dir / "paper.pdf").exists()
    has_digest = (paper_dir / f"{paper_id}-digest.md").exists()

    return PaperArtifactList(
        paper_id=paper_id,
        has_paper=has_paper,
        has_literature=has_literature,
        has_reviews=has_reviews,
        has_transcript=has_transcript,
        has_experiments=len(experiment_files) > 0,
        has_figures=len(figure_files) > 0,
        has_pdf=has_pdf,
        has_digest=has_digest,
        experiment_files=experiment_files,
        figure_files=figure_files,
    )
