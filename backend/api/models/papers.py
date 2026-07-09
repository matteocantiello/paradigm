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
    topics: list[str] = Field(default_factory=list)
    # Quality-ledger judge scores (novelty/rigor/clarity/significance/honesty
    # 1-10 + composite), None until the paper is judged.
    judge_scores: dict[str, object] | None = None
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
    topics: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    review_scores: dict[str, object] | None = None
    judge_scores: dict[str, object] | None = None
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


# --- Paper artifact models ---


class LiteratureSearchPaper(BaseModel):
    """A paper found during a literature search."""

    rank: int
    title: str
    authors: str = ""
    year: str = ""
    arxiv_id: str = ""
    arxiv_url: str = ""


class LiteratureSearchEntry(BaseModel):
    """A single search performed by an agent."""

    search_num: int
    phase: str = ""
    agent_id: str = ""
    query: str = ""
    papers: list[LiteratureSearchPaper] = Field(default_factory=list)


class LiteratureSearchLog(BaseModel):
    """Full literature search log for a paper."""

    thread_id: str = ""
    total_searches: int = 0
    searches: list[LiteratureSearchEntry] = Field(default_factory=list)
    unique_papers: list[LiteratureSearchPaper] = Field(default_factory=list)


class PaperArtifactList(BaseModel):
    """Which artifacts are available for a paper."""

    paper_id: str
    has_paper: bool = False
    has_literature: bool = False
    has_reviews: bool = False
    has_transcript: bool = False
    has_experiments: bool = False
    has_figures: bool = False
    has_pdf: bool = False
    has_digest: bool = False
    experiment_files: list[str] = Field(default_factory=list)
    figure_files: list[str] = Field(default_factory=list)


class PaperArtifactContent(BaseModel):
    """Raw content of a paper artifact."""

    paper_id: str
    filename: str
    content_type: str = "text/markdown"
    content: str = ""
