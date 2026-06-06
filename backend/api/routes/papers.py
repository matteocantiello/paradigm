"""REST endpoints for paper browsing and export."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.api.middleware.auth import verify_api_key
from backend.api.models.papers import (
    LiteratureSearchLog,
    OutputList,
    OutputSummary,
    PaperArtifactContent,
    PaperArtifactList,
    PaperDetail,
    PaperList,
    PaperSummary,
)
from backend.api.services.artifact_parser import (
    parse_literature_searches,
    scan_paper_artifacts,
)

router = APIRouter(prefix="/api/v1", tags=["papers"])

# In-memory store for demo papers (populated by demo_runner when core unavailable)
_demo_papers: dict[str, dict[str, Any]] = {}


@router.get(
    "/sessions/{session_id}/outputs",
    response_model=OutputList,
    dependencies=[Depends(verify_api_key)],
)
async def list_outputs(session_id: str, request: Request) -> OutputList:
    """List outputs (papers, figures, code) for a session."""
    manager = request.app.state.session_manager
    state = manager.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    outputs: list[OutputSummary] = []

    # Check if there's a paper associated with this session's thread
    db = request.app.state.database
    if db is not None and state.thread_id:
        thread = db.get_thread(state.thread_id)
        if thread and thread.get("current_draft_id"):
            paper_id = thread["current_draft_id"]
            paper = db.get_paper(paper_id)
            if paper:
                outputs.append(
                    OutputSummary(
                        output_id=paper_id,
                        output_type="paper",
                        title=paper.get("title", ""),
                        created_at=paper.get("created_at"),
                    )
                )
    elif db is None:
        # Demo mode: check in-memory demo papers for this session's cycle
        from backend.api.routes.research import _cycles

        for cycle in _cycles.values():
            if cycle.session_id == session_id and cycle.paper_id:
                paper = _demo_papers.get(cycle.paper_id)
                if paper:
                    outputs.append(
                        OutputSummary(
                            output_id=cycle.paper_id,
                            output_type="paper",
                            title=paper.get("title", ""),
                            created_at=paper.get("created_at"),
                        )
                    )
                break

    return OutputList(items=outputs, total=len(outputs))


@router.get(
    "/sessions/{session_id}/outputs/{output_id}",
    response_model=PaperDetail,
    dependencies=[Depends(verify_api_key)],
)
async def get_output(session_id: str, output_id: str, request: Request) -> PaperDetail:
    """Get a specific output (currently only papers)."""
    db = request.app.state.database
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    paper = db.get_paper(output_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Output not found")

    # Parse JSON fields
    authors = []
    if paper.get("authors"):
        try:
            authors = (
                json.loads(paper["authors"])
                if isinstance(paper["authors"], str)
                else paper["authors"]
            )
        except (json.JSONDecodeError, TypeError):
            pass

    keywords = []
    if paper.get("keywords"):
        try:
            keywords = (
                json.loads(paper["keywords"])
                if isinstance(paper["keywords"], str)
                else paper["keywords"]
            )
        except (json.JSONDecodeError, TypeError):
            pass

    return PaperDetail(
        paper_id=paper["id"],
        title=paper.get("title", ""),
        abstract=paper.get("abstract", ""),
        authors=authors,
        body=paper.get("body", ""),
        status=paper.get("status", ""),
        keywords=keywords,
        citation_count=paper.get("citation_count", 0),
        created_at=paper.get("created_at"),
        published_at=paper.get("published_at"),
    )


@router.get(
    "/papers",
    response_model=PaperList,
    dependencies=[Depends(verify_api_key)],
)
async def list_papers(
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
    request: Request = None,  # type: ignore[assignment]
) -> PaperList:
    """List all papers with optional filtering."""
    db = request.app.state.database
    if db is None:
        # Demo mode: serve from in-memory demo papers
        all_papers = list(_demo_papers.values())
        if status:
            all_papers = [p for p in all_papers if p.get("status") == status]
        else:
            # "All" tab: this system's own papers only, not ingested literature.
            all_papers = [p for p in all_papers if p.get("status") != "external"]
        page = all_papers[offset : offset + limit]
        items = [
            PaperSummary(
                paper_id=p["id"],
                title=p.get("title", ""),
                status=p.get("status", ""),
                abstract=p.get("abstract", "")[:500],
                created_at=p.get("created_at"),
                published_at=p.get("published_at"),
            )
            for p in page
        ]
        return PaperList(items=items, total=len(all_papers), offset=offset, limit=limit)

    rows = db.list_papers(status=status)
    # Ingested literature is stored as papers with status="external" (for citation
    # grounding / dedup). It must NOT appear in the user's own-papers list.
    if status != "external":
        rows = [p for p in rows if p.get("status") != "external"]
    total = len(rows)
    page = rows[offset : offset + limit]

    items = [
        PaperSummary(
            paper_id=p["id"],
            title=p.get("title", ""),
            status=p.get("status", ""),
            abstract=p.get("abstract", "")[:500],
            created_at=p.get("created_at"),
            published_at=p.get("published_at"),
        )
        for p in page
    ]

    return PaperList(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/papers/{paper_id}",
    response_model=PaperDetail,
    dependencies=[Depends(verify_api_key)],
)
async def get_paper(paper_id: str, request: Request) -> PaperDetail:
    """Get full paper details."""
    db = request.app.state.database
    if db is None:
        # Demo mode: serve from in-memory demo papers
        paper = _demo_papers.get(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")
        return PaperDetail(
            paper_id=paper["id"],
            title=paper.get("title", ""),
            abstract=paper.get("abstract", ""),
            authors=paper.get("authors", []),
            body=paper.get("body", ""),
            status=paper.get("status", ""),
            keywords=paper.get("keywords", []),
            citation_count=paper.get("citation_count", 0),
            created_at=paper.get("created_at"),
            published_at=paper.get("published_at"),
        )

    paper = db.get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    authors = []
    if paper.get("authors"):
        try:
            authors = (
                json.loads(paper["authors"])
                if isinstance(paper["authors"], str)
                else paper["authors"]
            )
        except (json.JSONDecodeError, TypeError):
            pass

    keywords = []
    if paper.get("keywords"):
        try:
            keywords = (
                json.loads(paper["keywords"])
                if isinstance(paper["keywords"], str)
                else paper["keywords"]
            )
        except (json.JSONDecodeError, TypeError):
            pass

    return PaperDetail(
        paper_id=paper["id"],
        title=paper.get("title", ""),
        abstract=paper.get("abstract", ""),
        authors=authors,
        body=paper.get("body", ""),
        status=paper.get("status", ""),
        keywords=keywords,
        citation_count=paper.get("citation_count", 0),
        created_at=paper.get("created_at"),
        published_at=paper.get("published_at"),
    )


# ---------------------------------------------------------------------------
# Paper artifact endpoints
# ---------------------------------------------------------------------------

_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\-][a-zA-Z0-9_\-. ]{0,128}$")


def _validate_filename(name: str) -> None:
    """Reject path-traversal or invalid filenames."""
    if ".." in name or "/" in name or "\\" in name or not _SAFE_FILENAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid filename: {name}")


def _paper_dir(request: Request, paper_id: str) -> Path | None:
    """Resolve the on-disk directory for a paper, or None if it doesn't exist."""
    config = request.app.state.config
    papers_dir = config.storage.papers_dir
    d = papers_dir / paper_id
    if d.is_dir():
        return d
    return None


@router.get(
    "/papers/{paper_id}/artifacts",
    response_model=PaperArtifactList,
    dependencies=[Depends(verify_api_key)],
)
async def get_paper_artifacts(paper_id: str, request: Request) -> PaperArtifactList:
    """List available artifacts for a paper."""
    paper_dir = _paper_dir(request, paper_id)
    if paper_dir is not None:
        return scan_paper_artifacts(paper_dir)

    # Demo mode: derive from in-memory data
    demo = _demo_papers.get(paper_id, {})
    return PaperArtifactList(
        paper_id=paper_id,
        has_paper=bool(demo.get("body")),
        has_literature=bool(demo.get("literature")),
        has_reviews=bool(demo.get("reviews")),
        has_transcript=False,
        has_experiments=False,
        has_figures=False,
    )


@router.get(
    "/papers/{paper_id}/literature",
    response_model=LiteratureSearchLog,
    dependencies=[Depends(verify_api_key)],
)
async def get_paper_literature(paper_id: str, request: Request) -> LiteratureSearchLog:
    """Get parsed literature search log for a paper."""
    paper_dir = _paper_dir(request, paper_id)
    if paper_dir is not None:
        lit_file = paper_dir / "literature_searches.md"
        if lit_file.exists():
            return parse_literature_searches(lit_file.read_text())
        raise HTTPException(status_code=404, detail="Literature log not found")

    # Demo mode
    demo = _demo_papers.get(paper_id, {})
    lit = demo.get("literature")
    if lit is not None:
        return lit
    raise HTTPException(status_code=404, detail="Literature log not found")


@router.get(
    "/papers/{paper_id}/reviews",
    response_model=PaperArtifactContent,
    dependencies=[Depends(verify_api_key)],
)
async def get_paper_reviews(paper_id: str, request: Request) -> PaperArtifactContent:
    """Get raw review markdown for a paper."""
    paper_dir = _paper_dir(request, paper_id)
    if paper_dir is not None:
        review_file = paper_dir / "reviews.md"
        if review_file.exists():
            return PaperArtifactContent(
                paper_id=paper_id,
                filename="reviews.md",
                content=review_file.read_text(),
            )
        raise HTTPException(status_code=404, detail="Reviews not found")

    # Demo mode
    demo = _demo_papers.get(paper_id, {})
    reviews = demo.get("reviews")
    if reviews is not None:
        return PaperArtifactContent(
            paper_id=paper_id,
            filename="reviews.md",
            content=reviews,
        )
    raise HTTPException(status_code=404, detail="Reviews not found")


@router.get(
    "/papers/{paper_id}/transcript",
    response_model=PaperArtifactContent,
    dependencies=[Depends(verify_api_key)],
)
async def get_paper_transcript(paper_id: str, request: Request) -> PaperArtifactContent:
    """Get raw transcript markdown for a paper."""
    paper_dir = _paper_dir(request, paper_id)
    if paper_dir is not None:
        transcript_file = paper_dir / "transcript.md"
        if transcript_file.exists():
            return PaperArtifactContent(
                paper_id=paper_id,
                filename="transcript.md",
                content=transcript_file.read_text(),
            )
    raise HTTPException(status_code=404, detail="Transcript not found")


@router.get(
    "/papers/{paper_id}/experiments/{filename}",
    response_model=PaperArtifactContent,
    dependencies=[Depends(verify_api_key)],
)
async def get_paper_experiment(
    paper_id: str, filename: str, request: Request
) -> PaperArtifactContent:
    """Get experiment source code file."""
    _validate_filename(filename)
    paper_dir = _paper_dir(request, paper_id)
    if paper_dir is not None:
        # Check both "experiments" and "code" directories
        for dir_name in ("experiments", "code"):
            exp_file = paper_dir / dir_name / filename
            if exp_file.is_file() and exp_file.resolve().is_relative_to(paper_dir.resolve()):
                return PaperArtifactContent(
                    paper_id=paper_id,
                    filename=filename,
                    content_type="text/x-python" if filename.endswith(".py") else "text/plain",
                    content=exp_file.read_text(),
                )
    raise HTTPException(status_code=404, detail="Experiment file not found")


_FIGURE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}


@router.get(
    "/papers/{paper_id}/figures/{filename}",
    dependencies=[Depends(verify_api_key)],
)
async def get_paper_figure(paper_id: str, filename: str, request: Request) -> FileResponse:
    """Serve a figure image file."""
    _validate_filename(filename)
    paper_dir = _paper_dir(request, paper_id)
    if paper_dir is not None:
        fig_file = paper_dir / "figures" / filename
        if fig_file.is_file() and fig_file.resolve().is_relative_to(paper_dir.resolve()):
            ext = fig_file.suffix.lower()
            media = _FIGURE_MEDIA_TYPES.get(ext, "application/octet-stream")
            return FileResponse(fig_file, media_type=media)
    raise HTTPException(status_code=404, detail="Figure not found")


@router.get(
    "/papers/{paper_id}/pdf",
    dependencies=[Depends(verify_api_key)],
)
async def get_paper_pdf(paper_id: str, request: Request) -> FileResponse:
    """Serve the paper's PDF, compiling on demand if a LaTeX engine is available.

    Returns a pre-built PDF if present; otherwise renders the stored body to LaTeX
    and compiles it (figures resolve from the paper's ``figures/`` dir). If no
    LaTeX engine is installed, responds 503 with a clear message rather than 500.
    """
    paper_dir = _paper_dir(request, paper_id)
    if paper_dir is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    for name in (f"{paper_id}.pdf", "paper.pdf"):
        pdf = paper_dir / name
        if pdf.is_file():
            return FileResponse(pdf, media_type="application/pdf", filename=f"{paper_id}.pdf")

    db = request.app.state.database
    paper = db.get_paper(paper_id) if db is not None else None
    if not paper or not paper.get("body"):
        raise HTTPException(status_code=404, detail="Paper body not available for PDF")

    from paradigm.journal.latex import write_paper_latex

    try:
        result = await asyncio.to_thread(
            write_paper_latex,
            paper_dir,
            paper_id,
            paper["body"],
            title=paper.get("title"),
            compile_to_pdf=True,
        )
    except Exception as e:  # noqa: BLE001 — surface as an HTTP error, never crash the server
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}") from e

    pdf_path = result.get("pdf_path")
    if result.get("pdf") and pdf_path and Path(str(pdf_path)).is_file():
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{paper_id}.pdf")

    raise HTTPException(
        status_code=503,
        detail=(
            "PDF generation requires a LaTeX engine on the server "
            "(install tectonic, xelatex, or pdflatex). "
            f"{result.get('pdf_message', '')}"
        ).strip(),
    )
