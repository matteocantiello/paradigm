"""Tests for PubMed NCBI E-utilities client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from paradigm.domains.base import pubmed_paper_to_source_result
from paradigm.literature.pubmed import (
    PubMedClient,
    PubMedPaper,
    _parse_pubmed_xml,
)

# --- Sample XML ---

SAMPLE_XML = """<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2023//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_230101.dtd">
<PubmedArticleSet>
<PubmedArticle>
    <MedlineCitation>
        <PMID>12345678</PMID>
        <Article>
            <Journal>
                <JournalIssue>
                    <PubDate><Year>2023</Year></PubDate>
                </JournalIssue>
                <Title>Nature Astronomy</Title>
            </Journal>
            <ArticleTitle>Stellar Convection in Massive Stars</ArticleTitle>
            <Abstract>
                <AbstractText>We study convective processes in massive stellar interiors.</AbstractText>
            </Abstract>
            <AuthorList>
                <Author><ForeName>Alice</ForeName><LastName>Smith</LastName></Author>
                <Author><ForeName>Bob</ForeName><LastName>Jones</LastName></Author>
            </AuthorList>
            <ELocationID EIdType="doi">10.1038/s41550-023-01234-5</ELocationID>
        </Article>
    </MedlineCitation>
</PubmedArticle>
<PubmedArticle>
    <MedlineCitation>
        <PMID>87654321</PMID>
        <Article>
            <Journal>
                <JournalIssue>
                    <PubDate><Year>2022</Year></PubDate>
                </JournalIssue>
                <Title>The Astrophysical Journal</Title>
            </Journal>
            <ArticleTitle>Wave Transport in Stellar Interiors</ArticleTitle>
            <Abstract>
                <AbstractText>Analysis of internal gravity waves.</AbstractText>
            </Abstract>
            <AuthorList>
                <Author><ForeName>Carol</ForeName><LastName>Davis</LastName></Author>
            </AuthorList>
        </Article>
    </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""


# --- XML parsing tests ---


class TestParsePubmedXml:
    def test_parses_multiple_articles(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        assert len(papers) == 2

    def test_first_paper_fields(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        p = papers[0]
        assert p.pmid == "12345678"
        assert p.title == "Stellar Convection in Massive Stars"
        assert p.authors == ["Alice Smith", "Bob Jones"]
        assert p.abstract == "We study convective processes in massive stellar interiors."
        assert p.journal == "Nature Astronomy"
        assert p.year == 2023
        assert p.doi == "10.1038/s41550-023-01234-5"
        assert p.url == "https://pubmed.ncbi.nlm.nih.gov/12345678"

    def test_second_paper_no_doi(self):
        papers = _parse_pubmed_xml(SAMPLE_XML)
        p = papers[1]
        assert p.pmid == "87654321"
        assert p.doi is None

    def test_invalid_xml_returns_empty(self):
        papers = _parse_pubmed_xml("not xml at all")
        assert papers == []

    def test_empty_xml_returns_empty(self):
        papers = _parse_pubmed_xml('<?xml version="1.0" ?><PubmedArticleSet></PubmedArticleSet>')
        assert papers == []

    def test_missing_title_skips_article(self):
        xml = """<?xml version="1.0" ?>
        <PubmedArticleSet>
        <PubmedArticle>
            <MedlineCitation>
                <PMID>99999</PMID>
                <Article>
                    <Journal><JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue></Journal>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        </PubmedArticleSet>"""
        papers = _parse_pubmed_xml(xml)
        assert papers == []


# --- PubMedPaper dataclass tests ---


class TestPubMedPaper:
    def test_defaults(self):
        paper = PubMedPaper(pmid="123", title="Test")
        assert paper.authors == []
        assert paper.abstract == ""
        assert paper.journal == ""
        assert paper.year is None
        assert paper.doi is None
        assert paper.url == ""

    def test_full_construction(self):
        paper = PubMedPaper(
            pmid="123",
            title="Test Paper",
            authors=["A", "B"],
            abstract="Abstract text",
            journal="Nature",
            year=2023,
            doi="10.1234/test",
            url="https://pubmed.ncbi.nlm.nih.gov/123",
        )
        assert paper.pmid == "123"
        assert paper.year == 2023


# --- Conversion helper tests ---


class TestPubmedPaperToSourceResult:
    def test_converts_correctly(self):
        paper = PubMedPaper(
            pmid="12345678",
            title="Test Paper",
            authors=["Alice Smith", "Bob Jones"],
            abstract="A test abstract.",
            journal="Nature",
            year=2023,
            doi="10.1038/test",
            url="https://pubmed.ncbi.nlm.nih.gov/12345678",
        )
        result = pubmed_paper_to_source_result(paper)
        assert result.id == "12345678"
        assert result.source_type == "pubmed"
        assert result.title == "Test Paper"
        assert result.authors == ["Alice Smith", "Bob Jones"]
        assert result.summary == "A test abstract."
        assert result.metadata["journal"] == "Nature"
        assert result.metadata["doi"] == "10.1038/test"
        assert result.date is not None
        assert result.date.year == 2023

    def test_none_year(self):
        paper = PubMedPaper(pmid="1", title="No Year", year=None)
        result = pubmed_paper_to_source_result(paper)
        assert result.date is None


# --- PubMedClient tests ---


class TestPubMedClient:
    @pytest.mark.asyncio
    async def test_search_returns_papers(self):
        client = PubMedClient(rate_limit=0.0)
        # Mock esearch (returns JSON)
        client._get_json = AsyncMock(
            return_value={"esearchresult": {"idlist": ["12345678", "87654321"]}}
        )
        # Mock efetch (returns XML)
        client._get_text = AsyncMock(return_value=SAMPLE_XML)

        papers = await client.search("stellar convection")
        assert len(papers) == 2
        assert papers[0].pmid == "12345678"
        await client.close()

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        client = PubMedClient(rate_limit=0.0)
        client._get_json = AsyncMock(return_value={"esearchresult": {"idlist": []}})

        papers = await client.search("nonexistent topic xyz")
        assert papers == []
        await client.close()

    @pytest.mark.asyncio
    async def test_search_handles_api_error(self):
        client = PubMedClient(rate_limit=0.0)
        client._get_json = AsyncMock(return_value=None)

        papers = await client.search("test query")
        assert papers == []
        await client.close()

    @pytest.mark.asyncio
    async def test_get_paper(self):
        client = PubMedClient(rate_limit=0.0)
        client._get_text = AsyncMock(return_value=SAMPLE_XML)

        paper = await client.get_paper("12345678")
        assert paper is not None
        assert paper.pmid == "12345678"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_paper_not_found(self):
        client = PubMedClient(rate_limit=0.0)
        client._get_text = AsyncMock(
            return_value='<?xml version="1.0" ?><PubmedArticleSet></PubmedArticleSet>'
        )

        paper = await client.get_paper("99999")
        assert paper is None
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with PubMedClient(rate_limit=0.0) as client:
            assert client is not None

    @pytest.mark.asyncio
    async def test_api_key_passed(self):
        client = PubMedClient(api_key="test-key", rate_limit=0.0)
        assert client._api_key == "test-key"
        await client.close()
