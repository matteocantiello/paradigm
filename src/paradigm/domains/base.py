"""Base interfaces and models for domain profiles."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Source provider models
# ---------------------------------------------------------------------------


class SourceResult(BaseModel):
    """Unified search result from any knowledge source."""

    id: str
    source_type: str  # "arxiv", "web", "sec_filing", etc.
    title: str
    authors: list[str] = Field(default_factory=list)
    summary: str = ""
    url: str = ""
    date: datetime | None = None
    content: str | None = None
    metadata: dict = Field(default_factory=dict)


class SourceDocument(BaseModel):
    """Full document content from a source."""

    id: str
    source_type: str
    title: str
    authors: list[str] = Field(default_factory=list)
    full_text: str = ""
    sections: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    metadata: dict = Field(default_factory=dict)


class SourceProvider(ABC):
    """Any searchable knowledge source."""

    name: str

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[SourceResult]:
        """Search for documents matching a query."""
        ...

    @abstractmethod
    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Fetch the full content of a document by ID."""
        ...

    async def get_references(self, source_id: str) -> list[SourceResult]:
        """Get documents referenced by this document (optional)."""
        return []

    async def get_citing(self, source_id: str) -> list[SourceResult]:
        """Get documents that cite this document (optional)."""
        return []


# ---------------------------------------------------------------------------
# Document template models
# ---------------------------------------------------------------------------


class SectionDef(BaseModel):
    """A section in the output document."""

    name: str  # "introduction", "executive_summary", etc.
    display_name: str  # "Introduction", "Executive Summary"
    description: str = ""  # guidance for the writing agent
    assigned_roles: list[str] = Field(default_factory=list)
    required: bool = True


class CriterionDef(BaseModel):
    """A review criterion."""

    name: str  # "novelty", "accuracy", etc.
    display_name: str  # "Novelty", "Accuracy"
    description: str = ""  # what the reviewer should evaluate
    weight: float = 1.0


class DocumentTemplate(BaseModel):
    """Defines the structure of the output document and how it's reviewed."""

    name: str  # "academic_paper", "research_report", etc.
    sections: list[SectionDef] = Field(default_factory=list)
    review_criteria: list[CriterionDef] = Field(default_factory=list)
    citation_style: str = "numbered"
    postprocessors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Source provider config
# ---------------------------------------------------------------------------


class SourceProviderConfig(BaseModel):
    """Configuration for a source provider within a domain."""

    name: str  # "arxiv", "web_search", etc.
    provider_class: str = ""  # dotted import path (for Phase 2)
    enabled: bool = True
    settings: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Domain profile
# ---------------------------------------------------------------------------


class DomainProfile(BaseModel):
    """A complete domain configuration.

    Bundles source providers, document template, agent prompts directory,
    team composition, and domain-specific prompt instructions.
    """

    name: str
    description: str = ""
    source_providers: list[SourceProviderConfig] = Field(default_factory=list)
    document_template: DocumentTemplate = Field(
        default_factory=lambda: DocumentTemplate(name="default")
    )
    prompts_dir: Path = Field(default_factory=lambda: Path("."))
    default_roles: dict[str, list[str]] = Field(default_factory=dict)
    role_search_strategies: dict[str, str] = Field(default_factory=dict)
    role_later_round_reinforcements: dict[str, str] = Field(default_factory=dict)
    literature_instruction: str = ""
    phase_active_roles: dict[str, list[str]] | None = None


# ---------------------------------------------------------------------------
# Conversion helpers — ArxivPaper / SemanticPaper ↔ SourceResult
# ---------------------------------------------------------------------------


def arxiv_paper_to_source_result(paper: object) -> SourceResult:
    """Convert an ArxivPaper to a SourceResult.

    Uses deferred import to avoid circular dependency.

    Args:
        paper: An ArxivPaper instance.

    Returns:
        Equivalent SourceResult.
    """
    from paradigm.literature.arxiv import ArxivPaper

    assert isinstance(paper, ArxivPaper)
    return SourceResult(
        id=paper.arxiv_id,
        source_type="arxiv",
        title=paper.title,
        authors=paper.authors,
        summary=paper.abstract,
        url=paper.abs_url,
        date=paper.published,
        content=paper.body,
        metadata={
            "categories": paper.categories,
            "primary_category": paper.primary_category,
            "pdf_url": paper.pdf_url,
        },
    )


def semantic_paper_to_source_result(paper: object) -> SourceResult:
    """Convert a SemanticPaper to a SourceResult.

    Uses deferred import to avoid circular dependency.

    Args:
        paper: A SemanticPaper instance.

    Returns:
        Equivalent SourceResult.
    """
    from paradigm.literature.semantic_scholar import SemanticPaper

    assert isinstance(paper, SemanticPaper)
    source_id = paper.arxiv_id or paper.paper_id
    date = datetime(paper.year, 1, 1) if paper.year else None
    return SourceResult(
        id=source_id,
        source_type="semantic_scholar",
        title=paper.title,
        authors=paper.authors,
        summary=paper.abstract,
        url=paper.url,
        date=date,
        metadata={
            "paper_id": paper.paper_id,
            "arxiv_id": paper.arxiv_id,
            "year": paper.year,
            "citation_count": paper.citation_count,
        },
    )


def pubmed_paper_to_source_result(paper: object) -> SourceResult:
    """Convert a PubMedPaper to a SourceResult.

    Uses deferred import to avoid circular dependency.

    Args:
        paper: A PubMedPaper instance.

    Returns:
        Equivalent SourceResult.
    """
    from paradigm.literature.pubmed import PubMedPaper

    assert isinstance(paper, PubMedPaper)
    date = datetime(paper.year, 1, 1) if paper.year else None
    return SourceResult(
        id=paper.pmid,
        source_type="pubmed",
        title=paper.title,
        authors=paper.authors,
        summary=paper.abstract,
        url=paper.url,
        date=date,
        metadata={
            "journal": paper.journal,
            "doi": paper.doi,
            "year": paper.year,
        },
    )


def biorxiv_paper_to_source_result(paper: object) -> SourceResult:
    """Convert a BiorxivPaper to a SourceResult.

    Uses deferred import to avoid circular dependency.

    Args:
        paper: A BiorxivPaper instance.

    Returns:
        Equivalent SourceResult.
    """
    from paradigm.literature.biorxiv import BiorxivPaper

    assert isinstance(paper, BiorxivPaper)
    date = None
    if paper.date:
        try:
            date = datetime.strptime(paper.date, "%Y-%m-%d")
        except ValueError:
            pass
    return SourceResult(
        id=paper.doi,
        source_type=paper.server,
        title=paper.title,
        authors=paper.authors,
        summary=paper.abstract,
        url=paper.url,
        date=date,
        metadata={
            "server": paper.server,
            "category": paper.category,
            "doi": paper.doi,
        },
    )


def ads_paper_to_source_result(paper: object) -> SourceResult:
    """Convert an ADSPaper to a SourceResult.

    Uses deferred import to avoid circular dependency.

    Args:
        paper: An ADSPaper instance.

    Returns:
        Equivalent SourceResult.
    """
    from paradigm.literature.nasa_ads import ADSPaper

    assert isinstance(paper, ADSPaper)
    date = datetime(paper.year, 1, 1) if paper.year else None
    return SourceResult(
        id=paper.arxiv_id or paper.bibcode,
        source_type="nasa_ads",
        title=paper.title,
        authors=paper.authors,
        summary=paper.abstract,
        url=paper.url,
        date=date,
        metadata={
            "bibcode": paper.bibcode,
            "arxiv_id": paper.arxiv_id,
            "doi": paper.doi,
            "year": paper.year,
            "citation_count": paper.citation_count,
        },
    )


def source_result_to_arxiv_paper(result: SourceResult) -> object:
    """Convert a SourceResult back to an ArxivPaper for ingestion paths.

    Uses deferred import to avoid circular dependency.

    Args:
        result: A SourceResult instance.

    Returns:
        Equivalent ArxivPaper.
    """
    from paradigm.literature.arxiv import ArxivPaper

    categories = result.metadata.get("categories", [])
    primary_category = result.metadata.get("primary_category", "")
    pdf_url = result.metadata.get("pdf_url", f"http://arxiv.org/pdf/{result.id}")
    published = result.date or datetime(2000, 1, 1)

    return ArxivPaper(
        arxiv_id=result.id,
        title=result.title,
        abstract=result.summary,
        authors=result.authors,
        categories=categories,
        primary_category=primary_category,
        published=published,
        updated=published,
        pdf_url=pdf_url,
        abs_url=result.url or f"http://arxiv.org/abs/{result.id}",
        body=result.content,
    )
