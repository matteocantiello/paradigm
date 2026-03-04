"""REST endpoints for paper browsing and export."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.middleware.auth import verify_api_key
from backend.api.models.papers import (
    OutputList,
    OutputSummary,
    PaperDetail,
    PaperList,
    PaperSummary,
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

    papers = db.list_papers(status=status, limit=limit)

    items = [
        PaperSummary(
            paper_id=p["id"],
            title=p.get("title", ""),
            status=p.get("status", ""),
            abstract=p.get("abstract", "")[:500],
            created_at=p.get("created_at"),
            published_at=p.get("published_at"),
        )
        for p in papers
    ]

    return PaperList(
        items=items,
        total=len(items),
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
