"""Tests for peer review pipeline: review models, parsing, decision synthesis, publication, engine integration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradigm.agents.base import AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.journal.publication import publish_paper, reject_paper
from paradigm.journal.review import (
    PeerReview,
    parse_peer_review,
    synthesize_decision,
)
from paradigm.logging.events import EventLogger
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.storage.database import Database

# --- PeerReview Model Tests ---


class TestPeerReviewModel:
    def test_defaults(self):
        review = PeerReview(reviewer_id="reviewer-0")
        assert review.reviewer_id == "reviewer-0"
        assert review.summary == ""
        assert review.strengths == []
        assert review.weaknesses == []
        assert review.questions == []
        assert review.suggestions == []
        assert review.scores == {}
        assert review.recommendation == "major_revision"

    def test_full_review(self):
        review = PeerReview(
            reviewer_id="reviewer-1",
            summary="Good paper",
            strengths=["Novel approach", "Clear writing"],
            weaknesses=["Missing references"],
            questions=["How does this compare to X?"],
            suggestions=["Add comparison table"],
            scores={"novelty": 8, "rigor": 7, "clarity": 9, "significance": 6},
            recommendation="minor_revision",
        )
        assert len(review.strengths) == 2
        assert review.scores["clarity"] == 9
        assert review.recommendation == "minor_revision"

    def test_scores_validation(self):
        review = PeerReview(
            reviewer_id="r-0",
            scores={"novelty": 1, "rigor": 10, "clarity": 5, "significance": 5},
        )
        assert review.scores["novelty"] == 1
        assert review.scores["rigor"] == 10


# --- Parsing Tests ---


class TestParsePeerReview:
    def test_full_review_text(self):
        text = (
            "## Summary\nThis paper presents a novel approach to stellar convection.\n\n"
            "## Strengths\n- Innovative methodology\n- Well-written\n\n"
            "## Weaknesses\n- Limited sample size\n- Missing error analysis\n\n"
            "## Questions\n- How sensitive are results to initial conditions?\n\n"
            "## Suggestions\n- Add uncertainty quantification\n- Compare with observational data\n\n"
            "## Scores\nNovelty: 8/10\nRigor: 6/10\nClarity: 9/10\nSignificance: 7/10\n\n"
            "## Recommendation\nminor_revision\n\nThe paper needs minor improvements."
        )
        review = parse_peer_review("reviewer-0", text)
        assert review.reviewer_id == "reviewer-0"
        assert "novel approach" in review.summary.lower()
        assert len(review.strengths) == 2
        assert len(review.weaknesses) == 2
        assert len(review.questions) == 1
        assert len(review.suggestions) == 2
        assert review.scores["novelty"] == 8
        assert review.scores["rigor"] == 6
        assert review.scores["clarity"] == 9
        assert review.scores["significance"] == 7
        assert review.recommendation == "minor_revision"

    def test_accept_recommendation(self):
        text = "## Recommendation\naccept"
        review = parse_peer_review("r-0", text)
        assert review.recommendation == "accept"

    def test_reject_recommendation(self):
        text = "## Recommendation\nreject\n\nFundamental flaws."
        review = parse_peer_review("r-0", text)
        assert review.recommendation == "reject"

    def test_major_revision_recommendation(self):
        text = "## Recommendation\nmajor_revision"
        review = parse_peer_review("r-0", text)
        assert review.recommendation == "major_revision"

    def test_minor_revision_natural_language(self):
        text = "## Recommendation\nI recommend minor revision before acceptance."
        review = parse_peer_review("r-0", text)
        assert review.recommendation == "minor_revision"

    def test_empty_text(self):
        review = parse_peer_review("r-0", "")
        assert review.reviewer_id == "r-0"
        assert review.scores == {}
        assert review.recommendation == "major_revision"

    def test_partial_scores(self):
        text = "## Scores\nNovelty: 5/10\nClarity: 8/10\n"
        review = parse_peer_review("r-0", text)
        assert review.scores.get("novelty") == 5
        assert review.scores.get("clarity") == 8
        assert "rigor" not in review.scores

    def test_score_clamping(self):
        text = "## Scores\nNovelty: 15/10\nRigor: 0/10\n"
        review = parse_peer_review("r-0", text)
        assert review.scores.get("novelty") == 10  # clamped to 10
        # 0 would be clamped to 1
        # Actually the regex would match 0, and max(1, min(10, 0)) = 1
        # But 0/10 regex: (\d+) matches "0" → int("0") = 0 → max(1,min(10,0)) = 1
        # Wait, let's check: the regex is (\d+) which matches one or more digits
        # 0 has one digit, so it matches. Then max(1, min(10, 0)) = max(1, 0) = 1


# --- Decision Synthesis Tests ---


class TestSynthesizeDecision:
    def test_accept_high_scores(self):
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 8, "rigor": 8, "clarity": 9, "significance": 7},
                recommendation="accept",
            ),
            PeerReview(
                reviewer_id="r-1",
                scores={"novelty": 7, "rigor": 7, "clarity": 8, "significance": 8},
                recommendation="accept",
            ),
        ]
        assert synthesize_decision(reviews) == "accept"

    def test_minor_revision_medium_scores(self):
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 6, "rigor": 5, "clarity": 6, "significance": 5},
                recommendation="minor_revision",
            ),
            PeerReview(
                reviewer_id="r-1",
                scores={"novelty": 6, "rigor": 6, "clarity": 7, "significance": 6},
                recommendation="minor_revision",
            ),
        ]
        assert synthesize_decision(reviews) == "minor_revision"

    def test_major_revision_low_scores(self):
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 4, "rigor": 4, "clarity": 5, "significance": 4},
                recommendation="major_revision",
            ),
            PeerReview(
                reviewer_id="r-1",
                scores={"novelty": 5, "rigor": 4, "clarity": 4, "significance": 4},
                recommendation="major_revision",
            ),
        ]
        assert synthesize_decision(reviews) == "major_revision"

    def test_reject_when_any_reviewer_rejects(self):
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 8, "rigor": 8, "clarity": 8, "significance": 8},
                recommendation="accept",
            ),
            PeerReview(
                reviewer_id="r-1",
                scores={"novelty": 6, "rigor": 6, "clarity": 6, "significance": 6},
                recommendation="reject",
            ),
        ]
        assert synthesize_decision(reviews) == "reject"

    def test_reject_very_low_scores(self):
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 2, "rigor": 3, "clarity": 3, "significance": 2},
                recommendation="major_revision",
            ),
            PeerReview(
                reviewer_id="r-1",
                scores={"novelty": 3, "rigor": 2, "clarity": 2, "significance": 3},
                recommendation="major_revision",
            ),
        ]
        assert synthesize_decision(reviews) == "reject"

    def test_empty_reviews(self):
        assert synthesize_decision([]) == "reject"

    def test_no_scores_with_reject(self):
        reviews = [
            PeerReview(reviewer_id="r-0", recommendation="reject"),
        ]
        assert synthesize_decision(reviews) == "reject"

    def test_no_scores_no_reject(self):
        reviews = [
            PeerReview(reviewer_id="r-0", recommendation="minor_revision"),
        ]
        assert synthesize_decision(reviews) == "major_revision"

    def test_boundary_score_7(self):
        """Avg exactly 7 → accept (if no reject)."""
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 7, "rigor": 7, "clarity": 7, "significance": 7},
                recommendation="accept",
            ),
        ]
        assert synthesize_decision(reviews) == "accept"

    def test_boundary_score_5(self):
        """Avg exactly 5 → minor_revision."""
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 5, "rigor": 5, "clarity": 5, "significance": 5},
                recommendation="minor_revision",
            ),
        ]
        assert synthesize_decision(reviews) == "minor_revision"

    def test_boundary_score_4(self):
        """Avg exactly 4 → major_revision."""
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 4, "rigor": 4, "clarity": 4, "significance": 4},
                recommendation="major_revision",
            ),
        ]
        assert synthesize_decision(reviews) == "major_revision"


# --- Publication Tests ---


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def tmp_logger(tmp_path):
    return EventLogger(tmp_path / "events.jsonl")


@pytest.fixture
def mock_corpus(tmp_path):
    corpus = MagicMock()
    corpus.build_literature_context = AsyncMock(return_value="No relevant papers found.")
    corpus.ingest_internal_paper = MagicMock()
    return corpus


class TestPublishPaper:
    @pytest.mark.asyncio
    async def test_publish_updates_status(self, tmp_db, tmp_logger, mock_corpus):
        tmp_db.create_paper(
            paper_id="paper-001",
            title="Test Paper",
            abstract="Abstract",
            authors=["writer-0", "theorist-0"],
            body="Full paper body",
            status="submitted",
        )
        await publish_paper("paper-001", tmp_db, mock_corpus, tmp_logger)

        paper = tmp_db.get_paper("paper-001")
        assert paper["status"] == "published"
        assert paper["published_at"] is not None

    @pytest.mark.asyncio
    async def test_publish_adds_to_chromadb(self, tmp_db, tmp_logger, mock_corpus):
        tmp_db.create_paper(
            paper_id="paper-002",
            title="Test Paper",
            abstract="Abstract",
            authors=["writer-0"],
            body="Body",
            status="submitted",
        )
        await publish_paper("paper-002", tmp_db, mock_corpus, tmp_logger)

        mock_corpus.ingest_internal_paper.assert_called_once_with(
            paper_id="paper-002",
            title="Test Paper",
            abstract="Abstract",
            authors=["writer-0"],
        )

    @pytest.mark.asyncio
    async def test_publish_updates_reputation(self, tmp_db, tmp_logger, mock_corpus):
        tmp_db.create_paper(
            paper_id="paper-003",
            title="Test",
            abstract="Abstract",
            authors=["writer-0"],
            body="Body",
            status="submitted",
        )
        tmp_db.create_agent(
            agent_id="writer-0",
            skill_profile="writer",
            personality={"style": "academic"},
        )
        await publish_paper("paper-003", tmp_db, mock_corpus, tmp_logger)

        agent = tmp_db.get_agent("writer-0")
        reputation = json.loads(agent["reputation"])
        assert reputation["papers_published"] == 1

    @pytest.mark.asyncio
    async def test_publish_stores_review_scores(self, tmp_db, tmp_logger, mock_corpus):
        tmp_db.create_paper(
            paper_id="paper-004",
            title="Test",
            abstract="Abs",
            authors=["w-0"],
            body="Body",
            status="submitted",
        )
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                scores={"novelty": 8, "rigor": 7},
                recommendation="accept",
            ),
        ]
        await publish_paper("paper-004", tmp_db, mock_corpus, tmp_logger, reviews=reviews)

        paper = tmp_db.get_paper("paper-004")
        scores = json.loads(paper["review_scores"])
        assert len(scores) == 1
        assert scores[0]["scores"]["novelty"] == 8

    @pytest.mark.asyncio
    async def test_publish_records_citations(self, tmp_db, tmp_logger, mock_corpus):
        """Publishing a paper that cites arXiv and internal papers records citations."""
        body = (
            "We build on the results of arXiv:2301.12345 and paper-aabbccddeeff. "
            "See also arXiv:2305.00001."
        )
        tmp_db.create_paper(
            paper_id="paper-citer000001",
            title="Citing Paper",
            abstract="Cites others",
            authors=["writer-0"],
            body=body,
            status="submitted",
        )

        # Set up mock_corpus.citations as a real CitationTracker
        from paradigm.literature.citations import CitationTracker

        citation_tracker = CitationTracker(tmp_db)
        mock_corpus.citations = citation_tracker

        await publish_paper("paper-citer000001", tmp_db, mock_corpus, tmp_logger)

        refs = citation_tracker.get_references("paper-citer000001")
        cited_ids = {r["cited_paper_id"] for r in refs}
        assert "arXiv:2301.12345" in cited_ids
        assert "paper-aabbccddeeff" in cited_ids
        assert "arXiv:2305.00001" in cited_ids

    @pytest.mark.asyncio
    async def test_publish_nonexistent_paper(self, tmp_db, tmp_logger, mock_corpus):
        with pytest.raises(ValueError, match="Paper not found"):
            await publish_paper("nonexistent", tmp_db, mock_corpus, tmp_logger)


class TestRejectPaper:
    def test_reject_updates_status(self, tmp_db, tmp_logger):
        tmp_db.create_paper(
            paper_id="paper-100",
            title="Bad Paper",
            abstract="Abs",
            authors=["w-0"],
            body="Body",
            status="submitted",
        )
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                weaknesses=["Fundamental flaw"],
                suggestions=["Start over"],
                recommendation="reject",
            ),
        ]
        reject_paper("paper-100", tmp_db, reviews, tmp_logger)

        paper = tmp_db.get_paper("paper-100")
        assert paper["status"] == "rejected"

    def test_reject_creates_graveyard_entry(self, tmp_db, tmp_logger):
        tmp_db.create_paper(
            paper_id="paper-101",
            title="Rejected Paper",
            abstract="Abs",
            authors=["w-0"],
            body="Body",
            status="submitted",
        )
        reviews = [
            PeerReview(
                reviewer_id="r-0",
                weaknesses=["No novelty", "Poor methodology"],
                suggestions=["Use proper controls"],
                recommendation="reject",
            ),
        ]
        reject_paper("paper-101", tmp_db, reviews, tmp_logger)

        # Check graveyard has an entry
        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT * FROM graveyard WHERE type = 'rejected_paper'")
        rows = cursor.fetchall()
        assert len(rows) >= 1
        row = dict(rows[0])
        assert "Rejected Paper" in row["content"]
        assert "No novelty" in row["failure_reason"]

    def test_reject_nonexistent_paper(self, tmp_db, tmp_logger):
        with pytest.raises(ValueError, match="Paper not found"):
            reject_paper("nonexistent", tmp_db, [], tmp_logger)


# --- Engine Integration Tests ---


@pytest.fixture
def mock_config(tmp_path):
    return Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 1,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": True,
            "enable_experimentation": False,
            "max_review_iterations": 1,
            "enable_peer_review": True,
            "num_reviewers": 2,
            "max_revision_rounds": 2,
        },
    )


@pytest.fixture
def mock_config_no_peer_review(tmp_path):
    return Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 1,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": True,
            "enable_experimentation": False,
            "max_review_iterations": 1,
            "enable_peer_review": False,
        },
    )


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


def _make_review_text(scores: dict[str, int], recommendation: str) -> str:
    scores_text = "\n".join(f"{k.title()}: {v}/10" for k, v in scores.items())
    return (
        "## Summary\nThis paper studies stellar convection.\n\n"
        "## Strengths\n- Good methodology\n\n"
        "## Weaknesses\n- Limited scope\n\n"
        "## Questions\n- Why not test other models?\n\n"
        "## Suggestions\n- Add more comparisons\n\n"
        f"## Scores\n{scores_text}\n\n"
        f"## Recommendation\n{recommendation}"
    )


def _make_writing_factory(
    editor_desk_response: str = "## Decision\nsend_to_review\n\n## Reason\nPaper looks good.",
    reviewer_texts: list[str] | None = None,
):
    """Create a factory that returns agents with role-appropriate responses."""
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
        "editor": editor_desk_response,
        "skeptic": "The methodology looks sound but I have concerns about...",
    }

    # Default reviewer texts with high scores (accept)
    if reviewer_texts is None:
        reviewer_texts = [
            _make_review_text(
                {"novelty": 8, "rigor": 7, "clarity": 9, "significance": 7}, "accept"
            ),
            _make_review_text(
                {"novelty": 7, "rigor": 8, "clarity": 8, "significance": 8}, "accept"
            ),
        ]

    review_idx = 0

    def _create_team(roles, skill_mode="default"):
        nonlocal review_idx
        agents = []
        for role in roles:
            if role == "reviewer":
                idx = review_idx % len(reviewer_texts)
                content = reviewer_texts[idx]
                review_idx += 1
            else:
                content = section_responses.get(role, f"Response from {role}")
            agents.append(_make_mock_agent(f"{role}-{len(agents)}", role, content))
        return agents

    factory.create_team = MagicMock(side_effect=_create_team)
    return factory


def _mock_checkpoint_response():
    response = MagicMock()
    response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "hypothesis": "Test hypothesis",
                    "key_findings": ["Finding 1"],
                    "open_questions": ["Question 1"],
                    "next_steps": ["Next step 1"],
                    "conversation_summary": "Agents discussed the topic.",
                }
            )
        )
    ]
    response.usage = MagicMock(input_tokens=200, output_tokens=100)
    return response


class TestEnginePublishedPath:
    """Test the full cycle ending in publication."""

    @pytest.mark.asyncio
    async def test_full_cycle_published(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Full cycle through PUBLISHED with high-scoring reviews."""
        factory = _make_writing_factory()

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

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

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "published"

        paper = tmp_db.get_paper(thread["current_draft_id"])
        assert paper["status"] == "published"
        assert paper["published_at"] is not None

        # Corpus should have received the paper
        mock_corpus.ingest_internal_paper.assert_called_once()


class TestEngineRejectedPath:
    """Test the full cycle ending in rejection."""

    @pytest.mark.asyncio
    async def test_full_cycle_rejected(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Full cycle through REJECTED with low-scoring reviews."""
        low_score_reviews = [
            _make_review_text(
                {"novelty": 2, "rigor": 3, "clarity": 3, "significance": 2}, "reject"
            ),
            _make_review_text(
                {"novelty": 3, "rigor": 2, "clarity": 2, "significance": 3}, "reject"
            ),
        ]
        factory = _make_writing_factory(reviewer_texts=low_score_reviews)

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Bad research topic",
                mode="directed",
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "rejected"

        paper = tmp_db.get_paper(thread["current_draft_id"])
        assert paper["status"] == "rejected"

        # Graveyard should have an entry
        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT * FROM graveyard WHERE type = 'rejected_paper'")
        rows = cursor.fetchall()
        assert len(rows) >= 1


class TestEngineDeskRejection:
    """Test desk rejection path."""

    @pytest.mark.asyncio
    async def test_desk_rejection(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Papers that fail desk review are rejected immediately."""
        factory = _make_writing_factory(
            editor_desk_response="## Decision\ndesk_reject\n\n## Reason\nIncoherent paper."
        )

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Incoherent topic",
                mode="directed",
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "rejected"


class TestEngineRevisionLoop:
    """Test revision loop path."""

    @pytest.mark.asyncio
    async def test_revision_then_accept(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Paper gets revised and then accepted on second review."""
        # First review: major_revision scores, second review: accept scores
        revision_reviews = [
            _make_review_text(
                {"novelty": 5, "rigor": 4, "clarity": 5, "significance": 4},
                "major_revision",
            ),
            _make_review_text(
                {"novelty": 4, "rigor": 5, "clarity": 4, "significance": 5},
                "major_revision",
            ),
        ]
        accept_reviews = [
            _make_review_text(
                {"novelty": 8, "rigor": 7, "clarity": 9, "significance": 7}, "accept"
            ),
            _make_review_text(
                {"novelty": 7, "rigor": 8, "clarity": 8, "significance": 8}, "accept"
            ),
        ]
        # Interleave: first create_team for reviewers returns revision scores,
        # second returns accept scores
        all_review_texts = revision_reviews + accept_reviews
        factory = _make_writing_factory(reviewer_texts=all_review_texts)

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Topic needing revision",
                mode="directed",
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "published"


class TestEnginePeerReviewDisabled:
    """Test with peer review disabled."""

    @pytest.mark.asyncio
    async def test_no_peer_review(
        self, mock_config_no_peer_review, tmp_db, tmp_logger, mock_corpus
    ):
        """When enable_peer_review=False, cycle stops at 'reviewed' status."""
        factory = _make_writing_factory()

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config_no_peer_review,
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
        assert thread["status"] == "reviewed"
