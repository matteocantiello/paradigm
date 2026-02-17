"""Prompt preprocessing utilities for literature search and debate challenges.

Extracts clean search queries, URLs, and challenge requests from user prompts
to avoid passing raw long-form text directly to the arXiv API.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from paradigm.domains.base import SourceResult
from paradigm.literature.arxiv import ArxivPaper

# Match http/https URLs, stopping at whitespace, quotes, angle brackets, or closing parens
_URL_PATTERN = re.compile(r"https?://[^\s<>\"\\)]+")

# Characters used for markdown formatting that should be stripped
_MARKDOWN_CHARS = re.compile(r"[#*>_`~\[\]]")
# Markdown list markers at start of line
_MARKDOWN_LIST = re.compile(r"^\s*[-+]\s", re.MULTILINE)

# Sentence-ending punctuation
_SENTENCE_END = re.compile(r"[.!?]\s")

# Maximum query length for arXiv API
_MAX_QUERY_LENGTH = 300

# Match [SEARCH: query] markers in agent text
_SEARCH_REQUEST_RE = re.compile(r"\[SEARCH:\s*([^\]]+?)\]", re.IGNORECASE)

# Match [FOLLOW: arxiv_id] markers in agent text (reference chasing)
_FOLLOW_REQUEST_RE = re.compile(r"\[FOLLOW:\s*([^\]]+?)\]", re.IGNORECASE)

# Match [CITED_BY: arxiv_id] markers in agent text (citation-forward search)
_CITED_BY_REQUEST_RE = re.compile(r"\[CITED_BY:\s*([^\]]+?)\]", re.IGNORECASE)

# Match [READ: arxiv_id] markers in agent text (deep reading)
_READ_REQUEST_RE = re.compile(r"\[READ:\s*([^\]]+?)\]", re.IGNORECASE)

# Match [DATA: url] markers in agent text (data staging)
_DATA_REQUEST_RE = re.compile(r"\[DATA:\s*([^\]]+?)\]", re.IGNORECASE)

# Match [CHALLENGE: agent-id: reason] markers in agent text
_CHALLENGE_REQUEST_RE = re.compile(
    r"\[CHALLENGE:\s*([a-z]+-\d+)\s*:\s*([^\]]+?)\]",
    re.IGNORECASE,
)


@dataclass
class ChallengeRequest:
    """A parsed challenge request from an agent's response."""

    challenged_agent_id: str
    reason: str


def extract_urls(text: str) -> list[str]:
    """Extract and deduplicate URLs from text.

    Args:
        text: Input text potentially containing URLs.

    Returns:
        List of unique URLs in order of first appearance.
    """
    urls = _URL_PATTERN.findall(text)
    # Strip trailing punctuation that's likely not part of the URL
    cleaned: list[str] = []
    seen: set[str] = set()
    for url in urls:
        url = url.rstrip(".,;:!?")
        if url not in seen:
            seen.add(url)
            cleaned.append(url)
    return cleaned


def extract_search_query(text: str) -> str | None:
    """Extract a clean search query from a prompt by stripping URLs and markdown.

    Short prompts (<= 300 chars after cleaning) are returned as-is.
    Longer prompts are truncated at a sentence boundary.

    Args:
        text: Raw user prompt text.

    Returns:
        Cleaned search query string, or None if nothing remains after stripping.
    """
    # Remove URLs
    cleaned = _URL_PATTERN.sub("", text)
    # Strip markdown formatting characters
    cleaned = _MARKDOWN_CHARS.sub(" ", cleaned)
    # Strip markdown list markers
    cleaned = _MARKDOWN_LIST.sub(" ", cleaned)
    # Collapse whitespace
    cleaned = " ".join(cleaned.split()).strip()

    if not cleaned:
        return None

    if len(cleaned) <= _MAX_QUERY_LENGTH:
        return cleaned

    # Truncate at sentence boundary within the limit
    truncated = cleaned[:_MAX_QUERY_LENGTH]
    matches = list(_SENTENCE_END.finditer(truncated))
    if matches:
        return truncated[: matches[-1].end()].strip()

    # No sentence boundary found; truncate at last space
    last_space = truncated.rfind(" ")
    if last_space > 0:
        return truncated[:last_space].strip()

    return truncated.strip()


def parse_search_requests(text: str) -> list[str]:
    """Extract [SEARCH: query] markers from agent text.

    Deduplicates queries case-insensitively, strips whitespace,
    and ignores empty queries.

    Args:
        text: Agent response text.

    Returns:
        List of unique search query strings.
    """
    matches = _SEARCH_REQUEST_RE.findall(text)
    seen: set[str] = set()
    queries: list[str] = []
    for match in matches:
        query = match.strip()
        if not query:
            continue
        key = query.lower()
        if key not in seen:
            seen.add(key)
            queries.append(query)
    return queries


def parse_challenge_requests(text: str) -> list[ChallengeRequest]:
    """Extract [CHALLENGE: agent-id: reason] markers from agent text.

    Deduplicates by challenged_agent_id (first occurrence wins),
    strips whitespace, and ignores entries with empty reasons.

    Args:
        text: Agent response text.

    Returns:
        List of unique ChallengeRequest objects.
    """
    matches = _CHALLENGE_REQUEST_RE.findall(text)
    seen: set[str] = set()
    challenges: list[ChallengeRequest] = []
    for agent_id_match, reason_match in matches:
        agent_id = agent_id_match.strip().lower()
        reason = reason_match.strip()
        if not reason:
            continue
        if agent_id not in seen:
            seen.add(agent_id)
            challenges.append(ChallengeRequest(challenged_agent_id=agent_id, reason=reason))
    return challenges


def format_search_results(query: str, papers: list[SourceResult], max_papers: int = 3) -> str:
    """Format search results as compact markdown for agent context.

    Args:
        query: The search query that produced these results.
        papers: List of SourceResult objects.
        max_papers: Maximum number of papers to include.

    Returns:
        Markdown-formatted search results string.
    """
    if not papers:
        return f"### Search: {query}\nNo results found.\n"

    lines = [f"### Search: {query}"]
    for i, paper in enumerate(papers[:max_papers], 1):
        authors_str = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_str += " et al."
        year = paper.date.strftime("%Y") if paper.date else "?"
        abstract_trunc = paper.summary[:200].strip()
        if len(paper.summary) > 200:
            abstract_trunc += "..."
        lines.append(
            f"{i}. **{paper.title}** — {authors_str} ({year}) [{paper.id}]\n   {abstract_trunc}"
        )
    lines.append("")
    return "\n".join(lines)


# Valid arXiv ID patterns:
# New format: YYMM.NNNNN (e.g., 2301.12345)
# Old format: category/YYMMNNN (e.g., astro-ph/0601001)
_ARXIV_ID_RE = re.compile(r"^(\d{4}\.\d{4,5}|[a-z-]+/\d{7})$")


def _normalize_arxiv_id(raw_id: str) -> str:
    """Normalize an arXiv ID by stripping prefixes and version suffixes.

    Returns empty string for invalid inputs (URLs, placeholder text, etc.).

    Args:
        raw_id: Raw arXiv ID (e.g., "arXiv:2301.12345v2").

    Returns:
        Cleaned arXiv ID, or empty string if input is not a valid arXiv ID.
    """
    cleaned = raw_id.strip()

    # Reject URLs immediately
    if cleaned.startswith(("http://", "https://", "www.")):
        return ""

    for prefix in ("arXiv:", "arxiv:", "ArXiv:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    # Strip version suffix
    if "v" in cleaned:
        parts = cleaned.rsplit("v", 1)
        if len(parts) == 2 and parts[1].isdigit():
            cleaned = parts[0]

    cleaned = cleaned.strip()

    # Validate against arXiv ID pattern
    if not _ARXIV_ID_RE.match(cleaned):
        return ""

    return cleaned


def parse_follow_requests(text: str) -> list[str]:
    """Extract [FOLLOW: arxiv_id] markers from agent text.

    Returns deduplicated, normalized arXiv IDs.

    Args:
        text: Agent response text.

    Returns:
        List of unique arXiv ID strings.
    """
    matches = _FOLLOW_REQUEST_RE.findall(text)
    seen: set[str] = set()
    ids: list[str] = []
    for match in matches:
        arxiv_id = _normalize_arxiv_id(match)
        if not arxiv_id:
            continue
        if arxiv_id not in seen:
            seen.add(arxiv_id)
            ids.append(arxiv_id)
    return ids


def parse_cited_by_requests(text: str) -> list[str]:
    """Extract [CITED_BY: arxiv_id] markers from agent text.

    Returns deduplicated, normalized arXiv IDs.

    Args:
        text: Agent response text.

    Returns:
        List of unique arXiv ID strings.
    """
    matches = _CITED_BY_REQUEST_RE.findall(text)
    seen: set[str] = set()
    ids: list[str] = []
    for match in matches:
        arxiv_id = _normalize_arxiv_id(match)
        if not arxiv_id:
            continue
        if arxiv_id not in seen:
            seen.add(arxiv_id)
            ids.append(arxiv_id)
    return ids


def parse_read_requests(text: str) -> list[str]:
    """Extract [READ: arxiv_id] markers from agent text.

    Returns deduplicated, normalized arXiv IDs.

    Args:
        text: Agent response text.

    Returns:
        List of unique arXiv ID strings.
    """
    matches = _READ_REQUEST_RE.findall(text)
    seen: set[str] = set()
    ids: list[str] = []
    for match in matches:
        arxiv_id = _normalize_arxiv_id(match)
        if not arxiv_id:
            continue
        if arxiv_id not in seen:
            seen.add(arxiv_id)
            ids.append(arxiv_id)
    return ids


def parse_data_requests(text: str) -> list[str]:
    """Extract [DATA: url] requests from agent text.

    Deduplicates URLs case-insensitively, strips whitespace,
    and only returns valid http/https URLs.

    Args:
        text: Agent response text.

    Returns:
        List of unique URL strings.
    """
    matches = _DATA_REQUEST_RE.findall(text)
    seen: set[str] = set()
    urls: list[str] = []
    for match in matches:
        url = match.strip()
        if not url:
            continue
        if not url.lower().startswith(("http://", "https://")):
            continue
        key = url.lower()
        if key not in seen:
            seen.add(key)
            urls.append(url)
    return urls


def format_follow_results(arxiv_id: str, papers: list[SourceResult], max_papers: int = 15) -> str:
    """Format reference list as markdown for agent context.

    Args:
        arxiv_id: The source paper whose references were fetched.
        papers: List of SourceResult objects.
        max_papers: Maximum number of papers to include.

    Returns:
        Markdown-formatted reference list.
    """
    if not papers:
        return f"### References of {arxiv_id}\nNo references found.\n"

    lines = [f"### References of {arxiv_id}"]
    for i, paper in enumerate(papers[:max_papers], 1):
        authors_str = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_str += " et al."
        year = paper.date.strftime("%Y") if paper.date else "?"
        abstract_trunc = paper.summary[:200].strip()
        if len(paper.summary) > 200:
            abstract_trunc += "..."
        lines.append(
            f"{i}. **{paper.title}** — {authors_str} ({year}) [{paper.id}]\n   {abstract_trunc}"
        )
    lines.append("")
    return "\n".join(lines)


def format_cited_by_results(arxiv_id: str, papers: list[SourceResult], max_papers: int = 10) -> str:
    """Format citation-forward results as markdown for agent context.

    Args:
        arxiv_id: The source paper whose citations were fetched.
        papers: List of SourceResult objects.
        max_papers: Maximum number of papers to include.

    Returns:
        Markdown-formatted citation list.
    """
    if not papers:
        return f"### Papers citing {arxiv_id}\nNo citations found.\n"

    lines = [f"### Papers citing {arxiv_id}"]
    for i, paper in enumerate(papers[:max_papers], 1):
        authors_str = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_str += " et al."
        year = paper.date.strftime("%Y") if paper.date else "?"
        citation_count = paper.metadata.get("citation_count")
        cite_count = f", {citation_count} citations" if citation_count else ""
        abstract_trunc = paper.summary[:200].strip()
        if len(paper.summary) > 200:
            abstract_trunc += "..."
        lines.append(
            f"{i}. **{paper.title}** — {authors_str} ({year}{cite_count}) "
            f"[{paper.id}]\n   {abstract_trunc}"
        )
    lines.append("")
    return "\n".join(lines)


def format_read_result(arxiv_id: str, title: str, extracted_text: str) -> str:
    """Format deep-read result as markdown for agent context.

    Args:
        arxiv_id: The paper's arXiv ID.
        title: The paper's title.
        extracted_text: Extracted key sections text.

    Returns:
        Markdown-formatted deep-read result.
    """
    return f"### Deep Read: {title} [{arxiv_id}]\n\n{extracted_text}\n"


def make_external_paper(url: str, pdf_text: str) -> ArxivPaper:
    """Create an ArxivPaper from an external URL and its extracted PDF text.

    Uses a deterministic synthetic ID based on the URL hash.

    Args:
        url: Source URL of the PDF.
        pdf_text: Extracted text content from the PDF.

    Returns:
        ArxivPaper with synthetic external ID.
    """
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    arxiv_id = f"ext-{url_hash}"

    # Extract title from first non-empty line
    lines = [line.strip() for line in pdf_text.split("\n") if line.strip()]
    title = lines[0] if lines else "External Paper"

    # Abstract: first 500 chars after title
    remaining_text = "\n".join(lines[1:]) if len(lines) > 1 else ""
    abstract = remaining_text[:500].strip() if remaining_text else ""

    now = datetime.now(UTC)

    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        authors=[],
        categories=[],
        primary_category="",
        published=now,
        updated=now,
        pdf_url=url,
        abs_url=url,
        body=pdf_text,
    )
