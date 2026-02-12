"""Skill loader, registry, and system prompt composition."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel


class SkillMetadata(BaseModel):
    """Parsed YAML frontmatter from a SKILL.md file."""

    name: str
    description: str = ""
    license: str | None = None
    author: str | None = None
    path: Path  # Path to the SKILL.md file


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Expects content starting with '---' delimiter.
    Returns parsed dict or empty dict if no frontmatter found.
    """
    match = re.match(r"^---\s*\n(.*?\n)---\s*\n", text, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from markdown text."""
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)


class SkillRegistry:
    """Discovers, indexes, and retrieves scientific skills."""

    def __init__(self, skills_dir: Path) -> None:
        """Scan skills_dir for SKILL.md files and build index.

        Args:
            skills_dir: Root directory containing skill subdirectories,
                        each with a SKILL.md file.
        """
        self._skills_dir = Path(skills_dir)
        self._index: dict[str, SkillMetadata] = {}
        self._scan()

    def _scan(self) -> None:
        """Walk skills_dir and index all SKILL.md files."""
        if not self._skills_dir.is_dir():
            return
        for skill_file in sorted(self._skills_dir.rglob("SKILL.md")):
            try:
                text = skill_file.read_text(encoding="utf-8")
                meta = _parse_frontmatter(text)
                # Use directory name as fallback for skill name
                name = meta.get("name", skill_file.parent.name)
                # Extract author from metadata sub-dict if present
                author = None
                if "metadata" in meta and isinstance(meta["metadata"], dict):
                    author = meta["metadata"].get("skill-author")
                skill = SkillMetadata(
                    name=name,
                    description=meta.get("description", ""),
                    license=meta.get("license"),
                    author=author,
                    path=skill_file,
                )
                self._index[name] = skill
            except Exception:
                # Skip malformed skill files
                continue

    def list_skills(self) -> list[SkillMetadata]:
        """List all available skills sorted by name."""
        return sorted(self._index.values(), key=lambda s: s.name)

    def get_skill(self, name: str) -> SkillMetadata | None:
        """Get a skill by name, or None if not found."""
        return self._index.get(name)

    def get_skill_content(self, name: str) -> str | None:
        """Get the full markdown content of a skill (without frontmatter).

        Returns None if the skill is not found.
        """
        skill = self._index.get(name)
        if skill is None:
            return None
        text = skill.path.read_text(encoding="utf-8")
        return _strip_frontmatter(text).strip()

    def search_skills(self, query: str) -> list[SkillMetadata]:
        """Search skills by keyword in name and description (case-insensitive)."""
        query_lower = query.lower()
        results = []
        for skill in self._index.values():
            if query_lower in skill.name.lower() or query_lower in skill.description.lower():
                results.append(skill)
        return sorted(results, key=lambda s: s.name)

    def get_skills_by_names(self, names: list[str]) -> list[SkillMetadata]:
        """Get multiple skills by name. Skips names that don't exist."""
        results = []
        for name in names:
            skill = self._index.get(name)
            if skill is not None:
                results.append(skill)
        return results

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, name: str) -> bool:
        return name in self._index


def compose_system_prompt(
    role_prompt: str,
    skills: list[str] | None = None,
    skill_registry: SkillRegistry | None = None,
    max_skill_chars: int | None = None,
) -> str:
    """Compose a system prompt from a role definition + skill content.

    The role_prompt defines the agent's persona (theorist, skeptic, etc.).
    Skill content is appended as reference material the agent can draw on.

    Args:
        role_prompt: The agent's role/persona prompt.
        skills: List of skill names to include.
        skill_registry: Registry to look up skill content.
        max_skill_chars: If set, truncate each skill's content to this many characters.

    Returns:
        Composed system prompt string.
    """
    if not skills or skill_registry is None:
        return role_prompt

    skill_sections: list[str] = []
    for name in skills:
        content = skill_registry.get_skill_content(name)
        if content is None:
            continue
        if max_skill_chars is not None and len(content) > max_skill_chars:
            content = content[:max_skill_chars] + "\n\n[... truncated for brevity]"
        skill_sections.append(f"### Skill: {name}\n\n{content}")

    if not skill_sections:
        return role_prompt

    skills_block = "\n\n---\n\n".join(skill_sections)
    return (
        f"{role_prompt}\n\n"
        f"---\n\n"
        f"## Scientific Skills Reference\n\n"
        f"The following scientific skills are available to you as reference material.\n"
        f"Draw on this knowledge when relevant to your work.\n\n"
        f"{skills_block}"
    )
