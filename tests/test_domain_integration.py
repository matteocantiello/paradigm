"""Integration tests for the domain profiles system.

Validates that the full profile loading → agent creation → section
assignments → review criteria chain works correctly for the science domain.
"""

import os

import pytest

from paradigm.domains.base import DomainProfile
from paradigm.domains.registry import _clear_registry, get_domain


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


class TestProfileLoading:
    """Test that domain profiles load correctly via config."""

    def test_config_loads_science_profile(self):
        """Config.get_domain_profile() returns the science profile by default."""
        from paradigm.config import Config

        config = Config()
        profile = config.get_domain_profile()
        assert isinstance(profile, DomainProfile)
        assert profile.name == "science"

    def test_config_domain_key_defaults_to_science(self):
        """Config.domain defaults to 'science'."""
        from paradigm.config import Config

        config = Config()
        assert config.domain == "science"

    def test_unknown_domain_raises(self):
        """Config with unknown domain raises ValueError on profile load."""
        from paradigm.config import Config

        config = Config(domain="nonexistent_xyz")
        with pytest.raises(ValueError, match="Could not load domain"):
            config.get_domain_profile()


class TestAgentCreationFromProfile:
    """Test that agents can be created using the profile's prompts directory."""

    def test_factory_loads_all_roles_from_profile(self):
        """AgentFactory loads all 8 roles from the science profile prompts."""
        from paradigm.agents.factory import AgentFactory
        from paradigm.config import Config

        config = Config()
        profile = config.get_domain_profile()
        factory = AgentFactory(config, prompts_dir=profile.prompts_dir)

        roles = factory.list_roles()
        assert len(roles) == 9
        expected = {
            "theorist",
            "analyst",
            "experimentalist",
            "synthesizer",
            "skeptic",
            "writer",
            "editor",
            "reviewer",
            "debate_judge",
        }
        assert set(roles) == expected

    def test_create_agent_from_profile_prompts(self):
        """Agent created from profile prompts has correct system prompt."""
        from paradigm.agents.factory import AgentFactory
        from paradigm.config import Config

        config = Config()
        profile = config.get_domain_profile()
        factory = AgentFactory(config, prompts_dir=profile.prompts_dir)

        agent = factory.create_agent("t1", role="theorist", skill_mode="none")
        assert "theoretical scientist" in agent.system_prompt

    def test_create_team_from_profile_roles(self):
        """Team created using profile's default roles for directed mode."""
        from paradigm.agents.factory import AgentFactory
        from paradigm.config import Config

        config = Config()
        profile = config.get_domain_profile()
        factory = AgentFactory(config, prompts_dir=profile.prompts_dir)

        roles = profile.default_roles.get("directed", [])
        team = factory.create_team(roles, skill_mode="none")
        assert len(team) == len(roles)
        team_roles = [a.skill_profile for a in team]
        assert team_roles == roles


class TestSectionAssignments:
    """Test that template sections produce correct writing assignments."""

    def test_template_to_assignments(self):
        """section_assignments_from_template produces correct role mapping."""
        from paradigm.journal.paper import section_assignments_from_template

        _clear_registry()
        profile = get_domain("science")
        assignments = section_assignments_from_template(profile.document_template.sections)

        assert "writer" in assignments
        assert "abstract" in assignments["writer"]
        assert "introduction" in assignments["writer"]
        assert "conclusion" in assignments["writer"]
        assert assignments["theorist"] == ["methods"]
        assert assignments["analyst"] == ["results"]
        assert assignments["synthesizer"] == ["discussion"]

    def test_all_sections_assigned(self):
        """Every section in the template has at least one assigned role."""
        _clear_registry()
        profile = get_domain("science")
        for section in profile.document_template.sections:
            assert len(section.assigned_roles) > 0, (
                f"Section '{section.name}' has no assigned roles"
            )


class TestReviewCriteria:
    """Test that template review criteria match expected format."""

    def test_criteria_match_score_categories(self):
        """Template criteria produce the same list as SCORE_CATEGORIES."""
        from paradigm.journal.review import SCORE_CATEGORIES, score_categories_from_criteria

        _clear_registry()
        profile = get_domain("science")
        criteria = score_categories_from_criteria(profile.document_template.review_criteria)
        assert criteria == SCORE_CATEGORIES

    def test_criteria_have_descriptions(self):
        """All review criteria have non-empty descriptions."""
        _clear_registry()
        profile = get_domain("science")
        for criterion in profile.document_template.review_criteria:
            assert criterion.description, f"Criterion '{criterion.name}' has no description"


class TestProfileConsistency:
    """Test that all profile components are consistent with each other."""

    def test_prompt_files_match_default_roles(self):
        """All roles in default_roles have corresponding YAML prompt files."""
        _clear_registry()
        profile = get_domain("science")
        yaml_roles = {f.stem for f in profile.prompts_dir.glob("*.yaml")}
        for mode, roles in profile.default_roles.items():
            for role in roles:
                assert role in yaml_roles, f"Role '{role}' in mode '{mode}' has no YAML prompt file"

    def test_section_roles_have_prompts(self):
        """All roles assigned to sections have corresponding prompt files."""
        _clear_registry()
        profile = get_domain("science")
        yaml_roles = {f.stem for f in profile.prompts_dir.glob("*.yaml")}
        for section in profile.document_template.sections:
            for role in section.assigned_roles:
                assert role in yaml_roles, (
                    f"Section '{section.name}' assigns role '{role}' which has no YAML prompt file"
                )

    def test_search_strategy_roles_have_prompts(self):
        """All roles with search strategies have corresponding prompt files."""
        _clear_registry()
        profile = get_domain("science")
        yaml_roles = {f.stem for f in profile.prompts_dir.glob("*.yaml")}
        for role in profile.role_search_strategies:
            assert role in yaml_roles, f"Search strategy for role '{role}' has no YAML prompt file"

    def test_reinforcement_roles_have_prompts(self):
        """All roles with reinforcements have corresponding prompt files."""
        _clear_registry()
        profile = get_domain("science")
        yaml_roles = {f.stem for f in profile.prompts_dir.glob("*.yaml")}
        for role in profile.role_later_round_reinforcements:
            assert role in yaml_roles, f"Reinforcement for role '{role}' has no YAML prompt file"
