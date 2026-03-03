"""Tests for agent factory."""

import os
from pathlib import Path
from textwrap import dedent

import pytest

from paradigm.agents.factory import AgentFactory, _load_role
from paradigm.agents.skills import SkillRegistry
from paradigm.config import Config


@pytest.fixture(autouse=True)
def _set_api_key():
    """Ensure API key is set for Config validation."""
    original = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "test-api-key"
    yield
    if original:
        os.environ["ANTHROPIC_API_KEY"] = original
    else:
        del os.environ["ANTHROPIC_API_KEY"]


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create test skills."""
    for name, desc in [
        ("hypothesis-generation", "Generate hypotheses"),
        ("scientific-writing", "Write papers"),
        ("citation-management", "Manage citations"),
    ]:
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\nContent for {name}.\n"
        )
    return tmp_path


@pytest.fixture
def registry(skill_dir: Path) -> SkillRegistry:
    return SkillRegistry(skill_dir)


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.fixture
def science_prompts_dir() -> Path:
    """Path to the science domain prompts directory."""
    return Path(__file__).parent.parent / "src/paradigm/domains/science/prompts"


class TestLoadRole:
    def test_load_builtin_role(self) -> None:
        prompts_dir = Path(__file__).parent.parent / "src/paradigm/domains/science/prompts"
        role = _load_role(prompts_dir / "theorist.yaml")
        assert role.name == "theorist"
        assert "theoretical scientist" in role.system_prompt
        assert "hypothesis-generation" in role.default_skills

    def test_load_custom_role(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "custom.yaml"
        yaml_file.write_text(
            dedent("""\
            name: custom
            description: A custom role
            system_prompt: |
              You are custom.
            default_skills:
              - scientific-writing
        """)
        )
        role = _load_role(yaml_file)
        assert role.name == "custom"
        assert role.default_skills == ["scientific-writing"]


class TestAgentFactory:
    def test_list_roles(self, config: Config, science_prompts_dir: Path) -> None:
        factory = AgentFactory(config, prompts_dir=science_prompts_dir)
        roles = factory.list_roles()
        assert "theorist" in roles
        assert "analyst" in roles
        assert "skeptic" in roles
        assert len(roles) == 9

    def test_get_role(self, config: Config, science_prompts_dir: Path) -> None:
        factory = AgentFactory(config, prompts_dir=science_prompts_dir)
        role = factory.get_role("theorist")
        assert role is not None
        assert role.name == "theorist"

    def test_create_agent_no_skills(self, config: Config, science_prompts_dir: Path) -> None:
        factory = AgentFactory(config, prompts_dir=science_prompts_dir)
        agent = factory.create_agent("t1", role="theorist", skill_mode="none")
        assert agent.agent_id == "t1"
        assert agent.skill_profile == "theorist"
        assert "theoretical scientist" in agent.system_prompt
        assert "Scientific Skills Reference" not in agent.system_prompt
        assert agent.skills == []

    def test_create_agent_default_skills(
        self, config: Config, registry: SkillRegistry, science_prompts_dir: Path
    ) -> None:
        factory = AgentFactory(config, skill_registry=registry, prompts_dir=science_prompts_dir)
        agent = factory.create_agent("t1", role="theorist", skill_mode="default")
        assert "hypothesis-generation" in agent.skills
        assert "Scientific Skills Reference" in agent.system_prompt

    def test_create_agent_custom_skills(
        self, config: Config, registry: SkillRegistry, science_prompts_dir: Path
    ) -> None:
        factory = AgentFactory(config, skill_registry=registry, prompts_dir=science_prompts_dir)
        agent = factory.create_agent(
            "a1",
            role="analyst",
            skills=["citation-management"],
            skill_mode="custom",
        )
        assert agent.skills == ["citation-management"]
        assert "### Skill: citation-management" in agent.system_prompt

    def test_create_agent_all_skills(
        self, config: Config, registry: SkillRegistry, science_prompts_dir: Path
    ) -> None:
        factory = AgentFactory(config, skill_registry=registry, prompts_dir=science_prompts_dir)
        agent = factory.create_agent("t1", role="theorist", skill_mode="all")
        assert len(agent.skills) == 3  # All test skills

    def test_create_agent_unknown_role(self, config: Config, science_prompts_dir: Path) -> None:
        factory = AgentFactory(config, prompts_dir=science_prompts_dir)
        with pytest.raises(ValueError, match="Unknown role 'nonexistent'"):
            factory.create_agent("x1", role="nonexistent")

    def test_create_agent_uses_config_model(
        self, config: Config, science_prompts_dir: Path
    ) -> None:
        factory = AgentFactory(config, prompts_dir=science_prompts_dir)
        agent = factory.create_agent("t1", role="theorist", skill_mode="none")
        assert agent.model == config.agent.default_model

    def test_create_agent_override_model(self, config: Config, science_prompts_dir: Path) -> None:
        factory = AgentFactory(config, prompts_dir=science_prompts_dir)
        agent = factory.create_agent(
            "t1", role="theorist", skill_mode="none", model="claude-opus-4-6-20250514"
        )
        assert agent.model == "claude-opus-4-6-20250514"

    def test_create_team(self, config: Config, science_prompts_dir: Path) -> None:
        factory = AgentFactory(config, prompts_dir=science_prompts_dir)
        team = factory.create_team(roles=["theorist", "analyst", "skeptic"], skill_mode="none")
        assert len(team) == 3
        assert team[0].skill_profile == "theorist"
        assert team[1].skill_profile == "analyst"
        assert team[2].skill_profile == "skeptic"

    def test_create_team_ids(self, config: Config, science_prompts_dir: Path) -> None:
        factory = AgentFactory(config, prompts_dir=science_prompts_dir)
        team = factory.create_team(roles=["theorist", "analyst"], skill_mode="none")
        assert team[0].agent_id == "theorist-0"
        assert team[1].agent_id == "analyst-1"

    def test_create_agent_no_registry_ignores_skills(
        self, config: Config, science_prompts_dir: Path
    ) -> None:
        """When no registry is available, default mode should not fail."""
        factory = AgentFactory(config, skill_registry=None, prompts_dir=science_prompts_dir)
        agent = factory.create_agent("t1", role="theorist", skill_mode="default")
        assert agent.skills == []
        assert "Scientific Skills Reference" not in agent.system_prompt

    def test_max_skill_chars_from_config(
        self,
        registry: SkillRegistry,
        science_prompts_dir: Path,
    ) -> None:
        config = Config(skills={"max_skill_chars": 20})
        factory = AgentFactory(config, skill_registry=registry, prompts_dir=science_prompts_dir)
        agent = factory.create_agent("t1", role="theorist", skill_mode="default")
        assert "[... truncated for brevity]" in agent.system_prompt
