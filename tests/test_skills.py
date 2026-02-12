"""Tests for skill loader and registry."""

from pathlib import Path
from textwrap import dedent

import pytest

from paradigm.agents.skills import (
    SkillRegistry,
    _parse_frontmatter,
    _strip_frontmatter,
    compose_system_prompt,
)


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create a temporary skill directory with test skills."""
    # Skill 1: hypothesis-generation
    skill1_dir = tmp_path / "hypothesis-generation"
    skill1_dir.mkdir()
    (skill1_dir / "SKILL.md").write_text(
        dedent("""\
        ---
        name: hypothesis-generation
        description: Methods for generating testable hypotheses.
        license: MIT
        metadata:
            skill-author: Test Author
        ---

        # Hypothesis Generation

        This skill covers techniques for generating hypotheses.

        ## When to Use

        Use this when brainstorming research directions.
    """)
    )

    # Skill 2: scientific-writing
    skill2_dir = tmp_path / "scientific-writing"
    skill2_dir.mkdir()
    (skill2_dir / "SKILL.md").write_text(
        dedent("""\
        ---
        name: scientific-writing
        description: Best practices for clear scientific prose.
        ---

        # Scientific Writing

        Write clearly and precisely.
    """)
    )

    # Skill 3: no frontmatter (edge case)
    skill3_dir = tmp_path / "no-frontmatter"
    skill3_dir.mkdir()
    (skill3_dir / "SKILL.md").write_text("# A skill with no frontmatter\n\nJust content.\n")

    return tmp_path


@pytest.fixture
def registry(skill_dir: Path) -> SkillRegistry:
    """Create a SkillRegistry from the test skill directory."""
    return SkillRegistry(skill_dir)


class TestParseFrontmatter:
    def test_valid_frontmatter(self) -> None:
        text = "---\nname: test\ndescription: A test skill.\n---\n\n# Content"
        result = _parse_frontmatter(text)
        assert result["name"] == "test"
        assert result["description"] == "A test skill."

    def test_no_frontmatter(self) -> None:
        text = "# Just a heading\n\nSome content."
        assert _parse_frontmatter(text) == {}

    def test_empty_frontmatter(self) -> None:
        text = "---\n---\n\n# Content"
        assert _parse_frontmatter(text) == {}


class TestStripFrontmatter:
    def test_strips_frontmatter(self) -> None:
        text = "---\nname: test\n---\n\n# Content here"
        result = _strip_frontmatter(text)
        assert result.strip() == "# Content here"

    def test_no_frontmatter_unchanged(self) -> None:
        text = "# Just content"
        assert _strip_frontmatter(text) == text


class TestSkillRegistry:
    def test_discovery(self, registry: SkillRegistry) -> None:
        """Registry should discover all skills with SKILL.md files."""
        assert len(registry) >= 3

    def test_list_skills(self, registry: SkillRegistry) -> None:
        skills = registry.list_skills()
        names = [s.name for s in skills]
        assert "hypothesis-generation" in names
        assert "scientific-writing" in names

    def test_list_skills_sorted(self, registry: SkillRegistry) -> None:
        skills = registry.list_skills()
        names = [s.name for s in skills]
        assert names == sorted(names)

    def test_get_skill(self, registry: SkillRegistry) -> None:
        skill = registry.get_skill("hypothesis-generation")
        assert skill is not None
        assert skill.name == "hypothesis-generation"
        assert skill.description == "Methods for generating testable hypotheses."
        assert skill.license == "MIT"
        assert skill.author == "Test Author"

    def test_get_skill_not_found(self, registry: SkillRegistry) -> None:
        assert registry.get_skill("nonexistent") is None

    def test_get_skill_content(self, registry: SkillRegistry) -> None:
        content = registry.get_skill_content("hypothesis-generation")
        assert content is not None
        assert "# Hypothesis Generation" in content
        assert "---" not in content  # frontmatter stripped

    def test_get_skill_content_not_found(self, registry: SkillRegistry) -> None:
        assert registry.get_skill_content("nonexistent") is None

    def test_search_skills_by_name(self, registry: SkillRegistry) -> None:
        results = registry.search_skills("hypothesis")
        assert len(results) == 1
        assert results[0].name == "hypothesis-generation"

    def test_search_skills_by_description(self, registry: SkillRegistry) -> None:
        results = registry.search_skills("prose")
        assert len(results) == 1
        assert results[0].name == "scientific-writing"

    def test_search_skills_case_insensitive(self, registry: SkillRegistry) -> None:
        results = registry.search_skills("HYPOTHESIS")
        assert len(results) == 1

    def test_search_no_results(self, registry: SkillRegistry) -> None:
        assert registry.search_skills("quantum-xyz-nonsense") == []

    def test_get_skills_by_names(self, registry: SkillRegistry) -> None:
        skills = registry.get_skills_by_names(
            ["hypothesis-generation", "scientific-writing", "nonexistent"]
        )
        assert len(skills) == 2
        names = [s.name for s in skills]
        assert "hypothesis-generation" in names
        assert "scientific-writing" in names

    def test_contains(self, registry: SkillRegistry) -> None:
        assert "hypothesis-generation" in registry
        assert "nonexistent" not in registry

    def test_no_frontmatter_fallback_name(self, registry: SkillRegistry) -> None:
        """Skill without frontmatter should use directory name."""
        skill = registry.get_skill("no-frontmatter")
        assert skill is not None
        assert skill.name == "no-frontmatter"

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Registry should handle empty/missing directory gracefully."""
        registry = SkillRegistry(tmp_path / "nonexistent")
        assert len(registry) == 0
        assert registry.list_skills() == []


class TestComposeSystemPrompt:
    def test_role_only(self) -> None:
        prompt = compose_system_prompt("You are a theorist.")
        assert prompt == "You are a theorist."

    def test_no_skills_list(self) -> None:
        prompt = compose_system_prompt("You are a theorist.", skills=None)
        assert prompt == "You are a theorist."

    def test_no_registry(self) -> None:
        prompt = compose_system_prompt("You are a theorist.", skills=["x"], skill_registry=None)
        assert prompt == "You are a theorist."

    def test_with_skills(self, registry: SkillRegistry) -> None:
        prompt = compose_system_prompt(
            "You are a theorist.",
            skills=["hypothesis-generation"],
            skill_registry=registry,
        )
        assert "You are a theorist." in prompt
        assert "## Scientific Skills Reference" in prompt
        assert "### Skill: hypothesis-generation" in prompt
        assert "# Hypothesis Generation" in prompt

    def test_multiple_skills(self, registry: SkillRegistry) -> None:
        prompt = compose_system_prompt(
            "You are a theorist.",
            skills=["hypothesis-generation", "scientific-writing"],
            skill_registry=registry,
        )
        assert "### Skill: hypothesis-generation" in prompt
        assert "### Skill: scientific-writing" in prompt

    def test_missing_skill_ignored(self, registry: SkillRegistry) -> None:
        prompt = compose_system_prompt(
            "You are a theorist.",
            skills=["nonexistent"],
            skill_registry=registry,
        )
        # No skills found, so just the role prompt
        assert prompt == "You are a theorist."

    def test_max_skill_chars(self, registry: SkillRegistry) -> None:
        prompt = compose_system_prompt(
            "You are a theorist.",
            skills=["hypothesis-generation"],
            skill_registry=registry,
            max_skill_chars=30,
        )
        assert "[... truncated for brevity]" in prompt

    def test_with_real_submodule(self) -> None:
        """Integration test: load real skills from the submodule."""
        skills_dir = Path("vendor/claude-scientific-skills/scientific-skills")
        if not skills_dir.is_dir():
            pytest.skip("Submodule not available")
        registry = SkillRegistry(skills_dir)
        assert len(registry) > 100  # Should have 140+ skills
        prompt = compose_system_prompt(
            "You are a scientist.",
            skills=["astropy"],
            skill_registry=registry,
        )
        assert "### Skill: astropy" in prompt
