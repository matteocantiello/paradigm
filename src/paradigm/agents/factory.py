"""Agent factory for creating agents with composed system prompts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from paradigm.agents.base import Agent
from paradigm.agents.skills import SkillRegistry, compose_system_prompt
from paradigm.config import Config


class RoleTemplate(BaseModel):
    """Parsed role prompt template from YAML."""

    name: str
    description: str = ""
    system_prompt: str
    default_skills: list[str] = Field(default_factory=list)


def _load_role(path: Path) -> RoleTemplate:
    """Load a role template from a YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RoleTemplate(**data)


class AgentFactory:
    """Creates agents with composed system prompts from role + skills."""

    def __init__(
        self,
        config: Config,
        skill_registry: SkillRegistry | None = None,
    ) -> None:
        """Initialize with config and optional skill registry.

        Args:
            config: Paradigm configuration.
            skill_registry: Registry for looking up scientific skills.
                            If None, agents are created without external skills.
        """
        self._config = config
        self._skill_registry = skill_registry
        self._roles: dict[str, RoleTemplate] = {}
        self._prompts_dir = Path(__file__).parent / "prompts"
        self._load_roles()

    def _load_roles(self) -> None:
        """Discover and load all role YAML files from prompts directory."""
        if not self._prompts_dir.is_dir():
            return
        for yaml_file in sorted(self._prompts_dir.glob("*.yaml")):
            try:
                role = _load_role(yaml_file)
                self._roles[role.name] = role
            except Exception:
                continue

    def create_agent(
        self,
        agent_id: str,
        role: str,
        skills: list[str] | None = None,
        skill_mode: str = "default",
        **kwargs: Any,
    ) -> Agent:
        """Create an agent with composed system prompt.

        Args:
            agent_id: Unique agent identifier.
            role: Role name (theorist, analyst, etc.).
            skills: Explicit list of skill names (used when skill_mode="custom").
            skill_mode: How to select skills:
                - "default": Use the role's default_skills from YAML
                - "all": Load all available skills
                - "none": No external skills, just the role prompt
                - "custom": Use the explicit `skills` list
            **kwargs: Additional arguments passed to Agent.__init__.

        Returns:
            Configured Agent instance.

        Raises:
            ValueError: If role is not found.
        """
        role_template = self._roles.get(role)
        if role_template is None:
            available = ", ".join(sorted(self._roles.keys()))
            raise ValueError(f"Unknown role '{role}'. Available roles: {available}")

        # Determine which skills to load
        selected_skills = self._resolve_skills(role_template, skills, skill_mode)

        # Get max_skill_chars from config if available
        max_skill_chars = None
        if hasattr(self._config, "skills") and self._config.skills is not None:
            max_skill_chars = self._config.skills.max_skill_chars

        # Compose system prompt
        system_prompt = compose_system_prompt(
            role_prompt=role_template.system_prompt,
            skills=selected_skills,
            skill_registry=self._skill_registry,
            max_skill_chars=max_skill_chars,
        )

        # Resolve provider + model for this role
        provider, resolved_model = self._config.get_provider_and_model_for_role(role)

        # Build Agent kwargs
        agent_kwargs: dict[str, Any] = {
            "agent_id": agent_id,
            "skill_profile": role,
            "system_prompt": system_prompt,
            "provider": provider,
            "model": kwargs.pop("model", resolved_model),
            "max_tokens": kwargs.pop("max_tokens", self._config.agent.max_tokens),
            "temperature": kwargs.pop("temperature", self._config.agent.temperature),
        }
        agent_kwargs.update(kwargs)

        agent = Agent(**agent_kwargs)
        agent.skills = selected_skills or []
        return agent

    def _resolve_skills(
        self,
        role_template: RoleTemplate,
        skills: list[str] | None,
        skill_mode: str,
    ) -> list[str] | None:
        """Resolve the list of skill names based on mode."""
        if skill_mode == "none" or self._skill_registry is None:
            return None
        if skill_mode == "all":
            return [s.name for s in self._skill_registry.list_skills()]
        if skill_mode == "custom":
            return skills
        # default mode
        return role_template.default_skills or None

    def create_team(
        self,
        roles: list[str],
        skill_mode: str = "default",
        shared_skills: list[str] | None = None,
    ) -> list[Agent]:
        """Create a team of agents with specified roles.

        Args:
            roles: List of role names.
            skill_mode: Skill selection mode for all agents.
            shared_skills: Additional skills applied to all agents
                           (merged with role-specific skills).

        Returns:
            List of configured Agent instances.
        """
        agents = []
        for i, role in enumerate(roles):
            agent_id = f"{role}-{i}"
            extra_skills = shared_skills if skill_mode == "custom" else None
            agent = self.create_agent(
                agent_id=agent_id,
                role=role,
                skills=extra_skills,
                skill_mode=skill_mode,
            )
            agents.append(agent)
        return agents

    def list_roles(self) -> list[str]:
        """List available role template names."""
        return sorted(self._roles.keys())

    def get_role(self, name: str) -> RoleTemplate | None:
        """Get a role template by name."""
        return self._roles.get(name)
