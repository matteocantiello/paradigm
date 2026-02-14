"""Tests for paper models, writing phase, and review pipeline."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from paradigm.agents.base import AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.journal.paper import (
    SECTION_ASSIGNMENTS,
    PaperDraft,
    PaperSection,
    ReviewFeedback,
    SectionDraft,
    parse_review_feedback,
    parse_sections_from_markdown,
    strip_agent_scaffolding,
)
from paradigm.logging.events import EventLogger
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.storage.database import Database

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
        assert fb.recommendation == "accept"

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


# --- Engine Integration Tests ---


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def tmp_logger(tmp_path):
    return EventLogger(tmp_path / "events.jsonl")


def _build_checkpoint_response(summary="The team discussed", hypothesis="Test hypothesis"):
    return (
        json.dumps(
            {
                "hypothesis": hypothesis,
                "key_findings": ["finding"],
                "open_questions": ["question"],
                "next_steps": ["step"],
                "conversation_summary": summary,
            }
        ),
        100,
        50,
    )


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
    mock_provider = MagicMock()
    mock_provider.complete.return_value = _build_checkpoint_response()
    mock_provider.default_model = "claude-sonnet-4-5-20250929"
    object.__setattr__(config, "get_provider", MagicMock(return_value=mock_provider))
    object.__setattr__(
        config,
        "get_provider_and_model_for_role",
        MagicMock(return_value=(mock_provider, "claude-sonnet-4-5-20250929")),
    )
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
    mock_provider = MagicMock()
    mock_provider.complete.return_value = _build_checkpoint_response()
    mock_provider.default_model = "claude-sonnet-4-5-20250929"
    object.__setattr__(config, "get_provider", MagicMock(return_value=mock_provider))
    object.__setattr__(
        config,
        "get_provider_and_model_for_role",
        MagicMock(return_value=(mock_provider, "claude-sonnet-4-5-20250929")),
    )
    return config


def _make_mock_agent(agent_id: str, role: str, content: str | None = None):
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.skill_profile = role

    if content is None:
        content = f"Response from {agent_id}"

    response = AgentResponse(
        content=content,
        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
        model="claude-sonnet-4-5-20250929",
    )
    agent.generate = AsyncMock(return_value=response)

    def _format_message(to, thread_id, phase, message_type, content, **kwargs):
        msg = MagicMock()
        msg.model_dump.return_value = {
            "from": agent_id,
            "to": to,
            "thread_id": thread_id,
            "phase": phase,
            "type": message_type,
            "content": content,
            "references": [],
            "metadata": {},
        }
        return msg

    agent.format_message = MagicMock(side_effect=_format_message)
    return agent


def _make_writing_factory():
    """Create a factory that returns agents with role-appropriate writing responses."""
    factory = MagicMock()

    section_responses = {
        "writer": (
            "# Convective Overshooting in Stellar Interiors\n\n"
            "## Abstract\n\nThis paper presents a comprehensive study of convective "
            "overshooting in intermediate-mass stars using one-dimensional stellar "
            "evolution models. We investigate how overshooting affects the main-sequence "
            "width and core hydrogen burning lifetime.\n\n"
            "## Introduction\n\nStellar convection is a fundamental process governing "
            "energy transport and chemical mixing in stellar interiors. Understanding "
            "convective processes is essential for accurate stellar evolution modeling.\n\n"
            "## Conclusion\n\nWe conclude that convective overshooting plays a critical "
            "role in determining the main-sequence width of intermediate-mass stars."
        ),
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
            agents.append(_make_mock_agent(f"{role}-0", role, content))
        return agents

    factory.create_team = MagicMock(side_effect=_create_team)
    return factory


@pytest.fixture
def mock_corpus():
    corpus = MagicMock()
    corpus.build_literature_context = AsyncMock(return_value="No relevant papers found.")
    return corpus


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
