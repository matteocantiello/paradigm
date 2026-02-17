"""Perplexity API client for citation grounding.

Sends paper paragraphs to Perplexity's sonar-reasoning-pro model to insert
numbered citation markers ([1], [2], ...) and collect arXiv citation URLs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

from paradigm.logging.events import EventLogger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CitedParagraph:
    """Result of citing a single paragraph."""

    original_text: str
    cited_text: str
    citation_urls: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_think_tags(content: str) -> str:
    """Remove <think>...</think> blocks from Perplexity reasoning responses."""
    return re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)


def _split_into_paragraphs(text: str) -> list[str]:
    """Split section text into citable paragraphs.

    Skips headers, images, tables, math display blocks, and very short lines.
    """
    paragraphs: list[str] = []
    current: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()

        # Blank line -> flush current paragraph
        if not stripped:
            if current:
                para = "\n".join(current).strip()
                if len(para) > 80:
                    paragraphs.append(para)
                current = []
            continue

        # Skip markdown headers
        if stripped.startswith("#"):
            if current:
                para = "\n".join(current).strip()
                if len(para) > 80:
                    paragraphs.append(para)
                current = []
            continue

        # Skip image tags
        if stripped.startswith("!["):
            continue

        # Skip table rows
        if stripped.startswith("|") or stripped.startswith("+-"):
            continue

        # Skip display math blocks
        if stripped.startswith("$$"):
            continue

        current.append(line)

    # Flush remaining
    if current:
        para = "\n".join(current).strip()
        if len(para) > 80:
            paragraphs.append(para)

    return paragraphs


def _build_discovery_prompt(topic: str) -> str:
    """Build a prompt to discover foundational arXiv papers on a topic."""
    return (
        f"What are the most important and recent arXiv papers on the following "
        f"research topic?\n\n{topic}\n\n"
        f"List the 10 most relevant papers with their arXiv IDs. "
        f"Focus on foundational works and recent advances. "
        f"For each paper, provide the arXiv ID (e.g., 2301.12345) and a brief "
        f"description of why it is relevant."
    )


def _extract_arxiv_urls(text: str, citations: list[str]) -> list[str]:
    """Extract and deduplicate arXiv URLs from Perplexity response.

    Combines URLs from the citations field and regex-parsed IDs from
    the response text.

    Args:
        text: The response text content.
        citations: The citations list from the API response.

    Returns:
        Deduplicated list of arXiv URLs.
    """
    urls: list[str] = []
    seen: set[str] = set()

    # Primary: extract arXiv URLs from the citations field
    for url in citations:
        if "arxiv.org" in url and url not in seen:
            seen.add(url)
            urls.append(url)

    # Fallback: regex-parse arXiv IDs from response text
    for match in re.finditer(r"(\d{4}\.\d{4,5})", text):
        arxiv_id = match.group(1)
        url = f"https://arxiv.org/abs/{arxiv_id}"
        if url not in seen:
            seen.add(url)
            urls.append(url)

    return urls


def _build_citation_prompt(paragraph: str) -> str:
    """Build the prompt to send to Perplexity for citation grounding."""
    return rf"""You perform scientific literature search on the arXiv.

Your goal is to populate the following text with references from the arXiv only:

<TEXT>
{paragraph}
</TEXT>

You should return the text unaltered, with references added in numerical format, e.g. "[1]", "[2]", "[3]", etc.

For example, if the text is:

"Lorem ipsum dolor sit amet, usu te epicuri epicurei. Vis alii nibh ex, per ex melius euripidis democritum."

You should return:

"Lorem ipsum dolor sit amet, usu te epicuri epicurei. Vis alii nibh ex, per ex melius euripidis democritum [1]."

Only add references where you are sure that the reference is relevant and necessary.

If the paragraph is very short, or if it is not clear what the paragraph is about, do not add any references and just return the paragraph without any references. If you don't easily find any references, just return the paragraph without any references.

Your answer should be the input text populated with references. You should not alter it in any way and not add any other information or explanations. Please follow these rules:

- Ignore tables, figures, and math equations
- Do not add citations inside tables or figures
- Do not wrap the output in <TEXT> tags, just return the text

Your answer should not have the formatting marks <TEXT> and </TEXT>, just the text."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PerplexityClient:
    """Async client for Perplexity citation grounding."""

    PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

    def __init__(
        self,
        api_key: str,
        event_logger: EventLogger | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._event_logger = event_logger
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def discover_papers(self, topic: str) -> list[str]:
        """Query Perplexity to discover foundational arXiv papers on a topic.

        Args:
            topic: Research topic description (e.g. the seed prompt).

        Returns:
            List of arXiv URLs discovered.
        """
        prompt = _build_discovery_prompt(topic)
        payload = {
            "model": "sonar-reasoning-pro",
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a scientific literature expert. Identify the most relevant arXiv papers.",
                },
                {"role": "user", "content": prompt},
            ],
            "search_domain_filter": ["arxiv.org"],
        }

        for attempt in range(self._max_retries):
            try:
                response = await self._client.post(self.PERPLEXITY_URL, json=payload)
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]
                citations = data.get("citations", [])
                cleaned = _strip_think_tags(content)

                return _extract_arxiv_urls(cleaned, citations)
            except Exception as e:
                logger.warning(
                    "Perplexity discover_papers attempt %d failed: %s", attempt + 1, e
                )
                if self._event_logger:
                    self._event_logger.log_error(
                        e, metadata_key="perplexity_discovery", attempt=attempt + 1
                    )

        return []

    async def cite_paragraph(self, paragraph: str) -> CitedParagraph | None:
        """Send a single paragraph to Perplexity for citation grounding.

        Args:
            paragraph: The paragraph text to cite.

        Returns:
            CitedParagraph with cited text and URLs, or None on failure.
        """
        prompt = _build_citation_prompt(paragraph)
        payload = {
            "model": "sonar-reasoning-pro",
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "Be precise and concise. Follow the instructions.",
                },
                {"role": "user", "content": prompt},
            ],
            "search_domain_filter": ["arxiv.org"],
        }

        for attempt in range(self._max_retries):
            try:
                response = await self._client.post(self.PERPLEXITY_URL, json=payload)
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]
                citations = data.get("citations", [])
                cleaned = _strip_think_tags(content)

                return CitedParagraph(
                    original_text=paragraph,
                    cited_text=cleaned,
                    citation_urls=citations,
                )
            except Exception as e:
                logger.warning(
                    "Perplexity cite_paragraph attempt %d failed: %s", attempt + 1, e
                )
                if self._event_logger:
                    self._event_logger.log_error(
                        e, metadata_key="perplexity", attempt=attempt + 1
                    )

        return None

    async def cite_section(
        self, section_text: str, section_name: str = ""
    ) -> tuple[str, list[str]]:
        """Cite an entire section by processing each paragraph independently.

        Args:
            section_text: Full section text.
            section_name: Name of the section (for logging).

        Returns:
            Tuple of (cited_text, all_citation_urls).
        """
        paragraphs = _split_into_paragraphs(section_text)
        if not paragraphs:
            return section_text, []

        all_urls: list[str] = []
        cited_text = section_text

        for para in paragraphs:
            result = await self.cite_paragraph(para)
            if result is None:
                continue

            # Replace original paragraph with cited version
            if result.cited_text and result.cited_text != para:
                cited_text = cited_text.replace(para, result.cited_text, 1)
                all_urls.extend(result.citation_urls)

        return cited_text, all_urls

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> PerplexityClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
