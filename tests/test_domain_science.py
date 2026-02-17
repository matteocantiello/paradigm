"""Tests for science domain profile."""

from paradigm.domains.registry import _clear_registry, get_domain


def test_science_profile_loads():
    """Science profile can be loaded via the registry."""
    _clear_registry()
    profile = get_domain("science")
    assert profile.name == "science"


def test_science_profile_has_template():
    """Science profile has an academic paper template."""
    _clear_registry()
    profile = get_domain("science")
    assert profile.document_template.name == "academic_paper"


def test_science_template_sections():
    """Science template has the 6 standard academic paper sections."""
    _clear_registry()
    profile = get_domain("science")
    section_names = [s.name for s in profile.document_template.sections]
    assert section_names == [
        "abstract",
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
    ]


def test_science_template_review_criteria():
    """Science template has novelty/rigor/clarity/significance criteria."""
    _clear_registry()
    profile = get_domain("science")
    criteria_names = [c.name for c in profile.document_template.review_criteria]
    assert criteria_names == ["novelty", "rigor", "clarity", "significance"]


def test_science_profile_has_mode_roles():
    """Science profile defines team roles for each operating mode."""
    _clear_registry()
    profile = get_domain("science")
    assert "directed" in profile.default_roles
    assert "explore" in profile.default_roles
    assert "theorist" in profile.default_roles["directed"]


def test_science_profile_prompts_dir():
    """Science profile points to a valid prompts directory."""
    _clear_registry()
    profile = get_domain("science")
    assert profile.prompts_dir.is_dir()
    yaml_files = list(profile.prompts_dir.glob("*.yaml"))
    assert len(yaml_files) == 8


def test_science_section_assignments_match_paper_py():
    """Science template section assignments match SECTION_ASSIGNMENTS in paper.py."""
    from paradigm.journal.paper import SECTION_ASSIGNMENTS

    _clear_registry()
    profile = get_domain("science")

    # Build assignments from template
    template_assignments: dict[str, list[str]] = {}
    for section in profile.document_template.sections:
        for role in section.assigned_roles:
            template_assignments.setdefault(role, []).append(section.name)

    # Compare to SECTION_ASSIGNMENTS
    for role, sections in SECTION_ASSIGNMENTS.items():
        expected = [s.value for s in sections]
        assert template_assignments.get(role) == expected, (
            f"Mismatch for role '{role}': template={template_assignments.get(role)}, "
            f"paper.py={expected}"
        )


def test_science_review_criteria_match_review_py():
    """Science template review criteria match SCORE_CATEGORIES in review.py."""
    from paradigm.journal.review import SCORE_CATEGORIES

    _clear_registry()
    profile = get_domain("science")
    criteria_names = [c.name for c in profile.document_template.review_criteria]
    assert criteria_names == SCORE_CATEGORIES


def test_science_profile_has_search_strategies():
    """Science profile defines role-specific search strategies."""
    _clear_registry()
    profile = get_domain("science")
    assert "theorist" in profile.role_search_strategies
    assert "skeptic" in profile.role_search_strategies


def test_science_profile_has_reinforcements():
    """Science profile defines role-specific later round reinforcements."""
    _clear_registry()
    profile = get_domain("science")
    assert "skeptic" in profile.role_later_round_reinforcements
    assert "theorist" in profile.role_later_round_reinforcements


def test_science_profile_has_literature_instruction():
    """Science profile has literature search instruction text."""
    _clear_registry()
    profile = get_domain("science")
    assert "[SEARCH:" in profile.literature_instruction
    assert "[FOLLOW:" in profile.literature_instruction
