"""Paper data models for the writing and review pipeline."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field


class PaperSection(StrEnum):
    """Sections of a research paper."""

    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"


# Which roles draft which sections
SECTION_ASSIGNMENTS: dict[str, list[PaperSection]] = {
    "writer": [PaperSection.ABSTRACT, PaperSection.INTRODUCTION, PaperSection.CONCLUSION],
    "theorist": [PaperSection.METHODS],
    "analyst": [PaperSection.RESULTS],
    "synthesizer": [PaperSection.DISCUSSION],
}


class SectionDraft(BaseModel):
    """A draft of a single paper section."""

    section: PaperSection
    content: str
    author: str  # agent_id that wrote it


class ReviewFeedback(BaseModel):
    """Structured feedback from the editor during internal review."""

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    recommendation: str = "revise"  # "accept" or "revise"


class PaperDraft(BaseModel):
    """A complete paper draft assembled from section drafts."""

    title: str = ""
    sections: dict[PaperSection, SectionDraft] = Field(default_factory=dict)
    assembled_body: str = ""  # Full markdown after writer assembly

    def add_section(self, draft: SectionDraft) -> None:
        """Add or replace a section draft."""
        self.sections[draft.section] = draft

    def is_complete(self) -> bool:
        """Check if all required sections have been drafted."""
        return all(s in self.sections for s in PaperSection)

    def to_markdown(self) -> str:
        """Render the paper as markdown from individual sections.

        If assembled_body is set (from writer assembly), returns that.
        Otherwise, concatenates sections in order.
        """
        if self.assembled_body:
            return self.assembled_body

        parts: list[str] = []
        if self.title:
            parts.append(f"# {self.title}\n")

        for section in PaperSection:
            if section in self.sections:
                heading = section.value.title()
                parts.append(f"## {heading}\n\n{self.sections[section].content}")

        return "\n\n".join(parts)


def strip_agent_scaffolding(text: str) -> str:
    """Remove agent meta-text (planning notes, XML tool calls) from paper content.

    Agent responses often include preamble ("I'll revise the paper..."),
    XML function call blocks, and commentary before the actual paper.
    Papers always start with a markdown heading (# or ##).

    Args:
        text: Raw agent response that should be a paper body.

    Returns:
        Cleaned text starting from the first markdown heading.
    """
    if not text:
        return text

    # Remove XML-style tool call blocks (e.g. <function_calls>...</function_calls>)
    cleaned = re.sub(
        r"<function_calls>.*?</function_calls>",
        "",
        text,
        flags=re.DOTALL,
    )
    # Remove standalone XML tags that might remain
    cleaned = re.sub(r"</?(?:invoke|parameter|function_calls)[^>]*>", "", cleaned)

    # Find the first markdown heading (# with space, not inside code blocks)
    match = re.search(r"^(#{1,2}\s+\S)", cleaned, flags=re.MULTILINE)
    if match:
        cleaned = cleaned[match.start() :]

    return cleaned.strip()


def parse_sections_from_markdown(markdown: str) -> dict[str, str]:
    """Extract sections from markdown text using ## headers.

    Matches headers like '## Abstract', '## Introduction', etc.
    Returns a dict mapping lowercase section name to content.

    Args:
        markdown: Markdown text with ## section headers.

    Returns:
        Dict mapping section name (lowercase) to section content.
    """
    sections: dict[str, str] = {}
    # Split on ## headers, keeping the header text
    pattern = r"^##\s+(.+?)$"
    parts = re.split(pattern, markdown, flags=re.MULTILINE)

    # parts[0] is text before first ##, then alternating header/content
    for i in range(1, len(parts) - 1, 2):
        header = parts[i].strip().lower()
        content = parts[i + 1].strip()
        sections[header] = content

    return sections


def parse_review_feedback(text: str) -> ReviewFeedback:
    """Parse structured review feedback from editor's response.

    Expects markdown with sections: Strengths, Weaknesses, Required Changes, Recommendation.

    Args:
        text: Editor's review text.

    Returns:
        ReviewFeedback with parsed fields.
    """
    sections = parse_sections_from_markdown(text)

    def _extract_list(content: str) -> list[str]:
        """Extract bullet points from markdown list."""
        items = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith(("- ", "* ", "• ")):
                items.append(line.lstrip("-*• ").strip())
            elif line and not line.startswith("#"):
                items.append(line)
        return [item for item in items if item]

    strengths = _extract_list(sections.get("strengths", ""))
    weaknesses = _extract_list(sections.get("weaknesses", ""))
    required_changes = _extract_list(sections.get("required changes", ""))

    # Parse recommendation
    rec_text = sections.get("recommendation", "revise").strip().lower()
    recommendation = "accept" if "accept" in rec_text else "revise"

    return ReviewFeedback(
        strengths=strengths,
        weaknesses=weaknesses,
        required_changes=required_changes,
        recommendation=recommendation,
    )
