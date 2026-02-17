"""Main orchestration engine for research cycles."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from paradigm.agents.base import Agent
from paradigm.agents.factory import AgentFactory
from paradigm.config import Config
from paradigm.journal.publication import publish_paper
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
    _MODE_PROMPT_OVERRIDES,
    _PHASE_ACTIVE_ROLES,
    _PHASE_CONTEXT_NEEDS,
    _PHASE_INSTRUCTIONS,
    _RECENT_MESSAGES_LIMIT,
    _SEARCH_ENABLED_PHASES,
    InterventionHook,
)
from paradigm.orchestrator.debate import DebateHandler
from paradigm.orchestrator.experimentation import ExperimentationHandler
from paradigm.orchestrator.literature import LiteratureHandler
from paradigm.orchestrator.memory import MemoryHandler
from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.review import ReviewHandler
from paradigm.orchestrator.scheduler import Scheduler
from paradigm.orchestrator.writing import WritingHandler
from paradigm.storage.checkpoints import Checkpoint, CheckpointManager
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

        # State set during run
        self._thread_id: str = ""
        self._seed_prompt: str = ""
        self._mode: str = "directed"
        self._agents: dict[str, Agent] = {}
        self._messages: list[dict[str, Any]] = []
        self._phase_manager: PhaseManager | None = None
        self._checkpoint: Checkpoint | None = None
        self._execution_context: str = ""
        self._execution_caveats: list[str] = []
        self._execution_figures: list[tuple[str, Path]] = []  # (experiment_name, file_path)
        self._successful_code: list[tuple[str, str]] = []  # (experiment_name, code)
        self._post_execution_summary: str = ""  # Team consensus from POST_EXECUTION
        self._consensus_summary: str = ""  # Accumulated consensus from phase boundaries
        self._planning_action_items: str = ""  # Extracted action items from PLANNING
        self._experiment_metadata: list[dict[str, str | bool]] = []
        self._code_context: str = ""
        self._data_context: str = ""
        self._reference_context: str = ""
        self._resolved_resources: list[ResolvedResource] = []
        self._start_time: float = time.monotonic()

        # Handler delegates
        self._literature = LiteratureHandler(self)
        self._debate = DebateHandler(self)
        self._writing = WritingHandler(self)
        self._review = ReviewHandler(self)
        self._citation_handler = CitationHandler(self)
        self._experimentation = ExperimentationHandler(self)
        self._memory = MemoryHandler(self)

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
        self._mode = mode
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

        self._seed_prompt = seed_prompt
        self._messages = []
        self._execution_context = ""
        self._execution_caveats = []
        self._execution_figures = []
        self._successful_code = []
        self._post_execution_summary = ""
        self._consensus_summary = ""
        self._planning_action_items = ""
        self._experiment_metadata = []
        self._code_context = ""
        self._data_context = ""
        self._reference_context = ""
        self._resolved_resources = []
        self._start_time = time.monotonic()

        # Reset handler state for new cycle
        self._literature.reset_cycle()
        self._debate.reset_cycle()
        self._review.reset_cycle()

        # Create agent team
        agents = self._factory.create_team(team_roles, skill_mode="default")
        self._agents = {a.agent_id: a for a in agents}

        # Phase 1: SEEDING
        self._display.phase_transition(ResearchPhase.SEEDING)
        self._thread_id = await self._run_seeding_phase(seed_prompt, mode)

        # Initialize phase manager (starts at SEEDING, transition to IDEATION)
        self._phase_manager = PhaseManager(ResearchPhase.SEEDING)

        # Seed discovery via Perplexity (optional, pre-populates literature context)
        if self._config.citation.enable_seed_discovery:
            try:
                n = await self._literature.run_seed_discovery(seed_prompt)
                if n > 0:
                    self._display.seed_discovery_complete(n)
            except Exception as e:
                self._logger.log_error(e, thread_id=self._thread_id)
                self._display.seed_discovery_error(e)

        # Phase 2: IDEATION
        max_rounds = self._config.orchestrator.max_rounds_per_phase
        checkpoint_interval = self._config.orchestrator.checkpoint_interval
        agent_count = len(self._agents)

        self._phase_manager.transition_to(ResearchPhase.IDEATION)
        self._log_phase_transition(ResearchPhase.SEEDING, ResearchPhase.IDEATION)
        active_ideation = self._get_phase_active_roles(ResearchPhase.IDEATION)
        active_ideation_count = (
            sum(1 for a in self._agents.values() if a.skill_profile in active_ideation)
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
                self._logger.log_error(e, thread_id=self._thread_id)

        # Phase 3: PLANNING (intervention check)
        intervention = self._check_intervention("ideation", "planning")
        if intervention == "abort":
            self._db.update_thread(self._thread_id, status="aborted")
            self._display.phase_aborted()
            return self._thread_id
        if intervention == "pause":
            self._db.update_thread(self._thread_id, status="paused")
            self._display.phase_paused()
            return self._thread_id

        self._phase_manager.transition_to(ResearchPhase.PLANNING)
        self._log_phase_transition(ResearchPhase.IDEATION, ResearchPhase.PLANNING)
        self._messages = []  # Reset messages for new phase
        active_planning = self._get_phase_active_roles(ResearchPhase.PLANNING)
        active_planning_count = (
            sum(1 for a in self._agents.values() if a.skill_profile in active_planning)
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

        # Extract action items from PLANNING for EXECUTION (Fix 5)
        self._planning_action_items = self._extract_planning_actions()

        # Phase 3.5: EXECUTION (optional — only when experimentalist present + sandbox enabled)
        should_experiment = (
            self._config.orchestrator.enable_experimentation
            and self._config.sandbox.enabled
            and self._find_agent_by_role("experimentalist") is not None
        )
        if should_experiment:
            intervention = self._check_intervention("planning", "execution")
            if intervention == "abort":
                self._db.update_thread(self._thread_id, status="aborted")
                self._display.phase_aborted()
                return self._thread_id
            if intervention == "pause":
                self._db.update_thread(self._thread_id, status="paused")
                self._display.phase_paused()
                return self._thread_id

            self._phase_manager.transition_to(ResearchPhase.EXECUTION)
            self._log_phase_transition(ResearchPhase.PLANNING, ResearchPhase.EXECUTION)
            self._messages = []
            self._display.phase_transition("EXECUTION")
            exp_result = await self._experimentation.run_experimentation_phase()
            self._execution_context = exp_result.execution_context
            self._execution_caveats = exp_result.caveats
            self._execution_figures = exp_result.execution_figures
            self._successful_code = exp_result.successful_code
            self._experiment_metadata = exp_result.experiment_metadata

        # Phase 3.75: POST_EXECUTION discussion (optional — after experimentation)
        ran_post_execution = False
        if (
            should_experiment
            and self._execution_context
            and self._config.orchestrator.enable_post_execution_discussion
        ):
            self._phase_manager.transition_to(ResearchPhase.POST_EXECUTION)
            self._log_phase_transition(ResearchPhase.EXECUTION, ResearchPhase.POST_EXECUTION)
            self._messages = []
            # Shorter discussion: cap at 2 rounds
            post_exec_rounds = min(2, max_rounds)
            active_post_exec = self._get_phase_active_roles(ResearchPhase.POST_EXECUTION)
            active_post_exec_count = (
                sum(1 for a in self._agents.values() if a.skill_profile in active_post_exec)
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
            ran_post_execution = True
            # Capture POST_EXECUTION discussion summary for WRITING
            self._post_execution_summary = self._build_post_execution_summary()

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
            intervention = self._check_intervention(from_label, "writing")
            if intervention == "abort":
                self._db.update_thread(self._thread_id, status="aborted")
                self._display.phase_aborted()
                return self._thread_id
            if intervention == "pause":
                self._db.update_thread(self._thread_id, status="paused")
                self._display.phase_paused()
                return self._thread_id

            self._phase_manager.transition_to(ResearchPhase.WRITING)
            self._log_phase_transition(from_phase, ResearchPhase.WRITING)
            self._messages = []
            self._display.phase_transition("WRITING")
            paper_draft = await self._writing.run_writing_phase()

            # Guard: if writing failed (empty/too short paper), skip all review phases
            if paper_draft is None:
                self._display.writing_failed_skip_review()
                # Save auxiliary files even on failure (search log is still useful)
                thread = self._db.get_thread(self._thread_id)
                paper_id = thread.get("current_draft_id") if thread else None
                if paper_id:
                    self._save_auxiliary_files(paper_id)
                self._print_token_summary()
                return self._thread_id

            # Phase 5: INTERNAL REVIEW
            self._phase_manager.transition_to(ResearchPhase.INTERNAL_REVIEW)
            self._log_phase_transition(ResearchPhase.WRITING, ResearchPhase.INTERNAL_REVIEW)
            self._messages = []
            self._display.phase_transition("INTERNAL_REVIEW")
            await self._review.run_review_phase(paper_draft)

            # Check if internal review exhausted iterations without acceptance
            thread = self._db.get_thread(self._thread_id)
            if thread and thread.get("status") == "writing_failed":
                self._display.writing_failed_review_exhausted()
                paper_id = thread.get("current_draft_id") if thread else None
                if paper_id:
                    self._save_auxiliary_files(paper_id)
                self._print_token_summary()
                return self._thread_id

            # Phase 6: PEER REVIEW PIPELINE (optional)
            if self._config.orchestrator.enable_peer_review:
                # Intervention check before SUBMITTED
                intervention = self._check_intervention("internal", "submitted")
                if intervention == "abort":
                    self._db.update_thread(self._thread_id, status="aborted")
                    self._display.phase_aborted()
                    return self._thread_id
                if intervention == "pause":
                    self._db.update_thread(self._thread_id, status="paused")
                    self._display.phase_paused()
                    return self._thread_id

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

                    thread = self._db.get_thread(self._thread_id)
                    paper_id = thread["current_draft_id"] if thread else None
                    if paper_id and decision in ("accept", "minor_revision"):
                        await publish_paper(paper_id, self._db, self._corpus, self._logger, reviews)
                        self._db.update_thread(self._thread_id, status="published")
                        self._display.paper_published()
                    elif paper_id:
                        from paradigm.journal.publication import reject_paper

                        reject_paper(paper_id, self._db, reviews, self._logger)
                        self._db.update_thread(self._thread_id, status="rejected")
                        self._display.paper_rejected()
                else:
                    # Desk rejected
                    self._db.update_thread(self._thread_id, status="rejected")
            else:
                self._db.update_thread(self._thread_id, status="reviewed")
        else:
            self._db.update_thread(self._thread_id, status="planning_complete")

        # Save auxiliary files (search log, review report)
        thread = self._db.get_thread(self._thread_id)
        paper_id = thread.get("current_draft_id") if thread else None
        if paper_id:
            self._save_auxiliary_files(paper_id)

        # Display token usage summary
        self._print_token_summary()

        # Generate agent episodic memories via reflection
        await self._memory.run_memory_generation()

        return self._thread_id

    async def _run_seeding_phase(self, seed_prompt: str, mode: str) -> str:
        """Initialize the research thread. No agent calls.

        Args:
            seed_prompt: Research question or topic.
            mode: Operating mode.

        Returns:
            Thread ID.
        """
        thread_id = f"thread-{uuid.uuid4().hex[:12]}"
        participants = list(self._agents.keys())

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

        self._resolved_resources = resolved
        self._code_context = build_code_context(resolved)
        self._data_context = build_data_context(resolved)
        self._reference_context = build_reference_context(resolved)

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
                self._graveyard_context = "\n".join(lines)
            else:
                self._graveyard_context = ""
        except Exception as e:
            self._logger.log_error(e, thread_id=thread_id)
            self._display.graveyard_error(e)
            self._graveyard_context = ""

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
        scheduler = Scheduler(list(self._agents.values()), mode="phase_appropriate")

        # Compute active agent count for convergence detection
        active_roles = self._get_phase_active_roles(phase)
        if active_roles is not None:
            active_count = sum(1 for a in self._agents.values() if a.skill_profile in active_roles)
        else:
            active_count = len(self._agents)

        for round_num in range(1, max_rounds + 1):
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
                            phase, rationale, self._messages[-active_count:]
                        )
                        if consensus:
                            self._consensus_summary += consensus + "\n\n"
                        break
                except Exception:
                    pass  # Non-fatal — continue with remaining rounds

            # Checkpoint at intervals
            should_checkpoint = (
                self._config.orchestrator.enable_checkpointing
                and round_num % checkpoint_interval == 0
            )
            if should_checkpoint:
                try:
                    self._checkpoint = await self._checkpoint_mgr.create_checkpoint(
                        thread_id=self._thread_id,
                        phase=str(phase),
                        round_number=round_num,
                        messages=self._messages,
                        previous_checkpoint=self._checkpoint,
                    )
                    self._display.checkpoint_saved(f"round {round_num}")
                except Exception as e:
                    self._logger.log_error(e, thread_id=self._thread_id)
                    self._display.checkpoint_error(e)

        # Final checkpoint at end of phase
        if self._messages and self._config.orchestrator.enable_checkpointing:
            try:
                self._checkpoint = await self._checkpoint_mgr.create_checkpoint(
                    thread_id=self._thread_id,
                    phase=str(phase),
                    round_number=max_rounds,
                    messages=self._messages,
                    previous_checkpoint=self._checkpoint,
                )
                self._display.checkpoint_saved("end of phase")
            except Exception as e:
                self._logger.log_error(e, thread_id=self._thread_id)
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
                aid for aid in speaker_order if self._agents[aid].skill_profile in active_roles
            ]

        for agent_id in speaker_order:
            agent = self._agents[agent_id]
            prompt = self._build_agent_prompt(agent, phase, round_num)

            try:
                response = await agent.generate(prompt)
            except Exception as e:
                self._logger.log_error(e, agent_id=agent_id, thread_id=self._thread_id)
                self._display.agent_error(agent_id, e)
                continue  # Skip this agent for this round

            # Create structured message
            msg = agent.format_message(
                to="team",
                thread_id=self._thread_id,
                phase=str(phase),
                message_type="proposal" if round_num == 1 else "discussion",
                content=response.content,
            )

            # Store message
            msg_dict = msg.model_dump(by_alias=True)
            self._messages.append(msg_dict)

            total_tokens = response.usage.input_tokens + response.usage.output_tokens
            self._display.agent_response(
                agent_id,
                total_tokens,
                role=agent.skill_profile,
                model=response.model,
                content=response.content,
            )

            # Log message and token usage
            self._logger.log_agent_message(
                agent_id=agent_id,
                thread_id=self._thread_id,
                phase=str(phase),
                message=msg_dict,
            )
            self._logger.log_api_call(
                agent_id=agent_id,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            self._db.record_token_usage(
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                agent_id=agent_id,
                thread_id=self._thread_id,
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
        mode_overrides = _MODE_PROMPT_OVERRIDES.get(self._mode, {})
        if template_key in mode_overrides:
            template = mode_overrides[template_key]

        # Build checkpoint context
        checkpoint_context = ""
        if self._checkpoint:
            checkpoint_context = self._checkpoint.to_context_string() + "\n\n"

        # Build recent messages string
        recent = self._messages[-_RECENT_MESSAGES_LIMIT:]
        recent_messages = "\n\n".join(
            f"**{m.get('from', 'unknown')}** ({m.get('type', 'message')}): "
            f"{m.get('content', '')[:500]}"
            for m in recent
        )

        # Phase-appropriate context injection — only inject what each phase needs
        context_needs = _PHASE_CONTEXT_NEEDS.get(phase, set())

        if "literature" in context_needs:
            lit = self._literature.literature_context
            if lit:
                checkpoint_context = "## Literature Context\n" + lit + "\n\n" + checkpoint_context

        if "references" in context_needs and self._reference_context:
            checkpoint_context = self._reference_context + "\n\n" + checkpoint_context

        if "execution" in context_needs and self._execution_context:
            exec_block = "## Experiment Results\n" + self._execution_context
            if self._execution_caveats:
                exec_block += "\n\n## Execution Caveats\n" + "\n".join(
                    f"- {c}" for c in self._execution_caveats
                )
            checkpoint_context = exec_block + "\n\n" + checkpoint_context

        if "code_data" in context_needs:
            if self._data_context:
                checkpoint_context = self._data_context + "\n\n" + checkpoint_context
            if self._code_context:
                checkpoint_context = self._code_context + "\n\n" + checkpoint_context

        # Graveyard context stays IDEATION round 1 only
        if phase == ResearchPhase.IDEATION and round_num == 1:
            graveyard = getattr(self, "_graveyard_context", "")
            if graveyard:
                checkpoint_context = checkpoint_context + graveyard + "\n\n"

        # Inject agent episodic memories (cross-cycle learning)
        if (
            "memory" in context_needs
            and self._memory_store is not None
            and self._config.memory.enabled
        ):
            from paradigm.agents.memory import format_memory_context, rank_memories_with_recency

            raw_memories = self._memory_store.search(
                query=self._seed_prompt,
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

        formatted = template.format(
            seed_prompt=self._seed_prompt,
            checkpoint_context=checkpoint_context,
            recent_messages=recent_messages,
        )

        # Inject prior phase consensus so agents don't re-derive settled conclusions
        if self._consensus_summary:
            formatted += (
                "\n\n## Prior Phase Consensus\n"
                "The following conclusions were agreed upon in earlier phases. "
                "Do NOT re-derive these — build on them.\n\n" + self._consensus_summary
            )

        # Inject role-specific and general reinforcements for later rounds
        if round_num > 1:
            # General anti-repetition rule for all agents
            formatted += _GENERAL_LATER_ROUND_REINFORCEMENT
            # Role-specific reinforcement (from profile or hardcoded fallback)
            if self._profile is not None:
                reinforcement = self._profile.role_later_round_reinforcements.get(
                    agent.skill_profile, ""
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
            # Role-specific search strategy to differentiate agent searches
            if self._profile is not None:
                role_strategy = self._profile.role_search_strategies.get(agent.skill_profile, "")
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

        return formatted

    def _check_intervention(self, from_phase: str, to_phase: str) -> str:
        """Check intervention hook before a phase transition.

        Args:
            from_phase: Phase transitioning from.
            to_phase: Phase transitioning to.

        Returns:
            "continue", "pause", or "abort".
        """
        if self._intervention_hook is None:
            return "continue"
        result = self._intervention_hook(self._thread_id, from_phase, to_phase)
        if result not in ("continue", "pause", "abort"):
            return "continue"
        return result

    def _build_post_execution_summary(self) -> str:
        """Build a compact summary of POST_EXECUTION discussion findings.

        Captures each agent's key conclusions from the POST_EXECUTION phase
        so they can be injected into WRITING prompts. Truncates each agent's
        contribution to keep the summary concise.

        Returns:
            Formatted summary string, or empty string if no messages.
        """
        if not self._messages:
            return ""

        parts: list[str] = []
        for msg in self._messages:
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
        for msg in self._messages:
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

        Grabs the last N messages (one per active agent) from the current round,
        truncates each to 500 chars, and asks an LLM whether agents have reached
        substantial agreement.

        Args:
            phase: Current research phase.
            round_num: Current round number.
            active_agent_count: Number of active agents in this phase.

        Returns:
            Tuple of (is_converged, rationale).
        """
        # Grab last N messages (N = active_agent_count)
        recent = self._messages[-active_agent_count:]
        if len(recent) < 2:
            return False, ""

        # Format messages, truncating content to 500 chars
        formatted_messages = "\n\n".join(
            f"**{m.get('from', 'unknown')}**: {m.get('content', '')[:500]}" for m in recent
        )

        prompt_text = _CONVERGENCE_CHECK_PROMPT.format(
            phase=str(phase).upper(),
            round_num=round_num,
            messages=formatted_messages,
        )

        provider = self._config.get_provider()
        text, input_tokens, output_tokens = provider.complete(
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
            thread_id=self._thread_id,
        )
        self._logger.log_api_call(
            agent_id="convergence_checker",
            model=provider.default_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        # Parse JSON response (strip markdown fences if present)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        result = json.loads(cleaned)
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
            },
            thread_id=self._thread_id,
            phase=str(phase),
        )

        return is_converged, rationale

    def _log_phase_transition(self, from_phase: ResearchPhase, to_phase: ResearchPhase) -> None:
        """Log a phase transition event."""
        self._logger.log(
            EventType.PHASE_TRANSITION,
            content={"from": str(from_phase), "to": str(to_phase)},
            thread_id=self._thread_id,
            phase=str(to_phase),
        )
        self._db.update_thread(self._thread_id, current_phase=str(to_phase))

    def _find_agent_by_role(self, role: str) -> Agent | None:
        """Find an agent by its skill profile / role.

        Args:
            role: Role name (e.g., 'writer', 'editor').

        Returns:
            Agent if found, None otherwise.
        """
        for agent in self._agents.values():
            if agent.skill_profile == role:
                return agent
        return None

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
        agent = self._agents.get(agent_id)
        self._display.agent_response(
            agent_id,
            total_tokens,
            role=agent.skill_profile if agent else "",
            model=response.model,
            content=response.content,
        )

        self._logger.log_agent_message(
            agent_id=agent_id,
            thread_id=self._thread_id,
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
        )
        self._db.record_token_usage(
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_id=agent_id,
            thread_id=self._thread_id,
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
        lines.append(f"Thread: {self._thread_id}")
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
        lines.append(f"Thread: {self._thread_id}")
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
        elapsed = time.monotonic() - self._start_time
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

        events = self._logger.read_events(thread_id=self._thread_id)
        if not events:
            return

        lines = ["# Research Transcript\n"]
        lines.append(f"Thread: {self._thread_id}")
        lines.append(f"Paper: {paper_id}")
        lines.append(f"Seed prompt: {self._seed_prompt[:200]}\n")
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
        """Write working experiment code to experiments/ subdirectory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._config.storage.papers_dir
        if papers_dir is None:
            return

        paper_dir = papers_dir / paper_id
        exp_dir = paper_dir / "experiments"
        exp_dir.mkdir(parents=True, exist_ok=True)

        readme_lines = ["# Experiments\n"]
        readme_lines.append(
            "Working experiment code that produced successful results during the EXECUTION phase.\n"
        )

        for exp_name, code in self._successful_code:
            # Sanitize experiment name for filename
            safe_name = re.sub(r"[^\w\-]", "_", exp_name).strip("_").lower()
            if not safe_name:
                safe_name = "experiment"
            filename = f"{safe_name}.py"

            # Write code file
            filepath = exp_dir / filename
            filepath.write_text(code)

            readme_lines.append(f"- **{exp_name}** → `{filename}`")

        # Write README
        readme_path = exp_dir / "README.md"
        readme_path.write_text("\n".join(readme_lines) + "\n")

    def _get_token_summary(self) -> dict[str, int]:
        """Get token usage for the current thread.

        Returns:
            Dict with input_tokens, output_tokens, total_tokens.
        """
        return self._db.get_token_usage(thread_id=self._thread_id)

    def _print_token_summary(self) -> None:
        """Display token usage and elapsed time at end of research cycle."""
        usage = self._get_token_summary()
        input_k = usage["input_tokens"] / 1000
        output_k = usage["output_tokens"] / 1000
        total_k = usage["total_tokens"] / 1000

        elapsed = time.monotonic() - self._start_time
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
            thread_id=self._thread_id,
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
        if self._successful_code:
            self._save_experiment_code(paper_id)
