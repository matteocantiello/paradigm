"""Integration tests for orchestration engine."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradigm.agents.base import Agent, AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.logging.events import EventLogger, EventType
from paradigm.orchestrator.engine import (
    MODE_TEAM_ROLES,
    OrchestrationEngine,
)
from paradigm.storage.database import Database


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database."""
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def tmp_logger(tmp_path):
    """Create a temporary event logger."""
    return EventLogger(tmp_path / "events.jsonl")


@pytest.fixture
def mock_config(tmp_path):
    """Create a config with small round counts for testing."""
    return Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 2,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": False,
        },
    )


def _make_mock_agent(agent_id: str, role: str) -> Agent:
    """Create a mock agent that returns canned responses."""
    agent = MagicMock(spec=Agent)
    agent.agent_id = agent_id
    agent.skill_profile = role

    # generate() returns a canned AgentResponse
    response = AgentResponse(
        content=f"Response from {agent_id}: I have ideas about this topic.",
        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
        model="claude-sonnet-4-5-20250929",
    )
    agent.generate = AsyncMock(return_value=response)

    # format_message returns a mock Message-like dict
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


@pytest.fixture
def mock_factory():
    """Create a mock AgentFactory."""
    factory = MagicMock()

    def _create_team(roles, skill_mode="default"):
        return [_make_mock_agent(f"{role}-0", role) for role in roles]

    factory.create_team = MagicMock(side_effect=_create_team)
    return factory


@pytest.fixture
def mock_corpus():
    """Create a mock Corpus."""
    corpus = MagicMock()
    corpus.build_literature_context = AsyncMock(return_value="## Literature\nNo papers found.")
    corpus.search = AsyncMock(return_value=[])
    return corpus


def _mock_checkpoint_response():
    """Build a mock Anthropic response for checkpoint compression."""
    response = MagicMock()
    response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "hypothesis": "Test hypothesis from checkpoint",
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


class TestOrchestrationEngine:
    """Integration tests for the orchestration engine."""

    @pytest.mark.asyncio
    async def test_full_cycle(self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus):
        """Full SEEDING -> IDEATION -> PLANNING cycle with mocked agents."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test stellar convection",
                mode="directed",
            )

        # Thread was created
        assert thread_id.startswith("thread-")
        thread = tmp_db.get_thread(thread_id)
        assert thread is not None

        # Thread reached planning_complete status
        assert thread["status"] == "planning_complete"

        # Phase was updated
        assert thread["current_phase"] == "planning"

        # Agents were called (6 agents * 2 rounds * 2 phases = 24 calls)
        total_generate_calls = sum(a.generate.call_count for a in engine._agents.values())
        assert total_generate_calls == 24  # 6 agents * 2 rounds * 2 phases

        # Token usage was recorded
        usage = tmp_db.get_token_usage(thread_id=thread_id)
        assert usage["total_tokens"] > 0

    @pytest.mark.asyncio
    async def test_thread_creation(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Thread is created with correct metadata."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test topic",
                mode="directed",
                team_roles=["theorist", "analyst"],
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["mode"] == "directed"
        assert thread["title"] == "Test topic"
        participants = json.loads(thread["participants"])
        assert "theorist-0" in participants
        assert "analyst-0" in participants

    @pytest.mark.asyncio
    async def test_phase_transitions_logged(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Phase transitions are logged as events."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test",
                mode="directed",
            )

        events = tmp_logger.read_events(event_type=EventType.PHASE_TRANSITION)
        # seeding + ideation + planning = 3 phase transition events
        assert len(events) >= 3

    @pytest.mark.asyncio
    async def test_checkpoint_saved(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Checkpoints are created and saved to DB."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test",
                mode="directed",
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["checkpoint_summary"] is not None
        assert len(thread["checkpoint_summary"]) > 0

        # Checkpoint events were logged
        events = tmp_logger.read_events(event_type=EventType.CHECKPOINT_CREATED)
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_messages_collected(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Agent messages are collected during rounds."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test",
                mode="directed",
            )

        # Agent message events were logged
        events = tmp_logger.read_events(event_type=EventType.AGENT_MESSAGE)
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_custom_team_roles(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Custom team roles are respected."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test",
                mode="directed",
                team_roles=["theorist", "skeptic"],
            )

        mock_factory.create_team.assert_called_once_with(
            ["theorist", "skeptic"], skill_mode="default"
        )

    @pytest.mark.asyncio
    async def test_explore_mode_team(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Explore mode uses the correct team composition from MODE_TEAM_ROLES."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test exploration",
                mode="explore",
            )

        expected_roles = MODE_TEAM_ROLES["explore"]
        mock_factory.create_team.assert_called_once_with(expected_roles, skill_mode="default")

    @pytest.mark.asyncio
    async def test_directed_mode_team(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Directed mode uses the correct team composition."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test directed",
                mode="directed",
            )

        expected_roles = MODE_TEAM_ROLES["directed"]
        mock_factory.create_team.assert_called_once_with(expected_roles, skill_mode="default")

    @pytest.mark.asyncio
    async def test_hypothesis_mode_team(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Hypothesis mode uses a smaller, focused team."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test hypothesis",
                mode="hypothesis",
            )

        expected_roles = MODE_TEAM_ROLES["hypothesis"]
        mock_factory.create_team.assert_called_once_with(expected_roles, skill_mode="default")

    @pytest.mark.asyncio
    async def test_custom_team_overrides_mode(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Explicit team_roles overrides mode-based defaults."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test custom",
                mode="hypothesis",
                team_roles=["writer", "editor"],
            )

        # Should use the explicit roles, not hypothesis defaults
        mock_factory.create_team.assert_called_once_with(["writer", "editor"], skill_mode="default")

    @pytest.mark.asyncio
    async def test_graveyard_context_in_seeding(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Graveyard entries matching seed prompt are loaded during seeding."""
        # Add a matching graveyard entry (content contains the seed prompt substring)
        tmp_db.add_to_graveyard(
            graveyard_id="grave-test-001",
            entry_type="rejected_paper",
            content="Paper on Test stellar convection was rejected",
            failure_reason="Lack of novelty",
            lessons_learned="Need more original hypotheses about convection",
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
                agent_factory=mock_factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test stellar convection",
                mode="directed",
            )

        # Graveyard context should have been set on the engine
        graveyard_ctx = getattr(engine, "_graveyard_context", "")
        assert "Lessons from Failed Research Attempts" in graveyard_ctx
        assert "Lack of novelty" in graveyard_ctx
        assert "NOT citable" in graveyard_ctx

    @pytest.mark.asyncio
    async def test_hook_continue(self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus):
        """Intervention hook returning 'continue' lets the cycle proceed normally."""
        hook_calls = []

        def hook(thread_id, from_phase, to_phase):
            hook_calls.append((from_phase, to_phase))
            return "continue"

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
                intervention_hook=hook,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test hook",
                mode="directed",
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "planning_complete"
        # Hook was called at least for ideation→planning
        assert ("ideation", "planning") in hook_calls

    @pytest.mark.asyncio
    async def test_hook_abort(self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus):
        """Intervention hook returning 'abort' stops the cycle."""

        def hook(thread_id, from_phase, to_phase):
            return "abort"

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
                intervention_hook=hook,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test abort",
                mode="directed",
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "aborted"

    @pytest.mark.asyncio
    async def test_hook_pause(self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus):
        """Intervention hook returning 'pause' pauses the cycle."""

        def hook(thread_id, from_phase, to_phase):
            return "pause"

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
                intervention_hook=hook,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test pause",
                mode="directed",
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "paused"

    @pytest.mark.asyncio
    async def test_no_hook_default(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Without a hook, cycle proceeds normally (same as 'continue')."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
                # No intervention_hook
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test no hook",
                mode="directed",
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "planning_complete"

    @pytest.mark.asyncio
    async def test_search_requests_processed(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Agent responses with [SEARCH: ...] markers trigger corpus.search()."""
        # Create a factory that returns agents whose responses contain search markers
        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = _make_mock_agent(f"{role}-0", role)
                # First agent includes a search marker in its response
                if role == roles[0]:
                    search_response = AgentResponse(
                        content=(
                            f"Response from {role}-0: [SEARCH: Cepheid period-luminosity relation]"
                        ),
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=search_response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

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

            await engine.run_research_cycle(
                seed_prompt="Test search",
                mode="directed",
            )

        # corpus.search should have been called with the extracted query
        mock_corpus.search.assert_called()
        search_calls = mock_corpus.search.call_args_list
        queries = [call.args[0] if call.args else call.kwargs.get("query") for call in search_calls]
        assert any("Cepheid" in q for q in queries if q)

    @pytest.mark.asyncio
    async def test_search_log_populated(self, mock_config, tmp_db, tmp_logger):
        """_search_log accumulates entries when agents make [SEARCH:] requests."""
        from datetime import UTC, datetime

        from paradigm.literature.arxiv import ArxivPaper

        # Mock corpus that returns actual ArxivPaper objects
        corpus = MagicMock()
        now = datetime.now(UTC)
        mock_paper = ArxivPaper(
            arxiv_id="2401.12345",
            title="Test Paper on Cepheids",
            abstract="Abstract text",
            authors=["Author One", "Author Two"],
            categories=["astro-ph.SR"],
            primary_category="astro-ph.SR",
            published=now,
            updated=now,
            pdf_url="https://arxiv.org/pdf/2401.12345",
            abs_url="https://arxiv.org/abs/2401.12345",
        )
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[mock_paper])

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = _make_mock_agent(f"{role}-0", role)
                if role == roles[0]:
                    response = AgentResponse(
                        content="Ideas [SEARCH: Cepheid period-luminosity]",
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=corpus,
                logger=tmp_logger,
                agent_factory=factory,
            )

            await engine.run_research_cycle(
                seed_prompt="Test search log",
                mode="directed",
            )

        # _search_log should have entries
        assert len(engine._search_log) >= 1
        entry = engine._search_log[0]
        assert entry["query"] == "Cepheid period-luminosity"
        assert entry["phase"] is not None
        assert len(entry["papers"]) == 1
        assert entry["papers"][0]["arxiv_id"] == "2401.12345"
        assert entry["papers"][0]["title"] == "Test Paper on Cepheids"

    @pytest.mark.asyncio
    async def test_save_search_log_writes_file(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """_save_search_log writes a literature_searches.md file."""
        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=MagicMock(),
            )
            engine._thread_id = "thread-test123"

            # Manually populate search log
            engine._search_log = [
                {
                    "query": "Cepheid metallicity",
                    "agent_id": "theorist-0",
                    "phase": "ResearchPhase.IDEATION",
                    "papers": [
                        {
                            "arxiv_id": "2401.12345",
                            "title": "Cepheid PLR",
                            "authors": ["Smith", "Jones"],
                            "year": "2024",
                        },
                    ],
                },
                {
                    "query": "RR Lyrae distance scale",
                    "agent_id": "analyst-0",
                    "phase": "ResearchPhase.PLANNING",
                    "papers": [],
                },
            ]

            # Ensure papers dir exists
            papers_dir = mock_config.storage.papers_dir
            papers_dir.mkdir(parents=True, exist_ok=True)

            engine._save_search_log("paper-test001")

        path = papers_dir / "paper-test001" / "literature_searches.md"
        assert path.exists()
        content = path.read_text()
        assert "# Literature Searches" in content
        assert "Total searches: 2" in content
        assert "Cepheid metallicity" in content
        assert "theorist-0" in content
        assert "IDEATION" in content
        assert "2401.12345" in content
        assert "RR Lyrae distance scale" in content
        assert "No results found." in content

    @pytest.mark.asyncio
    async def test_save_review_log_writes_file(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """_save_review_log writes a reviews.md file."""
        from paradigm.journal.review import PeerReview

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=MagicMock(),
            )
            engine._thread_id = "thread-test456"

            # Manually populate review log
            engine._review_log = [
                {
                    "type": "internal_review",
                    "reviewer_id": "editor-0",
                    "text": "The paper needs more rigor in Section 3.",
                    "iteration": 1,
                },
                {
                    "type": "desk_review",
                    "reviewer_id": "editor-0",
                    "text": "Paper is suitable for review.",
                    "decision": "send_to_review",
                },
                {
                    "type": "peer_review",
                    "reviewer_id": "peer-reviewer-0",
                    "text": "Good paper with minor issues.",
                    "review": PeerReview(
                        reviewer_id="peer-reviewer-0",
                        recommendation="minor_revision",
                        scores={"novelty": 7, "rigor": 6, "clarity": 8, "significance": 7},
                    ),
                },
                {
                    "type": "decision",
                    "decision": "minor_revision",
                },
                {
                    "type": "revision",
                    "reviewer_id": "writer-0",
                },
            ]

            papers_dir = mock_config.storage.papers_dir
            papers_dir.mkdir(parents=True, exist_ok=True)

            engine._save_review_log("paper-test002")

        path = papers_dir / "paper-test002" / "reviews.md"
        assert path.exists()
        content = path.read_text()
        assert "# Review Report" in content
        assert "paper-test002" in content
        assert "Internal Review" in content
        assert "needs more rigor" in content
        assert "Desk Review" in content
        assert "send_to_review" in content
        assert "peer-reviewer-0" in content
        assert "minor_revision" in content
        assert "Novelty: 7/10" in content
        assert "Final decision:" in content
        assert "Revision" in content

    @pytest.mark.asyncio
    async def test_subdirectory_layout_always_used(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Paper files always use subdirectory layout (papers/id/id.md)."""
        # Enable writing to trigger paper save
        mock_config_writing = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(mock_config.storage.data_dir)},
            orchestrator={
                "max_rounds_per_phase": 1,
                "checkpoint_interval": 1,
                "enable_checkpointing": False,
                "enable_writing": True,
                "enable_peer_review": False,
            },
        )

        with patch("paradigm.storage.checkpoints.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_checkpoint_response()
            mock_anthropic.return_value = mock_client

            engine = OrchestrationEngine(
                config=mock_config_writing,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            thread_id = await engine.run_research_cycle(
                seed_prompt="Test subdirectory layout",
                mode="directed",
            )

        # Find the paper_id from the thread
        thread = tmp_db.get_thread(thread_id)
        paper_id = thread.get("current_draft_id")
        assert paper_id is not None

        # Verify subdirectory layout
        papers_dir = mock_config_writing.storage.papers_dir
        paper_dir = papers_dir / paper_id
        assert paper_dir.is_dir()
        assert (paper_dir / f"{paper_id}.md").exists()
        # Flat file should NOT exist
        assert not (papers_dir / f"{paper_id}.md").exists()
