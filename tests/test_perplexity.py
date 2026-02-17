"""Tests for the Perplexity citation grounding module."""

from unittest.mock import AsyncMock

import httpx
import pytest

from paradigm.literature.perplexity import (
    CitedParagraph,
    PerplexityClient,
    _build_citation_prompt,
    _build_discovery_prompt,
    _extract_arxiv_urls,
    _split_into_paragraphs,
    _strip_think_tags,
)

# ---------------------------------------------------------------------------
# _strip_think_tags
# ---------------------------------------------------------------------------


class TestStripThinkTags:
    def test_removes_think_block(self):
        text = "<think>some reasoning here</think>\nActual content"
        assert _strip_think_tags(text) == "Actual content"

    def test_removes_multiline_think_block(self):
        text = "<think>\nline 1\nline 2\n</think>\nResult"
        assert _strip_think_tags(text) == "Result"

    def test_no_think_tags(self):
        text = "Plain content with no tags"
        assert _strip_think_tags(text) == text

    def test_multiple_think_blocks(self):
        text = "<think>first</think>Middle<think>second</think>End"
        assert _strip_think_tags(text) == "MiddleEnd"

    def test_empty_string(self):
        assert _strip_think_tags("") == ""


# ---------------------------------------------------------------------------
# _split_into_paragraphs
# ---------------------------------------------------------------------------


class TestSplitIntoParagraphs:
    def test_basic_paragraphs(self):
        text = (
            "This is a long first paragraph that is definitely over eighty characters "
            "because we need it to pass the minimum length check for citable paragraphs.\n\n"
            "This is a long second paragraph that is also over eighty characters "
            "because we need it to pass the minimum length check for citable paragraphs."
        )
        paras = _split_into_paragraphs(text)
        assert len(paras) == 2

    def test_skips_headers(self):
        text = (
            "## Introduction\n\n"
            "This is a long paragraph under the header that should be included because "
            "it exceeds the eighty character minimum threshold.\n\n"
            "### Sub-header\n\n"
            "This is another paragraph under a sub-header that should also be included "
            "because it is long enough to pass the check."
        )
        paras = _split_into_paragraphs(text)
        assert len(paras) == 2
        for p in paras:
            assert not p.startswith("#")

    def test_skips_images(self):
        text = (
            "This is a long paragraph before the image that is over eighty characters "
            "minimum threshold for inclusion in citation processing.\n\n"
            "![Figure 1](figures/test.png)\n\n"
            "This is a long paragraph after the image that is also over eighty characters "
            "minimum threshold for inclusion in citation processing."
        )
        paras = _split_into_paragraphs(text)
        assert len(paras) == 2
        for p in paras:
            assert "![" not in p

    def test_skips_table_rows(self):
        text = (
            "This is a long paragraph before the table that is over eighty characters "
            "minimum threshold for inclusion in citation processing.\n\n"
            "| Column 1 | Column 2 |\n"
            "|----------|----------|\n"
            "| Data 1   | Data 2   |\n\n"
            "This is a long paragraph after the table that is also over eighty characters "
            "minimum threshold for inclusion in citation processing."
        )
        paras = _split_into_paragraphs(text)
        assert len(paras) == 2
        for p in paras:
            assert "|" not in p

    def test_skips_display_math(self):
        text = (
            "This is a long paragraph before the math block that is over eighty characters "
            "minimum threshold for inclusion in citation processing.\n\n"
            "$$E = mc^2$$\n\n"
            "This is a long paragraph after the math block that is also over eighty characters "
            "minimum threshold for inclusion in citation processing."
        )
        paras = _split_into_paragraphs(text)
        assert len(paras) == 2
        for p in paras:
            assert "$$" not in p

    def test_skips_short_lines(self):
        text = "Short line.\n\nAnother short one."
        paras = _split_into_paragraphs(text)
        assert len(paras) == 0

    def test_empty_text(self):
        assert _split_into_paragraphs("") == []


# ---------------------------------------------------------------------------
# _build_citation_prompt
# ---------------------------------------------------------------------------


class TestBuildCitationPrompt:
    def test_contains_paragraph(self):
        para = "Test paragraph about stellar convection."
        prompt = _build_citation_prompt(para)
        assert para in prompt

    def test_contains_instructions(self):
        prompt = _build_citation_prompt("Some text here.")
        assert "arXiv" in prompt
        assert "[1]" in prompt
        assert "numerical format" in prompt

    def test_no_text_tags_in_instructions(self):
        prompt = _build_citation_prompt("Some text here.")
        assert "should not have the formatting marks" in prompt


# ---------------------------------------------------------------------------
# PerplexityClient.cite_paragraph (mocked)
# ---------------------------------------------------------------------------


class TestCiteParagraphMock:
    @pytest.mark.asyncio
    async def test_successful_citation(self):
        """Mock a successful Perplexity API response."""
        mock_request = httpx.Request("POST", "https://api.perplexity.ai/chat/completions")
        mock_response = httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Stellar convection is important [1]."}}],
                "citations": ["https://arxiv.org/abs/2301.12345"],
            },
            request=mock_request,
        )

        client = PerplexityClient(api_key="test-key")
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.cite_paragraph("Stellar convection is important.")
        assert result is not None
        assert isinstance(result, CitedParagraph)
        assert "[1]" in result.cited_text
        assert len(result.citation_urls) == 1
        assert "arxiv.org" in result.citation_urls[0]

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry logic when first attempt fails."""
        mock_request = httpx.Request("POST", "https://api.perplexity.ai/chat/completions")
        success_response = httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Text [1]."}}],
                "citations": ["https://arxiv.org/abs/2301.00001"],
            },
            request=mock_request,
        )

        client = PerplexityClient(api_key="test-key", max_retries=2)
        client._client = AsyncMock()
        client._client.post = AsyncMock(
            side_effect=[Exception("transient failure"), success_response]
        )

        result = await client.cite_paragraph("Some paragraph text.")
        assert result is not None
        assert "[1]" in result.cited_text

    @pytest.mark.asyncio
    async def test_all_retries_fail(self):
        """Returns None when all retries are exhausted."""
        client = PerplexityClient(api_key="test-key", max_retries=2)
        client._client = AsyncMock()
        client._client.post = AsyncMock(side_effect=Exception("API error"))

        result = await client.cite_paragraph("Text that fails.")
        assert result is None


# ---------------------------------------------------------------------------
# PerplexityClient.cite_section (mocked)
# ---------------------------------------------------------------------------


class TestCiteSectionMock:
    @pytest.mark.asyncio
    async def test_cite_section_multiple_paragraphs(self):
        """Process a section with multiple paragraphs."""
        para1 = (
            "First paragraph about stellar convection that is definitely over eighty "
            "characters because we need it to pass the minimum length check."
        )
        para2 = (
            "Second paragraph about nuclear burning that is also over eighty characters "
            "so it will be processed by the citation grounding pipeline."
        )
        section_text = f"{para1}\n\n{para2}"

        # Mock cite_paragraph to return cited versions
        async def mock_cite(paragraph):
            return CitedParagraph(
                original_text=paragraph,
                cited_text=paragraph + " [1]",
                citation_urls=["https://arxiv.org/abs/2301.99999"],
            )

        client = PerplexityClient(api_key="test-key")
        client.cite_paragraph = AsyncMock(side_effect=mock_cite)

        cited_text, urls = await client.cite_section(section_text, "introduction")

        assert "[1]" in cited_text
        assert len(urls) == 2  # One URL per paragraph


# ---------------------------------------------------------------------------
# _build_discovery_prompt
# ---------------------------------------------------------------------------


class TestBuildDiscoveryPrompt:
    def test_contains_topic(self):
        prompt = _build_discovery_prompt("stellar convection in massive stars")
        assert "stellar convection in massive stars" in prompt

    def test_contains_arxiv_instruction(self):
        prompt = _build_discovery_prompt("any topic")
        assert "arXiv" in prompt


# ---------------------------------------------------------------------------
# _extract_arxiv_urls
# ---------------------------------------------------------------------------


class TestExtractArxivUrls:
    def test_extracts_from_citations(self):
        citations = [
            "https://arxiv.org/abs/2301.12345",
            "https://arxiv.org/abs/2302.67890",
        ]
        urls = _extract_arxiv_urls("no IDs here", citations)
        assert len(urls) == 2
        assert "https://arxiv.org/abs/2301.12345" in urls

    def test_extracts_from_text_fallback(self):
        text = "The paper 2301.12345 discusses this topic."
        urls = _extract_arxiv_urls(text, [])
        assert len(urls) == 1
        assert "https://arxiv.org/abs/2301.12345" in urls

    def test_dedup_across_citations_and_text(self):
        citations = ["https://arxiv.org/abs/2301.12345"]
        text = "See paper 2301.12345 for details."
        urls = _extract_arxiv_urls(text, citations)
        assert len(urls) == 1

    def test_empty_inputs(self):
        urls = _extract_arxiv_urls("", [])
        assert urls == []

    def test_non_arxiv_citations_ignored(self):
        citations = [
            "https://arxiv.org/abs/2301.12345",
            "https://example.com/paper",
        ]
        urls = _extract_arxiv_urls("", citations)
        assert len(urls) == 1


# ---------------------------------------------------------------------------
# PerplexityClient.discover_papers (mocked)
# ---------------------------------------------------------------------------


class TestDiscoverPapersMock:
    @pytest.mark.asyncio
    async def test_discover_papers_from_citations(self):
        """Mock a successful Perplexity API response with citations."""
        mock_request = httpx.Request("POST", "https://api.perplexity.ai/chat/completions")
        mock_response = httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Here are the most relevant papers on stellar convection."
                        }
                    }
                ],
                "citations": [
                    "https://arxiv.org/abs/2301.12345",
                    "https://arxiv.org/abs/2302.67890",
                ],
            },
            request=mock_request,
        )

        client = PerplexityClient(api_key="test-key")
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        urls = await client.discover_papers("stellar convection")
        assert len(urls) == 2
        assert "https://arxiv.org/abs/2301.12345" in urls
        assert "https://arxiv.org/abs/2302.67890" in urls

    @pytest.mark.asyncio
    async def test_discover_papers_no_citations(self):
        """Returns empty list when no citations in response."""
        mock_request = httpx.Request("POST", "https://api.perplexity.ai/chat/completions")
        mock_response = httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "I could not find any papers."}}],
                "citations": [],
            },
            request=mock_request,
        )

        client = PerplexityClient(api_key="test-key")
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        urls = await client.discover_papers("obscure topic")
        assert urls == []

    @pytest.mark.asyncio
    async def test_discover_papers_all_retries_fail(self):
        """Returns empty list when all retries fail."""
        client = PerplexityClient(api_key="test-key", max_retries=2)
        client._client = AsyncMock()
        client._client.post = AsyncMock(side_effect=Exception("API error"))

        urls = await client.discover_papers("any topic")
        assert urls == []

    @pytest.mark.asyncio
    async def test_discover_papers_strips_think_tags(self):
        """Think tags are removed before extracting IDs from text."""
        mock_request = httpx.Request("POST", "https://api.perplexity.ai/chat/completions")
        mock_response = httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "<think>reasoning about 9999.00000</think>Paper 2301.12345 is key."
                        }
                    }
                ],
                "citations": [],
            },
            request=mock_request,
        )

        client = PerplexityClient(api_key="test-key")
        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        urls = await client.discover_papers("topic")
        assert "https://arxiv.org/abs/2301.12345" in urls
        # The ID inside <think> tags should be stripped
        assert "https://arxiv.org/abs/9999.00000" not in urls
