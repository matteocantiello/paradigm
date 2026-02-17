"""Main orchestration engine for research cycles."""

from __future__ import annotations

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
    _DEBATE_ENABLED_PHASES,
    _EXECUTION_STDERR_LIMIT,
    _FILE_NOT_FOUND_PATTERNS,
    _LITERATURE_INSTRUCTION,
    _MAX_RETRIES_PER_EXPERIMENT,
    _MODE_PROMPT_OVERRIDES,
    _NETWORK_ERROR_PATTERNS,
    _PHASE_ACTIVE_ROLES,
    _PHASE_CONTEXT_NEEDS,
    _PHASE_INSTRUCTIONS,
    _RECENT_MESSAGES_LIMIT,
    _SEARCH_ENABLED_PHASES,
    _WRITING_MAX_TOKENS,
    DEFAULT_TEAM_ROLES,
    MODE_TEAM_ROLES,
    InterventionHook,
    _extract_code_blocks,
    _format_execution_result,
    _is_vacuous_success,
    _list_shared_files,
)
from paradigm.orchestrator.debate import DebateHandler
from paradigm.orchestrator.literature import LiteratureHandler
from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.review import ReviewHandler
from paradigm.orchestrator.scheduler import Scheduler
from paradigm.orchestrator.writing import WritingHandler
from paradigm.sandbox.executor import CodeExecutor
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus
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
        """
        self._config = config
        self._db = database
        self._corpus = corpus
        self._logger = logger
        self._factory = agent_factory
        self._intervention_hook = intervention_hook
        self._memory_store = memory_store
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
        self._execution_figures: list[tuple[str, Path]] = []  # (experiment_name, file_path)
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
            team_roles: Agent roles to include. Defaults to DEFAULT_TEAM_ROLES.

        Returns:
            Thread ID of the completed cycle.
        """
        self._mode = mode
        if team_roles is None:
            team_roles = list(MODE_TEAM_ROLES.get(mode, DEFAULT_TEAM_ROLES))

        self._seed_prompt = seed_prompt
        self._messages = []
        self._execution_context = ""
        self._execution_figures = []
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
        active_ideation = _PHASE_ACTIVE_ROLES.get(ResearchPhase.IDEATION)
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
        active_planning = _PHASE_ACTIVE_ROLES.get(ResearchPhase.PLANNING)
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
            await self._run_experimentation_phase()

        # Phase 4: WRITING (optional, controlled by config)
        if self._config.orchestrator.enable_writing:
            from_phase = ResearchPhase.EXECUTION if should_experiment else ResearchPhase.PLANNING
            from_label = "execution" if should_experiment else "planning"

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
        if self._memory_store is not None and self._config.memory.enabled:
            try:
                from paradigm.agents.memory import generate_reflections

                self._display.memory_generating()
                all_messages = self._collect_all_messages()
                thread = self._db.get_thread(self._thread_id)
                outcome = thread.get("status", "completed") if thread else "completed"
                _reflection_provider = self._config.get_provider()
                reflections = await generate_reflections(
                    agents=self._agents,
                    messages=all_messages,
                    seed_prompt=self._seed_prompt,
                    thread_id=self._thread_id,
                    outcome_summary=f"Research cycle ended with status: {outcome}",
                    provider=_reflection_provider,
                    model=_reflection_provider.default_model,
                    database=self._db,
                )
                total = sum(len(r.memories) for r in reflections)
                for r in reflections:
                    self._memory_store.add_memories(r.memories)
                self._display.memory_stored(total, len(reflections))
                self._logger.log(
                    EventType.MEMORY_GENERATED,
                    content={
                        "thread_id": self._thread_id,
                        "total_memories": total,
                        "agents": [r.agent_id for r in reflections],
                    },
                    thread_id=self._thread_id,
                )
            except Exception as e:
                self._display.memory_error(e)

        return self._thread_id

    async def _run_experimentation_phase(self) -> None:
        """Run the EXECUTION phase: agents propose and run computational experiments."""
        explicit = self._config.orchestrator.max_experiment_rounds
        max_rounds = (
            explicit if explicit is not None else 2 * self._config.orchestrator.max_rounds_per_phase
        )

        # Collect sandbox paths for cloned repos (PYTHONPATH injection)
        repo_paths = [
            r.sandbox_path
            for r in self._resolved_resources
            if r.resource_type == ResourceType.CODE_REPO and r.sandbox_path and r.error is None
        ]
        # Also add parent directories of CODE_FILE resources so they are importable
        code_file_dirs = {
            str(Path(r.sandbox_path).parent)
            for r in self._resolved_resources
            if r.resource_type == ResourceType.CODE_FILE and r.sandbox_path and r.error is None
        }
        repo_paths.extend(sorted(code_file_dirs))

        # Per-thread workspace persists across executions so experiments
        # can read files (CSVs, data) produced by earlier experiments.
        workspace_dir = self._config.storage.data_dir / "workspaces" / self._thread_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        executor = CodeExecutor(
            config=self._config.sandbox,
            logger=self._logger,
            data_dir=self._config.storage.data_dir,
            workspace_dir=workspace_dir,
        )

        all_results: list[str] = []
        self._execution_figures = []

        try:
            for round_num in range(1, max_rounds + 1):
                self._display.experiment_round(round_num, max_rounds)
                self._literature.search_count_this_round = 0

                # Find experimenter (prefer experimentalist, fallback to analyst)
                experimenter = self._find_agent_by_role("experimentalist")
                if experimenter is None:
                    experimenter = self._find_agent_by_role("analyst")
                if experimenter is None:
                    self._display.experiment_no_agent()
                    break

                # Build prompt
                checkpoint_context = ""
                if self._checkpoint:
                    checkpoint_context = self._checkpoint.to_context_string() + "\n\n"

                # Inject actual file listing so agents know what exists
                file_listing = _list_shared_files(self._config.storage.data_dir)
                checkpoint_context = file_listing + "\n\n" + checkpoint_context

                # Inject code/data context from resolved resources
                if self._code_context:
                    checkpoint_context += self._code_context + "\n\n"
                if self._data_context:
                    checkpoint_context += self._data_context + "\n\n"

                previous_results = "\n\n".join(all_results) if all_results else ""

                if round_num == 1:
                    template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["propose_experiment"]
                    prompt = template.format(
                        seed_prompt=self._seed_prompt,
                        checkpoint_context=checkpoint_context,
                        previous_results=previous_results,
                    )
                else:
                    template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["analyze_results"]
                    prompt = template.format(
                        seed_prompt=self._seed_prompt,
                        checkpoint_context=checkpoint_context,
                        previous_results=previous_results,
                    )

                try:
                    response = await experimenter.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
                except Exception as e:
                    self._logger.log_error(
                        e, agent_id=experimenter.agent_id, thread_id=self._thread_id
                    )
                    self._display.agent_error(experimenter.agent_id, e)
                    break

                self._log_agent_response(
                    experimenter.agent_id, response, ResearchPhase.EXECUTION, "experiment_proposal"
                )

                await self._literature.process_search_requests(
                    experimenter.agent_id, response.content, ResearchPhase.EXECUTION
                )
                await self._literature.process_literature_actions(
                    experimenter.agent_id, response.content, ResearchPhase.EXECUTION
                )

                # Extract code blocks
                code_blocks = _extract_code_blocks(response.content)
                if not code_blocks and round_num > 1:
                    self._display.experiment_declared_sufficient()
                    break
                if not code_blocks:
                    self._display.experiment_no_code()
                    continue

                # Execute each code block
                round_total = 0
                round_failures = 0
                for exp_name, code in code_blocks:
                    self._display.experiment_running(exp_name)
                    result = await self._execute_with_retry(
                        executor,
                        experimenter,
                        exp_name,
                        code,
                        checkpoint_context,
                        repo_paths=repo_paths,
                    )
                    formatted = _format_execution_result(exp_name, result)
                    all_results.append(formatted)

                    round_total += 1
                    if result.status != ExecutionStatus.SUCCESS:
                        round_failures += 1

                    # Track output figures
                    for output_file in result.output_files:
                        if output_file.filename.endswith((".png", ".pdf")):
                            self._execution_figures.append((exp_name, Path(output_file.path)))

                    status_str = result.status.value
                    self._display.experiment_result(exp_name, status_str)

                # Circuit breaker: if >70% of executions failed, stop experimenting
                if round_total >= 3 and (round_failures / round_total) > 0.7:
                    self._display.experiment_high_failure_rate(round_failures, round_total)
                    break

            # Build execution context for WRITING phase
            self._execution_context = "\n\n".join(all_results) if all_results else ""

            # Checkpoint at end of execution
            if self._config.orchestrator.enable_checkpointing:
                try:
                    self._checkpoint = await self._checkpoint_mgr.create_checkpoint(
                        thread_id=self._thread_id,
                        phase=str(ResearchPhase.EXECUTION),
                        round_number=max_rounds,
                        messages=self._messages,
                        previous_checkpoint=self._checkpoint,
                    )
                    self._display.checkpoint_saved("end of execution")
                except Exception as e:
                    self._logger.log_error(e, thread_id=self._thread_id)
                    self._display.checkpoint_error(e)

        finally:
            await executor.cleanup()

    async def _execute_with_retry(
        self,
        executor: CodeExecutor,
        experimenter: Agent,
        experiment_name: str,
        code: str,
        checkpoint_context: str,
        repo_paths: list[str] | None = None,
    ) -> ExecutionResult:
        """Execute code with retry on failure/rejection.

        Args:
            executor: CodeExecutor instance.
            experimenter: Agent that proposed the code.
            experiment_name: Name of the experiment.
            code: Python code to execute.
            checkpoint_context: Checkpoint context string.

        Returns:
            Final ExecutionResult.
        """
        current_code = code
        for attempt in range(_MAX_RETRIES_PER_EXPERIMENT + 1):
            request = ExecutionRequest(
                code=current_code,
                agent_id=experimenter.agent_id,
                thread_id=self._thread_id,
            )
            result = await executor.execute(request, repo_paths=repo_paths)

            # Timeout — return immediately
            if result.status == ExecutionStatus.TIMEOUT:
                return result

            # Success — check for vacuous output before accepting
            if result.status == ExecutionStatus.SUCCESS:
                if not _is_vacuous_success(result):
                    return result
                # Vacuous: reclassify as failure so retry kicks in
                result = result.model_copy(
                    update={
                        "status": ExecutionStatus.FAILURE,
                        "error_message": (
                            "Script exited successfully but produced no scientific output. "
                            "No figures were saved and stdout contained no quantitative results. "
                            "Ensure your script: (1) prints numerical results to stdout, "
                            "and/or (2) saves figures with plt.savefig('name.png')."
                        ),
                    }
                )
                # Fall through to retry logic below

            # Last attempt — return whatever we got
            if attempt == _MAX_RETRIES_PER_EXPERIMENT:
                return result

            # Build error feedback for retry
            error_parts = []
            if result.status == ExecutionStatus.REJECTED:
                error_parts.append(f"**Safety rejection:** {result.error_message}")
            else:
                error_parts.append(f"**Execution failed** (status: {result.status.value})")
                if result.stderr:
                    error_parts.append(f"```\n{result.stderr[:_EXECUTION_STDERR_LIMIT]}\n```")
                if result.error_message:
                    error_parts.append(f"Error: {result.error_message}")

            # Detect network errors and prepend clear guidance
            stderr_text = result.stderr or ""
            if any(p in stderr_text for p in _NETWORK_ERROR_PATTERNS):
                error_parts.insert(
                    0,
                    "**\u26a0 NETWORK ERROR:** This failure is because the sandbox has "
                    "NO internet access. Do NOT use requests, urllib, httpx, or any "
                    "HTTP calls. Instead:\n"
                    "- Generate synthetic data that matches the expected statistical "
                    "properties\n"
                    "- Use files already available under /data/shared/ or "
                    "/data/workspace/\n"
                    "- Create mathematical models to simulate the data you need\n",
                )

            # Detect file-not-found errors (check both stderr and stdout for
            # scripts that caught the exception and printed to stdout)
            combined_text = stderr_text + (result.stdout or "")
            if any(p in combined_text for p in _FILE_NOT_FOUND_PATTERNS):
                file_listing = _list_shared_files(self._config.storage.data_dir)
                error_parts.insert(
                    0,
                    "**\u26a0 FILE NOT FOUND:** Your script tried to open a file that "
                    "does not exist in the sandbox. Do NOT guess or invent filenames.\n\n"
                    f"{file_listing}\n"
                    "Use ONLY the exact paths listed above. If no suitable data files "
                    "are available, generate realistic synthetic data instead.\n",
                )

            error_feedback = "\n\n".join(error_parts)
            self._display.experiment_retry(attempt + 1, _MAX_RETRIES_PER_EXPERIMENT)

            template = _PHASE_INSTRUCTIONS[ResearchPhase.EXECUTION]["retry_after_failure"]
            retry_prompt = template.format(
                seed_prompt=self._seed_prompt,
                checkpoint_context=checkpoint_context,
                error_feedback=error_feedback,
            )

            try:
                response = await experimenter.generate(retry_prompt, max_tokens=_WRITING_MAX_TOKENS)
            except Exception as e:
                self._logger.log_error(e, agent_id=experimenter.agent_id, thread_id=self._thread_id)
                return result  # Return last failed result

            self._log_agent_response(
                experimenter.agent_id, response, ResearchPhase.EXECUTION, "retry"
            )

            # Extract corrected code
            blocks = _extract_code_blocks(response.content)
            if not blocks:
                return result  # Agent didn't provide corrected code
            current_code = blocks[0][1]  # Use first block

        return result  # Should not reach here, but type-safety

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

        for round_num in range(1, max_rounds + 1):
            self._display.round_start(round_num, max_rounds)
            await self._run_round(phase, round_num, scheduler)
            scheduler.advance_round()

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
        active_roles = _PHASE_ACTIVE_ROLES.get(phase)
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

        # Inject discovered paper index for round 2+ in search-enabled phases
        # so agents always have concrete IDs for [FOLLOW:] / [CITED_BY:]
        if phase in _SEARCH_ENABLED_PHASES and round_num >= 2:
            paper_index = self._literature.build_paper_index()
            if paper_index:
                formatted = paper_index + "\n" + formatted

        # Append literature search instructions for search-enabled phases
        if phase in _SEARCH_ENABLED_PHASES:
            formatted += _LITERATURE_INSTRUCTION

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
                "content": response.content[:500],
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

    def _get_token_summary(self) -> dict[str, int]:
        """Get token usage for the current thread.

        Returns:
            Dict with input_tokens, output_tokens, total_tokens.
        """
        return self._db.get_token_usage(thread_id=self._thread_id)

    def _collect_all_messages(self) -> list[dict[str, Any]]:
        """Collect all agent messages from the event log for this thread.

        Returns:
            List of message dicts with keys like 'from', 'to', 'type', 'content'.
        """
        events = self._logger.read_events(
            event_type=EventType.AGENT_MESSAGE,
            thread_id=self._thread_id,
        )
        return [e.content for e in events if isinstance(e.content, dict)]

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
        """Save search log and review log alongside the paper.

        Args:
            paper_id: Paper identifier.
        """
        if self._literature.search_log:
            self._save_search_log(paper_id)
        # Always save review log (includes token summary even without reviews)
        self._save_review_log(paper_id)
