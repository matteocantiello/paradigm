"""Paper/output schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PaperSummary(BaseModel):
    """Summary of a paper for list views."""

    paper_id: str
    title: str
    status: str
    abstract: str = ""
    created_at: datetime | None = None
    published_at: datetime | None = None


class PaperDetail(BaseModel):
    """Full paper details."""

    paper_id: str
    title: str
    abstract: str
    authors: list[str] = Field(default_factory=list)
    body: str = ""
    status: str = ""
    keywords: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    review_scores: dict[str, object] | None = None
    citation_count: int = 0
    created_at: datetime | None = None
    published_at: datetime | None = None


class PaperList(BaseModel):
    """Paginated list of papers."""

    items: list[PaperSummary]
    total: int
    offset: int
    limit: int


class OutputSummary(BaseModel):
    """Summary of a session output (paper, figure, code, etc.)."""

    output_id: str
    output_type: str  # "paper", "figure", "code", "search_log", "review"
    title: str = ""
    created_at: datetime | None = None


class OutputList(BaseModel):
    """List of outputs for a session."""

    items: list[OutputSummary]
    total: int
