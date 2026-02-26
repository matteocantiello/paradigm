"""Tests for literature review mode (--mode review)."""

from paradigm.domains.registry import _clear_registry, get_domain
from paradigm.domains.science.constants import (
    MODE_TEAM_ROLES,
    REVIEW_ROLE_LATER_ROUND_REINFORCEMENTS,
    REVIEW_ROLE_SEARCH_STRATEGIES,
)
from paradigm.domains.science.template import REVIEW_TEMPLATE
from paradigm.journal.paper import section_assignments_from_template
from paradigm.orchestrator.constants import (
    _MODE_PROMPT_OVERRIDES,
    _MODE_SYNTHESIS_OVERRIDES,
    _MODE_WRITING_OVERRIDES,
)
from paradigm.orchestrator.phases import ResearchPhase

# ---------------------------------------------------------------------------
# Team composition
# ---------------------------------------------------------------------------


def test_review_mode_in_team_roles():
    """Review mode is defined in MODE_TEAM_ROLES."""
    assert "review" in MODE_TEAM_ROLES


def test_review_team_has_no_experimentalist():
    """Review team excludes experimentalist — no experiments in review mode."""
    roles = MODE_TEAM_ROLES["review"]
    assert "experimentalist" not in roles


def test_review_team_has_no_analyst():
    """Review team excludes analyst — no data analysis in review mode."""
    roles = MODE_TEAM_ROLES["review"]
    assert "analyst" not in roles


def test_review_team_has_required_roles():
    """Review team includes theorist, synthesizer, skeptic, writer, editor."""
    roles = MODE_TEAM_ROLES["review"]
    for required in ["theorist", "synthesizer", "skeptic", "writer", "editor"]:
        assert required in roles, f"Missing role: {required}"


# ---------------------------------------------------------------------------
# Document template
# ---------------------------------------------------------------------------


def test_review_template_name():
    """Review template is named 'literature_review'."""
    assert REVIEW_TEMPLATE.name == "literature_review"


def test_review_template_sections():
    """Review template has correct section names in order."""
    section_names = [s.name for s in REVIEW_TEMPLATE.sections]
    assert section_names == [
        "abstract",
        "introduction",
        "literature_landscape",
        "thematic_analysis",
        "critical_assessment",
        "future_directions",
        "conclusion",
    ]


def test_review_template_no_methods_results():
    """Review template does not have methods or results sections."""
    section_names = {s.name for s in REVIEW_TEMPLATE.sections}
    assert "methods" not in section_names
    assert "results" not in section_names


def test_review_template_section_assignments():
    """Review template section assignments map to roles present in the team."""
    assignments = section_assignments_from_template(REVIEW_TEMPLATE.sections)
    review_roles = set(MODE_TEAM_ROLES["review"])
    for role in assignments:
        assert role in review_roles, (
            f"Section assigned to role '{role}' which is not in the review team"
        )


def test_review_template_has_review_criteria():
    """Review template has review criteria."""
    assert len(REVIEW_TEMPLATE.review_criteria) > 0


# ---------------------------------------------------------------------------
# Domain profile integration
# ---------------------------------------------------------------------------


def test_science_profile_has_review_template():
    """Science profile registers a review template in mode_templates."""
    _clear_registry()
    profile = get_domain("science")
    assert "review" in profile.mode_templates
    assert profile.mode_templates["review"].name == "literature_review"


def test_science_profile_has_review_reinforcements():
    """Science profile registers review-mode role reinforcements."""
    _clear_registry()
    profile = get_domain("science")
    assert "review" in profile.mode_role_reinforcements
    review_reinforcements = profile.mode_role_reinforcements["review"]
    assert "theorist" in review_reinforcements
    assert "synthesizer" in review_reinforcements
    assert "skeptic" in review_reinforcements


def test_science_profile_has_review_search_strategies():
    """Science profile registers review-mode search strategies."""
    _clear_registry()
    profile = get_domain("science")
    assert "review" in profile.mode_role_search_strategies
    review_strategies = profile.mode_role_search_strategies["review"]
    assert "theorist" in review_strategies
    assert "synthesizer" in review_strategies
    assert "skeptic" in review_strategies


def test_science_profile_review_team():
    """Science profile default_roles includes review mode."""
    _clear_registry()
    profile = get_domain("science")
    assert "review" in profile.default_roles
    assert "experimentalist" not in profile.default_roles["review"]


# ---------------------------------------------------------------------------
# Prompt overrides
# ---------------------------------------------------------------------------


def test_review_mode_prompt_overrides_exist():
    """Review mode has entries in _MODE_PROMPT_OVERRIDES."""
    assert "review" in _MODE_PROMPT_OVERRIDES


def test_review_prompt_overrides_have_required_keys():
    """Review mode overrides include round_1, later_rounds, and planning keys."""
    overrides = _MODE_PROMPT_OVERRIDES["review"]
    assert "round_1" in overrides
    assert "later_rounds" in overrides
    assert "planning_round_1" in overrides
    assert "planning_later_rounds" in overrides


def test_review_prompts_mention_literature_review():
    """Review prompts emphasize literature review, not experiments."""
    overrides = _MODE_PROMPT_OVERRIDES["review"]
    for key, prompt in overrides.items():
        assert "LITERATURE REVIEW" in prompt or "literature" in prompt.lower(), (
            f"Prompt '{key}' does not mention literature review"
        )


# ---------------------------------------------------------------------------
# Synthesis overrides
# ---------------------------------------------------------------------------


def test_review_synthesis_overrides_exist():
    """Review mode has entries in _MODE_SYNTHESIS_OVERRIDES."""
    assert "review" in _MODE_SYNTHESIS_OVERRIDES


def test_review_synthesis_overrides_have_ideation_and_planning():
    """Review synthesis overrides cover IDEATION and PLANNING phases."""
    overrides = _MODE_SYNTHESIS_OVERRIDES["review"]
    assert ResearchPhase.IDEATION in overrides
    assert ResearchPhase.PLANNING in overrides


# ---------------------------------------------------------------------------
# Writing overrides
# ---------------------------------------------------------------------------


def test_review_writing_overrides_exist():
    """Review mode has entries in _MODE_WRITING_OVERRIDES."""
    assert "review" in _MODE_WRITING_OVERRIDES


def test_review_writing_overrides_have_required_keys():
    """Review writing overrides include section_drafting and assembly."""
    overrides = _MODE_WRITING_OVERRIDES["review"]
    assert "section_drafting" in overrides
    assert "assembly" in overrides


def test_review_writing_prompts_mention_review():
    """Review writing prompts emphasize this is a review paper."""
    overrides = _MODE_WRITING_OVERRIDES["review"]
    assert "REVIEW paper" in overrides["section_drafting"]
    assert "literature review" in overrides["assembly"].lower()


# ---------------------------------------------------------------------------
# Review-mode reinforcements
# ---------------------------------------------------------------------------


def test_review_reinforcements_have_review_content():
    """Review reinforcements reference literature review tasks."""
    for role, text in REVIEW_ROLE_LATER_ROUND_REINFORCEMENTS.items():
        assert "Literature Review" in text or "literature" in text.lower(), (
            f"Reinforcement for '{role}' does not reference literature review"
        )


def test_review_search_strategies_have_review_content():
    """Review search strategies reference literature review tasks."""
    for role, text in REVIEW_ROLE_SEARCH_STRATEGIES.items():
        assert "Literature Review" in text or "review" in text.lower(), (
            f"Search strategy for '{role}' does not reference review"
        )
