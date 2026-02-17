"""Tests for finance domain profile."""

from paradigm.domains.registry import _clear_registry, get_domain


def test_finance_profile_loads():
    """Finance profile can be loaded via the registry."""
    _clear_registry()
    profile = get_domain("finance")
    assert profile.name == "finance"


def test_finance_profile_has_template():
    """Finance profile has a research report template."""
    _clear_registry()
    profile = get_domain("finance")
    assert profile.document_template.name == "research_report"


def test_finance_template_sections():
    """Finance template has the 8 research report sections."""
    _clear_registry()
    profile = get_domain("finance")
    section_names = [s.name for s in profile.document_template.sections]
    assert section_names == [
        "executive_summary",
        "background",
        "literature_review",
        "methodology",
        "results",
        "analysis",
        "risk_assessment",
        "recommendations",
    ]


def test_finance_template_review_criteria():
    """Finance template has rigor/novelty/relevance/actionability/risk_awareness criteria."""
    _clear_registry()
    profile = get_domain("finance")
    criteria_names = [c.name for c in profile.document_template.review_criteria]
    assert criteria_names == ["rigor", "novelty", "relevance", "actionability", "risk_awareness"]


def test_finance_profile_has_mode_roles():
    """Finance profile defines team roles for each operating mode."""
    _clear_registry()
    profile = get_domain("finance")
    assert "directed" in profile.default_roles
    assert "explore" in profile.default_roles
    assert "empirical" in profile.default_roles
    assert "strategy" in profile.default_roles
    assert "policy" in profile.default_roles
    assert "economist" in profile.default_roles["directed"]
    assert "quant" in profile.default_roles["directed"]


def test_finance_profile_prompts_dir():
    """Finance profile points to a valid prompts directory."""
    _clear_registry()
    profile = get_domain("finance")
    assert profile.prompts_dir.is_dir()
    yaml_files = list(profile.prompts_dir.glob("*.yaml"))
    assert len(yaml_files) == 8


def test_finance_prompt_files_match_roles():
    """All roles referenced in mode team configs have a YAML prompt file."""
    _clear_registry()
    profile = get_domain("finance")
    yaml_roles = {f.stem for f in profile.prompts_dir.glob("*.yaml")}
    all_roles: set[str] = set()
    for roles in profile.default_roles.values():
        all_roles.update(roles)
    for role in all_roles:
        assert role in yaml_roles, f"Role '{role}' has no YAML prompt file"


def test_finance_profile_has_search_strategies():
    """Finance profile defines role-specific search strategies."""
    _clear_registry()
    profile = get_domain("finance")
    assert "economist" in profile.role_search_strategies
    assert "risk_analyst" in profile.role_search_strategies
    assert "quant" in profile.role_search_strategies


def test_finance_profile_has_reinforcements():
    """Finance profile defines role-specific later round reinforcements."""
    _clear_registry()
    profile = get_domain("finance")
    assert "risk_analyst" in profile.role_later_round_reinforcements
    assert "economist" in profile.role_later_round_reinforcements


def test_finance_profile_has_literature_instruction():
    """Finance profile has literature search instruction text."""
    _clear_registry()
    profile = get_domain("finance")
    assert "[SEARCH:" in profile.literature_instruction
    assert "[FOLLOW:" in profile.literature_instruction


def test_finance_profile_has_phase_active_roles():
    """Finance profile defines phase-active role mapping."""
    _clear_registry()
    profile = get_domain("finance")
    assert profile.phase_active_roles is not None
    assert "ideation" in profile.phase_active_roles
    assert "planning" in profile.phase_active_roles
    assert "economist" in profile.phase_active_roles["ideation"]
    # Writer and editor should NOT be in ideation/planning
    assert "writer" not in profile.phase_active_roles["ideation"]
    assert "editor" not in profile.phase_active_roles["planning"]


def test_finance_source_providers():
    """Finance profile has SSRN, SEC EDGAR, FRED, Semantic Scholar, and internal corpus providers."""
    _clear_registry()
    profile = get_domain("finance")
    provider_names = [p.name for p in profile.source_providers]
    assert "ssrn" in provider_names
    assert "sec_edgar" in provider_names
    assert "fred" in provider_names
    assert "semantic_scholar" in provider_names
    assert "internal_corpus" in provider_names


def test_finance_explore_mode_has_no_writer():
    """Explore mode should not include writer/editor/experimentalist."""
    _clear_registry()
    profile = get_domain("finance")
    explore_roles = profile.default_roles["explore"]
    assert "writer" not in explore_roles
    assert "editor" not in explore_roles
    assert "experimentalist" not in explore_roles


def test_finance_directed_mode_has_all_roles():
    """Directed mode includes all 8 roles."""
    _clear_registry()
    profile = get_domain("finance")
    directed_roles = profile.default_roles["directed"]
    assert len(directed_roles) == 8
