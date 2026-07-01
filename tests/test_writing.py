"""Tests for paper models, writing phase, and review pipeline."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from helpers import LONG_RESPONSE, make_mock_agent, patch_config_provider

from paradigm.config import Config
from paradigm.journal.paper import (
    SECTION_ASSIGNMENTS,
    PaperDraft,
    PaperSection,
    ReviewFeedback,
    SectionDraft,
    parse_review_feedback,
    parse_sections_from_markdown,
    sanitize_unicode_math,
    strip_agent_scaffolding,
)
from paradigm.orchestrator.constants import (
    _MODE_WRITING_OVERRIDES,
    _PHASE_INSTRUCTIONS,
    DIGEST_PROMPT,
)
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.phases import ResearchPhase
from paradigm.orchestrator.writing import (
    WritingHandler,
    _humanize_figure_name,
    _strip_missing_figure_refs,
)


# --- Figure caption humanization (B2) ---
class TestHumanizeFigureName:
    def test_snake_case_to_caption(self):
        assert _humanize_figure_name("mass_luminosity_fit") == "Mass luminosity fit"

    def test_strips_generic_figure_words_and_extension(self):
        assert (
            _humanize_figure_name("entrainment_vs_coupling_plot.png") == "Entrainment vs coupling"
        )
        assert _humanize_figure_name("fig_correlation") == "Correlation"

    def test_empty_when_only_generic_words(self):
        assert _humanize_figure_name("figure") == ""
        assert _humanize_figure_name("") == ""


# --- Strip references to figures that were never generated (PDF robustness) ---
class TestStripMissingFigureRefs:
    def test_strips_missing_keeps_present(self, tmp_path):
        (tmp_path / "figures").mkdir()
        (tmp_path / "figures" / "real.png").write_bytes(b"x")
        body = (
            "# Paper\n\n"
            "![Graphical abstract for paper summary](figures/ghost.png)\n\n"
            "Intro text.\n\n"
            "![Figure 1: Real](figures/real.png)\n\n"
            "End.\n"
        )
        out = _strip_missing_figure_refs(body, tmp_path)
        assert "figures/ghost.png" not in out  # hallucinated/missing → stripped
        assert "![Figure 1: Real](figures/real.png)" in out  # present → kept
        assert "Intro text." in out and "End." in out

    def test_no_figures_dir_strips_all_figure_refs(self, tmp_path):
        body = "# P\n\n![Graphical abstract](figures/ghost.png)\n\nText."
        out = _strip_missing_figure_refs(body, tmp_path)
        assert "figures/ghost.png" not in out
        assert "Text." in out


# --- Paper Model Tests ---


class TestPaperSection:
    def test_all_sections_defined(self):
        assert len(PaperSection) == 6
        assert PaperSection.ABSTRACT == "abstract"
        assert PaperSection.CONCLUSION == "conclusion"

    def test_section_assignments_cover_all_sections(self):
        assigned = set()
        for sections in SECTION_ASSIGNMENTS.values():
            assigned.update(sections)
        assert assigned == set(PaperSection)

    def test_writer_sections(self):
        assert SECTION_ASSIGNMENTS["writer"] == [
            PaperSection.ABSTRACT,
            PaperSection.INTRODUCTION,
            PaperSection.CONCLUSION,
        ]

    def test_theorist_sections(self):
        assert SECTION_ASSIGNMENTS["theorist"] == [PaperSection.METHODS]

    def test_analyst_sections(self):
        assert SECTION_ASSIGNMENTS["analyst"] == [PaperSection.RESULTS]

    def test_synthesizer_sections(self):
        assert SECTION_ASSIGNMENTS["synthesizer"] == [PaperSection.DISCUSSION]


class TestSectionDraft:
    def test_create(self):
        draft = SectionDraft(
            section=PaperSection.ABSTRACT,
            content="This paper studies...",
            author="writer-0",
        )
        assert draft.section == PaperSection.ABSTRACT
        assert draft.author == "writer-0"


class TestPaperDraft:
    def test_add_section(self):
        draft = PaperDraft()
        draft.add_section(
            SectionDraft(section=PaperSection.ABSTRACT, content="Abstract text", author="w-0")
        )
        assert PaperSection.ABSTRACT in draft.sections
        assert draft.sections[PaperSection.ABSTRACT].content == "Abstract text"

    def test_is_complete_false(self):
        draft = PaperDraft()
        draft.add_section(SectionDraft(section=PaperSection.ABSTRACT, content="x", author="w-0"))
        assert not draft.is_complete()

    def test_is_complete_true(self):
        draft = PaperDraft()
        for section in PaperSection:
            draft.add_section(SectionDraft(section=section, content="text", author="a-0"))
        assert draft.is_complete()

    def test_to_markdown_from_sections(self):
        draft = PaperDraft(title="My Paper")
        draft.add_section(
            SectionDraft(section=PaperSection.ABSTRACT, content="Abstract here", author="w-0")
        )
        draft.add_section(
            SectionDraft(section=PaperSection.INTRODUCTION, content="Intro here", author="w-0")
        )
        md = draft.to_markdown()
        assert "# My Paper" in md
        assert "## Abstract" in md
        assert "Abstract here" in md
        assert "## Introduction" in md
        assert "Intro here" in md

    def test_to_markdown_uses_assembled_body(self):
        draft = PaperDraft(assembled_body="# Full Paper\n\nContent here")
        assert draft.to_markdown() == "# Full Paper\n\nContent here"

    def test_section_ordering(self):
        draft = PaperDraft()
        # Add out of order
        draft.add_section(
            SectionDraft(section=PaperSection.CONCLUSION, content="end", author="w-0")
        )
        draft.add_section(
            SectionDraft(section=PaperSection.ABSTRACT, content="start", author="w-0")
        )
        md = draft.to_markdown()
        # Abstract should come before Conclusion
        assert md.index("Abstract") < md.index("Conclusion")


class TestReviewFeedback:
    def test_defaults(self):
        fb = ReviewFeedback()
        assert fb.recommendation == "revise"
        assert fb.strengths == []
        assert fb.weaknesses == []
        assert fb.required_changes == []

    def test_accept(self):
        fb = ReviewFeedback(recommendation="accept")
        assert fb.recommendation == "accept"


# --- Scaffolding Stripping Tests ---


class TestStripAgentScaffolding:
    def test_removes_preamble_before_heading(self):
        text = (
            "I'll revise the paper now.\n\n"
            "Let me start with the abstract.\n\n"
            "---\n\n"
            "# My Paper Title\n\n## Abstract\n\nContent here."
        )
        result = strip_agent_scaffolding(text)
        assert result.startswith("# My Paper Title")
        assert "I'll revise" not in result

    def test_removes_xml_function_calls(self):
        text = (
            '<function_calls>\n<invoke name="tool">\n'
            '<parameter name="x">y</parameter>\n'
            "</invoke>\n</function_calls>\n\n"
            "# Paper Title\n\nContent."
        )
        result = strip_agent_scaffolding(text)
        assert result.startswith("# Paper Title")
        assert "function_calls" not in result
        assert "invoke" not in result

    def test_removes_mixed_scaffolding(self):
        text = (
            "I'll revise the paper to address feedback.\n\n"
            '<function_calls>\n<invoke name="mcp_research">\n'
            '<parameter name="query">test</parameter>\n'
            "</invoke>\n</function_calls>\n\n"
            "Now I'll write the revision:\n\n"
            "---\n\n"
            "# Red Noise in Massive Stars\n\n## Abstract\n\nRed noise is..."
        )
        result = strip_agent_scaffolding(text)
        assert result.startswith("# Red Noise")
        assert "I'll revise" not in result
        assert "function_calls" not in result
        assert "Now I'll write" not in result

    def test_preserves_clean_paper(self):
        text = "# My Paper\n\n## Abstract\n\nThis is the abstract.\n\n## Introduction\n\nIntro."
        result = strip_agent_scaffolding(text)
        assert result == text

    def test_removes_inline_citation_inspection_note(self):
        """A leaked 'Need to inspect [1]/[9]...' note *inside* a section (the real
        bug that drew a major-revision) must be removed, not just preamble."""
        text = (
            "# Paper\n\n## Introduction\n\n"
            "Stellar convection drives observable variability in massive stars.\n\n"
            "Need to inspect [1]/[9] before citing — confirm they support the claim.\n\n"
            "We address this with a classical pipeline."
        )
        result = strip_agent_scaffolding(text)
        assert "Need to inspect" not in result
        assert "Stellar convection drives" in result
        assert "We address this" in result

    def test_removes_inline_first_person_lines(self):
        text = (
            "# Paper\n\n## Methods\n\n"
            "Let me tighten this section before finalizing.\n\n"
            "We trained a LinearSVC on TF-IDF features.\n\n"
            "I'll add the confusion matrix here.\n"
        )
        result = strip_agent_scaffolding(text)
        assert "Let me tighten" not in result
        assert "I'll add" not in result
        assert "We trained a LinearSVC" in result

    def test_preserves_legitimate_prose_with_inspect_and_we(self):
        """Formal prose ('we ... inspect', 'Here are the results', tables) must survive."""
        text = (
            "# Paper\n\n## Results\n\n"
            "We manually inspect the 20 hardest cases and compare against Smith et al. [1].\n\n"
            "Here are the results of the held-out evaluation.\n\n"
            "| Model | Accuracy |\n| --- | --- |\n| SVC | 0.78 |\n"
        )
        result = strip_agent_scaffolding(text)
        assert "We manually inspect" in result
        assert "Here are the results" in result
        assert "| SVC | 0.78 |" in result

    def test_handles_h2_start(self):
        text = "Some commentary.\n\n## Abstract\n\nContent."
        result = strip_agent_scaffolding(text)
        assert result.startswith("## Abstract")

    def test_empty_input(self):
        assert strip_agent_scaffolding("") == ""

    def test_no_heading_returns_content(self):
        text = "Just plain text without any headings."
        result = strip_agent_scaffolding(text)
        assert result == text

    def test_removes_standalone_xml_tags(self):
        text = (
            "<invoke name='tool'>\n"
            "<parameter name='x'>val</parameter>\n"
            "</invoke>\n\n"
            "# Title\n\nBody."
        )
        result = strip_agent_scaffolding(text)
        assert result.startswith("# Title")


# --- Unicode Math Sanitization Tests ---


class TestSanitizeUnicodeMath:
    def test_greek_letters(self):
        assert sanitize_unicode_math("The value α is small") == r"The value $\alpha$ is small"

    def test_subscripts(self):
        assert sanitize_unicode_math("mass m₁") == "mass m$_1$"

    def test_superscripts(self):
        assert sanitize_unicode_math("x² + y²") == "x$^2$ + y$^2$"

    def test_math_operators(self):
        assert sanitize_unicode_math("a ≈ b") == r"a $\approx$ b"

    def test_solar_symbol(self):
        assert sanitize_unicode_math("M☉") == r"M$\odot$"

    def test_no_double_wrap(self):
        """Characters already inside $...$ should not be wrapped again."""
        text = r"The spin $\chi$ is small"
        assert sanitize_unicode_math(text) == text


# --- Readability directive + plain-language Digest ---


class TestReadabilityDirective:
    """The writer's section-drafting prompts carry the digestibility directive."""

    def test_default_section_drafting_has_readability(self):
        prompt = _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["section_drafting"]
        assert "Readability" in prompt
        assert "plain-language sentence" in prompt
        assert "one idea per sentence" in prompt

    def test_review_override_has_readability(self):
        prompt = _MODE_WRITING_OVERRIDES["review"]["section_drafting"]
        assert "Readability" in prompt
        assert "plain-language sentence" in prompt


class TestDigestPrompt:
    def test_prompt_is_grounded_and_plain(self):
        assert "{paper_body}" in DIGEST_PROMPT  # grounded in the actual paper
        assert "FAITHFUL" in DIGEST_PROMPT  # no invented claims
        assert "NO equations" in DIGEST_PROMPT  # layman-readable


def _digest_engine(tmp_path, *, enabled=True, writer_content="A clear, plain summary."):
    """MagicMock engine wired just enough to drive _generate_and_save_digest."""
    engine = MagicMock()
    engine._config.journal.enable_digest = enabled
    engine._config.storage.papers_dir = tmp_path
    if writer_content is None:
        engine._find_agent_by_role.return_value = None
    else:
        engine._find_agent_by_role.return_value = make_mock_agent(
            "writer-0", "writer", content=writer_content
        )
    return engine


class TestGenerateDigest:
    @pytest.mark.asyncio
    async def test_writes_digest_when_enabled(self, tmp_path):
        engine = _digest_engine(tmp_path, writer_content="Breast milk carries antibodies...")
        await WritingHandler(engine)._generate_and_save_digest("paper-abc", "# T\n\nBody.")
        f = tmp_path / "paper-abc" / "paper-abc-digest.md"
        assert f.exists()
        assert "Breast milk carries antibodies" in f.read_text()
        engine.emit_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_gate_off_skips_generation(self, tmp_path):
        engine = _digest_engine(tmp_path, enabled=False)
        await WritingHandler(engine)._generate_and_save_digest("paper-abc", "body")
        assert not (tmp_path / "paper-abc" / "paper-abc-digest.md").exists()
        engine._find_agent_by_role.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_output_writes_no_file(self, tmp_path):
        engine = _digest_engine(tmp_path, writer_content="   ")
        await WritingHandler(engine)._generate_and_save_digest("paper-abc", "body")
        assert not (tmp_path / "paper-abc" / "paper-abc-digest.md").exists()

    @pytest.mark.asyncio
    async def test_no_writer_agent_no_crash(self, tmp_path):
        engine = _digest_engine(tmp_path, writer_content=None)
        await WritingHandler(engine)._generate_and_save_digest("paper-abc", "body")
        assert not (tmp_path / "paper-abc" / "paper-abc-digest.md").exists()

    @pytest.mark.asyncio
    async def test_writer_error_is_swallowed(self, tmp_path):
        engine = MagicMock()
        engine._config.journal.enable_digest = True
        engine._config.storage.papers_dir = tmp_path
        writer = MagicMock()
        writer.generate = AsyncMock(side_effect=RuntimeError("boom"))
        engine._find_agent_by_role.return_value = writer
        await WritingHandler(engine)._generate_and_save_digest("paper-abc", "body")
        assert not (tmp_path / "paper-abc" / "paper-abc-digest.md").exists()
        engine._logger.log_error.assert_called_once()

    def test_mixed_inline_and_outside(self):
        text = r"We find α in $\beta$ and γ"
        result = sanitize_unicode_math(text)
        assert r"$\alpha$" in result
        assert r"$\gamma$" in result
        # The β inside math should stay untouched
        assert r"$\beta$" in result

    def test_empty_string(self):
        assert sanitize_unicode_math("") == ""

    def test_no_unicode(self):
        text = "Plain text with no math"
        assert sanitize_unicode_math(text) is text  # same object, fast path

    def test_script_letters(self):
        assert sanitize_unicode_math("the likelihood ℒ") == r"the likelihood $\mathcal{L}$"

    def test_display_math_untouched(self):
        text = "Text\n$$\n\\alpha + \\beta\n$$\nmore text"
        assert sanitize_unicode_math(text) == text


# --- Parsing Tests ---


class TestParseSectionsFromMarkdown:
    def test_basic_parsing(self):
        md = "## Abstract\n\nThis is abstract.\n\n## Introduction\n\nThis is intro."
        result = parse_sections_from_markdown(md)
        assert "abstract" in result
        assert "introduction" in result
        assert "This is abstract." in result["abstract"]

    def test_empty_input(self):
        result = parse_sections_from_markdown("")
        assert result == {}

    def test_no_headers(self):
        result = parse_sections_from_markdown("Just plain text without headers.")
        assert result == {}

    def test_preserves_content(self):
        md = "## Methods\n\nWe used method A.\nThen method B.\n\n## Results\n\nResult 1."
        result = parse_sections_from_markdown(md)
        assert "We used method A." in result["methods"]
        assert "Then method B." in result["methods"]
        assert "Result 1." in result["results"]


class TestParseReviewFeedback:
    def test_full_review(self):
        review = (
            "## Strengths\n- Clear writing\n- Novel approach\n\n"
            "## Weaknesses\n- Missing references\n\n"
            "## Required Changes\n- Add citations\n- Fix equation 3\n\n"
            "## Recommendation\nAccept with minor revisions"
        )
        fb = parse_review_feedback(review)
        assert len(fb.strengths) == 2
        assert "Clear writing" in fb.strengths
        assert len(fb.weaknesses) == 1
        assert len(fb.required_changes) == 2
        # "Accept with minor revisions" → revise (accept + revisions = revise)
        assert fb.recommendation == "revise"

    def test_pure_accept_recommendation(self):
        review = "## Strengths\n- Excellent work\n\n## Recommendation\nAccept"
        fb = parse_review_feedback(review)
        assert fb.recommendation == "accept"

    def test_recommendation_explicit_when_section_present(self):
        review = "## Recommendation\nAccept\n\n## Strengths\n- Good"
        assert parse_review_feedback(review).recommendation_explicit is True

    def test_recommendation_not_explicit_when_truncated(self):
        # A review cut off mid-Strengths (no ## Recommendation) — must be flagged
        # NOT explicit so it can't be silently accepted downstream.
        review = "## Strengths\n- Rigorous methodology\n- Strong derivation, and the"
        fb = parse_review_feedback(review)
        assert fb.recommendation_explicit is False
        assert fb.recommendation == "revise"  # defaulted, not accepted

    def test_revise_recommendation(self):
        review = "## Recommendation\nRevise and resubmit"
        fb = parse_review_feedback(review)
        assert fb.recommendation == "revise"

    def test_empty_review(self):
        fb = parse_review_feedback("")
        assert fb.recommendation == "revise"
        assert fb.strengths == []

    def test_bullet_styles(self):
        review = "## Strengths\n* Point 1\n- Point 2\n"
        fb = parse_review_feedback(review)
        assert len(fb.strengths) == 2

    def test_h3_headers_fallback(self):
        """### headers are parsed when ## parsing misses recommendation."""
        review = (
            "## Scientific Editorial Review\n\n"
            "### Strengths\n- Good analysis\n\n"
            "### Weaknesses\n- Needs more data\n\n"
            "### Required Changes\n- None\n\n"
            "### Recommendation\nAccept"
        )
        fb = parse_review_feedback(review)
        assert fb.recommendation == "accept"
        assert len(fb.strengths) == 1

    def test_missing_recommendation_fulltext_fallback(self):
        """When no Recommendation section exists, scan full text."""
        review = (
            "## Strengths\n- Excellent methodology\n\n"
            "## Weaknesses\n- Minor formatting issues\n\n"
            "## Required Changes\n- None\n\n"
            "Overall this paper is ready to accept for publication."
        )
        fb = parse_review_feedback(review)
        assert fb.recommendation == "accept"

    def test_header_with_trailing_colon(self):
        """## Recommendation: (with colon) is parsed correctly."""
        review = "## Strengths:\n- Clear writing\n\n## Recommendation:\nAccept"
        fb = parse_review_feedback(review)
        assert fb.recommendation == "accept"

    def test_reject_recommendation(self):
        """Explicit reject in recommendation section is parsed correctly."""
        review = (
            "## Strengths\n- None\n\n"
            "## Weaknesses\n- Fundamental flaws\n\n"
            "## Required Changes\n- Complete rewrite needed\n\n"
            "## Recommendation\nReject — fundamentally flawed"
        )
        fb = parse_review_feedback(review)
        assert fb.recommendation == "reject"

    def test_reject_fulltext_fallback(self):
        """Reject in body text (no Recommendation section) is detected."""
        review = (
            "## Strengths\n- Clear writing\n\n"
            "## Weaknesses\n- Fatal logical error\n\n"
            "I must reject this paper due to fundamental flaws."
        )
        fb = parse_review_feedback(review)
        assert fb.recommendation == "reject"

    def test_reject_not_triggered_when_accept_also_present(self):
        """If both 'reject' and 'accept' appear in text, neither wins alone."""
        review = (
            "I considered whether to reject or accept this paper. "
            "Overall the paper should be revised and resubmitted. Revise."
        )
        fb = parse_review_feedback(review)
        # Both reject+accept in text, but "revise" also present → fallback to revise
        assert fb.recommendation == "revise"


# --- Experiment Ledger Tests (Fix 3) ---


class TestExperimentLedger:
    def _make_engine(self, tmp_path):
        """Create a minimal engine for unit testing."""
        from paradigm.config import Config
        from paradigm.storage.database import Database

        config = Config(
            api_key="fake",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={"max_rounds_per_phase": 1},
        )
        patch_config_provider(config)
        db = Database(tmp_path / "test.db")
        from paradigm.logging.events import EventLogger

        logger = EventLogger(tmp_path / "events.jsonl")
        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[])
        corpus = MagicMock()
        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        db.close()
        return engine

    def test_ledger_empty_when_no_experiments(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.experiment_metadata = []
        fact_sheet = engine._writing._build_execution_fact_sheet()
        assert fact_sheet == ""

    def test_ledger_contains_experiment_info(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.experiment_metadata = [
            {
                "name": "gravity_test",
                "status": "success",
                "stdout_preview": "Mean: 42.0",
                "stdout_full": "Mean: 42.0\nStd: 1.5",
                "has_figures": True,
                "failure_reason": "",
            },
            {
                "name": "failed_test",
                "status": "failure",
                "stdout_preview": "Error occurred",
                "stdout_full": "Error occurred",
                "has_figures": False,
                "failure_reason": "ValueError: invalid input",
            },
        ]
        fact_sheet = engine._writing._build_execution_fact_sheet()
        assert "Execution Fact Sheet" in fact_sheet
        assert "gravity_test" in fact_sheet
        assert "failed_test" in fact_sheet
        assert "success" in fact_sheet
        assert "FAILED" in fact_sheet
        assert "Successful Results (USE THESE)" in fact_sheet
        assert "FAILED Experiments (DO NOT USE)" in fact_sheet
        assert "ANTI-CONFABULATION" in fact_sheet
        assert "DO NOT describe this experiment as having produced results" in fact_sheet

    def test_ledger_has_figures_column(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.experiment_metadata = [
            {
                "name": "fig_test",
                "status": "success",
                "stdout_preview": "",
                "stdout_full": "",
                "has_figures": True,
                "failure_reason": "",
            },
        ]
        fact_sheet = engine._writing._build_execution_fact_sheet()
        assert "Yes" in fact_sheet


# --- Engine Integration Tests ---


@pytest.fixture
def mock_config(tmp_path):
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 2,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": True,
            "enable_experimentation": False,
            "max_review_iterations": 1,
            "enable_peer_review": False,
        },
    )
    patch_config_provider(config)
    return config


@pytest.fixture
def mock_config_no_writing(tmp_path):
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 2,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": False,
            "enable_experimentation": False,
            "max_review_iterations": 1,
            "enable_peer_review": False,
        },
    )
    patch_config_provider(config)
    return config


def _make_writing_factory():
    """Create a factory that returns agents with role-appropriate writing responses."""
    factory = MagicMock()

    section_responses = {
        "writer": LONG_RESPONSE,
        "theorist": (
            "## Methods\n\nWe use mixing-length theory to model convection in our "
            "stellar evolution calculations. The models span masses from 1.5 to 8 solar masses."
        ),
        "analyst": (
            "## Results\n\nOur analysis shows a strong correlation between the overshooting "
            "parameter and the main-sequence lifetime for stars above 2 solar masses."
        ),
        "synthesizer": (
            "## Discussion\n\nThese results suggest that convective overshooting extends "
            "the main-sequence lifetime by up to 25 percent for the most massive models."
        ),
        "editor": (
            "## Strengths\n- Well structured\n- Clear methodology\n\n"
            "## Weaknesses\n- Needs more references\n\n"
            "## Required Changes\n- Add citations to section 2\n\n"
            "## Recommendation\nAccept"
        ),
        "skeptic": "The methodology looks sound but I have concerns about...",
    }

    def _create_team(roles, skill_mode="default"):
        agents = []
        for role in roles:
            content = section_responses.get(role, f"Response from {role}")
            agents.append(make_mock_agent(f"{role}-0", role, content))
        return agents

    factory.create_team = MagicMock(side_effect=_create_team)
    return factory


class TestWritingPhaseEngine:
    @pytest.mark.asyncio
    async def test_full_cycle_with_writing(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Full cycle SEEDING -> IDEATION -> PLANNING -> WRITING -> REVIEW."""
        factory = _make_writing_factory()

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        thread_id = await engine.run_research_cycle(
            seed_prompt="Test stellar convection",
            mode="directed",
        )

        # Thread completed
        thread = tmp_db.get_thread(thread_id)
        assert thread is not None
        assert thread["status"] == "reviewed"
        assert thread["current_draft_id"] is not None

        # Paper was created
        paper = tmp_db.get_paper(thread["current_draft_id"])
        assert paper is not None
        assert paper["status"] in ("reviewed", "revised")
        assert len(paper["body"]) > 0

    @pytest.mark.asyncio
    async def test_writing_disabled(self, mock_config_no_writing, tmp_db, tmp_logger, mock_corpus):
        """When enable_writing=False, cycle stops after PLANNING."""
        factory = _make_writing_factory()

        engine = OrchestrationEngine(
            config=mock_config_no_writing,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        thread_id = await engine.run_research_cycle(
            seed_prompt="Test topic",
            mode="directed",
        )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "planning_complete"
        assert thread["current_draft_id"] is None

    @pytest.mark.asyncio
    async def test_paper_saved_to_database(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Paper is persisted to the papers table."""
        factory = _make_writing_factory()

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        thread_id = await engine.run_research_cycle(
            seed_prompt="Convection in massive stars",
            mode="directed",
        )

        thread = tmp_db.get_thread(thread_id)
        paper_id = thread["current_draft_id"]
        assert paper_id is not None

        paper = tmp_db.get_paper(paper_id)
        assert paper is not None
        assert paper["abstract"] != ""
        authors = json.loads(paper["authors"])
        assert len(authors) > 0

    @pytest.mark.asyncio
    async def test_phase_transitions_include_writing(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        """Phase transitions include WRITING and INTERNAL_REVIEW."""
        factory = _make_writing_factory()

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(
            seed_prompt="Test",
            mode="directed",
        )

        from paradigm.logging.events import EventType

        events = tmp_logger.read_events(event_type=EventType.PHASE_TRANSITION)
        phases_seen = []
        for e in events:
            c = e.content if isinstance(e.content, dict) else {}
            phases_seen.append(c.get("to", c.get("phase")))
        assert "writing" in phases_seen
        assert "internal" in phases_seen

    @pytest.mark.asyncio
    async def test_editor_accept_skips_revision(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """When editor recommends accept, no revision round occurs."""
        factory = _make_writing_factory()

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        thread_id = await engine.run_research_cycle(
            seed_prompt="Test",
            mode="directed",
        )

        # Editor's default response recommends "Accept" so paper should be "reviewed"
        thread = tmp_db.get_thread(thread_id)
        paper = tmp_db.get_paper(thread["current_draft_id"])
        assert paper["status"] == "reviewed"


# --- Unit tests: partitioned fact sheet (Fix 6) ---


class TestPartitionedFactSheet:
    def _make_engine(self, tmp_path):
        from paradigm.config import Config
        from paradigm.storage.database import Database

        config = Config(
            api_key="fake",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={"max_rounds_per_phase": 1},
        )
        patch_config_provider(config)
        db = Database(tmp_path / "test.db")
        from paradigm.logging.events import EventLogger

        logger = EventLogger(tmp_path / "events.jsonl")
        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[])
        corpus = MagicMock()
        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        db.close()
        return engine

    def test_all_successful(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.experiment_metadata = [
            {
                "name": "exp_a",
                "status": "success",
                "stdout_full": "Result: 42",
                "has_figures": True,
                "failure_reason": "",
            },
        ]
        fact_sheet = engine._writing._build_execution_fact_sheet()
        assert "Successful Results (USE THESE)" in fact_sheet
        assert "exp_a" in fact_sheet
        assert "All experiments succeeded" in fact_sheet

    def test_all_failed(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.experiment_metadata = [
            {
                "name": "exp_fail",
                "status": "failure",
                "stdout_full": "",
                "has_figures": False,
                "failure_reason": "TypeError: bad arg",
            },
        ]
        fact_sheet = engine._writing._build_execution_fact_sheet()
        assert "No experiments succeeded" in fact_sheet
        assert "FAILED Experiments (DO NOT USE)" in fact_sheet
        assert "exp_fail" in fact_sheet
        assert "TypeError" in fact_sheet


# --- Unit tests: _filter_successful_execution_context (Fix 6) ---


class TestFilterSuccessfulExecutionContext:
    def _make_engine(self, tmp_path):
        from paradigm.config import Config
        from paradigm.storage.database import Database

        config = Config(
            api_key="fake",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={"max_rounds_per_phase": 1},
        )
        patch_config_provider(config)
        db = Database(tmp_path / "test.db")
        from paradigm.logging.events import EventLogger

        logger = EventLogger(tmp_path / "events.jsonl")
        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[])
        corpus = MagicMock()
        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        db.close()
        return engine

    def test_filters_out_failed_experiments(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_context = (
            "Preamble text\n"
            "### Experiment: good_exp\nResult: 42\n\n"
            "### Experiment: bad_exp\nFailed with error\n"
        )
        engine.state.experiment_metadata = [
            {"name": "good_exp", "status": "success"},
            {"name": "bad_exp", "status": "failure"},
        ]
        result = engine._writing._filter_successful_execution_context()
        assert "good_exp" in result
        assert "bad_exp" not in result
        assert "Preamble" in result

    def test_empty_context_returns_empty(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_context = ""
        engine.state.experiment_metadata = []
        result = engine._writing._filter_successful_execution_context()
        assert result == ""

    def test_no_successful_returns_empty(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_context = "### Experiment: bad_exp\nFailed\n"
        engine.state.experiment_metadata = [
            {"name": "bad_exp", "status": "failure"},
        ]
        result = engine._writing._filter_successful_execution_context()
        assert result == ""

    def test_all_successful_returns_all(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_context = (
            "### Experiment: exp_a\nResult A\n\n### Experiment: exp_b\nResult B\n"
        )
        engine.state.experiment_metadata = [
            {"name": "exp_a", "status": "success"},
            {"name": "exp_b", "status": "success"},
        ]
        result = engine._writing._filter_successful_execution_context()
        assert "exp_a" in result
        assert "exp_b" in result


# --- Unit tests: _build_established_points (Fix 5) ---


class TestBuildEstablishedPoints:
    def test_extracts_bullet_points(self):
        messages = [
            {
                "content": "- The period-luminosity relation is well established\n- Mass loss rates are uncertain"
            },
            {
                "content": "1. We should focus on Cepheid observations\n2. Red noise contamination is a concern"
            },
        ]
        result = OrchestrationEngine._build_established_points(messages)
        assert "Points Already Established" in result
        assert "DO NOT RESTATE" in result
        assert "period-luminosity" in result

    def test_empty_messages(self):
        result = OrchestrationEngine._build_established_points([])
        assert result == ""

    def test_no_bullets(self):
        messages = [
            {"content": "This is just prose without any bullet points or lists."},
        ]
        result = OrchestrationEngine._build_established_points(messages)
        assert result == ""

    def test_max_five_points(self):
        lines = "\n".join(f"- Point number {i} is important enough to note" for i in range(10))
        messages = [{"content": lines}]
        result = OrchestrationEngine._build_established_points(messages)
        # Should have at most 5 bullet points in output
        assert result.count("- ") <= 5


# --- Unit tests: _validate_figure_references (Fix 3 from paper-cdddc9232c19) ---


class TestValidateFigureReferences:
    def _make_engine(self, tmp_path):
        from paradigm.config import Config
        from paradigm.logging.events import EventLogger
        from paradigm.storage.database import Database

        config = Config(
            api_key="fake",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={"max_rounds_per_phase": 1},
        )
        patch_config_provider(config)
        db = Database(tmp_path / "test.db")
        logger = EventLogger(tmp_path / "events.jsonl")
        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[])
        corpus = MagicMock()
        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        db.close()
        return engine

    def test_no_figures_no_refs(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = []
        warnings = engine._writing._validate_figure_references("No figures here.")
        assert warnings == []

    def test_refs_but_no_figures(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = []
        body = "As shown in Figure 1 and Figure 2, the results are clear."
        warnings = engine._writing._validate_figure_references(body)
        assert len(warnings) == 1
        assert "NO figure files" in warnings[0]
        assert "Figure 1, 2" in warnings[0]

    def test_refs_within_figure_count(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = [
            ("exp_a", Path("/tmp/fig1.png")),
            ("exp_b", Path("/tmp/fig2.png")),
        ]
        body = "Figure 1 and Figure 2 show the data."
        warnings = engine._writing._validate_figure_references(body)
        assert warnings == []

    def test_refs_exceed_figure_count(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = [("exp_a", Path("/tmp/fig1.png"))]
        body = "Figure 1 is good, but Figure 3 is missing."
        warnings = engine._writing._validate_figure_references(body)
        assert len(warnings) == 1
        assert "Figure(s) 3" in warnings[0]

    def test_fig_abbreviation(self, tmp_path):
        engine = self._make_engine(tmp_path)
        engine.state.execution_figures = []
        body = "See Fig. 1 for details and Fig 2 for more."
        warnings = engine._writing._validate_figure_references(body)
        assert len(warnings) == 1
        assert "NO figure files" in warnings[0]


# --- Unit tests: _fallback_assembly (Fix 2 from paper-cdddc9232c19) ---


class TestFallbackAssembly:
    def _make_engine(self, tmp_path):
        from paradigm.config import Config
        from paradigm.logging.events import EventLogger
        from paradigm.storage.database import Database

        config = Config(
            api_key="fake",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={"max_rounds_per_phase": 1},
        )
        patch_config_provider(config)
        db = Database(tmp_path / "test.db")
        logger = EventLogger(tmp_path / "events.jsonl")
        factory = MagicMock()
        factory.create_team = MagicMock(return_value=[])
        corpus = MagicMock()
        engine = OrchestrationEngine(
            config=config, database=db, corpus=corpus, logger=logger, agent_factory=factory
        )
        db.close()
        return engine

    def test_concatenates_sections_in_order(self, tmp_path):
        engine = self._make_engine(tmp_path)
        draft = PaperDraft(section_order=["abstract", "introduction", "conclusion"])
        draft.add_section(
            SectionDraft(section="abstract", content="This is the abstract.", author="w")
        )
        draft.add_section(
            SectionDraft(section="conclusion", content="This is the conclusion.", author="w")
        )
        draft.add_section(
            SectionDraft(section="introduction", content="This is the introduction.", author="w")
        )

        result = engine._writing._fallback_assembly(draft)
        # Sections should be in section_order order, not insertion order
        assert result.index("abstract") < result.index("introduction")
        assert result.index("introduction") < result.index("conclusion")

    def test_empty_draft(self, tmp_path):
        engine = self._make_engine(tmp_path)
        draft = PaperDraft(section_order=["abstract", "introduction"])
        result = engine._writing._fallback_assembly(draft)
        assert result == ""
