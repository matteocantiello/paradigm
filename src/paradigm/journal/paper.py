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


def section_assignments_from_template(
    sections: list,
) -> dict[str, list[str]]:
    """Convert a list of SectionDef objects to a role → section names mapping.

    This adapts the domain profile's DocumentTemplate into the format
    expected by the writing handler.

    Args:
        sections: List of SectionDef from a DocumentTemplate.

    Returns:
        Dict mapping role name to list of section names.
    """
    assignments: dict[str, list[str]] = {}
    for section_def in sections:
        for role in section_def.assigned_roles:
            assignments.setdefault(role, []).append(section_def.name)
    return assignments


class SectionDraft(BaseModel):
    """A draft of a single paper section."""

    section: PaperSection | str
    content: str
    author: str  # agent_id that wrote it


class ReviewFeedback(BaseModel):
    """Structured feedback from the editor during internal review."""

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    recommendation: str = "revise"  # "accept", "revise", or "reject"


class PaperDraft(BaseModel):
    """A complete paper draft assembled from section drafts."""

    title: str = ""
    sections: dict[str, SectionDraft] = Field(default_factory=dict)
    assembled_body: str = ""  # Full markdown after writer assembly
    references: list[dict] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)

    def add_section(self, draft: SectionDraft) -> None:
        """Add or replace a section draft."""
        key = draft.section if isinstance(draft.section, str) else draft.section.value
        self.sections[key] = draft

    def is_complete(self) -> bool:
        """Check if all required sections have been drafted.

        Uses section_order if set (from domain template), otherwise
        falls back to PaperSection enum.
        """
        if self.section_order:
            return all(s in self.sections for s in self.section_order)
        return all(s.value in self.sections for s in PaperSection)

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

        # Use section_order if available, else PaperSection enum order
        order = self.section_order or [s.value for s in PaperSection]
        for section_name in order:
            if section_name in self.sections:
                heading = section_name.replace("_", " ").title()
                parts.append(f"## {heading}\n\n{self.sections[section_name].content}")

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


# ---------------------------------------------------------------------------
# Unicode → LaTeX math post-processing
# ---------------------------------------------------------------------------

# Mapping of Unicode characters to their LaTeX equivalents (without $ delimiters).
# The replacement function wraps each in $...$ only when the character appears
# outside an existing math environment.
_UNICODE_TO_LATEX: dict[str, str] = {
    # Greek lowercase
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    # Greek uppercase
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Λ": r"\Lambda",
    "Σ": r"\Sigma",
    "Ω": r"\Omega",
    # Subscripts
    "₀": "_0",
    "₁": "_1",
    "₂": "_2",
    "₃": "_3",
    "₄": "_4",
    "₅": "_5",
    "₆": "_6",
    "₇": "_7",
    "₈": "_8",
    "₉": "_9",
    # Superscripts
    "⁰": "^0",
    "¹": "^1",
    "²": "^2",
    "³": "^3",
    "⁴": "^4",
    "⁵": "^5",
    "⁶": "^6",
    "⁷": "^7",
    "⁸": "^8",
    "⁹": "^9",
    "⁻": "^-",
    # Math operators and relations
    "≈": r"\approx",
    "≥": r"\geq",
    "≤": r"\leq",
    "≠": r"\neq",
    "∝": r"\propto",
    "∈": r"\in",
    "±": r"\pm",
    "×": r"\times",
    "→": r"\rightarrow",
    "∞": r"\infty",
    # Astronomy / special
    "☉": r"\odot",
    # Script / calligraphic letters
    "ℒ": r"\mathcal{L}",
    "ℳ": r"\mathcal{M}",
    "𝒩": r"\mathcal{N}",
}

# Pre-compile a regex matching any of the Unicode characters in the mapping.
_UNICODE_MATH_RE = re.compile("[" + re.escape("".join(_UNICODE_TO_LATEX.keys())) + "]")


def sanitize_unicode_math(text: str) -> str:
    """Replace Unicode math characters with LaTeX equivalents.

    Splits the text on ``$`` delimiters so that characters already inside
    math environments are left untouched.  Only non-math segments are
    processed.

    Args:
        text: Markdown paper body, possibly containing Unicode math chars.

    Returns:
        Text with Unicode math replaced by ``$\\latex$`` equivalents.
    """
    if not text:
        return text

    # Fast path: nothing to replace
    if not _UNICODE_MATH_RE.search(text):
        return text

    # Split on $ boundaries.  Even-indexed segments are outside math mode,
    # odd-indexed segments are inside math mode.
    parts = text.split("$")
    for i in range(0, len(parts), 2):  # only non-math segments
        parts[i] = _UNICODE_MATH_RE.sub(lambda m: f"${_UNICODE_TO_LATEX[m.group()]}$", parts[i])
    return "$".join(parts)


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
        header = parts[i].strip().rstrip(":").lower()
        content = parts[i + 1].strip()
        sections[header] = content

    return sections


def _parse_h3_sections(markdown: str) -> dict[str, str]:
    """Extract sections from markdown text using ### headers.

    Used as a fallback when ## parsing misses sections because the editor
    used ### headers (e.g. under a ## wrapper heading).

    Args:
        markdown: Markdown text with ### section headers.

    Returns:
        Dict mapping section name (lowercase) to section content.
    """
    sections: dict[str, str] = {}
    pattern = r"^###\s+(.+?)$"
    parts = re.split(pattern, markdown, flags=re.MULTILINE)

    for i in range(1, len(parts) - 1, 2):
        header = parts[i].strip().rstrip(":").lower()
        content = parts[i + 1].strip()
        sections[header] = content

    return sections


def parse_review_feedback(text: str) -> ReviewFeedback:
    """Parse structured review feedback from editor's response.

    Expects markdown with sections: Strengths, Weaknesses, Required Changes, Recommendation.
    Falls back to ### headers and full-text scanning if ## parsing fails.

    Args:
        text: Editor's review text.

    Returns:
        ReviewFeedback with parsed fields.
    """
    sections = parse_sections_from_markdown(text)

    # Fallback: if ## parsing didn't find a recommendation, try ### headers
    if "recommendation" not in sections:
        h3_sections = _parse_h3_sections(text)
        for key, value in h3_sections.items():
            if key not in sections:
                sections[key] = value

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

    # Parse recommendation (reject is strongest signal, then accept, then revise)
    _revise_words = re.compile(r"\brevis(?:e|ion|ions)\b")
    if "recommendation" in sections:
        rec_text = sections["recommendation"].strip().lower()
        if "reject" in rec_text:
            recommendation = "reject"
        elif "accept" in rec_text and not _revise_words.search(rec_text):
            recommendation = "accept"
        elif "accept" in rec_text:
            # "accept with revisions" / "accept pending revision" → revise
            recommendation = "revise"
        else:
            recommendation = "revise"
    else:
        # Full-text fallback: scan body for reject/accept/revise when recommendation
        # section is missing entirely (e.g. due to truncation)
        text_lower = text.lower()
        if "reject" in text_lower and "accept" not in text_lower:
            recommendation = "reject"
        elif "accept" in text_lower and "revise" not in text_lower:
            recommendation = "accept"
        else:
            recommendation = "revise"

    return ReviewFeedback(
        strengths=strengths,
        weaknesses=weaknesses,
        required_changes=required_changes,
        recommendation=recommendation,
    )
