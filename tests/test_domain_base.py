"""Tests for domain profile base interfaces."""

from pathlib import Path

from paradigm.domains.base import (
    CriterionDef,
    DocumentTemplate,
    DomainProfile,
    SectionDef,
    SourceDocument,
    SourceProviderConfig,
    SourceResult,
)


def test_source_result_minimal():
    """SourceResult can be created with just id and source_type."""
    r = SourceResult(id="123", source_type="arxiv", title="Test")
    assert r.id == "123"
    assert r.source_type == "arxiv"
    assert r.authors == []
    assert r.metadata == {}


def test_source_result_synthesizes_id_when_none():
    """A None upstream id (Semantic Scholar/bioRxiv/PubMed/ADS) is synthesized, not rejected."""
    # Previously raised: "1 validation error for SourceResult: id Input should be a valid string"
    r = SourceResult(id=None, source_type="semantic_scholar", title="T", url="http://x/abs/1")
    assert r.id.startswith("src-")
    assert r.id != "src-unknown"


def test_source_result_synthesized_id_is_stable():
    """Same url yields the same synthesized id (so dedup still works)."""
    a = SourceResult(id=None, source_type="biorxiv", title="A", url="http://x/abs/1")
    b = SourceResult(id=None, source_type="biorxiv", title="different", url="http://x/abs/1")
    assert a.id == b.id


def test_source_result_synthesizes_id_from_title_then_unknown():
    """Falls back to title when no url, and to a sentinel when neither is present."""
    from_title = SourceResult(id=None, source_type="pubmed", title="Only a title")
    assert from_title.id.startswith("src-")
    nothing = SourceResult(id="", source_type="nasa_ads", title="")
    assert nothing.id == "src-unknown"


def test_source_document_minimal():
    """SourceDocument can be created with required fields."""
    d = SourceDocument(id="123", source_type="arxiv", title="Test")
    assert d.full_text == ""
    assert d.sections == {}


def test_section_def():
    """SectionDef stores section metadata."""
    s = SectionDef(
        name="introduction",
        display_name="Introduction",
        description="Opening section",
        assigned_roles=["writer"],
    )
    assert s.name == "introduction"
    assert s.required is True


def test_criterion_def():
    """CriterionDef stores review criterion metadata."""
    c = CriterionDef(name="novelty", display_name="Novelty", weight=1.5)
    assert c.weight == 1.5


def test_document_template():
    """DocumentTemplate bundles sections and criteria."""
    t = DocumentTemplate(
        name="academic_paper",
        sections=[
            SectionDef(name="abstract", display_name="Abstract"),
            SectionDef(name="introduction", display_name="Introduction"),
        ],
        review_criteria=[
            CriterionDef(name="novelty", display_name="Novelty"),
        ],
        citation_style="arxiv",
        postprocessors=["latex_math"],
    )
    assert len(t.sections) == 2
    assert len(t.review_criteria) == 1
    assert t.citation_style == "arxiv"


def test_source_provider_config():
    """SourceProviderConfig stores provider settings."""
    c = SourceProviderConfig(name="arxiv", enabled=True)
    assert c.provider_class == ""
    assert c.settings == {}


def test_domain_profile():
    """DomainProfile bundles all domain configuration."""
    profile = DomainProfile(
        name="science",
        description="Academic science research",
        document_template=DocumentTemplate(name="academic_paper"),
        prompts_dir=Path("/some/path"),
        default_roles={"directed": ["theorist", "analyst"]},
        literature_instruction="Search for papers",
    )
    assert profile.name == "science"
    assert profile.default_roles["directed"] == ["theorist", "analyst"]
    assert profile.role_search_strategies == {}
    assert profile.role_later_round_reinforcements == {}


def test_domain_profile_defaults():
    """DomainProfile has sensible defaults for all optional fields."""
    profile = DomainProfile(name="test")
    assert profile.description == ""
    assert profile.source_providers == []
    assert profile.default_roles == {}
    assert profile.literature_instruction == ""
