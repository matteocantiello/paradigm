"""Main orchestration engine for research cycles."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from paradigm.agents.base import Agent
from paradigm.agents.factory import AgentFactory
from paradigm.config import Config
from paradigm.journal.publication import publish_paper
from paradigm.knowledge.world_model_handler import WorldModelHandler
from paradigm.literature.corpus import Corpus
from paradigm.literature.prompt_utils import extract_urls
from paradigm.literature.resources import (
    ResolvedResource,
    ResourceType,
    build_code_context,
    build_data_context,
    build_reference_context,
    classify_resource,
    resolve_resource,
)
from paradigm.logging.events import EventLogger, EventType
from paradigm.orchestrator.citation_handler import CitationHandler
from paradigm.orchestrator.constants import (
    _CHALLENGE_INSTRUCTION,
    _CONVERGENCE_CHECK_PHASES,
    _CONVERGENCE_CHECK_PROMPT,
    _DEBATE_ENABLED_PHASES,
    _GENERAL_LATER_ROUND_REINFORCEMENT,
    _KNOWLEDGE_TAG_INSTRUCTION,
    _MODE_PROMPT_OVERRIDES,
    _MODE_SYNTHESIS_OVERRIDES,
    _PHASE_ACTIVE_ROLES,
    _PHASE_CONTEXT_NEEDS,
    _PHASE_INSTRUCTIONS,
    _RECENT_MESSAGES_LIMIT,
    _SEARCH_ENABLED_PHASES,
    _SYNTHESIS_CLOSING_TEMPLATES,
    InterventionHook,
)
from paradigm.orchestrator.debate import DebateHandler
from paradigm.orchestrator.experimentation import ExperimentationHandler
from paradigm.orchestrator.human_gate import build_provenance, decide_human_gate
from paradigm.orchestrator.literature import LiteratureHandler
from paradigm.orchestrator.memory import MemoryHandler
from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.preregistration import PreRegistrationHandler
from paradigm.orchestrator.review import ReviewHandler
from paradigm.orchestrator.scheduler import Scheduler
from paradigm.orchestrator.state import ResearchState
from paradigm.orchestrator.verification import VerificationKernel
from paradigm.orchestrator.writing import WritingHandler
from paradigm.storage.checkpoints import CheckpointManager
from paradigm.storage.database import Database

if TYPE_CHECKING:
    from paradigm.display import DisplayManager


class OrchestrationEngine:
    """Orchestrates multi-agent research cycles through structured phases."""

    def __init__(
        self,
        config: Config,
        database: Database,
        corpus: Corpus,
        logger: EventLogger,
        agent_factory: AgentFactory,
        intervention_hook: InterventionHook | None = None,
        memory_store: Any | None = None,
        display: DisplayManager | None = None,
        domain_profile: Any | None = None,
        pause_gate: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the orchestration engine.

        Args:
            config: Application configuration.
            database: Database for persistence.
            corpus: Literature corpus for context.
            logger: Event logger.
            agent_factory: Factory for creating agents.
            intervention_hook: Optional callback invoked before certain phase transitions.
                Returns "continue", "pause", or "abort".
            memory_store: Optional AgentMemoryStore for cross-cycle episodic memory.
            display: Optional DisplayManager for terminal output.
            domain_profile: Optional DomainProfile. If None, loaded from config.domain.
        """
        self._config = config
        self._db = database
        self._corpus = corpus
        self._logger = logger
        self._factory = agent_factory
        self._intervention_hook = intervention_hook
        self._memory_store = memory_store
        self._profile = domain_profile
        # Optional async gate (supplied by the backend) that blocks while the
        # session is paused. Awaited at round boundaries. No-op for the CLI.
        self._pause_gate = pause_gate
        if display is not None:
            self._display = display
        else:
            from paradigm.display import DisplayManager

            self._display = DisplayManager(verbose=True)
        _default_provider = config.get_provider()
        self._checkpoint_mgr = CheckpointManager(
            database=database,
            provider=_default_provider,
            compression_model=_default_provider.default_model,
            event_logger=logger,
        )

        # Per-cycle mutable state (reset at start of each research cycle)
        self.state = ResearchState()

        # Handler delegates
        self._literature = LiteratureHandler(self)
        self._debate = DebateHandler(self)
        self._writing = WritingHandler(self)
        self._review = ReviewHandler(self)
        self._citation_handler = CitationHandler(self)
        self._experimentation = ExperimentationHandler(self)
        self._memory = MemoryHandler(self)
        self._world_model = WorldModelHandler(self)
        self._prereg = PreRegistrationHandler(self)
        self._verification = VerificationKernel(self)

        # Lazy import to avoid circular dependency (tournament_handler → constants → engine)
        from paradigm.knowledge.tournament_handler import TournamentHandler

        self._tournament = TournamentHandler(self)

    def _emit_knowledge_update(self) -> None:
        """Broadcast the current knowledge architecture state via the display adapter."""
        kwargs: dict[str, Any] = {}

        # World model
        wm = self.state.world_model
        if wm is not None:
            snap = wm.to_snapshot()
            kwargs["entities"] = list(snap.get("entities", {}).values())
            kwargs["relationships"] = list(snap.get("relationships", {}).values())
            kwargs["hypotheses"] = list(snap.get("hypotheses", {}).values())
            kwargs["evidence"] = list(snap.get("evidence", {}).values())
            kwargs["open_questions"] = list(snap.get("open_questions", {}).values())
            kwargs["research_goals"] = list(snap.get("research_goals", {}).values())
            kwargs["world_model_summary"] = wm.summarize_state()

        # Evidence graph
        eg = self.state.evidence_graph
        if eg is not None:
            eg_snap = eg.to_snapshot()
            kwargs["conflicts"] = list(eg_snap.get("conflicts", {}).values())
            kwargs["assumptions"] = list(eg_snap.get("assumptions", {}).values())
            kwargs["provenance_chains"] = list(eg_snap.get("provenance_chains", {}).values())
            kwargs["evidence_landscape_summary"] = eg.summarize_evidence_landscape()

        # Tournament
        t_data = self._tournament.get_tournament_data()
        if t_data is not None:
            kwargs["tournament_rankings"] = t_data["rankings"]
            kwargs["matchup_results"] = t_data["matchup_results"]
            kwargs["tournament_summary"] = t_data.get("summary", "")
            kwargs["tournament_status"] = "completed"

        self._display.knowledge_updated(**kwargs)

    def _get_phase_active_roles(self, phase: ResearchPhase) -> set[str] | None:
        """Get the set of active roles for a given phase.

        Checks domain profile phase_active_roles first, then falls back
        to the hardcoded _PHASE_ACTIVE_ROLES from constants.

        Args:
            phase: The research phase.

        Returns:
            Set of active role names, or None if all roles are active.
        """
        if self._profile is not None and self._profile.phase_active_roles is not None:
            phase_key = phase.value
            roles = self._profile.phase_active_roles.get(phase_key)
            if roles is not None:
                return set(roles)
            return None
        return _PHASE_ACTIVE_ROLES.get(phase)

    async def run_research_cycle(
        self,
        seed_prompt: str,
        mode: str = "directed",
        team_roles: list[str] | None = None,
    ) -> str:
        """Run a full research cycle: SEEDING -> IDEATION -> PLANNING -> WRITING -> REVIEW -> PEER REVIEW.

        Args:
            seed_prompt: The research question or topic.
            mode: Operating mode (directed, explore, etc.).
            team_roles: Agent roles to include. Defaults to profile-defined roles.

        Returns:
            Thread ID of the completed cycle.
        """
        self.state = ResearchState(seed_prompt=seed_prompt, mode=mode)
        if team_roles is None:
            if self._profile is not None and self._profile.default_roles:
                # Use domain profile for team composition
                default_fallback = list(next(iter(self._profile.default_roles.values()), []))
                team_roles = list(self._profile.default_roles.get(mode, default_fallback))
            else:
                # Fallback to hardcoded science defaults
                from paradigm.domains.science.constants import (
                    DEFAULT_TEAM_ROLES,
                    MODE_TEAM_ROLES,
                )

                team_roles = list(MODE_TEAM_ROLES.get(mode, DEFAULT_TEAM_ROLES))

        # Reset handler state for new cycle
        self._literature.reset_cycle()
        self._debate.reset_cycle()
        self._review.reset_cycle()

        # Create agent team
        agents = self._factory.create_team(team_roles, skill_mode="default")
        self.state.agents = {a.agent_id: a for a in agents}

        # Live token streaming (opt-in): wire each agent's stream side-channel to
        # the display so the GUI animates output token-by-token. No-op for the CLI.
        if self._config.display.stream_tokens:
            _min_chars = self._config.display.stream_chunk_min_chars
            for agent in agents:
                agent.set_stream_sink(
                    self._make_stream_sink(agent.skill_profile), min_chars=_min_chars
                )

        # Phase 1: SEEDING
        self._display.phase_transition(ResearchPhase.SEEDING)
        self.state.thread_id = await self._run_seeding_phase(seed_prompt, mode)

        # Initialize phase manager (starts at SEEDING, transition to IDEATION)
        self.state.phase_manager = PhaseManager(ResearchPhase.SEEDING)

        # Seed discovery via Perplexity (optional, pre-populates literature context)
        if self._config.citation.enable_seed_discovery:
            try:
                n = await self._literature.run_seed_discovery(seed_prompt)
                if n > 0:
                    self._display.seed_discovery_complete(n)
            except Exception as e:
                self._logger.log_error(e, thread_id=self.state.thread_id)
                self._display.seed_discovery_error(e)

        # Initialize world model (if enabled)
        if self._config.knowledge.enable_world_model:
            self.state.world_model = self._world_model.initialize_world_model()

        # Initialize evidence graph (if enabled)
        if self._config.knowledge.enable_evidence_graph:
            self.state.evidence_graph = self._world_model.initialize_evidence_graph()

        # Emit initial knowledge state (empty but signals feature is enabled)
        if self.state.world_model is not None or self.state.evidence_graph is not None:
            self._emit_knowledge_update()

        # Phase 2: IDEATION
        max_rounds = self._config.orchestrator.max_rounds_per_phase
        checkpoint_interval = self._config.orchestrator.checkpoint_interval
        agent_count = len(self.state.agents)

        # 1E: problem-selection human gate (default-off).
        if self._handle_gate_decision(
            await self._human_gate("problem_selection", payload=f"Problem: {seed_prompt[:200]}")
        ):
            return self.state.thread_id

        self.state.phase_manager.transition_to(ResearchPhase.IDEATION)
        self._log_phase_transition(ResearchPhase.SEEDING, ResearchPhase.IDEATION)
        active_ideation = self._get_phase_active_roles(ResearchPhase.IDEATION)
        active_ideation_count = (
            sum(1 for a in self.state.agents.values() if a.skill_profile in active_ideation)
            if active_ideation
            else agent_count
        )
        self._display.phase_transition(
            "IDEATION",
            max_rounds=max_rounds,
            active_agents=active_ideation_count,
            total_agents=agent_count,
        )
        await self._run_phase(
            ResearchPhase.IDEATION,
            max_rounds=max_rounds,
            checkpoint_interval=checkpoint_interval,
        )
        # Hypothesis tournament (optional, runs before synthesis)
        if self._config.knowledge.enable_hypothesis_tournament:
            winners = await self._tournament.run_tournament()
            if winners:
                # Carry winners forward so PRE_REGISTRATION (1A) can freeze rules for them.
                self.state.selected_hypotheses = list(winners)
                self._emit_knowledge_update()
                await self._run_tournament_synthesis(winners)
            else:
                await self._run_synthesis_round(ResearchPhase.IDEATION)
        else:
            await self._run_synthesis_round(ResearchPhase.IDEATION)

        # Novelty check (optional, after IDEATION)
        if self._config.citation.enable_novelty_check:
            try:
                novelty = await self._citation_handler.check_novelty(
                    seed_prompt, self._config.citation.novelty_mode
                )
                if not novelty.is_novel:
                    self._display.warning(
                        f"Novelty check: idea may not be novel "
                        f"(confidence: {novelty.confidence:.0%}, "
                        f"{novelty.papers_found} related papers found)"
                    )
            except Exception as e:
                self._logger.log_error(e, thread_id=self.state.thread_id)

        # Phase 3: PLANNING (intervention check)
        intervention = await self._check_intervention("ideation", "planning")
        if intervention == "abort":
            self._db.update_thread(self.state.thread_id, status="aborted")
            self._display.phase_aborted()
            return self.state.thread_id
        if intervention == "pause":
            self._db.update_thread(self.state.thread_id, status="paused")
            self._display.phase_paused()
            return self.state.thread_id

        self.state.phase_manager.transition_to(ResearchPhase.PLANNING)
        self._log_phase_transition(ResearchPhase.IDEATION, ResearchPhase.PLANNING)
        self.state.messages = []  # Reset messages for new phase
        active_planning = self._get_phase_active_roles(ResearchPhase.PLANNING)
        active_planning_count = (
            sum(1 for a in self.state.agents.values() if a.skill_profile in active_planning)
            if active_planning
            else agent_count
        )
        self._display.phase_transition(
            "PLANNING",
            max_rounds=max_rounds,
            active_agents=active_planning_count,
            total_agents=agent_count,
        )
        await self._run_phase(
            ResearchPhase.PLANNING,
            max_rounds=max_rounds,
            checkpoint_interval=checkpoint_interval,
        )
        await self._run_synthesis_round(ResearchPhase.PLANNING)

        # Extract action items from PLANNING for EXECUTION (Fix 5)
        self.state.planning_action_items = self._extract_planning_actions()

        # Phase 3.5: EXECUTION (optional — only when experimentalist present + sandbox enabled)
        should_experiment = (
            self._config.orchestrator.enable_experimentation
            and self._config.sandbox.enabled
            and self._find_agent_by_role("experimentalist") is not None
        )
        if should_experiment:
            intervention = await self._check_intervention("planning", "execution")
            if intervention == "abort":
                self._db.update_thread(self.state.thread_id, status="aborted")
                self._display.phase_aborted()
                return self.state.thread_id
            if intervention == "pause":
                self._db.update_thread(self.state.thread_id, status="paused")
                self._display.phase_paused()
                return self.state.thread_id

            # Phase 3.4: PRE_REGISTRATION (1A, optional) — freeze falsifiable
            # predictions before execution so results can't be reinterpreted later.
            if self._config.knowledge.enable_preregistration:
                self.state.phase_manager.transition_to(ResearchPhase.PRE_REGISTRATION)
                self._log_phase_transition(
                    ResearchPhase.PLANNING, ResearchPhase.PRE_REGISTRATION
                )
                self._display.phase_transition("PRE_REGISTRATION")
                frozen_rules = await self._prereg.run_freeze()
                if not frozen_rules and self._config.knowledge.prereg_on_empty == "blocking":
                    self._db.update_thread(self.state.thread_id, status="prereg_failed")
                    self._display.phase_aborted()
                    self._print_token_summary()
                    return self.state.thread_id
                # 1E: pre-registration human gate (default-off).
                gate_payload = f"{len(frozen_rules)} prediction(s) frozen before execution"
                if self._handle_gate_decision(
                    await self._human_gate("pre_registration", payload=gate_payload)
                ):
                    return self.state.thread_id
                self.state.phase_manager.transition_to(ResearchPhase.EXECUTION)
                self._log_phase_transition(
                    ResearchPhase.PRE_REGISTRATION, ResearchPhase.EXECUTION
                )
            else:
                self.state.phase_manager.transition_to(ResearchPhase.EXECUTION)
                self._log_phase_transition(ResearchPhase.PLANNING, ResearchPhase.EXECUTION)
            self.state.messages = []
            self._display.phase_transition("EXECUTION")
            exp_result = await self._experimentation.run_experimentation_phase()
            self.state.execution_context = exp_result.execution_context
            self.state.execution_caveats = exp_result.caveats
            self.state.execution_figures = exp_result.execution_figures
            self.state.successful_code = exp_result.successful_code
            self.state.experiment_metadata = exp_result.experiment_metadata

            # Pre-registration verdicts (1A): evaluate frozen rules against the
            # captured experiment output. Verdicts feed the writing Fact Sheet so
            # refuted hypotheses are reported honestly (and are publishable).
            if self._config.knowledge.enable_preregistration and self.state.registered_rules:
                verdicts = self._prereg.evaluate(exp_result.experiment_metadata)
                for v in verdicts:
                    self._display.info(
                        f"Pre-registration verdict [{v['verdict']}]: {v['detail']}"
                    )

            # Go/no-go gate: if experiments were attempted but none produced usable
            # output, a data-driven paper is impossible. Stop before WRITING rather
            # than burning ~1M tokens on a paper the internal editor will reject for
            # "reporting failed experiments as results". (successful_code excludes
            # vacuous runs, which are reclassified to FAILURE upstream.)
            if (
                self._config.orchestrator.abort_on_execution_failure
                and not exp_result.successful_code
            ):
                self._db.update_thread(self.state.thread_id, status="execution_failed")
                self._display.execution_failed_abort(exp_result.caveats)
                self._print_token_summary()
                return self.state.thread_id

            # Phase 3.6: VERIFICATION (1B, optional) — re-execute results in a fresh
            # sandbox; demote anything that does not reproduce so WRITING can't use it.
            if self._config.orchestrator.enable_verification and self.state.successful_code:
                self.state.phase_manager.transition_to(ResearchPhase.VERIFICATION)
                self._log_phase_transition(ResearchPhase.EXECUTION, ResearchPhase.VERIFICATION)
                self._display.phase_transition("VERIFICATION")
                records = await self._verification.verify_experiments()
                demoted = VerificationKernel.apply_gate(self, records)
                if demoted:
                    self._display.info(
                        f"Verification demoted {demoted} unreproduced experiment(s)."
                    )
                if (
                    self._config.orchestrator.abort_on_verification_failure
                    and not self.state.successful_code
                ):
                    self._db.update_thread(self.state.thread_id, status="verification_failed")
                    self._display.execution_failed_abort(
                        ["No experiments reproduced under verification."]
                    )
                    self._print_token_summary()
                    return self.state.thread_id
                # 1E: final-verification human gate (default-off).
                accepted = sum(1 for r in records if r.status == "accepted")
                if self._handle_gate_decision(
                    await self._human_gate(
                        "final_verification",
                        payload=f"{accepted}/{len(records)} experiment(s) reproduced",
                    )
                ):
                    return self.state.thread_id

        # Phase 3.75: POST_EXECUTION discussion (optional — after experimentation)
        ran_post_execution = False
        if (
            should_experiment
            and self.state.execution_context
            and self._config.orchestrator.enable_post_execution_discussion
        ):
            self.state.phase_manager.transition_to(ResearchPhase.POST_EXECUTION)
            self._log_phase_transition(ResearchPhase.EXECUTION, ResearchPhase.POST_EXECUTION)
            self.state.messages = []
            # Shorter discussion: cap at 2 rounds
            post_exec_rounds = min(2, max_rounds)
            active_post_exec = self._get_phase_active_roles(ResearchPhase.POST_EXECUTION)
            active_post_exec_count = (
                sum(1 for a in self.state.agents.values() if a.skill_profile in active_post_exec)
                if active_post_exec
                else agent_count
            )
            self._display.phase_transition(
                "POST_EXECUTION",
                max_rounds=post_exec_rounds,
                active_agents=active_post_exec_count,
                total_agents=agent_count,
            )
            await self._run_phase(
                ResearchPhase.POST_EXECUTION,
                max_rounds=post_exec_rounds,
                checkpoint_interval=checkpoint_interval,
            )
            await self._run_synthesis_round(ResearchPhase.POST_EXECUTION)
            if self.state.world_model is not None:
                self._emit_knowledge_update()
            ran_post_execution = True
            # Capture POST_EXECUTION discussion summary for WRITING
            self.state.post_execution_summary = self._build_post_execution_summary()

        # Phase 4: WRITING (optional, controlled by config)
        if self._config.orchestrator.enable_writing:
            if ran_post_execution:
                from_phase = ResearchPhase.POST_EXECUTION
                from_label = "post_execution"
            elif should_experiment:
                from_phase = ResearchPhase.EXECUTION
                from_label = "execution"
            else:
                from_phase = ResearchPhase.PLANNING
                from_label = "planning"

            # Intervention check before WRITING
            intervention = await self._check_intervention(from_label, "writing")
            if intervention == "abort":
                self._db.update_thread(self.state.thread_id, status="aborted")
                self._display.phase_aborted()
                return self.state.thread_id
            if intervention == "pause":
                self._db.update_thread(self.state.thread_id, status="paused")
                self._display.phase_paused()
                return self.state.thread_id

            self.state.phase_manager.transition_to(ResearchPhase.WRITING)
            self._log_phase_transition(from_phase, ResearchPhase.WRITING)
            self.state.messages = []
            self._display.phase_transition("WRITING")
            paper_draft = await self._writing.run_writing_phase()

            # Guard: if writing failed (empty/too short paper), skip all review phases
            if paper_draft is None:
                self._display.writing_failed_skip_review()
                # Save auxiliary files even on failure (search log is still useful)
                thread = self._db.get_thread(self.state.thread_id)
                paper_id = thread.get("current_draft_id") if thread else None
                if paper_id:
                    self._save_auxiliary_files(paper_id)
                self._print_token_summary()
                return self.state.thread_id

            # 1E: record provenance once a paper exists (only when gates/verification/
            # pre-registration were in play, so default runs are unchanged).
            if (
                self._config.orchestrator.human_gate_mode != "off"
                or self.state.verification_records
                or self.state.registered_rules
            ):
                self._record_provenance()

            # Phase 5: INTERNAL REVIEW
            self.state.phase_manager.transition_to(ResearchPhase.INTERNAL_REVIEW)
            self._log_phase_transition(ResearchPhase.WRITING, ResearchPhase.INTERNAL_REVIEW)
            self.state.messages = []
            self._display.phase_transition("INTERNAL_REVIEW")
            await self._review.run_review_phase(paper_draft)

            # Check if internal review ended without acceptance (editor rejected the
            # paper, or revisions never converged within the iteration budget).
            thread = self._db.get_thread(self.state.thread_id)
            review_status = thread.get("status") if thread else None
            if review_status in ("review_rejected", "revision_exhausted"):
                self._display.writing_failed_review_exhausted(review_status)
                paper_id = thread.get("current_draft_id") if thread else None
                if paper_id:
                    self._save_auxiliary_files(paper_id)
                self._print_token_summary()
                return self.state.thread_id

            # Phase 6: PEER REVIEW PIPELINE (optional)
            if self._config.orchestrator.enable_peer_review:
                # Intervention check before SUBMITTED
                intervention = await self._check_intervention("internal", "submitted")
                if intervention == "abort":
                    self._db.update_thread(self.state.thread_id, status="aborted")
                    self._display.phase_aborted()
                    return self.state.thread_id
                if intervention == "pause":
                    self._db.update_thread(self.state.thread_id, status="paused")
                    self._display.phase_paused()
                    return self.state.thread_id

                accepted = await self._review.run_submission_phase(paper_draft)
                if accepted:
                    decision, reviews = await self._review.run_peer_review_phase(paper_draft)
                    revision_count = 0
                    max_revisions = self._config.orchestrator.max_revision_rounds
                    while (
                        decision in ("minor_revision", "major_revision")
                        and revision_count < max_revisions
                    ):
                        paper_draft = await self._review.run_revision_phase(paper_draft, reviews)
                        decision, reviews = await self._review.run_peer_review_phase(paper_draft)
                        revision_count += 1

                    thread = self._db.get_thread(self.state.thread_id)
                    paper_id = thread["current_draft_id"] if thread else None
                    if paper_id and decision in ("accept", "minor_revision"):
                        await publish_paper(paper_id, self._db, self._corpus, self._logger, reviews)
                        self._db.update_thread(self.state.thread_id, status="published")
                        self._display.paper_published()
                    elif paper_id:
                        from paradigm.journal.publication import reject_paper

                        reject_paper(paper_id, self._db, reviews, self._logger)
                        self._db.update_thread(self.state.thread_id, status="rejected")
                        self._display.paper_rejected()
                else:
                    # Desk rejected
                    self._db.update_thread(self.state.thread_id, status="rejected")
            else:
                self._db.update_thread(self.state.thread_id, status="reviewed")
        else:
            self._db.update_thread(self.state.thread_id, status="planning_complete")

        # Save auxiliary files (search log, review report)
        thread = self._db.get_thread(self.state.thread_id)
        paper_id = thread.get("current_draft_id") if thread else None
        if paper_id:
            self._save_auxiliary_files(paper_id)

        # Display token usage summary
        self._print_token_summary()

        # Generate agent episodic memories via reflection
        await self._memory.run_memory_generation()

        return self.state.thread_id

    async def _run_seeding_phase(self, seed_prompt: str, mode: str) -> str:
        """Initialize the research thread. No agent calls.

        Args:
            seed_prompt: Research question or topic.
            mode: Operating mode.

        Returns:
            Thread ID.
        """
        thread_id = f"thread-{uuid.uuid4().hex[:12]}"
        participants = list(self.state.agents.keys())

        self._db.create_thread(
            thread_id=thread_id,
            title=seed_prompt[:200],
            mode=mode,
            participants=participants,
        )

        # Set initial hypothesis from seed prompt
        self._db.update_thread(thread_id, hypothesis=seed_prompt)

        self._logger.log(
            EventType.PHASE_TRANSITION,
            content={"phase": "seeding", "seed_prompt": seed_prompt, "mode": mode},
            thread_id=thread_id,
            phase="seeding",
        )

        # Extract and classify URLs referenced in the prompt
        prompt_urls = extract_urls(seed_prompt)
        shared_dir = self._config.storage.data_dir / "shared"
        resolved: list[ResolvedResource] = []

        for url in prompt_urls:
            rtype = classify_resource(url)
            self._display.resource_detected(url, rtype.value)

            if rtype == ResourceType.PAPER:
                # Papers go through the existing corpus pipeline
                try:
                    paper = await self._corpus.fetch_and_ingest_url(url)
                    if paper:
                        self._display.resource_ingested(paper.title)
                        # Also save raw PDF to sandbox so experimentalist can parse it
                        await self._save_pdf_for_sandbox(url)
                    else:
                        self._display.resource_extract_error(url)
                except Exception as e:
                    self._logger.log_error(e, thread_id=thread_id)
                    self._display.resource_fetch_error(url, e)
            else:
                # Non-paper resources: clone, download, or scrape
                resource = await resolve_resource(url, rtype, shared_dir, self._logger)
                if resource.error:
                    self._display.resource_error(resource.error)
                else:
                    self._display.resource_resolved(resource.name, rtype.value)
                resolved.append(resource)

        self.state.resolved_resources = resolved
        self.state.code_context = build_code_context(resolved)
        self.state.data_context = build_data_context(resolved)
        self.state.reference_context = build_reference_context(resolved)

        # Literature context starts empty — agents populate it via [SEARCH:] requests
        self._literature.literature_context = ""

        # Fetch graveyard context (lessons from past failures)
        try:
            graveyard_entries = self._db.search_graveyard(keyword=seed_prompt[:100], limit=5)
            if graveyard_entries:
                lines = ["## Lessons from Failed Research Attempts\n"]
                lines.append(
                    "_The following are summaries of past failed research attempts. "
                    "These are NOT citable papers \u2014 use them only to avoid repeating "
                    "mistakes._\n"
                )
                for entry in graveyard_entries:
                    lines.append(f"### {entry.get('type', 'unknown')}: {entry['id']}")
                    lines.append(f"**Content:** {entry.get('content', 'N/A')}")
                    if entry.get("failure_reason"):
                        lines.append(f"**Failure reason:** {entry['failure_reason']}")
                    if entry.get("lessons_learned"):
                        lines.append(f"**Lessons learned:** {entry['lessons_learned']}")
                    lines.append("")
                self.state.graveyard_context = "\n".join(lines)
            else:
                self.state.graveyard_context = ""
        except Exception as e:
            self._logger.log_error(e, thread_id=thread_id)
            self._display.graveyard_error(e)
            self.state.graveyard_context = ""

        return thread_id

    async def _run_phase(
        self,
        phase: ResearchPhase,
        max_rounds: int,
        checkpoint_interval: int,
    ) -> None:
        """Run rounds within a phase.

        Args:
            phase: Current phase.
            max_rounds: Maximum number of rounds.
            checkpoint_interval: How often to checkpoint.
        """
        scheduler = Scheduler(list(self.state.agents.values()), mode="phase_appropriate")

        # Compute active agent count for convergence detection
        active_roles = self._get_phase_active_roles(phase)
        if active_roles is not None:
            active_count = sum(
                1 for a in self.state.agents.values() if a.skill_profile in active_roles
            )
        else:
            active_count = len(self.state.agents)

        for round_num in range(1, max_rounds + 1):
            # Real pause: block here while the session is paused (GUI-driven).
            if self._pause_gate is not None:
                await self._pause_gate()
            self._display.round_start(round_num, max_rounds)
            await self._run_round(phase, round_num, scheduler)
            scheduler.advance_round()

            # Convergence detection: skip remaining rounds if agents agree
            if (
                self._config.orchestrator.enable_convergence_detection
                and phase in _CONVERGENCE_CHECK_PHASES
                and round_num < max_rounds
            ):
                try:
                    converged, rationale = await self._check_convergence(
                        phase, round_num, active_count
                    )
                    if converged:
                        self._display.convergence_detected(str(phase), round_num, max_rounds)
                        consensus = self._build_consensus_summary(
                            phase, rationale, self.state.messages[-active_count:]
                        )
                        if consensus:
                            self.state.consensus_summary += consensus + "\n\n"
                        break
                except Exception as e:
                    # Non-fatal — continue with remaining rounds, but record it
                    # so a systematically broken convergence check is visible.
                    self._logger.log_error(e, thread_id=self.state.thread_id)

            # Checkpoint at intervals
            should_checkpoint = (
                self._config.orchestrator.enable_checkpointing
                and round_num % checkpoint_interval == 0
            )
            if should_checkpoint:
                try:
                    self.state.checkpoint = await self._checkpoint_mgr.create_checkpoint(
                        thread_id=self.state.thread_id,
                        phase=str(phase),
                        round_number=round_num,
                        messages=self.state.messages,
                        previous_checkpoint=self.state.checkpoint,
                    )
                    self._display.checkpoint_saved(f"round {round_num}")
                except Exception as e:
                    self._logger.log_error(e, thread_id=self.state.thread_id)
                    self._display.checkpoint_error(e)

        # Final checkpoint at end of phase
        if self.state.messages and self._config.orchestrator.enable_checkpointing:
            try:
                self.state.checkpoint = await self._checkpoint_mgr.create_checkpoint(
                    thread_id=self.state.thread_id,
                    phase=str(phase),
                    round_number=max_rounds,
                    messages=self.state.messages,
                    previous_checkpoint=self.state.checkpoint,
                )
                self._display.checkpoint_saved("end of phase")
            except Exception as e:
                self._logger.log_error(e, thread_id=self.state.thread_id)
                self._display.checkpoint_error(e)

    async def _run_round(
        self,
        phase: ResearchPhase,
        round_num: int,
        scheduler: Scheduler,
    ) -> None:
        """Run one round: each agent speaks in order.

        Args:
            phase: Current phase.
            round_num: Current round number.
            scheduler: Scheduler for speaker order.
        """
        self._literature.reset_round_counters()
        speaker_order = scheduler.get_speaker_order(phase)

        # Phase-appropriate filtering: skip roles not active in this phase
        active_roles = self._get_phase_active_roles(phase)
        if active_roles is not None:
            speaker_order = [
                aid for aid in speaker_order if self.state.agents[aid].skill_profile in active_roles
            ]

        for agent_id in speaker_order:
            agent = self.state.agents[agent_id]
            prompt = self._build_agent_prompt(agent, phase, round_num)

            try:
                response = await agent.generate(prompt)
            except Exception as e:
                self._logger.log_error(e, agent_id=agent_id, thread_id=self.state.thread_id)
                self._display.agent_error(agent_id, e)
                continue  # Skip this agent for this round

            # Create structured message
            msg = agent.format_message(
                to="team",
                thread_id=self.state.thread_id,
                phase=str(phase),
                message_type="proposal" if round_num == 1 else "discussion",
                content=response.content,
            )

            # Store message (suppress non-substantive round-1 contributions
            # to avoid wasting context on search-only responses)
            msg_dict = msg.model_dump(by_alias=True)
            if round_num == 1 and not self._is_substantive_contribution(response.content):
                pass  # Search requests still processed below; skip context storage
            else:
                self.state.messages.append(msg_dict)

            total_tokens = response.usage.input_tokens + response.usage.output_tokens
            self._display.agent_response(
                agent_id,
                total_tokens,
                role=agent.skill_profile,
                model=response.model,
                content=response.content,
                stream_id=getattr(response, "stream_id", ""),
            )
            self._display.agent_step_complete(
                agent_id,
                role=agent.skill_profile,
                summary=" ".join(response.content.split())[:140],
                phase=str(phase),
                tokens=total_tokens,
            )

            # Log message and token usage
            self._logger.log_agent_message(
                agent_id=agent_id,
                thread_id=self.state.thread_id,
                phase=str(phase),
                message=msg_dict,
            )
            self._logger.log_api_call(
                agent_id=agent_id,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                thread_id=self.state.thread_id,
            )
            self._db.record_token_usage(
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                agent_id=agent_id,
                thread_id=self.state.thread_id,
            )

            # Process any [SEARCH: ...] requests in the agent's response
            await self._literature.process_search_requests(agent_id, response.content, phase)

            # Process any [FOLLOW:], [CITED_BY:], [READ:] requests
            await self._literature.process_literature_actions(agent_id, response.content, phase)

            # Process any [DATA: url] requests (pre-stage datasets for sandbox)
            await self._literature.process_data_requests(agent_id, response.content, phase)

            # Process any [CHALLENGE: ...] requests in the agent's response
            await self._debate.process_challenge_requests(
                agent_id, response.content, phase, round_num
            )

            # Update world model from structured tags ([ENTITY:], [HYPOTHESIS:], [EVIDENCE:])
            if self.state.world_model is not None:
                self._world_model.update_from_agent_response(agent_id, response.content, str(phase))
                self._emit_knowledge_update()

    async def _run_synthesis_round(self, phase: ResearchPhase) -> None:
        """Run a synthesis round at the end of a phase.

        Only the synthesizer speaks, using the structured closing template.
        The result is stored in ``_phase_synthesis`` for injection into
        subsequent phase prompts.

        Args:
            phase: The phase being concluded.
        """
        # Check mode-specific synthesis overrides first
        template = _MODE_SYNTHESIS_OVERRIDES.get(self.state.mode, {}).get(phase)
        if template is None:
            template = _SYNTHESIS_CLOSING_TEMPLATES.get(phase)
        if template is None:
            return

        synthesizer = self._find_agent_by_role("synthesizer")
        if synthesizer is None:
            return

        # Build recent messages for the template
        recent = self.state.messages[-_RECENT_MESSAGES_LIMIT:]
        recent_messages = "\n\n".join(
            f"**{m.get('from', 'unknown')}**: {m.get('content', '')[:500]}" for m in recent
        )

        prompt = template.format(
            seed_prompt=self.state.seed_prompt,
            recent_messages=recent_messages,
        )

        # For POST_EXECUTION, inject the execution fact sheet so the
        # synthesizer grounds its summary in actual experiment outputs
        # rather than confabulating from the discussion alone.
        if phase == ResearchPhase.POST_EXECUTION:
            fact_sheet = self._writing._build_execution_fact_sheet()
            if fact_sheet:
                prompt += (
                    "\n\n" + fact_sheet + "\n\n"
                    "Base your synthesis ONLY on the actual experiment outputs above. "
                    "Do NOT describe failed experiments as having produced results."
                )

        try:
            response = await synthesizer.generate(prompt)
        except Exception as e:
            self._logger.log_error(e, agent_id=synthesizer.agent_id, thread_id=self.state.thread_id)
            return

        self._log_agent_response(synthesizer.agent_id, response, phase, "synthesis")

        # Store synthesis, capped at 1500 chars
        synthesis_text = response.content[:1500]
        self.state.phase_synthesis[str(phase)] = synthesis_text

    async def _run_tournament_synthesis(self, winners: list) -> None:
        """Run a synthesis round using tournament winners instead of normal closing.

        Args:
            winners: List of winning Hypothesis objects from the tournament.
        """
        from paradigm.orchestrator.constants import _TOURNAMENT_SYNTHESIS_TEMPLATE

        synthesizer = self._find_agent_by_role("synthesizer")
        if synthesizer is None:
            return

        winners_summary = "\n".join(
            f"- **{w.statement}** (Elo: {w.elo_rating:.0f}): {w.rationale}" for w in winners
        )

        recent = self.state.messages[-_RECENT_MESSAGES_LIMIT:]
        recent_messages = "\n\n".join(
            f"**{m.get('from', 'unknown')}**: {m.get('content', '')[:500]}" for m in recent
        )

        prompt = _TOURNAMENT_SYNTHESIS_TEMPLATE.format(
            seed_prompt=self.state.seed_prompt,
            winners_summary=winners_summary,
            recent_messages=recent_messages,
        )

        try:
            response = await synthesizer.generate(prompt)
        except Exception as e:
            self._logger.log_error(e, agent_id=synthesizer.agent_id, thread_id=self.state.thread_id)
            return

        self._log_agent_response(
            synthesizer.agent_id, response, ResearchPhase.IDEATION, "synthesis"
        )

        synthesis_text = response.content[:1500]
        self.state.phase_synthesis[str(ResearchPhase.IDEATION)] = synthesis_text

    def _build_agent_prompt(
        self,
        agent: Agent,
        phase: ResearchPhase,
        round_num: int,
    ) -> str:
        """Build the prompt for an agent in a given phase and round.

        Args:
            agent: The agent to prompt.
            phase: Current phase.
            round_num: Current round number.

        Returns:
            Formatted prompt string.
        """
        templates = _PHASE_INSTRUCTIONS.get(phase, {})
        template_key = "round_1" if round_num == 1 else "later_rounds"
        template = templates.get(template_key, "Contribute to the research discussion.")

        # Apply mode-specific overrides if available
        # Check phase-specific key first (e.g., "planning_round_1"), then generic
        mode_overrides = _MODE_PROMPT_OVERRIDES.get(self.state.mode, {})
        phase_key = f"{phase.value}_{template_key}"  # e.g., "planning_round_1"
        if phase_key in mode_overrides:
            template = mode_overrides[phase_key]
        elif template_key in mode_overrides:
            template = mode_overrides[template_key]

        # Build checkpoint context
        checkpoint_context = ""
        if self.state.checkpoint:
            checkpoint_context = self.state.checkpoint.to_context_string() + "\n\n"

        # Build recent messages string
        recent = self.state.messages[-_RECENT_MESSAGES_LIMIT:]
        recent_messages = "\n\n".join(
            f"**{m.get('from', 'unknown')}** ({m.get('type', 'message')}): "
            f"{m.get('content', '')[:500]}"
            for m in recent
        )

        # For round_1, prepend a clear header so agents know these are
        # prior team proposals from the same round (not prior-phase context)
        if round_num == 1 and recent_messages:
            # Filter to messages from current phase only
            phase_messages = [m for m in recent if m.get("phase") == str(phase)]
            if phase_messages:
                recent_messages = (
                    "## Prior Team Proposals (this round)\n" + recent_messages + "\n\n"
                )

        # Phase-appropriate context injection — only inject what each phase needs
        context_needs = _PHASE_CONTEXT_NEEDS.get(phase, set())

        if "literature" in context_needs:
            lit = self._literature.literature_context
            if lit:
                checkpoint_context = "## Literature Context\n" + lit + "\n\n" + checkpoint_context

        if "references" in context_needs and self.state.reference_context:
            checkpoint_context = self.state.reference_context + "\n\n" + checkpoint_context

        if "execution" in context_needs and self.state.execution_context:
            exec_block = "## Experiment Results\n" + self.state.execution_context
            if self.state.execution_caveats:
                exec_block += "\n\n## Execution Caveats\n" + "\n".join(
                    f"- {c}" for c in self.state.execution_caveats
                )
            checkpoint_context = exec_block + "\n\n" + checkpoint_context

        if "code_data" in context_needs:
            if self.state.data_context:
                checkpoint_context = self.state.data_context + "\n\n" + checkpoint_context
            if self.state.code_context:
                checkpoint_context = self.state.code_context + "\n\n" + checkpoint_context

        # Graveyard context stays IDEATION round 1 only
        if phase == ResearchPhase.IDEATION and round_num == 1:
            graveyard = self.state.graveyard_context
            if graveyard:
                checkpoint_context = checkpoint_context + graveyard + "\n\n"

        # Inject structured phase syntheses near the top of the prompt
        # so agents see them early and don't re-derive settled conclusions
        if self.state.phase_synthesis:
            synthesis_parts: list[str] = []
            for phase_key, synthesis_text in self.state.phase_synthesis.items():
                phase_label = phase_key.upper().replace("RESEARCHPHASE.", "")
                capped = synthesis_text[:1500]
                synthesis_parts.append(f"### {phase_label} Synthesis\n{capped}")
            if synthesis_parts:
                synthesis_block = (
                    "## MANDATORY: Phase Syntheses (DO NOT RE-DERIVE)\n"
                    "The following structured conclusions were produced at the end of "
                    "prior phases. Build on these — do NOT re-derive them.\n\n"
                    + "\n\n---\n\n".join(synthesis_parts)
                    + "\n\n"
                )
                checkpoint_context = synthesis_block + checkpoint_context

        # Inject prior phase consensus near the top as well
        if self.state.consensus_summary:
            consensus_block = (
                "## Prior Phase Consensus\n"
                "The following conclusions were agreed upon in earlier phases. "
                "Do NOT re-derive these — build on them.\n\n"
                + self.state.consensus_summary
                + "\n\n"
            )
            checkpoint_context = consensus_block + checkpoint_context

        # Inject agent episodic memories (cross-cycle learning)
        if (
            "memory" in context_needs
            and self._memory_store is not None
            and self._config.memory.enabled
        ):
            from paradigm.agents.memory import format_memory_context, rank_memories_with_recency

            raw_memories = self._memory_store.search(
                query=self.state.seed_prompt,
                agent_id=agent.agent_id,
                n_results=self._config.memory.max_memories_per_prompt * 4,
            )
            ranked = rank_memories_with_recency(
                raw_memories,
                half_life_days=self._config.memory.recency_half_life_days,
                top_k=self._config.memory.max_memories_per_prompt,
            )
            mem_ctx = format_memory_context(ranked, max_chars=self._config.memory.max_memory_chars)
            if mem_ctx:
                checkpoint_context = mem_ctx + "\n\n" + checkpoint_context

        # Inject world model context (if enabled and populated)
        if "world_model" in context_needs and self._config.knowledge.enable_world_model:
            wm_ctx = self._world_model.build_world_model_context(
                max_chars=self._config.knowledge.world_model_max_context_chars,
            )
            if wm_ctx:
                checkpoint_context = wm_ctx + "\n\n" + checkpoint_context

        # Inject evidence landscape (if enabled, role-gated)
        if (
            "evidence_landscape" in context_needs
            and self._config.knowledge.enable_evidence_graph
            and agent.skill_profile in ("skeptic", "synthesizer", "analyst")
        ):
            el_ctx = self._world_model.build_evidence_landscape_context()
            if el_ctx:
                checkpoint_context = el_ctx + "\n\n" + checkpoint_context

        formatted = template.format(
            seed_prompt=self.state.seed_prompt,
            checkpoint_context=checkpoint_context,
            recent_messages=recent_messages,
        )

        # Inject role-specific and general reinforcements for later rounds
        if round_num > 1:
            # General anti-repetition rule for all agents
            formatted += _GENERAL_LATER_ROUND_REINFORCEMENT
            # Inject established points to further reduce redundancy
            established = self._build_established_points(
                self.state.messages[-_RECENT_MESSAGES_LIMIT:]
            )
            if established:
                formatted += established
            # Role-specific reinforcement (mode override > profile default > hardcoded)
            reinforcement = ""
            if self._profile is not None:
                mode_reinforcements = self._profile.mode_role_reinforcements.get(
                    self.state.mode, {}
                )
                reinforcement = mode_reinforcements.get(
                    agent.skill_profile,
                    self._profile.role_later_round_reinforcements.get(agent.skill_profile, ""),
                )
            else:
                from paradigm.domains.science.constants import (
                    ROLE_LATER_ROUND_REINFORCEMENTS as _ROLE_LATER_ROUND_REINFORCEMENTS,
                )

                reinforcement = _ROLE_LATER_ROUND_REINFORCEMENTS.get(agent.skill_profile, "")
            if reinforcement:
                formatted += reinforcement

        # Inject discovered paper index for round 2+ in search-enabled phases
        # so agents always have concrete IDs for [FOLLOW:] / [CITED_BY:]
        if phase in _SEARCH_ENABLED_PHASES and round_num >= 2:
            paper_index = self._literature.build_paper_index()
            if paper_index:
                formatted = paper_index + "\n" + formatted

        # Append literature search instructions for search-enabled phases
        if phase in _SEARCH_ENABLED_PHASES:
            if self._profile is not None and self._profile.literature_instruction:
                formatted += self._profile.literature_instruction
            else:
                from paradigm.domains.science.constants import (
                    LITERATURE_INSTRUCTION as _LITERATURE_INSTRUCTION,
                )

                formatted += _LITERATURE_INSTRUCTION
            # Role-specific search strategy (mode override > profile default > hardcoded)
            role_strategy = ""
            if self._profile is not None:
                mode_strategies = self._profile.mode_role_search_strategies.get(self.state.mode, {})
                role_strategy = mode_strategies.get(
                    agent.skill_profile,
                    self._profile.role_search_strategies.get(agent.skill_profile, ""),
                )
            else:
                from paradigm.domains.science.constants import (
                    ROLE_SEARCH_STRATEGIES as _ROLE_SEARCH_STRATEGIES,
                )

                role_strategy = _ROLE_SEARCH_STRATEGIES.get(agent.skill_profile, "")
            if role_strategy:
                formatted += role_strategy

        # Append debate/challenge instructions for debate-enabled phases
        if phase in _DEBATE_ENABLED_PHASES and self._config.orchestrator.enable_debates:
            formatted += _CHALLENGE_INSTRUCTION

        # Append knowledge tag instructions for world-model-enabled phases
        if (
            self._config.knowledge.enable_world_model
            and phase in _PHASE_CONTEXT_NEEDS
            and "world_model" in _PHASE_CONTEXT_NEEDS[phase]
        ):
            formatted += _KNOWLEDGE_TAG_INSTRUCTION

        return formatted

    @staticmethod
    def _build_established_points(messages: list[dict[str, Any]]) -> str:
        """Extract key points already made in recent messages to prevent restating.

        Scans recent agent messages for bullet points and numbered items,
        extracts up to 5 key points, and returns a formatted block instructing
        agents not to restate them.

        Args:
            messages: Recent message dicts (with 'content' key).

        Returns:
            Formatted "Points Already Established" block, or empty string.
        """
        points: list[str] = []
        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue
            for line in content.split("\n"):
                stripped = line.strip()
                # Match bullet points (-, *, •) or numbered items (1., 2.)
                if re.match(r"^[-*•]\s+.{15,150}$", stripped) or re.match(
                    r"^\d+[.)]\s+.{15,150}$", stripped
                ):
                    # Clean the prefix
                    clean = re.sub(r"^[-*•\d.)\s]+", "", stripped).strip()
                    if 15 <= len(clean) <= 150 and clean not in points:
                        points.append(clean)
                if len(points) >= 5:
                    break
            if len(points) >= 5:
                break

        if not points:
            return ""
        items = "\n".join(f"- {p}" for p in points)
        return (
            "\n\n## Points Already Established (DO NOT RESTATE)\n"
            f"{items}\n"
            "Skip these — add NEW insights only."
        )

    @staticmethod
    def _is_substantive_contribution(content: str, min_chars: int = 200) -> bool:
        """Check if an agent's response contains substantive discussion content.

        Strips out search/action tags and checks whether the remaining text
        is long enough to constitute a real contribution.  Responses that
        consist only of search requests waste context window space.

        Args:
            content: Agent response text.
            min_chars: Minimum character count after stripping tags.

        Returns:
            True if the contribution is substantive.
        """
        stripped = re.sub(
            r"\[(SEARCH|FOLLOW|CITED_BY|READ|DATA|CHALLENGE):[^\]]*\]",
            "",
            content,
        )
        stripped = stripped.strip()
        return len(stripped) >= min_chars

    async def _check_intervention(self, from_phase: str, to_phase: str) -> str:
        """Check intervention hook before a phase transition.

        The hook may BLOCK (a GUI approval waits for the user), so it is run off
        the event loop via ``to_thread`` — calling it inline would deadlock, as
        the backend hook waits on a coroutine that needs this same loop to run.

        Args:
            from_phase: Phase transitioning from.
            to_phase: Phase transitioning to.

        Returns:
            "continue", "pause", or "abort".
        """
        if self._intervention_hook is None:
            return "continue"
        result = await asyncio.to_thread(
            self._intervention_hook, self.state.thread_id, from_phase, to_phase
        )
        if result not in ("continue", "pause", "abort"):
            return "continue"
        return result

    async def _human_gate(self, point: str, payload: str = "") -> str:
        """Config-driven human gate (1E) at a named point.

        Records the decision in ``state.gate_decisions`` (for provenance) and, in
        ``advisory`` mode, surfaces the payload without blocking. Returns
        "continue" when the gate is off/unset or no hook is registered.

        In ``blocking`` mode ``decide_human_gate`` invokes the (blocking)
        intervention hook, so it is run off the event loop via ``to_thread`` —
        calling it inline would deadlock the loop the approval coroutine needs.

        Args:
            point: Gate-point name (problem_selection / pre_registration / final_verification).
            payload: Short human-readable context shown in advisory mode.

        Returns:
            "continue", "pause", or "abort".
        """
        cfg = self._config.orchestrator
        decision, reason = await asyncio.to_thread(
            decide_human_gate,
            cfg.human_gate_mode,
            cfg.human_gate_points,
            point,
            self._intervention_hook,
            self.state.thread_id,
        )
        if cfg.human_gate_mode != "off" and point in cfg.human_gate_points:
            self.state.gate_decisions[point] = decision
            if cfg.human_gate_mode == "advisory":
                self._display.info(f"[human gate: {point}] {payload or '(review and continue)'}")
            elif decision != "continue":
                self._display.info(f"[human gate: {point}] {decision} ({reason})")
        return decision

    def _handle_gate_decision(self, decision: str) -> bool:
        """Apply a pause/abort gate decision. Returns True if the cycle should stop."""
        if decision == "abort":
            self._db.update_thread(self.state.thread_id, status="aborted")
            self._display.phase_aborted()
            self._print_token_summary()
            return True
        if decision == "pause":
            self._db.update_thread(self.state.thread_id, status="paused")
            self._display.phase_paused()
            self._print_token_summary()
            return True
        return False

    def _record_provenance(self) -> None:
        """Build and surface the human-vs-agent provenance record for the draft (1E)."""
        thread = self._db.get_thread(self.state.thread_id)
        paper_id = (thread.get("current_draft_id") if thread else "") or ""
        record = build_provenance(
            paper_id=paper_id,
            thread_id=self.state.thread_id,
            mode=self._config.orchestrator.human_gate_mode,
            gate_decisions=self.state.gate_decisions,
            registered_rules=self.state.registered_rules,
            verification_records=self.state.verification_records,
        )
        self.state.provenance = record
        if paper_id:
            # Persist correctness-kernel artifacts on the paper so the eval harness
            # (1D) can read reproduction-pass-rate, prereg verdicts, and provenance.
            self._db.update_paper(
                paper_id,
                provenance=record.model_dump(),
                verification=[r.model_dump() for r in self.state.verification_records],
                prereg=self.state.prereg_verdicts,
            )
        self._display.info(
            f"Provenance: framed_by={record.framed_by}, registered_by={record.registered_by}, "
            f"verified_by={record.verified_by}, gate_mode={record.human_gate_mode}"
        )

    def _build_post_execution_summary(self) -> str:
        """Build a compact summary of POST_EXECUTION discussion findings.

        Captures each agent's key conclusions from the POST_EXECUTION phase
        so they can be injected into WRITING prompts. Truncates each agent's
        contribution to keep the summary concise.

        Returns:
            Formatted summary string, or empty string if no messages.
        """
        if not self.state.messages:
            return ""

        parts: list[str] = []
        for msg in self.state.messages:
            agent_id = msg.get("from", "unknown")
            content = msg.get("content", "")
            # Truncate to 800 chars per agent to keep summary manageable
            if len(content) > 800:
                content = content[:800] + "..."
            parts.append(f"**{agent_id}**: {content}")

        if not parts:
            return ""

        return (
            "## Team Assessment (from POST_EXECUTION discussion)\n"
            "The research team reviewed the experimental results and identified "
            "the following issues. The paper MUST reflect these findings:\n\n" + "\n\n".join(parts)
        )

    def _build_consensus_summary(
        self,
        phase: ResearchPhase,
        rationale: str,
        messages: list[dict[str, Any]],
    ) -> str:
        """Build a compact consensus summary from converged phase discussion.

        Args:
            phase: The phase that converged.
            rationale: Convergence rationale from the LLM check.
            messages: Final-round messages from active agents.

        Returns:
            Formatted consensus string, capped at 1000 chars.
        """
        parts = [f"### {str(phase).upper()} Consensus"]
        if rationale:
            parts.append(f"**Agreement:** {rationale}")

        # Include truncated key points from final messages
        for msg in messages[:5]:  # Cap at 5 agents
            agent_id = msg.get("from", "unknown")
            content = msg.get("content", "")[:200]
            if content:
                parts.append(f"- **{agent_id}:** {content}")

        summary = "\n".join(parts)
        return summary[:1000]

    def _extract_planning_actions(self) -> str:
        """Extract experiment-related action items from PLANNING messages.

        Scans the last round's PLANNING messages for experiment-related keywords
        and extracts them as numbered action items.

        Returns:
            Numbered action items string, or empty string if none found.
        """
        experiment_keywords = {
            "experiment",
            "test",
            "simulate",
            "compute",
            "calculate",
            "measure",
            "plot",
            "analyze",
            "run",
            "implement",
            "code",
            "script",
            "model",
            "fit",
            "regression",
            "monte carlo",
            "numerical",
            "benchmark",
        }

        actions: list[str] = []
        for msg in self.state.messages:
            content = msg.get("content", "")
            if not content:
                continue
            # Split into sentences / bullet points
            lines = re.split(r"[\n•\-\d+\.\)]", content)
            for line in lines:
                line = line.strip()
                if len(line) < 10 or len(line) > 200:
                    continue
                line_lower = line.lower()
                if any(kw in line_lower for kw in experiment_keywords):
                    actions.append(line)
                    if len(actions) >= 10:
                        break
            if len(actions) >= 10:
                break

        if not actions:
            return ""

        return "\n".join(f"{i}. {a}" for i, a in enumerate(actions, 1))

    async def _check_convergence(
        self,
        phase: ResearchPhase,
        round_num: int,
        active_agent_count: int,
    ) -> tuple[bool, str]:
        """Check if agents have converged using a cheap LLM call.

        Grabs messages from the last two rounds (up to 2 × active_agent_count),
        truncates each to 800 chars, and asks an LLM whether agents have reached
        substantial agreement.

        Args:
            phase: Current research phase.
            round_num: Current round number.
            active_agent_count: Number of active agents in this phase.

        Returns:
            Tuple of (is_converged, rationale).
        """
        # Two-round lookback: grab up to 2 rounds of messages
        lookback = min(2 * active_agent_count, len(self.state.messages))
        recent = self.state.messages[-lookback:]
        if len(recent) < 2:
            return False, ""

        # Format messages, truncating content to 800 chars
        formatted_messages = "\n\n".join(
            f"**{m.get('from', 'unknown')}**: {m.get('content', '')[:800]}" for m in recent
        )

        prompt_text = _CONVERGENCE_CHECK_PROMPT.format(
            phase=str(phase).upper(),
            round_num=round_num,
            messages=formatted_messages,
        )

        provider = self._config.get_provider()
        text, input_tokens, output_tokens = await asyncio.to_thread(
            provider.complete,
            model=provider.default_model,
            system="You are a concise evaluator. Return only JSON.",
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=256,
            temperature=0.2,
        )

        # Track token usage
        self._db.record_token_usage(
            model=provider.default_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            agent_id="convergence_checker",
            thread_id=self.state.thread_id,
        )
        self._logger.log_api_call(
            agent_id="convergence_checker",
            model=provider.default_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thread_id=self.state.thread_id,
        )

        # Parse JSON response (strip markdown fences if present)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        result = None
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Weaker open-weight models often wrap the JSON in prose — fall back
            # to extracting the first {...} object before giving up.
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group(0))
                except json.JSONDecodeError:
                    result = None

        if not isinstance(result, dict):
            # Not an ERROR: a non-JSON reply just means "not converged, keep
            # going". Log as a STATE_CHANGE so it stays visible without polluting
            # the error stream.
            self._logger.log(
                EventType.STATE_CHANGE,
                content={
                    "event": "convergence_check_unparsed",
                    "phase": str(phase),
                    "round": round_num,
                    "raw_response": cleaned[:500],
                    "interpretation": "Convergence reply was not valid JSON — treating as not converged.",
                },
                thread_id=self.state.thread_id,
                phase=str(phase),
            )
            return False, ""

        converged = bool(result.get("converged", False))
        confidence = float(result.get("confidence", 0.0))
        rationale = result.get("rationale", "")

        threshold = self._config.orchestrator.convergence_confidence_threshold
        is_converged = converged and confidence >= threshold

        # Log the check result
        self._logger.log(
            EventType.STATE_CHANGE,
            content={
                "event": "convergence_check",
                "phase": str(phase),
                "round": round_num,
                "converged": converged,
                "confidence": confidence,
                "threshold": threshold,
                "rationale": rationale,
                "skipping": is_converged,
                "interpretation": (
                    f"LLM judged {'converged' if converged else 'not converged'} "
                    f"with {confidence:.0%} certainty "
                    f"(threshold: {threshold:.0%}). "
                    f"{'Skipping remaining rounds.' if is_converged else 'Continuing.'}"
                ),
            },
            thread_id=self.state.thread_id,
            phase=str(phase),
        )

        return is_converged, rationale

    def _log_phase_transition(self, from_phase: ResearchPhase, to_phase: ResearchPhase) -> None:
        """Log a phase transition event."""
        self._logger.log(
            EventType.PHASE_TRANSITION,
            content={"from": str(from_phase), "to": str(to_phase)},
            thread_id=self.state.thread_id,
            phase=str(to_phase),
        )
        self._db.update_thread(self.state.thread_id, current_phase=str(to_phase))

    def _find_agent_by_role(self, role: str) -> Agent | None:
        """Find an agent by its skill profile / role.

        Args:
            role: Role name (e.g., 'writer', 'editor').

        Returns:
            Agent if found, None otherwise.
        """
        for agent in self.state.agents.values():
            if agent.skill_profile == role:
                return agent
        return None

    def _make_stream_sink(self, role: str):
        """Build a thread-safe streaming sink for an agent of the given role.

        The agent calls this from a worker thread (generation runs in
        ``asyncio.to_thread``); the display adapter is responsible for scheduling
        the actual broadcast back onto the event loop safely.
        """
        display = self._display

        def sink(agent_id: str, stream_id: str, chunk: str, event: str, usage: Any) -> None:
            # The streaming side-channel must NEVER break an agent turn — swallow
            # any display/broadcast error (it only affects live UI, not results).
            try:
                pm = self.state.phase_manager if self.state else None
                phase = str(pm.current_phase) if pm else ""
                if event == "start":
                    display.agent_stream_start(agent_id, stream_id, role=role, phase=phase)
                elif event == "chunk":
                    display.agent_stream_chunk(agent_id, stream_id, chunk, role=role, phase=phase)
                # "final" is rendered by agent_response() below (carries token totals).
            except Exception:  # noqa: BLE001 - side-channel must not propagate
                pass

        return sink

    def _log_agent_response(
        self,
        agent_id: str,
        response: Any,
        phase: ResearchPhase,
        message_type: str,
    ) -> None:
        """Log an agent's response and token usage.

        Args:
            agent_id: Agent identifier.
            response: AgentResponse from agent.generate().
            phase: Current research phase.
            message_type: Type of message.
        """
        total_tokens = response.usage.input_tokens + response.usage.output_tokens
        agent = self.state.agents.get(agent_id)
        role = agent.skill_profile if agent else ""
        self._display.agent_response(
            agent_id,
            total_tokens,
            role=role,
            model=response.model,
            content=response.content,
            stream_id=getattr(response, "stream_id", ""),
        )
        # Structured step marker for the activity timeline (Phase B). Harmless to
        # the chat view (final content is rendered by agent_response above).
        summary = " ".join(response.content.split())[:140]
        self._display.agent_step_complete(
            agent_id, role=role, summary=summary, phase=str(phase), tokens=total_tokens
        )

        self._logger.log_agent_message(
            agent_id=agent_id,
            thread_id=self.state.thread_id,
            phase=str(phase),
            message={
                "from": agent_id,
                "type": message_type,
                "content": response.content,
            },
        )
        self._logger.log_api_call(
            agent_id=agent_id,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            thread_id=self.state.thread_id,
        )
        self._db.record_token_usage(
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_id=agent_id,
            thread_id=self.state.thread_id,
        )

    async def _save_pdf_for_sandbox(self, url: str) -> None:
        """Save raw PDF bytes to data/shared/papers/ for sandbox access.

        Non-fatal: if the download or save fails, logs and continues
        (the paper is already in ChromaDB for literature context).

        Args:
            url: URL of the PDF to save.
        """
        try:
            pdf_bytes = await self._corpus._arxiv.fetch_pdf_bytes(url)
            if pdf_bytes is None:
                return

            papers_dir = self._config.storage.data_dir / "shared" / "papers"
            papers_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize filename from URL
            name = url.rstrip("/").split("/")[-1]
            if not name.endswith(".pdf"):
                name += ".pdf"
            # Remove query params and unsafe chars
            name = re.sub(r"[?#&=].*", "", name)
            name = re.sub(r"[^\w.\-]", "_", name)

            dest = papers_dir / name
            dest.write_bytes(pdf_bytes)
            self._display.pdf_saved(name)
        except Exception as e:
            self._logger.log_error(e, metadata_key="pdf_sandbox_save", url=url)
            self._display.pdf_save_error(e)

    def _save_search_log(self, paper_id: str) -> None:
        """Write literature_searches.md to the paper directory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._config.storage.papers_dir
        if papers_dir is None:
            return

        lines = ["# Literature Searches\n"]
        lines.append(f"Thread: {self.state.thread_id}")
        lines.append(f"Total searches: {len(self._literature.search_log)}\n")
        lines.append("---\n")

        for i, entry in enumerate(self._literature.search_log, 1):
            phase = entry["phase"].upper().replace("RESEARCHPHASE.", "")
            agent_id = entry["agent_id"]
            query = entry["query"]
            papers = entry["papers"]

            lines.append(f"## Search {i} \u2014 {phase} ({agent_id})")
            lines.append(f"**Query:** {query}\n")

            if papers:
                for j, p in enumerate(papers, 1):
                    authors_str = ", ".join(p["authors"][:2])
                    if len(p["authors"]) > 2:
                        authors_str += " et al."
                    lines.append(
                        f"{j}. **{p['title']}** \u2014 {authors_str} ({p['year']}) [{p['arxiv_id']}]"
                    )
            else:
                lines.append("No results found.")

            lines.append("\n---\n")

        paper_dir = papers_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / "literature_searches.md"
        path.write_text("\n".join(lines))

    def _save_review_log(self, paper_id: str) -> None:
        """Write reviews.md to the paper directory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._config.storage.papers_dir
        if papers_dir is None:
            return

        lines = ["# Review Report\n"]
        lines.append(f"Thread: {self.state.thread_id}")
        lines.append(f"Paper: {paper_id}\n")
        lines.append("---\n")

        for entry in self._review.review_log:
            entry_type = entry["type"]

            if entry_type == "internal_review":
                iteration = entry.get("iteration", "")
                reviewer = entry["reviewer_id"]
                lines.append(f"## Internal Review \u2014 Iteration {iteration} ({reviewer})\n")
                lines.append(entry["text"])
                lines.append("\n---\n")

            elif entry_type == "desk_review":
                reviewer = entry["reviewer_id"]
                decision = entry.get("decision", "unknown")
                lines.append(f"## Desk Review ({reviewer})\n")
                lines.append(f"**Decision:** {decision}\n")
                lines.append(entry["text"])
                lines.append("\n---\n")

            elif entry_type == "peer_review":
                reviewer = entry["reviewer_id"]
                review = entry["review"]
                lines.append(f"### Reviewer: {reviewer}")
                lines.append(f"**Recommendation:** {review.recommendation}")
                if review.scores:
                    scores_str = ", ".join(f"{k.title()}: {v}/10" for k, v in review.scores.items())
                    lines.append(f"**Scores:** {scores_str}")
                lines.append("")
                lines.append(entry["text"])
                lines.append("\n---\n")

            elif entry_type == "decision":
                decision = entry["decision"]
                lines.append("## Decision\n")
                lines.append(f"**Final decision:** {decision}")
                lines.append("\n---\n")

            elif entry_type == "revision":
                reviewer = entry["reviewer_id"]
                lines.append(f"## Revision ({reviewer})\n")
                lines.append("Paper revised based on reviewer feedback.")
                lines.append("\n---\n")

        # Append token usage and timing summary
        usage = self._get_token_summary()
        elapsed = time.monotonic() - self.state.start_time
        minutes, seconds = divmod(int(elapsed), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"

        lines.append("## Session Summary\n")
        lines.append(f"**Input tokens:** {usage['input_tokens']:,}")
        lines.append(f"**Output tokens:** {usage['output_tokens']:,}")
        lines.append(f"**Total tokens:** {usage['total_tokens']:,}")
        lines.append(f"**Elapsed time:** {time_str}")

        paper_dir = papers_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / "reviews.md"
        path.write_text("\n".join(lines))

    def _save_transcript(self, paper_id: str) -> None:
        """Write transcript.md — a full conversation log organized by phase.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._config.storage.papers_dir
        if papers_dir is None:
            return

        events = self._logger.read_events(thread_id=self.state.thread_id)
        if not events:
            return

        lines = ["# Research Transcript\n"]
        lines.append(f"Thread: {self.state.thread_id}")
        lines.append(f"Paper: {paper_id}")
        lines.append(f"Seed prompt: {self.state.seed_prompt[:200]}\n")
        lines.append("---\n")

        current_phase = ""
        for event in events:
            ts = event.timestamp.strftime("%Y-%m-%d %H:%M:%S")

            if event.event_type == EventType.PHASE_TRANSITION:
                content = event.content if isinstance(event.content, dict) else {}
                phase_name = content.get("to", content.get("phase", "unknown"))
                current_phase = phase_name.upper().replace("RESEARCHPHASE.", "")
                lines.append(f"\n---\n\n## {current_phase}\n")

            elif event.event_type == EventType.AGENT_MESSAGE:
                agent_id = event.agent_id or "unknown"
                content = event.content if isinstance(event.content, dict) else {}
                msg_type = content.get("type", "message")
                msg_content = content.get("content", "")
                lines.append(f"### {agent_id} ({msg_type}) — {ts}\n")
                lines.append(f"{msg_content}\n")

            elif event.event_type == EventType.CODE_EXECUTION:
                content = event.content if isinstance(event.content, dict) else {}
                success = content.get("success", False)
                status = "SUCCESS" if success else "FAILURE"
                code = content.get("code", "")
                output = content.get("output", "")
                error = content.get("error", "")
                lines.append(f"### Code Execution — {ts} [{status}]\n")
                if code:
                    lines.append(f"```python\n{code[:5000]}\n```\n")
                if output:
                    lines.append(f"**Output:** {output[:2000]}\n")
                if error:
                    lines.append(f"**Error:** {error[:2000]}\n")

            elif event.event_type == EventType.LITERATURE_SEARCH:
                agent_id = event.agent_id or "system"
                content = event.content if isinstance(event.content, dict) else {}
                query = content.get("query", str(content))
                lines.append(f"- [{ts}] **Literature search** ({agent_id}): {query}")

            elif event.event_type == EventType.DEBATE_TRIGGERED:
                content = event.content if isinstance(event.content, dict) else {}
                challenger = content.get("challenger", "?")
                defender = content.get("defender", "?")
                lines.append(f"- [{ts}] **Debate triggered**: {challenger} challenges {defender}")

            elif event.event_type == EventType.ERROR:
                content = str(event.content) if event.content else "unknown error"
                lines.append(f"- [{ts}] **Error**: {content[:200]}")

            elif event.event_type == EventType.PAPER_SUBMITTED:
                content = event.content if isinstance(event.content, dict) else {}
                action = content.get("action", str(content))
                lines.append(f"- [{ts}] **Paper event**: {action}")

            elif event.event_type == EventType.REVIEW_COMPLETED:
                content = event.content if isinstance(event.content, dict) else {}
                lines.append(f"- [{ts}] **Review completed**: {content}")

        paper_dir = papers_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / "transcript.md"
        path.write_text("\n".join(lines))

    def _save_experiment_code(self, paper_id: str) -> None:
        """Write working code (experiments + conceptual figures) to code/ subdirectory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._config.storage.papers_dir
        if papers_dir is None:
            return

        paper_dir = papers_dir / paper_id
        code_dir = paper_dir / "code"
        code_dir.mkdir(parents=True, exist_ok=True)

        readme_lines = ["# Code\n"]
        readme_lines.append(
            "Working code that produced successful results during the research cycle.\n"
            "Includes experiment scripts from EXECUTION and conceptual figure scripts from WRITING.\n"
        )

        for exp_name, code in self.state.successful_code:
            # Sanitize experiment name for filename
            safe_name = re.sub(r"[^\w\-]", "_", exp_name).strip("_").lower()
            if not safe_name:
                safe_name = "experiment"
            filename = f"{safe_name}.py"

            # Write code file
            filepath = code_dir / filename
            filepath.write_text(code)

            readme_lines.append(f"- **{exp_name}** → `{filename}`")

        # Write README
        readme_path = code_dir / "README.md"
        readme_path.write_text("\n".join(readme_lines) + "\n")

        self._display.code_saved(len(self.state.successful_code))

    def _get_token_summary(self) -> dict[str, int]:
        """Get token usage for the current thread.

        Returns:
            Dict with input_tokens, output_tokens, total_tokens.
        """
        return self._db.get_token_usage(thread_id=self.state.thread_id)

    def _print_token_summary(self) -> None:
        """Display token usage and elapsed time at end of research cycle."""
        usage = self._get_token_summary()
        input_k = usage["input_tokens"] / 1000
        output_k = usage["output_tokens"] / 1000
        total_k = usage["total_tokens"] / 1000

        elapsed = time.monotonic() - self.state.start_time
        minutes, seconds = divmod(int(elapsed), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"

        self._display.token_summary(total_k, input_k, output_k, time_str)

        self._logger.log(
            EventType.STATE_CHANGE,
            content={
                "event": "cycle_complete",
                "elapsed_seconds": round(elapsed, 1),
                "total_tokens": usage["total_tokens"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
            },
            thread_id=self.state.thread_id,
        )

    def _save_auxiliary_files(self, paper_id: str) -> None:
        """Save auxiliary files alongside the paper.

        Args:
            paper_id: Paper identifier.
        """
        if self._literature.search_log:
            self._save_search_log(paper_id)
        # Always save review log (includes token summary even without reviews)
        self._save_review_log(paper_id)
        self._save_transcript(paper_id)
        if self.state.successful_code:
            self._save_experiment_code(paper_id)
        # Save world model snapshot
        if self.state.world_model is not None:
            self._world_model.save_to_thread(paper_id)
            self._world_model.persist_snapshot()
