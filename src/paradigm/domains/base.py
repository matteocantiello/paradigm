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
    document_template: DocumentTemplate = Field(default_factory=lambda: DocumentTemplate(name="default"))
    prompts_dir: Path = Field(default_factory=lambda: Path("."))
    default_roles: dict[str, list[str]] = Field(default_factory=dict)
    role_search_strategies: dict[str, str] = Field(default_factory=dict)
    role_later_round_reinforcements: dict[str, str] = Field(default_factory=dict)
    literature_instruction: str = ""
