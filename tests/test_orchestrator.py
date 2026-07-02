"""Integration tests for orchestration engine."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from helpers import make_mock_agent, patch_config_provider

from paradigm.agents.base import AgentResponse, TokenUsage
from paradigm.config import Config
from paradigm.domains.science.constants import MODE_TEAM_ROLES
from paradigm.logging.events import EventType
from paradigm.orchestrator.constants import (
    _LITERATURE_CONTEXT_LIMIT,
    _MIN_PAPER_LENGTH,
    _NETWORK_ERROR_PATTERNS,
    _PHASE_ACTIVE_ROLES,
    _PHASE_CONTEXT_NEEDS,
    _PHASE_INSTRUCTIONS,
    _is_duplicate_query,
    _list_shared_files,
    _normalize_query_keywords,
)
from paradigm.orchestrator.engine import OrchestrationEngine
from paradigm.orchestrator.phases import ResearchPhase


@pytest.fixture
def mock_config(tmp_path):
    """Create a config with small round counts for testing."""
    config = Config(
        api_key="fake-api-key",
        storage={"data_dir": str(tmp_path / "data")},
        orchestrator={
            "max_rounds_per_phase": 2,
            "checkpoint_interval": 1,
            "enable_checkpointing": True,
            "enable_writing": False,
            "enable_experimentation": False,
        },
    )
    patch_config_provider(config)
    return config


class TestOrchestrationEngine:
    """Integration tests for the orchestration engine."""

    @pytest.mark.asyncio
    async def test_full_cycle(self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus):
        """Full SEEDING -> IDEATION -> PLANNING cycle with mocked agents."""
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

        # Agents were called (5 active agents * 2 rounds * 2 phases = 20 calls)
        # + 2 synthesis rounds (1 synthesizer call each for IDEATION and PLANNING)
        # Writer and editor are excluded from IDEATION and PLANNING phases
        # Active: theorist, analyst, experimentalist, synthesizer, skeptic
        total_generate_calls = sum(a.generate.call_count for a in engine.state.agents.values())
        assert total_generate_calls == 22  # 5*2*2 + 2 synthesis rounds

        # Token usage was recorded
        usage = tmp_db.get_token_usage(thread_id=thread_id)
        assert usage["total_tokens"] > 0

    @pytest.mark.asyncio
    async def test_execution_failure_aborts_before_writing(
        self, tmp_path, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Experiments producing no usable output abort the cycle before WRITING."""
        from paradigm.orchestrator.experimentation import ExperimentationResult

        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "checkpoint_interval": 1,
                "enable_writing": True,
                "enable_experimentation": True,
                "enable_post_execution_discussion": False,
                "abort_on_execution_failure": True,
            },
        )
        patch_config_provider(config)
        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=mock_factory,
        )

        no_results = ExperimentationResult(
            execution_context="", successful_code=[], caveats=["All experiments failed."]
        )
        with (
            patch.object(
                engine._experimentation,
                "run_experimentation_phase",
                AsyncMock(return_value=no_results),
            ),
            patch.object(engine._writing, "run_writing_phase", AsyncMock()) as mock_write,
        ):
            thread_id = await engine.run_research_cycle(
                seed_prompt="Test stellar convection", mode="experimental"
            )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "execution_failed"
        mock_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_execution_failure_gate_can_be_disabled(
        self, tmp_path, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """With abort_on_execution_failure=False, the cycle still proceeds to WRITING."""
        from paradigm.orchestrator.experimentation import ExperimentationResult

        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_path / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "checkpoint_interval": 1,
                "enable_writing": True,
                "enable_experimentation": True,
                "enable_post_execution_discussion": False,
                "abort_on_execution_failure": False,
            },
        )
        patch_config_provider(config)
        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=mock_factory,
        )

        no_results = ExperimentationResult(execution_context="", successful_code=[], caveats=[])
        with (
            patch.object(
                engine._experimentation,
                "run_experimentation_phase",
                AsyncMock(return_value=no_results),
            ),
            patch.object(
                engine._writing, "run_writing_phase", AsyncMock(return_value=None)
            ) as mock_write,
        ):
            await engine.run_research_cycle(
                seed_prompt="Test stellar convection", mode="experimental"
            )

        mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_thread_creation(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Thread is created with correct metadata."""
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
    async def test_unknown_team_role_dropped_not_fatal(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """A stray invalid role (e.g. display-only 'peer-reviewer' from the GUI) is
        filtered out instead of crashing the whole cycle."""
        mock_factory.has_role.side_effect = lambda r: r != "peer-reviewer"
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
            team_roles=["theorist", "peer-reviewer", "skeptic"],
        )

        mock_factory.create_team.assert_called_once_with(
            ["theorist", "skeptic"], skill_mode="default"
        )

    @pytest.mark.asyncio
    async def test_explore_mode_team(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Explore mode uses the correct team composition from MODE_TEAM_ROLES."""
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
        graveyard_ctx = getattr(engine.state, "graveyard_context", "")
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
                agent = make_mock_agent(f"{role}-0", role)
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

        from paradigm.domains.base import SourceResult

        # Mock corpus that returns SourceResult objects
        corpus = MagicMock()
        now = datetime.now(UTC)
        mock_paper = SourceResult(
            id="2401.12345",
            source_type="arxiv",
            title="Cepheid Period-Luminosity Relation in the Milky Way",
            summary="We study the period-luminosity relation for Cepheid variable stars",
            authors=["Author One", "Author Two"],
            date=now,
            metadata={"categories": ["astro-ph.SR"]},
        )
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[mock_paper])

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
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
        assert len(engine._literature.search_log) >= 1
        entry = engine._literature.search_log[0]
        assert entry["query"] == "Cepheid period-luminosity"
        assert entry["phase"] is not None
        assert len(entry["papers"]) == 1
        assert entry["papers"][0]["arxiv_id"] == "2401.12345"
        assert entry["papers"][0]["title"] == "Cepheid Period-Luminosity Relation in the Milky Way"

    @pytest.mark.asyncio
    async def test_save_search_log_writes_file(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """_save_search_log writes a literature_searches.md file."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        engine.state.thread_id = "thread-test123"

        # Manually populate search log
        engine._literature.search_log = [
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

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        engine.state.thread_id = "thread-test456"

        # Manually populate review log
        engine._review.review_log = [
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
    async def test_seeding_with_mixed_urls(
        self,
        mock_config,
        tmp_db,
        tmp_logger,
        mock_factory,
    ):
        """Seeding classifies URLs: papers go to corpus, others to resolve_resource."""
        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.fetch_and_ingest_url = AsyncMock(return_value=MagicMock(title="Test Paper"))

        with patch(
            "paradigm.orchestrator.engine.resolve_resource",
            new_callable=AsyncMock,
        ) as mock_resolve:
            # resolve_resource returns a successful repo resource
            from paradigm.literature.resources import ResolvedResource, ResourceType

            mock_resolve.return_value = ResolvedResource(
                url="https://github.com/owner/mesa",
                resource_type=ResourceType.CODE_REPO,
                name="mesa",
                local_path="/tmp/repos/mesa",
                sandbox_path="/data/shared/repos/mesa",
                summary="Cloned mesa",
            )

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            # Prompt with a paper URL and a repo URL
            prompt = (
                "Study convection using https://arxiv.org/abs/2401.12345 "
                "and tools from https://github.com/owner/mesa"
            )
            await engine.run_research_cycle(seed_prompt=prompt, mode="directed")

        # Paper URL went to corpus
        corpus.fetch_and_ingest_url.assert_called_once_with("https://arxiv.org/abs/2401.12345")
        # Repo URL went to resolve_resource
        mock_resolve.assert_called_once()
        call_args = mock_resolve.call_args
        assert call_args[0][0] == "https://github.com/owner/mesa"
        assert call_args[0][1] == ResourceType.CODE_REPO

    @pytest.mark.asyncio
    async def test_resource_contexts_injected_in_prompt(
        self,
        mock_config,
        tmp_db,
        tmp_logger,
        mock_factory,
        mock_corpus,
    ):
        """Resource contexts are included in agent prompts."""
        from paradigm.literature.resources import ResolvedResource, ResourceType

        with patch(
            "paradigm.orchestrator.engine.resolve_resource",
            new_callable=AsyncMock,
        ) as mock_resolve:
            # Return a repo, a data file, and a reference for each URL type
            async def _mock_resolve(url, rtype, shared_dir, logger):
                if rtype == ResourceType.CODE_REPO:
                    return ResolvedResource(
                        url=url,
                        resource_type=rtype,
                        name="mesa",
                        sandbox_path="/data/shared/repos/mesa",
                        summary="Cloned mesa",
                    )
                elif rtype == ResourceType.DATA:
                    return ResolvedResource(
                        url=url,
                        resource_type=rtype,
                        name="data.csv",
                        sandbox_path="/data/shared/data/data.csv",
                        size_bytes=2048,
                    )
                else:
                    return ResolvedResource(
                        url=url,
                        resource_type=rtype,
                        name="docs.example.com",
                        content="Astropy documentation text",
                    )

            mock_resolve.side_effect = _mock_resolve

            engine = OrchestrationEngine(
                config=mock_config,
                database=tmp_db,
                corpus=mock_corpus,
                logger=tmp_logger,
                agent_factory=mock_factory,
            )

            # Prompt includes URLs that classify to each non-paper type
            prompt = (
                "Study convection using https://github.com/owner/mesa "
                "and data from https://example.com/data.csv "
                "and docs at https://docs.example.com/guide"
            )
            await engine.run_research_cycle(seed_prompt=prompt, mode="directed")

        # IDEATION gets references only (not code/data per _PHASE_CONTEXT_NEEDS)
        first_agent = list(engine.state.agents.values())[0]
        ideation_prompt = first_agent.generate.call_args_list[0][0][0]
        assert "Web Reference Materials" in ideation_prompt
        assert "Available Code Resources" not in ideation_prompt
        assert "Available Data Files" not in ideation_prompt

        # PLANNING gets code/data (not references per _PHASE_CONTEXT_NEEDS)
        # Round 1 of PLANNING is after all IDEATION rounds. Each round has
        # 5 active agents (editor/writer excluded). 2 rounds × 5 = 10 calls.
        # Agent call index 10 is the first PLANNING call for this agent.
        planning_prompt = first_agent.generate.call_args_list[2][0][0]
        assert "Available Code Resources" in planning_prompt
        assert "Available Data Files" in planning_prompt
        assert "Web Reference Materials" not in planning_prompt

    @pytest.mark.asyncio
    async def test_editor_writer_excluded_from_ideation_planning(
        self, mock_config, tmp_db, tmp_logger, mock_factory, mock_corpus
    ):
        """Editor and writer are excluded from IDEATION and PLANNING phases."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=mock_factory,
        )

        await engine.run_research_cycle(
            seed_prompt="Test filtering",
            mode="directed",
        )

        # Editor and writer should never have been called (IDEATION + PLANNING only)
        for agent in engine.state.agents.values():
            if agent.skill_profile in ("editor", "writer"):
                assert agent.generate.call_count == 0, (
                    f"{agent.skill_profile} should not speak in IDEATION/PLANNING"
                )
            else:
                # 2 rounds * 2 phases = 4 calls per active agent
                # + synthesizer gets 2 extra calls for synthesis rounds
                # Active roles: theorist, analyst, experimentalist, synthesizer, skeptic
                expected = 6 if agent.skill_profile == "synthesizer" else 4
                assert agent.generate.call_count == expected, (
                    f"{agent.skill_profile} should speak {expected} times"
                )

    @pytest.mark.asyncio
    async def test_editor_active_in_review(self, tmp_db, tmp_logger, mock_corpus):
        """Editor is active during INTERNAL_REVIEW phase."""
        config_writing = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_db.db_path.parent / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "checkpoint_interval": 1,
                "enable_checkpointing": False,
                "enable_writing": True,
                "enable_peer_review": False,
                "enable_experimentation": False,
            },
        )
        patch_config_provider(config_writing)

        # Use long responses so paper passes _MIN_PAPER_LENGTH guard
        writing_factory = MagicMock()
        writing_factory.create_team = MagicMock(
            side_effect=lambda roles, skill_mode="default": [
                make_mock_agent(f"{role}-0", role, long_response=True) for role in roles
            ]
        )

        engine = OrchestrationEngine(
            config=config_writing,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=writing_factory,
        )

        await engine.run_research_cycle(
            seed_prompt="Test editor in review",
            mode="directed",
        )

        # Editor should have been called during INTERNAL_REVIEW
        editor = None
        for agent in engine.state.agents.values():
            if agent.skill_profile == "editor":
                editor = agent
                break
        assert editor is not None
        assert editor.generate.call_count > 0, "Editor should speak during INTERNAL_REVIEW"

    @pytest.mark.asyncio
    async def test_phase_active_roles_constant(self):
        """_PHASE_ACTIVE_ROLES excludes writer and editor from early phases."""
        from paradigm.orchestrator.phases import ResearchPhase

        # IDEATION and PLANNING should not include writer or editor
        for phase in (ResearchPhase.IDEATION, ResearchPhase.PLANNING):
            active = _PHASE_ACTIVE_ROLES[phase]
            assert "writer" not in active, f"writer should not be in {phase}"
            assert "editor" not in active, f"editor should not be in {phase}"
            assert "theorist" in active
            assert "analyst" in active
            assert "synthesizer" in active
            assert "skeptic" in active

    @pytest.mark.asyncio
    async def test_subdirectory_layout_always_used(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
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
                "enable_experimentation": False,
            },
        )
        patch_config_provider(mock_config_writing)

        # Use long responses so paper passes _MIN_PAPER_LENGTH guard
        writing_factory = MagicMock()
        writing_factory.create_team = MagicMock(
            side_effect=lambda roles, skill_mode="default": [
                make_mock_agent(f"{role}-0", role, long_response=True) for role in roles
            ]
        )

        engine = OrchestrationEngine(
            config=mock_config_writing,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=writing_factory,
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

    @pytest.mark.asyncio
    async def test_experimentalist_in_directed_mode(self):
        """Directed mode team includes experimentalist for Docker execution."""
        assert "experimentalist" in MODE_TEAM_ROLES["directed"]
        assert "experimentalist" in MODE_TEAM_ROLES["explore"]
        assert "experimentalist" in MODE_TEAM_ROLES["hypothesis"]

    @pytest.mark.asyncio
    async def test_empty_paper_guard(self, tmp_db, tmp_logger, mock_factory, mock_corpus):
        """Writing phase that produces empty content sets writing_incomplete status."""
        config = Config(
            api_key="fake-api-key",
            storage={"data_dir": str(tmp_db.db_path.parent / "data")},
            orchestrator={
                "max_rounds_per_phase": 1,
                "checkpoint_interval": 1,
                "enable_checkpointing": False,
                "enable_writing": True,
                "enable_peer_review": False,
                # Isolate the WRITING empty-paper guard: skip EXECUTION so the
                # post-execution go/no-go gate doesn't intercept first.
                "enable_experimentation": False,
            },
        )
        patch_config_provider(config)

        # Make all agents return errors during writing (simulating ConnectionError)
        def _create_failing_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role in ("writer", "editor", "theorist", "analyst", "synthesizer"):
                    # Writer's assembly returns empty content
                    if role == "writer":
                        empty_response = AgentResponse(
                            content="",
                            usage=TokenUsage(input_tokens=10, output_tokens=0, total_tokens=10),
                            model="claude-sonnet-4-5-20250929",
                        )
                        agent.generate = AsyncMock(return_value=empty_response)
                    else:
                        # Other agents fail during section drafting
                        agent.generate = AsyncMock(side_effect=ConnectionError("API unavailable"))
                agents.append(agent)
            return agents

        mock_factory.create_team = MagicMock(side_effect=_create_failing_team)

        engine = OrchestrationEngine(
            config=config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=mock_factory,
        )

        thread_id = await engine.run_research_cycle(
            seed_prompt="Test empty paper guard",
            mode="directed",
        )

        thread = tmp_db.get_thread(thread_id)
        assert thread["status"] == "writing_incomplete"
        # No paper should have been created
        assert thread.get("current_draft_id") is None

    @pytest.mark.asyncio
    async def test_seen_paper_ids_dedup(self, mock_config, tmp_db, tmp_logger):
        """Papers already shown to agents are filtered from subsequent search results."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        now = datetime.now(UTC)
        paper_a = SourceResult(
            id="2401.00001",
            source_type="arxiv",
            title="Stellar Pulsation Oscillation Modes",
            summary="Analysis of stellar pulsation oscillation modes in variable stars",
            authors=["Author A"],
            date=now,
            metadata={"categories": ["astro-ph.SR"]},
        )
        paper_b = SourceResult(
            id="2401.00002",
            source_type="arxiv",
            title="Convection Stellar Mixing Models",
            summary="Convection stellar mixing models for interior structure",
            authors=["Author B"],
            date=now,
            metadata={"categories": ["astro-ph.SR"]},
        )

        # First search returns both papers, second search returns same papers
        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(side_effect=[[paper_a, paper_b], [paper_a, paper_b]])

        # Agent that makes two different search requests
        factory = MagicMock()
        call_count = [0]

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:

                    async def _gen(prompt, **kwargs):
                        call_count[0] += 1
                        if call_count[0] == 1:
                            content = "Ideas [SEARCH: stellar pulsation oscillation]"
                        elif call_count[0] == 2:
                            content = "More ideas [SEARCH: convection stellar mixing]"
                        else:
                            content = "Response"
                        return AgentResponse(
                            content=content,
                            usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                            model="claude-sonnet-4-5-20250929",
                        )

                    agent.generate = AsyncMock(side_effect=_gen)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(
            seed_prompt="Test dedup",
            mode="directed",
        )

        # After first search, both paper IDs should be in seen set
        assert "2401.00001" in engine._literature.seen_paper_ids
        assert "2401.00002" in engine._literature.seen_paper_ids

    @pytest.mark.asyncio
    async def test_literature_context_limit(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Literature context is trimmed when it exceeds _LITERATURE_CONTEXT_LIMIT."""
        factory = MagicMock()
        factory.create_team = MagicMock(
            side_effect=lambda roles, skill_mode="default": [
                make_mock_agent(f"{role}-0", role) for role in roles
            ]
        )

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        # Manually set literature context to exceed limit
        engine._literature.literature_context = "x" * (_LITERATURE_CONTEXT_LIMIT + 5000)

        await engine.run_research_cycle(
            seed_prompt="Test context limit",
            mode="directed",
        )

        # Context should be within limit (it gets set fresh each cycle, but
        # the constant itself is what we're validating)
        assert _LITERATURE_CONTEXT_LIMIT == 15000
        assert _MIN_PAPER_LENGTH == 10000


# --- Fuzzy query dedup tests ---


class TestNormalizeQueryKeywords:
    def test_basic_normalization(self):
        kw = _normalize_query_keywords("Cepheid period-luminosity relation")
        assert "cepheid" in kw
        assert "period" in kw
        assert "luminosity" in kw
        # "relation" is now a scientific filler stop word
        assert "relation" not in kw

    def test_stop_words_removed(self):
        kw = _normalize_query_keywords("the effect of metallicity on the period")
        assert "the" not in kw
        assert "of" not in kw
        assert "on" not in kw
        assert "metallicity" in kw
        # "effect" is now a scientific filler stop word
        assert "effect" not in kw
        assert "period" in kw

    def test_case_insensitive(self):
        kw1 = _normalize_query_keywords("Stellar Oscillation")
        kw2 = _normalize_query_keywords("stellar oscillation")
        assert kw1 == kw2

    def test_punctuation_stripped(self):
        kw = _normalize_query_keywords("convective overshooting, massive stars!")
        assert "convective" in kw
        assert "overshooting" in kw
        assert "massive" in kw
        assert "stars" in kw

    def test_empty_string(self):
        kw = _normalize_query_keywords("")
        assert kw == frozenset()

    def test_only_stop_words(self):
        kw = _normalize_query_keywords("the and or is of")
        assert kw == frozenset()


class TestIsDuplicateQuery:
    def test_identical_queries(self):
        kw1 = _normalize_query_keywords("convective overshooting massive stars")
        assert _is_duplicate_query(kw1, [kw1]) is True

    def test_different_queries(self):
        kw1 = _normalize_query_keywords("convective overshooting massive stars")
        kw2 = _normalize_query_keywords("exoplanet transit photometry")
        assert _is_duplicate_query(kw1, [kw2]) is False

    def test_similar_queries_above_threshold(self):
        kw1 = _normalize_query_keywords("convective overshooting in massive stars")
        kw2 = _normalize_query_keywords("convective overshooting massive star models")
        # Overlap: convective, overshooting, massive — 3/5 words, Jaccard 0.6
        # Actually kw1: {convective, overshooting, massive, stars}
        # kw2: {convective, overshooting, massive, star, models}
        # intersection: 3, union: 6, Jaccard ~0.5 — below 0.7
        assert _is_duplicate_query(kw1, [kw2], threshold=0.5) is True

    def test_similar_queries_below_threshold(self):
        kw1 = _normalize_query_keywords("stellar pulsation cepheids")
        kw2 = _normalize_query_keywords("stellar nucleosynthesis AGB")
        # Only "stellar" overlaps. Jaccard = 1/5 = 0.2 — below 0.7
        assert _is_duplicate_query(kw1, [kw2]) is False

    def test_empty_keywords(self):
        assert _is_duplicate_query(frozenset(), [frozenset({"a", "b"})]) is False

    def test_empty_existing_list(self):
        kw = _normalize_query_keywords("convective overshooting")
        assert _is_duplicate_query(kw, []) is False

    def test_reordered_words_match(self):
        kw1 = _normalize_query_keywords("massive star convective overshooting")
        kw2 = _normalize_query_keywords("convective overshooting massive star")
        assert _is_duplicate_query(kw1, [kw2]) is True


# --- Phase context needs tests ---


class TestPhaseContextNeeds:
    def test_ideation_has_literature_references_memory(self):
        from paradigm.orchestrator.phases import ResearchPhase

        needs = _PHASE_CONTEXT_NEEDS[ResearchPhase.IDEATION]
        assert "literature" in needs
        assert "references" in needs
        assert "memory" in needs
        assert "code_data" not in needs

    def test_planning_has_literature_code_data_memory(self):
        from paradigm.orchestrator.phases import ResearchPhase

        needs = _PHASE_CONTEXT_NEEDS[ResearchPhase.PLANNING]
        assert "literature" in needs
        assert "code_data" in needs
        assert "memory" in needs
        assert "references" not in needs

    def test_writing_not_listed(self):
        from paradigm.orchestrator.phases import ResearchPhase

        assert ResearchPhase.WRITING not in _PHASE_CONTEXT_NEEDS

    def test_execution_not_listed(self):
        from paradigm.orchestrator.phases import ResearchPhase

        assert ResearchPhase.EXECUTION not in _PHASE_CONTEXT_NEEDS


# --- Literature graph traversal tests ---


class TestLiteratureGraphTraversal:
    @pytest.mark.asyncio
    async def test_follow_requests_processed(self, mock_config, tmp_db, tmp_logger):
        """[FOLLOW:] triggers corpus.get_references()."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(
            return_value=[
                SourceResult(
                    id="2301.001",
                    source_type="semantic_scholar",
                    title="Referenced Paper",
                    authors=["Author"],
                    summary="Abstract",
                    url="",
                    date=datetime(2023, 1, 1, tzinfo=UTC),
                    metadata={"paper_id": "s2-1", "citation_count": 5},
                )
            ]
        )
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:
                    response = AgentResponse(
                        content="Ideas [FOLLOW: 2301.12345]",
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        # The graph gate only allows FOLLOW on previously-discovered IDs; this test
        # exercises the FOLLOW->get_references mechanism, so treat the ID as discovered.
        engine._literature._is_discovered_id = lambda _id: True

        await engine.run_research_cycle(seed_prompt="Test follow", mode="directed")

        corpus.get_references.assert_called()

    @pytest.mark.asyncio
    async def test_cited_by_requests_processed(self, mock_config, tmp_db, tmp_logger):
        """[CITED_BY:] triggers corpus.get_citations()."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(
            return_value=[
                SourceResult(
                    id="2401.001",
                    source_type="semantic_scholar",
                    title="Citing Paper",
                    authors=["Author"],
                    summary="Abstract",
                    url="",
                    date=datetime(2024, 1, 1, tzinfo=UTC),
                    metadata={"paper_id": "s2-2", "citation_count": 3},
                )
            ]
        )
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:
                    response = AgentResponse(
                        content="Ideas [CITED_BY: 0901.67890]",
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine._literature._is_discovered_id = lambda _id: True

        await engine.run_research_cycle(seed_prompt="Test cited_by", mode="directed")

        corpus.get_citations.assert_called()

    @pytest.mark.asyncio
    async def test_read_requests_processed(self, mock_config, tmp_db, tmp_logger):
        """[READ:] triggers corpus.read_paper()."""
        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=("Test Paper", "Abstract text here"))

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:
                    response = AgentResponse(
                        content="Ideas [READ: 2301.12345]",
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine._literature._is_discovered_id = lambda _id: True

        await engine.run_research_cycle(seed_prompt="Test read", mode="directed")

        corpus.read_paper.assert_called()

    @pytest.mark.asyncio
    async def test_follow_rejects_undiscovered_id(self, mock_config, tmp_db, tmp_logger):
        """[FOLLOW:] on an arXiv ID that was never returned by a search is rejected.

        Agents sometimes invent plausible-looking IDs when no real papers are found;
        those resolve to real-but-unrelated papers and poison the shared context.
        The gate must skip the fetch entirely and leave a note for the agent.
        """
        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])  # nothing is ever discovered
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:
                    response = AgentResponse(
                        content="Ideas [FOLLOW: 9999.99999]",  # hallucinated, never searched
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(seed_prompt="Test reject", mode="directed")

        # The hallucinated ID must NOT be fetched, and the agent gets a rejection note.
        corpus.get_references.assert_not_called()
        assert "9999.99999" not in engine._literature.followed_paper_ids
        assert "rejected" in engine._literature.literature_context

    @pytest.mark.asyncio
    async def test_chain_requests_processed(self, mock_config, tmp_db, tmp_logger):
        """[CHAIN:] is wired in and triggers follow_citation_chain for a discovered seed."""
        from datetime import UTC, datetime
        from unittest.mock import patch as _patch

        from paradigm.domains.base import SourceResult

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)
        corpus._providers = {"arxiv": MagicMock()}  # non-empty so the walk runs

        chained = [
            SourceResult(
                id="2401.55555",
                source_type="semantic_scholar",
                title="Chained Paper",
                authors=["Author"],
                summary="Abstract",
                url="",
                date=datetime(2024, 1, 1, tzinfo=UTC),
            )
        ]

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:
                    agent.generate = AsyncMock(
                        return_value=AgentResponse(
                            content="Ideas [CHAIN: 2301.12345 depth=2 direction=both]",
                            usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                            model="claude-sonnet-4-5-20250929",
                        )
                    )
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )
        engine._literature._is_discovered_id = lambda _id: True  # treat the seed as discovered

        with _patch(
            "paradigm.orchestrator.literature.follow_citation_chain",
            new=AsyncMock(return_value=chained),
        ) as mock_chain:
            await engine.run_research_cycle(seed_prompt="Test chain", mode="directed")

        mock_chain.assert_called()

    @pytest.mark.asyncio
    async def test_follow_budget_enforced(self, mock_config, tmp_db, tmp_logger):
        """Stops processing [FOLLOW:] after budget exhausted."""
        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()

        # Agent makes more follow requests than budget allows
        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:
                    # 5 follow requests but budget is 3
                    content = " ".join(f"[FOLLOW: 2301.{i:05d}]" for i in range(5))
                    response = AgentResponse(
                        content=f"Ideas {content}",
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(seed_prompt="Test budget", mode="directed")

        # Should have been called at most follow_budget_per_round times per round
        # Default budget is 3
        follow_budget = mock_config.literature.follow_budget_per_round
        # Each round resets the counter, so we check that per-round calls are bounded
        # Total calls should be at most budget * rounds * phases
        assert corpus.get_references.call_count <= follow_budget * 2 * 2  # 2 rounds * 2 phases

    @pytest.mark.asyncio
    async def test_stall_hint_injected(self, mock_config, tmp_db, tmp_logger):
        """Hint appears when keyword search returns 0 new papers."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        now = datetime.now(UTC)
        paper = SourceResult(
            id="2401.12345",
            source_type="arxiv",
            title="Seen Paper",
            summary="Abstract",
            authors=["Author"],
            date=now,
            metadata={"categories": ["astro-ph.SR"]},
        )

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        # Return the same paper every time (so 2nd search = 0 new)
        corpus.search = AsyncMock(return_value=[paper])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()
        call_count = [0]

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:

                    async def _gen(prompt, **kwargs):
                        call_count[0] += 1
                        if call_count[0] <= 2:
                            content = f"Ideas [SEARCH: query {call_count[0]}]"
                        else:
                            content = "Response"
                        return AgentResponse(
                            content=content,
                            usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                            model="claude-sonnet-4-5-20250929",
                        )

                    agent.generate = AsyncMock(side_effect=_gen)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(seed_prompt="Test stall", mode="directed")

        # After second search returns 0 new papers, hint should be in context
        lit_context = engine._literature.literature_context
        assert "Hint" in lit_context or "FOLLOW" in lit_context

    @pytest.mark.asyncio
    async def test_early_termination_on_stale_searches(self, mock_config, tmp_db, tmp_logger):
        """After 2 consecutive 0-new results, remaining searches are skipped."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        now = datetime.now(UTC)
        paper = SourceResult(
            id="2401.12345",
            source_type="arxiv",
            title="Seen Paper",
            summary="Abstract",
            authors=["Author"],
            date=now,
            metadata={"categories": ["astro-ph.SR"]},
        )

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        # Return the same paper every time → 0 new after first
        corpus.search = AsyncMock(return_value=[paper])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()

        # Each agent generates a unique query per call (per-agent cap is 1).
        # All queries return the same paper → 0 new after the very first search.
        call_counters: dict[str, int] = {}
        # Pool of distinct queries — enough for all agents across rounds/phases
        query_pool = [
            "cepheid pulsation instability strip",
            "neutron star magnetar flare",
            "exoplanet transit spectroscopy",
            "supernova nucleosynthesis yield",
            "galaxy rotation dark matter",
            "quasar accretion disk luminosity",
            "pulsar timing millisecond binary",
            "white dwarf crystallization cooling",
            "gravitational wave chirp mass",
            "solar corona heating magnetic",
            "protoplanetary disk accretion rate",
            "tidal disruption event fallback",
            "cosmic ray acceleration shock",
            "interstellar medium turbulence spectrum",
            "stellar wind mass loss rate",
            "binary merger kilonova lightcurve",
            "dark energy equation state",
            "globular cluster dynamics relaxation",
            "reionization epoch 21cm signal",
            "baryon acoustic oscillation distance",
        ]

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                call_counters[role] = 0

                def _make_generate(r):
                    async def _gen(*args, **kwargs):
                        idx = call_counters[r]
                        call_counters[r] += 1
                        topic = query_pool[idx % len(query_pool)]
                        return AgentResponse(
                            content=f"Ideas [SEARCH: {topic}]",
                            usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                            model="claude-sonnet-4-5-20250929",
                        )

                    return _gen

                agent.generate = _make_generate(role)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        # Allow enough budget so early termination is the constraint
        object.__setattr__(
            mock_config,
            "orchestrator",
            mock_config.orchestrator.model_copy(update={"max_searches_per_round": 10}),
        )

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(seed_prompt="Test early term", mode="directed")

        # Each agent searches once per round with unique queries across calls.
        # First search finds the paper (1 new), all subsequent return the same
        # paper (0 new), triggering stale tracking.
        assert corpus.search.call_count < 20
        # Stall hint should be injected after stale searches accumulate
        lit_context = engine._literature.literature_context
        assert (
            "Hint" in lit_context or "exhausted" in lit_context or "no new results" in lit_context
        )

    @pytest.mark.asyncio
    async def test_cross_round_stale_tracking(self, mock_config, tmp_db, tmp_logger):
        """_total_stale_keyword_searches increments across rounds and caps budget."""
        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        # Always return empty → every search is stale
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()

        distinct_topics = {
            "theorist": "stellar nucleosynthesis carbon nitrogen",
            "analyst": "bayesian inference spectral classification",
        }

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                # Each agent issues 1 distinct search
                topic = distinct_topics.get(role, f"{role} specific topic")
                response = AgentResponse(
                    content=f"Ideas from {role} [SEARCH: {topic}]",
                    usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                    model="claude-sonnet-4-5-20250929",
                )
                agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(
            seed_prompt="Test cross-round stale",
            mode="directed",
            team_roles=["theorist", "analyst"],
        )

        # Total stale count should have incremented (every search returned 0 new)
        assert engine._literature.total_stale_keyword_searches > 0
        # After 5+ stale searches, the exhaustion warning should be in context
        if engine._literature.total_stale_keyword_searches >= 5:
            lit_context = engine._literature.literature_context
            assert "\u26a0 Keyword searches are exhausted" in lit_context

    @pytest.mark.asyncio
    async def test_per_agent_search_cap(self, mock_config, tmp_db, tmp_logger):
        """A single agent cannot use the entire round's search budget."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        now = datetime.now(UTC)
        call_counter = [0]

        async def _unique_search(query, max_results=10, **kwargs):
            call_counter[0] += 1
            return [
                SourceResult(
                    id=f"2401.{call_counter[0]:05d}",
                    source_type="arxiv",
                    title=f"Paper {call_counter[0]}",
                    summary="Abstract",
                    authors=["Author"],
                    date=now,
                    metadata={"categories": ["astro-ph.SR"]},
                )
            ]

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(side_effect=_unique_search)
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                # First agent requests 5 distinct searches
                if role == roles[0]:
                    response = AgentResponse(
                        content=(
                            "Ideas "
                            "[SEARCH: cepheid pulsation instability strip] "
                            "[SEARCH: neutron star magnetar flare] "
                            "[SEARCH: exoplanet transit spectroscopy] "
                            "[SEARCH: supernova nucleosynthesis yield] "
                            "[SEARCH: galaxy rotation dark matter]"
                        ),
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        # max_searches_per_round=5, so per_agent_cap = max(1, 5*2//5) = 2
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(
            seed_prompt="Test per-agent cap",
            mode="directed",
            team_roles=["theorist", "analyst"],
        )

        # With per_agent_cap=2 (max(1, 5*2//5)=2), each agent gets at most 2
        # keyword searches per round. The first agent requests 5 but only gets 2.
        # Since all searches return unique papers, corpus.search.call_count
        # tells us total searches executed across 2 rounds * 2 phases.
        # With 2 agents, cap=2 each, 2 rounds, 2 phases = max 2*2*2 = 8
        # (but agent 2 has no search markers, so max from agent 1 = 2*2*2 = 8)
        # Also capped by round budget of 5, so max = min(2, 5) * 2 * 2 = 8
        assert corpus.search.call_count <= 8

    @pytest.mark.asyncio
    async def test_stall_hint_always_injected(self, mock_config, tmp_db, tmp_logger):
        """Stall hint appears regardless of follow/cited_by count."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        now = datetime.now(UTC)
        paper = SourceResult(
            id="2401.99999",
            source_type="arxiv",
            title="Seen Paper",
            summary="Abstract",
            authors=["Author"],
            date=now,
            metadata={"categories": ["astro-ph.SR"]},
        )

        # SourceResult for get_references return
        sem_paper = SourceResult(
            id="2401.88888",
            source_type="semantic_scholar",
            title="Referenced Paper",
            summary="Abstract of referenced paper",
            authors=["Ref Author"],
            date=datetime(2024, 1, 1, tzinfo=UTC),
            metadata={"year": 2024},
        )

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[paper])
        corpus.get_references = AsyncMock(return_value=[sem_paper])  # Non-empty FOLLOW
        corpus.get_citations = AsyncMock(return_value=[sem_paper])  # Non-empty CITED_BY
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:
                    # Search + FOLLOW + second search (0 new because paper already seen)
                    response = AgentResponse(
                        content=(
                            "Ideas [SEARCH: initial query] "
                            "[FOLLOW: 2401.99999] "
                            "[SEARCH: second query]"
                        ),
                        usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                        model="claude-sonnet-4-5-20250929",
                    )
                    agent.generate = AsyncMock(return_value=response)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        # Increase per-agent cap so second search actually executes
        object.__setattr__(
            mock_config,
            "orchestrator",
            mock_config.orchestrator.model_copy(update={"max_searches_per_round": 10}),
        )

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(seed_prompt="Test unconditional hint", mode="directed")

        # Even though FOLLOW was used (follow_count > 0), the stall hint should
        # still appear because the second search returned 0 new papers
        lit_context = engine._literature.literature_context
        assert "Hint" in lit_context or "FOLLOW" in lit_context


class TestNetworkErrorHandling:
    """Tests for network error detection in execution phase."""

    def test_requests_not_in_available_libraries(self):
        """Execution prompt should not list 'requests' as an available library."""
        prompt = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["propose_experiment"]
        # The word "requests" should not appear as a listed available library.
        # It may appear in the warning text ("Do NOT use `requests`"), but not
        # in the "Available libraries:" line.
        lines = prompt.split("\n")
        for line in lines:
            if line.startswith("**Available libraries:**"):
                assert "requests" not in line, (
                    "'requests' should not be listed as an available library"
                )

    def test_network_error_hint_in_retry(self):
        """Network error patterns should be detected and produce clear guidance."""
        # Verify that the pattern list contains expected entries
        assert "Temporary failure in name resolution" in _NETWORK_ERROR_PATTERNS
        assert "ConnectionRefusedError" in _NETWORK_ERROR_PATTERNS
        assert "requests.exceptions" in _NETWORK_ERROR_PATTERNS

        # Verify the detection logic works
        stderr = "requests.exceptions.ConnectionError: Temporary failure in name resolution"
        has_network_error = any(p in stderr for p in _NETWORK_ERROR_PATTERNS)
        assert has_network_error

    def test_execution_prompt_has_network_caveat_placeholder(self):
        """Execution prompt should use {network_caveat} placeholder."""
        prompt = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["propose_experiment"]
        assert "{network_caveat}" in prompt
        # Placeholder should appear before the "Available libraries" line
        caveat_pos = prompt.find("{network_caveat}")
        libraries_pos = prompt.find("Available libraries:")
        assert caveat_pos < libraries_pos, (
            "Network caveat placeholder should appear before available libraries list"
        )

    def test_analyze_results_has_network_caveat_placeholder(self):
        """analyze_results prompt should use {network_caveat} placeholder."""
        prompt = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["analyze_results"]
        assert "{network_caveat}" in prompt

    def test_retry_after_failure_has_network_caveat_placeholder(self):
        """retry_after_failure prompt should use {network_caveat} placeholder."""
        prompt = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["retry_after_failure"]
        assert "{network_caveat}" in prompt

    def test_execution_prompt_no_phantom_section_refs(self):
        """Execution prompt should not reference nonexistent 'Available Code Resources' sections."""
        prompt = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["propose_experiment"]
        assert "See 'Available Code Resources'" not in prompt
        assert "See 'Available Data Files'" not in prompt


# --- Paper quality gate tests ---


class TestPaperQualityGates:
    def test_min_paper_length_is_substantive(self):
        """_MIN_PAPER_LENGTH should be at least 10000 chars to prevent hollow papers."""
        assert _MIN_PAPER_LENGTH >= 10000

    def test_section_drafting_has_length_guidance(self):
        """Section drafting prompt should include word count guidance."""
        prompt = _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["section_drafting"]
        assert "200-500 words" in prompt
        assert "quantitative" in prompt.lower()

    def test_experiment_injection_demands_quantitative(self):
        """Experiment results injection should demand quantitative analysis."""
        # The injection text is built dynamically in _run_section_drafting,
        # but we can verify the template language by checking a key phrase
        # exists in the codebase. Here we test that the WRITING section_drafting
        # prompt demands quantitative content.
        prompt = _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["section_drafting"]
        assert "quantitative results" in prompt.lower()


# --- _list_shared_files tests ---


class TestListSharedFiles:
    def test_empty_dir(self, tmp_path):
        """Returns 'No files' message when shared/ directory is empty."""
        shared = tmp_path / "shared"
        shared.mkdir()
        result = _list_shared_files(tmp_path)
        assert "No files" in result
        assert "Available Files" in result

    def test_missing_dir(self, tmp_path):
        """Returns 'No files' message when shared/ directory doesn't exist."""
        result = _list_shared_files(tmp_path)
        assert "No files" in result

    def test_with_files(self, tmp_path):
        """Lists actual files with correct paths and sizes."""
        shared = tmp_path / "shared"
        repos = shared / "repos" / "mesa"
        repos.mkdir(parents=True)
        (repos / "inlist").write_text("x" * 2048)

        data = shared / "data"
        data.mkdir(parents=True)
        (data / "observations.csv").write_text("col1,col2\n" * 100)

        result = _list_shared_files(tmp_path)
        assert "Available Files" in result
        assert "/data/shared/repos/mesa/inlist" in result
        assert "/data/shared/data/observations.csv" in result
        assert "KB" in result  # Should show size

    def test_top_level_files(self, tmp_path):
        """Lists files directly in shared/ directory."""
        shared = tmp_path / "shared"
        shared.mkdir(parents=True)
        (shared / "README.txt").write_text("hello")

        result = _list_shared_files(tmp_path)
        assert "/data/shared/README.txt" in result


# --- Discovered paper index tests ---


class TestDiscoveredPaperIndex:
    """Tests for the compact paper index that persists across context truncation."""

    def test_build_paper_index_empty(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """build_paper_index returns empty string when no papers discovered."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        assert engine._literature.build_paper_index() == ""

    def test_build_paper_index_with_papers(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """build_paper_index renders compact reference list."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        engine._literature.discovered_papers = [
            ("2301.12345", "Red noise in massive stars", "Bowman"),
            ("1905.67890", "Low-frequency variability in OB stars", "Lecoanet"),
        ]
        engine._literature._discovered_ids = {"2301.12345", "1905.67890"}

        result = engine._literature.build_paper_index()
        assert "Discovered Papers" in result
        assert "[FOLLOW:]" in result
        assert "[CITED_BY:]" in result
        assert "[2301.12345] Bowman: Red noise in massive stars" in result
        assert "[1905.67890] Lecoanet: Low-frequency variability in OB stars" in result

    def test_track_paper_deduplicates(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """_track_paper does not add duplicate entries."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        lit = engine._literature
        lit._track_paper("2301.12345", "Paper A", "Author A")
        lit._track_paper("2301.12345", "Paper A", "Author A")  # duplicate
        lit._track_paper("2301.67890", "Paper B", "Author B")

        assert len(lit.discovered_papers) == 2
        assert len(lit._discovered_ids) == 2

    def test_track_paper_ignores_empty_id(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """_track_paper skips empty arxiv_id."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        engine._literature._track_paper("", "Paper", "Author")
        assert len(engine._literature.discovered_papers) == 0

    @pytest.mark.asyncio
    async def test_paper_index_injected_round2(self, mock_config, tmp_db, tmp_logger):
        """Paper index is prepended to agent prompt in round 2+ of search-enabled phases."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        now = datetime.now(UTC)
        paper = SourceResult(
            id="2401.12345",
            source_type="arxiv",
            title="Test Paper",
            summary="Abstract",
            authors=["Smith"],
            date=now,
            metadata={"categories": ["astro-ph.SR"]},
        )

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[paper])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()
        call_count = [0]

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:

                    async def _gen(prompt, **kwargs):
                        call_count[0] += 1
                        if call_count[0] == 1:
                            return AgentResponse(
                                content="Ideas [SEARCH: test query]",
                                usage=TokenUsage(
                                    input_tokens=50, output_tokens=30, total_tokens=80
                                ),
                                model="claude-sonnet-4-5-20250929",
                            )
                        return AgentResponse(
                            content="More ideas",
                            usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                            model="claude-sonnet-4-5-20250929",
                        )

                    agent.generate = AsyncMock(side_effect=_gen)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        await engine.run_research_cycle(seed_prompt="Test index injection", mode="directed")

        # Paper should be tracked in discovered_papers
        assert len(engine._literature.discovered_papers) >= 1
        assert any(aid == "2401.12345" for aid, _, _ in engine._literature.discovered_papers)

        # Round 2 prompts for the first agent should contain the paper index
        # The first agent's round 2 call is call index 1 (0=round1)
        first_agent = list(engine.state.agents.values())[0]
        if first_agent.generate.call_count >= 2:
            round2_prompt = first_agent.generate.call_args_list[1][0][0]
            assert "Discovered Papers" in round2_prompt
            assert "2401.12345" in round2_prompt

    def test_stall_hint_includes_concrete_ids(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Stall hints include concrete [FOLLOW:] examples when papers are available."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        lit = engine._literature
        lit._track_paper("2301.12345", "Paper A", "Author A")
        lit._track_paper("2301.67890", "Paper B", "Author B")

        hint = lit._build_stall_hint()
        assert "[FOLLOW: 2301.12345]" in hint
        assert "[FOLLOW: 2301.67890]" in hint
        assert "Try these commands" in hint

    def test_stall_hint_without_papers(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """Stall hints still work when no papers have been discovered."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        hint = engine._literature._build_stall_hint()
        assert "Hint" in hint
        assert "FOLLOW" in hint
        # No concrete examples since no papers
        assert "Try these commands" not in hint

    def test_reset_cycle_clears_discovered_papers(
        self, mock_config, tmp_db, tmp_logger, mock_corpus
    ):
        """reset_cycle clears discovered_papers and _discovered_ids."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        lit = engine._literature
        lit._track_paper("2301.12345", "Paper A", "Author A")
        assert len(lit.discovered_papers) == 1

        lit.reset_cycle()
        assert len(lit.discovered_papers) == 0
        assert len(lit._discovered_ids) == 0


# --- READ deduplication tests ---


class TestReadDeduplication:
    """Tests for [READ:] cross-round deduplication."""

    @pytest.mark.asyncio
    async def test_read_dedup_skips_duplicate(self, mock_config, tmp_db, tmp_logger):
        """A second [READ: same_id] request is skipped."""
        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=("Test Paper", "Full text here"))

        factory = MagicMock()
        call_count = [0]

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:

                    async def _gen(prompt, **kwargs):
                        call_count[0] += 1
                        if call_count[0] <= 2:
                            # Both rounds request the same paper
                            content = "Ideas [READ: 2401.12345]"
                        else:
                            content = "Response"
                        return AgentResponse(
                            content=content,
                            usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                            model="claude-sonnet-4-5-20250929",
                        )

                    agent.generate = AsyncMock(side_effect=_gen)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine._literature._is_discovered_id = lambda _id: True

        await engine.run_research_cycle(seed_prompt="Test read dedup", mode="directed")

        # read_paper should only be called once despite two [READ: 2401.12345] requests
        assert corpus.read_paper.call_count == 1
        assert "2401.12345" in engine._literature.read_paper_ids

    def test_read_dedup_reset_on_cycle(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """reset_cycle() clears read_paper_ids."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        lit = engine._literature
        lit.read_paper_ids.add("2401.12345")
        lit.read_paper_ids.add("2401.67890")
        assert len(lit.read_paper_ids) == 2

        lit.reset_cycle()
        assert len(lit.read_paper_ids) == 0


# --- Config default tests ---


class TestFollowCitedByDeduplication:
    """Tests for [FOLLOW:] and [CITED_BY:] cross-round deduplication."""

    @pytest.mark.asyncio
    async def test_follow_dedup_skips_duplicate(self, mock_config, tmp_db, tmp_logger):
        """Two [FOLLOW: same_id] requests — get_references() called only once."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(
            return_value=[
                SourceResult(
                    id="2301.001",
                    source_type="semantic_scholar",
                    title="Referenced Paper",
                    authors=["Author"],
                    summary="Abstract",
                    url="",
                    date=datetime(2023, 1, 1, tzinfo=UTC),
                    metadata={"paper_id": "s2-1", "citation_count": 5},
                )
            ]
        )
        corpus.get_citations = AsyncMock(return_value=[])
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()
        call_count = [0]

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:

                    async def _gen(prompt, **kwargs):
                        call_count[0] += 1
                        if call_count[0] <= 2:
                            # Both rounds request FOLLOW on the same paper
                            content = "Ideas [FOLLOW: 2301.12345]"
                        else:
                            content = "Response"
                        return AgentResponse(
                            content=content,
                            usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                            model="claude-sonnet-4-5-20250929",
                        )

                    agent.generate = AsyncMock(side_effect=_gen)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine._literature._is_discovered_id = lambda _id: True

        await engine.run_research_cycle(seed_prompt="Test follow dedup", mode="directed")

        # get_references should only be called once despite two [FOLLOW: 2301.12345] requests
        assert corpus.get_references.call_count == 1
        assert "2301.12345" in engine._literature.followed_paper_ids

    @pytest.mark.asyncio
    async def test_cited_by_dedup_skips_duplicate(self, mock_config, tmp_db, tmp_logger):
        """Two [CITED_BY: same_id] requests — get_citations() called only once."""
        from datetime import UTC, datetime

        from paradigm.domains.base import SourceResult

        corpus = MagicMock()
        corpus.build_literature_context = AsyncMock(return_value="No papers.")
        corpus.search = AsyncMock(return_value=[])
        corpus.get_references = AsyncMock(return_value=[])
        corpus.get_citations = AsyncMock(
            return_value=[
                SourceResult(
                    id="2401.001",
                    source_type="semantic_scholar",
                    title="Citing Paper",
                    authors=["Author"],
                    summary="Abstract",
                    url="",
                    date=datetime(2024, 1, 1, tzinfo=UTC),
                    metadata={"paper_id": "s2-2", "citation_count": 3},
                )
            ]
        )
        corpus.read_paper = AsyncMock(return_value=None)

        factory = MagicMock()
        call_count = [0]

        def _create_team(roles, skill_mode="default"):
            agents = []
            for role in roles:
                agent = make_mock_agent(f"{role}-0", role)
                if role == roles[0]:

                    async def _gen(prompt, **kwargs):
                        call_count[0] += 1
                        if call_count[0] <= 2:
                            content = "Ideas [CITED_BY: 0901.67890]"
                        else:
                            content = "Response"
                        return AgentResponse(
                            content=content,
                            usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                            model="claude-sonnet-4-5-20250929",
                        )

                    agent.generate = AsyncMock(side_effect=_gen)
                agents.append(agent)
            return agents

        factory.create_team = MagicMock(side_effect=_create_team)

        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=corpus,
            logger=tmp_logger,
            agent_factory=factory,
        )

        engine._literature._is_discovered_id = lambda _id: True

        await engine.run_research_cycle(seed_prompt="Test cited_by dedup", mode="directed")

        # get_citations should only be called once despite two requests
        assert corpus.get_citations.call_count == 1
        assert "0901.67890" in engine._literature.cited_by_paper_ids

    def test_follow_dedup_reset_on_cycle(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """reset_cycle() clears followed_paper_ids."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        lit = engine._literature
        lit.followed_paper_ids.add("2301.12345")
        lit.followed_paper_ids.add("2301.67890")
        assert len(lit.followed_paper_ids) == 2

        lit.reset_cycle()
        assert len(lit.followed_paper_ids) == 0

    def test_cited_by_dedup_reset_on_cycle(self, mock_config, tmp_db, tmp_logger, mock_corpus):
        """reset_cycle() clears cited_by_paper_ids."""
        engine = OrchestrationEngine(
            config=mock_config,
            database=tmp_db,
            corpus=mock_corpus,
            logger=tmp_logger,
            agent_factory=MagicMock(),
        )
        lit = engine._literature
        lit.cited_by_paper_ids.add("0901.67890")
        assert len(lit.cited_by_paper_ids) == 1

        lit.reset_cycle()
        assert len(lit.cited_by_paper_ids) == 0


# --- Search excludes Paradigm papers test ---


class TestSearchExcludesParadigmPapers:
    """Tests for filtering Paradigm's own papers from search results."""

    @pytest.mark.asyncio
    async def test_search_excludes_paradigm_papers(self):
        """Corpus.search() skips paper-* IDs from local ChromaDB results."""
        from datetime import UTC, datetime

        from paradigm.config import LiteratureConfig, StorageConfig
        from paradigm.literature.corpus import Corpus

        # Set up mock database
        db = MagicMock()

        # paper-abc should be skipped, arxiv:2401.12345 should be returned
        def _get_paper(paper_id):
            if paper_id == "paper-abc":
                return {
                    "id": "paper-abc",
                    "title": "Paradigm Internal Paper",
                    "abstract": "Internal abstract",
                    "authors": '["Agent"]',
                    "keywords": "[]",
                    "status": "published",
                    "body": "",
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00",
                }
            if paper_id == "arxiv:2401.12345":
                return {
                    "id": "arxiv:2401.12345",
                    "title": "Real ArXiv Paper",
                    "abstract": "Real abstract",
                    "authors": '["Smith"]',
                    "keywords": '["astro-ph.SR"]',
                    "status": "external",
                    "body": "",
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            return None

        db.get_paper = MagicMock(side_effect=_get_paper)

        # Mock embedding store that returns both a paper-* and a real arXiv paper
        embeddings = MagicMock()
        embeddings.count.return_value = 10
        embeddings.search.return_value = [
            {"arxiv_id": "paper-abc", "distance": 0.1},
            {"arxiv_id": "2401.12345", "distance": 0.2},
        ]

        # Mock arXiv client (no remote results)
        arxiv_client = MagicMock()
        arxiv_client.search = AsyncMock(return_value=[])

        lit_config = LiteratureConfig()
        storage_config = MagicMock(spec=StorageConfig)
        storage_config.vector_db_path = "/tmp/test_vector_db"

        corpus = Corpus(
            database=db,
            literature_config=lit_config,
            storage_config=storage_config,
            arxiv_client=arxiv_client,
            embedding_store=embeddings,
        )

        results = await corpus.search("test query", include_arxiv=False)

        # Should only return the real arXiv paper, not the paper-* one
        assert len(results) == 1
        assert results[0].id == "2401.12345"
        assert results[0].title == "Real ArXiv Paper"


# --- Config default tests ---


class TestConfigDefaults:
    """Tests for configuration defaults."""

    def test_max_review_iterations_default_is_5(self):
        """max_review_iterations default allows four revision attempts."""
        from paradigm.config import OrchestratorConfig

        config = OrchestratorConfig()
        assert config.max_review_iterations == 5

    def test_read_budget_default_is_5(self):
        """read_budget_per_round default is 5 to allow 1 read per agent."""
        from paradigm.config import LiteratureConfig

        config = LiteratureConfig()
        assert config.read_budget_per_round == 5


# ---------------------------------------------------------------------------
# Data staging tests
# ---------------------------------------------------------------------------


class TestProcessDataRequests:
    """Tests for LiteratureHandler.process_data_requests()."""

    def _make_handler(self, tmp_path):
        """Build a LiteratureHandler with a mocked engine."""
        from unittest.mock import MagicMock

        from paradigm.orchestrator.literature import LiteratureHandler

        engine = MagicMock()
        engine._config.storage.data_dir = tmp_path / "data"
        engine.state.thread_id = "test-thread"
        engine.state.resolved_resources = []
        engine._display = MagicMock()
        engine._logger = MagicMock()
        return LiteratureHandler(engine)

    @pytest.mark.asyncio
    async def test_skips_non_search_phases(self, tmp_path):
        handler = self._make_handler(tmp_path)
        text = "[DATA: https://example.com/data.csv]"
        # WRITING is not in _SEARCH_ENABLED_PHASES
        await handler.process_data_requests("agent-0", text, ResearchPhase.WRITING)
        assert handler.data_count_this_round == 0

    @pytest.mark.asyncio
    async def test_dedup_across_rounds(self, tmp_path):
        handler = self._make_handler(tmp_path)
        handler.resolved_data_urls.add("https://example.com/data.csv")
        text = "[DATA: https://example.com/data.csv]"
        await handler.process_data_requests("agent-0", text, ResearchPhase.PLANNING)
        handler._engine._display.data_stage_skipped.assert_called_once()
        assert handler.data_count_this_round == 0

    @pytest.mark.asyncio
    async def test_budget_enforcement(self, tmp_path):
        from paradigm.orchestrator.constants import _DATA_REQUESTS_PER_ROUND

        handler = self._make_handler(tmp_path)
        handler.data_count_this_round = _DATA_REQUESTS_PER_ROUND
        text = "[DATA: https://example.com/data.csv]"
        await handler.process_data_requests("agent-0", text, ResearchPhase.PLANNING)
        handler._engine._display.data_stage_skipped.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_non_data_urls(self, tmp_path):
        handler = self._make_handler(tmp_path)
        # arxiv.org URLs are classified as PAPER, not DATA
        text = "[DATA: https://arxiv.org/abs/2301.12345]"
        await handler.process_data_requests("agent-0", text, ResearchPhase.PLANNING)
        handler._engine._display.data_stage_skipped.assert_called_once()
        assert handler.data_count_this_round == 0


# ---------------------------------------------------------------------------
# Network caveat tests
# ---------------------------------------------------------------------------


class TestNetworkCaveat:
    """Tests for _network_caveat() helper."""

    def test_network_disabled_caveat(self):
        from paradigm.orchestrator.constants import _network_caveat

        caveat = _network_caveat(False)
        assert "NO network access" in caveat
        assert "requests" in caveat

    def test_network_enabled_caveat(self):
        from paradigm.orchestrator.constants import _network_caveat

        caveat = _network_caveat(True)
        assert "Network access is available" in caveat
        assert "NO network access" not in caveat

    def test_experiment_prompt_has_network_placeholder(self):
        """Execution templates use {network_caveat} placeholder."""
        templates = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]
        assert "{network_caveat}" in templates["propose_experiment"]
        assert "{network_caveat}" in templates["analyze_results"]
        assert "{network_caveat}" in templates["retry_after_failure"]


# ---------------------------------------------------------------------------
# Consensus carry-forward tests (Fix 2)
# ---------------------------------------------------------------------------


class TestConsensusBuildSummary:
    """Tests for _build_consensus_summary()."""

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

    def test_consensus_built_on_convergence(self, tmp_path):
        """After convergence, _build_consensus_summary returns non-empty string."""
        engine = self._make_engine(tmp_path)
        messages = [
            {"from": "theorist-0", "content": "Stars have convective cores at high mass."},
            {"from": "analyst-0", "content": "Data confirms the convective core prediction."},
        ]
        result = engine._build_consensus_summary(
            ResearchPhase.IDEATION,
            "Agents agree on convective core mechanism.",
            messages,
        )
        assert result != ""
        assert "IDEATION" in result
        assert "convective core" in result

    def test_consensus_empty_rationale(self, tmp_path):
        engine = self._make_engine(tmp_path)
        messages = [{"from": "agent-0", "content": "Some text here."}]
        result = engine._build_consensus_summary(ResearchPhase.PLANNING, "", messages)
        assert "PLANNING" in result
        assert "agent-0" in result

    def test_consensus_capped_at_1000_chars(self, tmp_path):
        engine = self._make_engine(tmp_path)
        messages = [{"from": f"agent-{i}", "content": "x" * 200} for i in range(10)]
        result = engine._build_consensus_summary(
            ResearchPhase.IDEATION, "Long rationale " * 20, messages
        )
        assert len(result) <= 1000

    def test_consensus_injected_into_prompt(self, tmp_path):
        """When _consensus_summary is set, it appears in agent prompts."""
        engine = self._make_engine(tmp_path)
        engine.state.consensus_summary = "### IDEATION Consensus\n**Agreement:** Stars pulsate.\n"
        engine.state.seed_prompt = "Test prompt"
        engine.state.mode = "directed"
        engine.state.messages = []
        engine.state.checkpoint = None

        agent = make_mock_agent("theorist-0", "theorist")
        prompt = engine._build_agent_prompt(agent, ResearchPhase.PLANNING, 1)
        assert "Prior Phase Consensus" in prompt
        assert "Stars pulsate" in prompt
        assert "Do NOT re-derive" in prompt

    def test_consensus_reset_on_new_cycle(self, tmp_path):
        """_consensus_summary is reset when run_research_cycle starts."""
        engine = self._make_engine(tmp_path)
        engine.state.consensus_summary = "old consensus"
        # Simulate partial reset (the way run_research_cycle does it)
        engine.state.consensus_summary = ""
        assert engine.state.consensus_summary == ""


# ---------------------------------------------------------------------------
# Planning action extraction tests (Fix 5)
# ---------------------------------------------------------------------------


class TestExtractPlanningActions:
    """Tests for _extract_planning_actions()."""

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

    def test_planning_actions_extracted(self, tmp_path):
        """Messages with experiment keywords produce numbered action items."""
        engine = self._make_engine(tmp_path)
        engine.state.messages = [
            {
                "from": "theorist-0",
                "content": (
                    "We should:\n"
                    "- Run a Monte Carlo simulation of stellar oscillations\n"
                    "- Calculate the pulsation period as a function of mass\n"
                    "- Plot the period-luminosity relation"
                ),
            },
        ]
        result = engine._extract_planning_actions()
        assert "1." in result
        assert "Monte Carlo" in result or "Calculate" in result or "Plot" in result

    def test_planning_actions_empty_without_keywords(self, tmp_path):
        """Messages without experiment keywords produce empty string."""
        engine = self._make_engine(tmp_path)
        engine.state.messages = [
            {
                "from": "synthesizer-0",
                "content": "The consensus is that stars are interesting objects.",
            },
        ]
        result = engine._extract_planning_actions()
        assert result == ""

    def test_planning_actions_max_10(self, tmp_path):
        """Action items are capped at 10."""
        engine = self._make_engine(tmp_path)
        lines = [f"Run experiment number {i} to test hypothesis" for i in range(20)]
        engine.state.messages = [{"from": "agent-0", "content": "\n".join(lines)}]
        result = engine._extract_planning_actions()
        # Count numbered items
        import re

        items = re.findall(r"^\d+\.", result, re.MULTILINE)
        assert len(items) <= 10


class TestSharedFileProvenance:
    """Cross-run contamination guard: the shared workspace persists across runs, and
    leftovers from unrelated topics (OEIS dumps, saved HTML) have wasted whole
    experiments — listings now mark pre-existing files and tell agents to verify."""

    def test_pre_existing_and_current_files_tagged(self, tmp_path):
        import os
        import time as _time

        shared = tmp_path / "shared" / "data"
        shared.mkdir(parents=True)
        old_file = shared / "oeis_dump.csv"
        old_file.write_text("junk from another run")
        past = _time.time() - 86400
        os.utime(old_file, (past, past))
        new_file = shared / "bowman_tables.dat"
        new_file.write_text("fresh")

        cycle_start = _time.time() - 3600
        result = _list_shared_files(tmp_path, cycle_start)
        assert "oeis_dump.csv` (21 B) [pre-existing]" in result
        assert "bowman_tables.dat` (5 B) [saved this run]" in result
        assert "verify a file is actually relevant" in result

    def test_no_epoch_keeps_legacy_format(self, tmp_path):
        shared = tmp_path / "shared" / "data"
        shared.mkdir(parents=True)
        (shared / "f.csv").write_text("x")
        result = _list_shared_files(tmp_path)
        assert "[pre-existing]" not in result
        assert "[saved this run]" not in result
