"""Main orchestration engine for research cycles."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from paradigm.agents.base import Agent
from paradigm.agents.factory import AgentFactory
from paradigm.config import Config
from paradigm.journal.publication import publish_paper
from paradigm.knowledge.json_utils import first_json_object, strip_fences
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
    stage_local_dataset,
)
from paradigm.logging.events import EventLogger, EventType
from paradigm.logging.stream import ResearchEventStream
from paradigm.orchestrator.artifacts import ArtifactsHandler
from paradigm.orchestrator.citation_handler import CitationHandler
from paradigm.orchestrator.constants import (
    _CHALLENGE_INSTRUCTION,
    _CONVERGENCE_CHECK_PHASES,
    _CONVERGENCE_CHECK_PROMPT,
    _DEBATE_ENABLED_PHASES,
    _GENERAL_LATER_ROUND_REINFORCEMENT,
    _KNOWLEDGE_TAG_INSTRUCTION,
    _MIN_PAPER_LENGTH,
    _MODE_PROMPT_OVERRIDES,
    _MODE_SYNTHESIS_OVERRIDES,
    _PHASE_ACTIVE_ROLES,
    _PHASE_CONTEXT_NEEDS,
    _PHASE_INSTRUCTIONS,
    _PROMPT_REFINER_MAX_TOKENS,
    _PROMPT_REFINER_MIN_RATIO,
    _PROMPT_REFINER_PROMPT,
    _PROMPT_REFINER_SYSTEM,
    _RECENT_MESSAGES_LIMIT,
    _SEARCH_ENABLED_PHASES,
    _SYNTHESIS_CLOSING_TEMPLATES,
    DecisionHook,
    InterventionHook,
)
from paradigm.orchestrator.debate import DebateHandler
from paradigm.orchestrator.experimentation import ExperimentationHandler
from paradigm.orchestrator.human_gate import build_provenance, decide_human_gate
from paradigm.orchestrator.literature import LiteratureHandler
from paradigm.orchestrator.memory import MemoryHandler
from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.preregistration import PreRegistrationHandler
from paradigm.orchestrator.reflection import ReflectionHandler
from paradigm.orchestrator.review import ReviewHandler
from paradigm.orchestrator.scheduler import Scheduler
from paradigm.orchestrator.state import ResearchState
from paradigm.orchestrator.verification import VerificationKernel
from paradigm.orchestrator.writing import WritingHandler
from paradigm.storage.checkpoints import CheckpointManager
from paradigm.storage.database import Database

if TYPE_CHECKING:
    from paradigm.display import DisplayManager
    from paradigm.journal.paper import PaperDraft


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
        decision_hook: DecisionHook | None = None,
        memory_store: Any | None = None,
        display: DisplayManager | None = None,
        domain_profile: Any | None = None,
        pause_gate: Callable[[], Awaitable[None]] | None = None,
        is_paused: Callable[[], bool] | None = None,
        guidance_provider: Callable[[], Awaitable[list[str]]] | None = None,
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
            decision_hook: Optional callback for STRUCTURED human decisions
                (interactive mode) — hypothesis selection, experiment-plan
                approval. Returns a dict with "decision" plus optional
                "notes"/"modifications".
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
        self._decision_hook = decision_hook
        self._memory_store = memory_store
        self._profile = domain_profile
        # Optional async gate (supplied by the backend) that blocks while the
        # session is paused. Awaited at round boundaries. No-op for the CLI.
        self._pause_gate = pause_gate
        # Optional sync predicate: True when a pause is in effect. Used to persist a
        # checkpoint at the pause point so the run can be RESUMED LATER (even after a
        # backend restart) from where it stopped, not just the last interval/phase end.
        self._is_paused = is_paused
        # Optional async provider (supplied by the backend) that returns any
        # human guidance typed into the GUI since the last round. Drained at
        # round boundaries and injected into the next agent prompts. No-op for
        # the CLI (None → free-text steering simply isn't available there).
        self._guidance_provider = guidance_provider
        # (text, drained_round) — each entry stays visible for the rest of the
        # round it arrived in plus one full round, so every agent sees it once.
        self._pending_guidance: list[tuple[str, int]] = []
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

        # Per-thread dashboard event stream (opened once the thread exists)
        self._events: ResearchEventStream | None = None

        # Handler delegates
        self._artifacts = ArtifactsHandler(self)
        self._literature = LiteratureHandler(self)
        self._debate = DebateHandler(self)
        self._writing = WritingHandler(self)
        self._review = ReviewHandler(self)
        self._reflection = ReflectionHandler(self)
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

    # ------------------------------------------------------------------
    # Dashboard event stream (per-thread, seq-ordered events.jsonl)
    # ------------------------------------------------------------------

    def emit_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        agent: str | None = None,
    ) -> None:
        """Append an event to the per-thread dashboard stream (no-op pre-thread)."""
        if self._events is not None:
            self._events.emit(event_type, payload, agent=agent)

    def _open_event_stream(self, thread_id: str) -> None:
        """Open the per-thread event stream (best-effort, never breaks a run)."""
        try:
            if self._events is not None:
                self._events.close()
            path = self._config.storage.threads_dir / thread_id / "events.jsonl"
            self._events = ResearchEventStream(path)
            self._events.set_context(phase=str(ResearchPhase.SEEDING), round_num=None)
        except Exception as e:
            self._logger.log_error(e, thread_id=thread_id, metadata_key="event_stream")
            self._events = None

    def _emit_run_completed(self) -> None:
        """Emit run.completed with final status + totals, then close the stream.

        Called from the run_research_cycle finally block so EVERY terminal path
        (published, rejected, aborted, failed, cancelled) closes the record.
        """
        if self._events is None:
            return
        try:
            thread = self._db.get_thread(self.state.thread_id) if self.state.thread_id else None
        except Exception:
            thread = None
        status = (thread or {}).get("status") or "failed"
        try:
            tokens = self._get_token_summary().get("total_tokens", 0)
        except Exception:
            tokens = 0
        self.emit_event(
            "run.completed",
            {
                "status": status,
                "paper_id": (thread or {}).get("current_draft_id"),
                "duration_s": round(time.monotonic() - self.state.start_time, 1),
                "totals": {
                    "searches": len(self._literature.search_log),
                    "papers_read": len(self._literature.read_paper_ids),
                    "experiments": len(self.state.experiment_metadata),
                    "debates": sum(self._debate.debate_counts.values()),
                    "tokens": tokens,
                },
            },
        )
        self._events.close()
        self._events = None

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
        datasets: list[str] | None = None,
    ) -> str:
        """Run a full research cycle: SEEDING -> IDEATION -> PLANNING -> WRITING -> REVIEW -> PEER REVIEW.

        Args:
            seed_prompt: The research question or topic.
            mode: Operating mode (directed, explore, etc.).
            team_roles: Agent roles to include. Defaults to profile-defined roles.
            datasets: Local dataset files/dirs to stage into the sandbox-visible
                shared data dir (with data-card schema previews) during seeding.

        Returns:
            Thread ID of the completed cycle.
        """
        try:
            return await self._run_cycle_impl(seed_prompt, mode, team_roles, datasets)
        finally:
            # Close the dashboard record on EVERY terminal path, including
            # cancellation and crashes (run.completed carries the final status).
            try:
                self._emit_run_completed()
            except Exception as e:
                self._logger.log_error(e, thread_id=self.state.thread_id)

    async def _run_cycle_impl(
        self,
        seed_prompt: str,
        mode: str,
        team_roles: list[str] | None,
        datasets: list[str] | None = None,
    ) -> str:
        """The research cycle body (see run_research_cycle).

        A thin sequencer: each stage method runs one phase group and returns
        truthy when the cycle must stop there (abort/pause/gate/failure). All
        terminal-path side effects (thread status, displays, token summary)
        live INSIDE the stage that ends the cycle.
        """
        # Pre-process the prompt into a structured research brief (strong-LLM first
        # pass) BEFORE any downstream use — thread title, resource extraction,
        # topics, requirements checklist and every agent prompt all see the brief.
        original_prompt = seed_prompt
        seed_prompt = await self._refine_seed_prompt(seed_prompt)

        self.state = ResearchState(seed_prompt=seed_prompt, mode=mode)
        if seed_prompt != original_prompt:
            self.state.original_prompt = original_prompt
        self.state.attached_datasets = [str(d) for d in (datasets or [])]
        await self._setup_team(mode, team_roles)
        await self._run_seeding_and_discovery(seed_prompt, mode)

        if await self._run_ideation_stage(seed_prompt):
            return self.state.thread_id
        if await self._run_planning_stage():
            return self.state.thread_id

        # EXECUTION is optional — only when an experimentalist is on the team and
        # the sandbox is enabled. The flag is also needed downstream (POST_EXECUTION
        # condition + WRITING's from-phase label).
        should_experiment = (
            self._config.orchestrator.enable_experimentation
            and self._config.sandbox.enabled
            and self._find_agent_by_role("experimentalist") is not None
        )
        if should_experiment and await self._run_execution_stage():
            return self.state.thread_id

        ran_post_execution = await self._run_post_execution_stage(should_experiment)

        if self._config.orchestrator.enable_writing:
            paper_draft = await self._run_writing_stage(should_experiment, ran_post_execution)
            if paper_draft is None:
                return self.state.thread_id
            # PI reflection (R1): step back, judge the draft, possibly loop back
            # for more experiments / a re-plan before the draft faces review.
            paper_draft = await self._run_reflection_loop(paper_draft, should_experiment)
            if await self._run_internal_review_stage(paper_draft):
                return self.state.thread_id
            if self._config.orchestrator.enable_peer_review:
                if await self._run_peer_review_stage(paper_draft):
                    return self.state.thread_id
            else:
                self._db.update_thread(self.state.thread_id, status="reviewed")
        else:
            self._db.update_thread(self.state.thread_id, status="planning_complete")

        await self._finalize_cycle()
        return self.state.thread_id

    async def _refine_seed_prompt(self, seed_prompt: str) -> str:
        """One strong-LLM pass turning the raw prompt into a structured research
        brief (role ``prompt_refiner``; see _PROMPT_REFINER_PROMPT).

        Best-effort with hard guards: a failed/degenerate generation keeps the
        original, and any URL the refiner drops is re-appended VERBATIM so the
        resource pipeline can never lose an attachment.
        """
        if not getattr(self._config.orchestrator, "enable_prompt_preprocessing", False):
            return seed_prompt
        try:
            provider, model, extra_body = self._config.get_provider_and_model_for_role(
                "prompt_refiner"
            )
            prompt_text = _PROMPT_REFINER_PROMPT.format(seed_prompt=seed_prompt[:20000])
            text, input_tokens, output_tokens = await asyncio.to_thread(
                provider.complete,
                model=model,
                system=_PROMPT_REFINER_SYSTEM,
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=_PROMPT_REFINER_MAX_TOKENS,
                temperature=0.3,
                extra_body=extra_body,
            )
            self._db.record_token_usage(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                agent_id="prompt_refiner",
                thread_id=self.state.thread_id,
            )
            refined = strip_fences(text or "").strip()
            # Degenerate-output guards: keep the original rather than run the whole
            # cycle on a truncated, empty, or off-format generation. A valid brief
            # is structured (## sections per the instructions) — anything else
            # (refusal prose, stray JSON) must not replace the user's prompt.
            if len(refined) < max(80, int(len(seed_prompt) * _PROMPT_REFINER_MIN_RATIO)):
                return seed_prompt
            if "## " not in refined:
                return seed_prompt
            # URL guard: the resource pipeline parses URLs from the seed prompt —
            # anything the refiner dropped is re-appended verbatim.
            missing = [u for u in extract_urls(seed_prompt) if u not in refined]
            if missing:
                refined += "\n\n## Resources (verbatim from the original request)\n" + "\n".join(
                    missing
                )
            self._display.info(
                f"Prompt refined into a research brief ({len(seed_prompt)} -> "
                f"{len(refined)} chars, model {model})"
            )
            return refined
        except Exception as e:
            self._logger.log_error(e, thread_id=self.state.thread_id)
            return seed_prompt

    async def _setup_team(self, mode: str, team_roles: list[str] | None) -> None:
        """Resolve team roles, pre-flight models, and create the agent team."""
        # Treat an empty list the same as None — otherwise a caller passing
        # team_roles=[] (e.g. the GUI with no roles selected) yields a team of
        # ZERO agents: every phase races through producing nothing and the run
        # dies at writing with "insufficient content". Always fall back to the
        # profile/default roles when no roles are given.
        if not team_roles:
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

        # Drop any roles this factory can't build (e.g. a stale or display-only
        # role like "peer-reviewer" from the GUI) so one bad role never crashes the
        # whole cycle. Fall back to defaults if nothing valid remains.
        valid_roles = [r for r in team_roles if self._factory.has_role(r)]
        dropped = [r for r in team_roles if not self._factory.has_role(r)]
        if dropped:
            self._logger.log_error(
                ValueError(f"Ignoring unknown team roles: {dropped}"),
                thread_id=self.state.thread_id,
            )
        if not valid_roles:
            from paradigm.domains.science.constants import DEFAULT_TEAM_ROLES, MODE_TEAM_ROLES

            valid_roles = list(MODE_TEAM_ROLES.get(mode, DEFAULT_TEAM_ROLES))
        team_roles = valid_roles

        # Reset handler state for new cycle
        self._literature.reset_cycle()
        self._debate.reset_cycle()
        self._review.reset_cycle()

        # Pre-flight: ping each agent's model and swap any that don't respond to a
        # healthy fallback, so a dead/over-capacity provider can't cripple a role.
        role_overrides: dict[str, Any] | None = None
        if getattr(self._config.orchestrator, "model_preflight", True):
            from paradigm.agents.preflight import preflight_team_models

            preflight = await preflight_team_models(self._config, team_roles, logger=self._logger)
            self._display.model_preflight(preflight.checked, preflight.swaps)
            role_overrides = preflight.overrides or None

        # Create agent team (pass role_overrides only when the pre-flight actually
        # swapped a model, so the common no-swap path matches the plain signature).
        if role_overrides:
            agents = self._factory.create_team(
                team_roles, skill_mode="default", role_overrides=role_overrides
            )
        else:
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

    async def _run_seeding_and_discovery(self, seed_prompt: str, mode: str) -> None:
        """SEEDING: create the thread, tag topics, seed the literature + knowledge."""
        # Phase 1: SEEDING
        self._display.phase_transition(ResearchPhase.SEEDING)
        self.state.thread_id = await self._run_seeding_phase(seed_prompt, mode)

        # Initialize phase manager (starts at SEEDING, transition to IDEATION)
        self.state.phase_manager = PhaseManager(ResearchPhase.SEEDING)

        # Topic tags: the theorist's first read of the problem. An early badge so
        # the cycle shows a field while it runs (refined from the paper at the end).
        await self._assign_topics(seed_prompt, stage="initial", paper_id=None)

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

    async def _intervention_gate(self, from_label: str, to_label: str) -> bool:
        """Check the human-intervention hook at a phase boundary.

        Returns True when the cycle must stop here (user aborted or paused);
        thread status + display are already updated for that outcome.
        """
        intervention = await self._check_intervention(from_label, to_label)
        if intervention == "abort":
            self._db.update_thread(self.state.thread_id, status="aborted")
            self._display.phase_aborted()
            return True
        if intervention == "pause":
            self._db.update_thread(self.state.thread_id, status="paused")
            self._display.phase_paused()
            return True
        return False

    def _announce_discussion_phase(self, label: str, phase: ResearchPhase, max_rounds: int) -> None:
        """Display a discussion-phase transition with its active/total agent counts."""
        agent_count = len(self.state.agents)
        active = self._get_phase_active_roles(phase)
        active_count = (
            sum(1 for a in self.state.agents.values() if a.skill_profile in active)
            if active
            else agent_count
        )
        self._display.phase_transition(
            label,
            max_rounds=max_rounds,
            active_agents=active_count,
            total_agents=agent_count,
        )

    async def _run_ideation_stage(self, seed_prompt: str) -> bool:
        """IDEATION: discussion rounds + tournament/synthesis + novelty check.

        Returns True when the cycle must stop (problem-selection gate).
        """
        max_rounds = self._config.orchestrator.max_rounds_per_phase
        checkpoint_interval = self._config.orchestrator.checkpoint_interval

        # 1E: problem-selection human gate (default-off).
        if self._handle_gate_decision(
            await self._human_gate("problem_selection", payload=f"Problem: {seed_prompt[:200]}")
        ):
            return True

        self.state.phase_manager.transition_to(ResearchPhase.IDEATION)
        self._log_phase_transition(
            ResearchPhase.SEEDING, ResearchPhase.IDEATION, rounds_planned=max_rounds
        )
        self._announce_discussion_phase("IDEATION", ResearchPhase.IDEATION, max_rounds)
        await self._run_phase(
            ResearchPhase.IDEATION,
            max_rounds=max_rounds,
            checkpoint_interval=checkpoint_interval,
        )
        # Hypothesis tournament (optional, runs before synthesis)
        if self._config.knowledge.enable_hypothesis_tournament:
            winners = await self._tournament.run_tournament()
            if winners:
                # Interactive mode: the human confirms/edits the winner set.
                selected = await self._decide_hypothesis_selection(winners)
                if selected is None:
                    return True
                winners = selected
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
        return False

    async def _run_planning_stage(self) -> bool:
        """PLANNING: discussion rounds + synthesis + action-item extraction.

        Returns True when the cycle must stop (intervention abort/pause).
        """
        if await self._intervention_gate("ideation", "planning"):
            return True

        max_rounds = self._config.orchestrator.max_rounds_per_phase
        self.state.phase_manager.transition_to(ResearchPhase.PLANNING)
        self._log_phase_transition(
            ResearchPhase.IDEATION, ResearchPhase.PLANNING, rounds_planned=max_rounds
        )
        self.state.messages = []  # Reset messages for new phase
        self._announce_discussion_phase("PLANNING", ResearchPhase.PLANNING, max_rounds)
        await self._run_phase(
            ResearchPhase.PLANNING,
            max_rounds=max_rounds,
            checkpoint_interval=self._config.orchestrator.checkpoint_interval,
        )
        await self._run_synthesis_round(ResearchPhase.PLANNING)

        # Extract action items from PLANNING for EXECUTION (Fix 5)
        self.state.planning_action_items = self._extract_planning_actions()
        return False

    async def _run_execution_stage(self) -> bool:
        """PRE_REGISTRATION (optional) + EXECUTION + VERIFICATION (optional).

        Returns True when the cycle must stop (intervention, prereg failure/gate,
        no usable experiment output, or verification failure/gate).
        """
        # Interactive mode gets the STRUCTURED plan-approval decision (which
        # subsumes the plain continue/pause/abort gate); otherwise the classic
        # phase-transition intervention gate.
        if self._decision_hook is not None:
            if await self._decide_experiment_plan():
                return True
        elif await self._intervention_gate("planning", "execution"):
            return True

        # Phase 3.4: PRE_REGISTRATION (1A, optional) — freeze falsifiable
        # predictions before execution so results can't be reinterpreted later.
        if self._config.knowledge.enable_preregistration:
            self.state.phase_manager.transition_to(ResearchPhase.PRE_REGISTRATION)
            self._log_phase_transition(ResearchPhase.PLANNING, ResearchPhase.PRE_REGISTRATION)
            self._display.phase_transition("PRE_REGISTRATION")
            frozen_rules = await self._prereg.run_freeze()
            if not frozen_rules and self._config.knowledge.prereg_on_empty == "blocking":
                self._db.update_thread(self.state.thread_id, status="prereg_failed")
                self._display.phase_aborted()
                self._print_token_summary()
                return True
            # 1E: pre-registration human gate (default-off).
            gate_payload = f"{len(frozen_rules)} prediction(s) frozen before execution"
            if self._handle_gate_decision(
                await self._human_gate("pre_registration", payload=gate_payload)
            ):
                return True
            self.state.phase_manager.transition_to(ResearchPhase.EXECUTION)
            self._log_phase_transition(ResearchPhase.PRE_REGISTRATION, ResearchPhase.EXECUTION)
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
            # C2 step 4: a confirmed/refuted prediction revises its hypothesis's
            # status in the canonical world model (no-op unless unified_hypotheses).
            self._world_model.revise_from_prereg_verdicts(verdicts)
            for v in verdicts:
                self._display.info(f"Pre-registration verdict [{v['verdict']}]: {v['detail']}")

        # Go/no-go gate: if experiments were attempted but none produced usable
        # output, a data-driven paper is impossible. Stop before WRITING rather
        # than burning ~1M tokens on a paper the internal editor will reject for
        # "reporting failed experiments as results". (successful_code excludes
        # vacuous runs, which are reclassified to FAILURE upstream.)
        if self._config.orchestrator.abort_on_execution_failure and not exp_result.successful_code:
            self._db.update_thread(self.state.thread_id, status="execution_failed")
            # Surface a terminal outcome to the live UI (settle the phase bar +
            # render the terminal screen now), consistent with the reject paths.
            self._display.phase_transition(ResearchPhase.REJECTED)
            self._display.execution_failed_abort(exp_result.caveats)
            self._print_token_summary()
            return True

        # Phase 3.6: VERIFICATION (1B, optional) — re-execute results in a fresh
        # sandbox; demote anything that does not reproduce so WRITING can't use it.
        if self._config.orchestrator.enable_verification and self.state.successful_code:
            self.state.phase_manager.transition_to(ResearchPhase.VERIFICATION)
            self._log_phase_transition(ResearchPhase.EXECUTION, ResearchPhase.VERIFICATION)
            self._display.phase_transition("VERIFICATION")
            records = await self._verification.verify_experiments()
            demoted = VerificationKernel.apply_gate(self, records)
            if demoted:
                self._display.info(f"Verification demoted {demoted} unreproduced experiment(s).")
            if (
                self._config.orchestrator.abort_on_verification_failure
                and not self.state.successful_code
            ):
                self._db.update_thread(self.state.thread_id, status="verification_failed")
                self._display.phase_transition(ResearchPhase.REJECTED)
                self._display.execution_failed_abort(
                    ["No experiments reproduced under verification."]
                )
                self._print_token_summary()
                return True
            # 1E: final-verification human gate (default-off).
            accepted = sum(1 for r in records if r.status == "accepted")
            if self._handle_gate_decision(
                await self._human_gate(
                    "final_verification",
                    payload=f"{accepted}/{len(records)} experiment(s) reproduced",
                )
            ):
                return True
        return False

    async def _run_post_execution_stage(self, should_experiment: bool) -> bool:
        """POST_EXECUTION discussion (optional, after experimentation).

        Returns True when the discussion actually ran (WRITING uses this for its
        from-phase label) — NOT a terminal signal.
        """
        if not (
            should_experiment
            and self.state.execution_context
            and self._config.orchestrator.enable_post_execution_discussion
        ):
            return False

        max_rounds = self._config.orchestrator.max_rounds_per_phase
        self.state.phase_manager.transition_to(ResearchPhase.POST_EXECUTION)
        self._log_phase_transition(
            ResearchPhase.EXECUTION,
            ResearchPhase.POST_EXECUTION,
            rounds_planned=min(2, max_rounds),
        )
        self.state.messages = []
        # Shorter discussion: cap at 2 rounds
        post_exec_rounds = min(2, max_rounds)
        self._announce_discussion_phase(
            "POST_EXECUTION", ResearchPhase.POST_EXECUTION, post_exec_rounds
        )
        await self._run_phase(
            ResearchPhase.POST_EXECUTION,
            max_rounds=post_exec_rounds,
            checkpoint_interval=self._config.orchestrator.checkpoint_interval,
        )
        await self._run_synthesis_round(ResearchPhase.POST_EXECUTION)
        if self.state.world_model is not None:
            self._emit_knowledge_update()
        # Capture POST_EXECUTION discussion summary for WRITING
        self.state.post_execution_summary = self._build_post_execution_summary()
        return True

    async def _run_writing_stage(
        self, should_experiment: bool, ran_post_execution: bool
    ) -> PaperDraft | None:
        """WRITING: draft + assemble the paper.

        Returns the PaperDraft, or None when the cycle must stop here
        (intervention abort/pause, or writing produced no usable paper).
        """
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
        if await self._intervention_gate(from_label, "writing"):
            return None

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
            return None

        # 1E: record provenance once a paper exists (only when gates/verification/
        # pre-registration were in play, so default runs are unchanged).
        if (
            self._config.orchestrator.human_gate_mode != "off"
            or self.state.verification_records
            or self.state.registered_rules
        ):
            self._record_provenance()
        return paper_draft

    async def _run_reflection_loop(
        self, paper_draft: PaperDraft, should_experiment: bool
    ) -> PaperDraft:
        """R1: PI reflection on the fresh draft, with budgeted loop-backs.

        The PI (strongest model, config role ``pi``) may send the team back to
        EXECUTION (more experiments) or PLANNING (rethink, then experiments),
        after which the paper is revised IN PLACE (the revision path — same
        paper row, citation net intact) and re-reflected. Convergence is
        mechanical: max_loop_backs, no-repeat-target, and call_it.
        Never stops the cycle; always returns a draft for review.
        """
        cfg = self._config.orchestrator
        if not cfg.enable_reflection or not should_experiment:
            return paper_draft

        while True:
            current_body = paper_draft.assembled_body or paper_draft.to_markdown()
            verdict = await self._reflection.run_reflection(current_body)
            self.emit_event(
                "reflection.verdict",
                {
                    "verdict": verdict.get("verdict"),
                    "target": verdict.get("target"),
                    "reason": str(verdict.get("reason") or "")[:400],
                    "loop_backs_used": self.state.loop_backs_used,
                },
            )
            kind = verdict.get("verdict")
            if kind == "proceed":
                self._display.info(
                    f"[PI reflection] proceed to review — {verdict.get('reason', '')}"
                )
                return paper_draft
            if kind == "call_it":
                self.state.called_by_pi = True
                self.state.pi_call_reason = str(verdict.get("reason") or "")[:400]
                self._display.info(f"[PI reflection] calling it — {self.state.pi_call_reason}")
                # The paper still faces review honestly; record the call in caveats
                # so the editor/reviewers see the declared scope.
                self.state.execution_caveats.append(
                    "The PI declared the investigation complete at its current scope "
                    f"(no further experiments): {self.state.pi_call_reason}"
                )
                return paper_draft

            # loop_back (already budget/target-validated by the handler)
            target = verdict.get("target", "execution")
            directives = verdict.get("directives", [])
            self.state.loop_backs_used += 1
            self.state.reflection_log.append(verdict)
            self._display.info(
                f"[PI reflection] loop back to {target} "
                f"({self.state.loop_backs_used}/{cfg.max_loop_backs}): " + "; ".join(directives)
            )
            self.emit_event(
                "reflection.loop_back",
                {"target": target, "directives": directives[:5]},
            )
            directive_block = "\n".join(f"PI DIRECTIVE (must be honored): {d}" for d in directives)
            plan = self.state.planning_action_items.strip()
            self.state.planning_action_items = f"{plan}\n\n{directive_block}".strip()

            if target == "planning":
                self.state.phase_manager.transition_to(ResearchPhase.PLANNING)
                self._log_phase_transition(ResearchPhase.WRITING, ResearchPhase.PLANNING)
                self.state.messages = []
                self._pending_guidance.append((f"PI reflection: {'; '.join(directives)}", 0))
                self._announce_discussion_phase("PLANNING", ResearchPhase.PLANNING, 1)
                await self._run_phase(
                    ResearchPhase.PLANNING,
                    max_rounds=1,
                    checkpoint_interval=cfg.checkpoint_interval,
                )
                await self._run_synthesis_round(ResearchPhase.PLANNING)
                # Fresh action items from the re-plan, PI directives re-appended.
                replanned = self._extract_planning_actions()
                self.state.planning_action_items = f"{replanned}\n\n{directive_block}".strip()
                self.state.phase_manager.transition_to(ResearchPhase.EXECUTION)
                self._log_phase_transition(ResearchPhase.PLANNING, ResearchPhase.EXECUTION)
            else:
                self.state.phase_manager.transition_to(ResearchPhase.EXECUTION)
                self._log_phase_transition(ResearchPhase.WRITING, ResearchPhase.EXECUTION)
            self.state.messages = []
            self._display.phase_transition("EXECUTION")
            exp = await self._experimentation.run_experimentation_phase(max_rounds_override=2)
            self._merge_execution_results(exp)

            # Revise the paper IN PLACE with the new evidence (same paper row).
            self.state.phase_manager.transition_to(ResearchPhase.WRITING)
            self._log_phase_transition(ResearchPhase.EXECUTION, ResearchPhase.WRITING)
            self._display.phase_transition("WRITING")
            pseudo_review = (
                "## PI Reflection — revision after additional work\n"
                f"{directive_block}\n"
                "New experiments were run to address the directives above; their "
                "results are in the Execution Fact Sheet. Integrate them into the "
                "paper (methods, results, discussion, abstract) and update any "
                "affected numbers. Success criteria for this revision: "
                f"{verdict.get('success_criteria', '(none stated)')}\n"
                "## Blocking Changes\n- Address the PI directives with the new results\n"
                "## Minor Changes\n- None"
            )
            revised = await self._review.run_revision(current_body, pseudo_review)
            if len(revised) >= _MIN_PAPER_LENGTH:
                paper_draft.assembled_body = revised
                thread = self._db.get_thread(self.state.thread_id)
                if thread and thread.get("current_draft_id"):
                    paper_id = thread["current_draft_id"]
                    self._db.update_paper(paper_id, body=revised, status="revised")
                    await asyncio.to_thread(self._writing.save_paper_file, paper_id, revised)

    async def _run_deep_revision_loop(self, reviews: list[Any]) -> str:
        """R2: PI triage of peer reviews; run new analyses when rewording won't do.

        Returns extra revision feedback describing the new work ("" when the
        triage decides a text-only revision suffices or the budget is spent).
        Runs WITHOUT phase transitions (the peer-review loop owns the phase);
        experiments execute exactly as in a reflection loop-back.
        """
        cfg = self._config.orchestrator
        if self.state.loop_backs_used >= cfg.max_loop_backs:
            return ""
        review_text = "\n\n".join(str(getattr(r, "text", None) or r) for r in reviews)[:16_000]
        triage = await self._reflection.triage_peer_reviews(review_text)
        self.emit_event(
            "reflection.peer_triage",
            {
                "deep_loop": bool(triage.get("deep_loop")),
                "reason": str(triage.get("reason") or "")[:400],
            },
        )
        if not triage.get("deep_loop"):
            return ""

        directives = triage.get("directives", [])
        self.state.loop_backs_used += 1
        self.state.reflection_log.append({"target": "peer_deep_revision", "directives": directives})
        self._display.info(
            "[PI triage] reviewers demand new analysis — running a deep revision: "
            + "; ".join(directives)
        )
        directive_block = "\n".join(f"PI DIRECTIVE (must be honored): {d}" for d in directives)
        plan = self.state.planning_action_items.strip()
        self.state.planning_action_items = f"{plan}\n\n{directive_block}".strip()
        exp = await self._experimentation.run_experimentation_phase(max_rounds_override=2)
        self._merge_execution_results(exp)
        return (
            "### PI Deep-Revision Addendum\n"
            "The team ran ADDITIONAL experiments to answer the reviews above:\n"
            f"{directive_block}\n"
            "Their results are now part of the experiment record — integrate them "
            "into the revision (methods, results, discussion) and answer the "
            "reviewers with the new evidence, not just rewording."
        )

    def _merge_execution_results(self, exp: Any) -> None:
        """Fold a loop-back experimentation pass into the cycle's evidence state."""
        if exp.execution_context:
            joiner = "\n\n" if self.state.execution_context else ""
            self.state.execution_context += joiner + exp.execution_context
        self.state.execution_caveats.extend(exp.caveats)
        self.state.execution_figures.extend(exp.execution_figures)
        self.state.successful_code.extend(exp.successful_code)
        self.state.experiment_metadata.extend(exp.experiment_metadata)

    async def _run_internal_review_stage(self, paper_draft: PaperDraft) -> bool:
        """INTERNAL_REVIEW: editor review + revision loop.

        Returns True when the cycle must stop here (editor rejected the paper or
        revisions never converged) — the terminal outcome is fully surfaced.
        """
        self.state.phase_manager.transition_to(ResearchPhase.INTERNAL_REVIEW)
        self._log_phase_transition(ResearchPhase.WRITING, ResearchPhase.INTERNAL_REVIEW)
        self.state.messages = []
        # Pass the enum (value "internal"), NOT the string "INTERNAL_REVIEW":
        # the display lowercases its arg, and "internal_review" != the canonical
        # phase value "internal" the UI keys on, so the "Review" pip never lit.
        self._display.phase_transition(ResearchPhase.INTERNAL_REVIEW)
        await self._review.run_review_phase(paper_draft)

        # Check if internal review ended without acceptance (editor rejected the
        # paper, or revisions never converged within the iteration budget).
        thread = self._db.get_thread(self.state.thread_id)
        review_status = thread.get("status") if thread else None
        if review_status in ("review_rejected", "revision_exhausted"):
            self.emit_event("review.final", {"outcome": review_status, "stage": "internal"})
            self._display.writing_failed_review_exhausted(review_status)
            # Surface a terminal REJECTED outcome to the live UI (the tracker +
            # terminal screen key off the broadcast phase + a paper_rejected
            # notice). Without this the run looks stuck on "internal review"
            # instead of ending with "Paper was not accepted" + the draft.
            self._display.phase_transition(ResearchPhase.REJECTED)
            self._display.paper_rejected()
            paper_id = thread.get("current_draft_id") if thread else None
            if paper_id:
                await self._assign_final_topics(paper_id)
                self._save_auxiliary_files(paper_id)
                await self._writing.finalize_digest(paper_id)
            self._print_token_summary()
            return True
        return False

    async def _run_peer_review_stage(self, paper_draft: PaperDraft) -> bool:
        """SUBMITTED + PEER_REVIEW pipeline: desk review, reviews, revisions, decision.

        Returns True when the cycle must stop here (intervention abort/pause);
        publish/reject outcomes fall through to the common finalization tail.
        """
        # Intervention check before SUBMITTED
        if await self._intervention_gate("internal", "submitted"):
            return True

        accepted = await self._review.run_submission_phase(paper_draft)
        if accepted:
            decision, reviews = await self._review.run_peer_review_phase(paper_draft)
            revision_count = 0
            max_revisions = self._config.orchestrator.max_revision_rounds
            while (
                decision in ("minor_revision", "major_revision") and revision_count < max_revisions
            ):
                # R2: on a major revision the PI triages the reviews — demands
                # that need NEW ANALYSIS (not rewording) trigger one deep
                # revision loop: extra experiments before the writer responds.
                extra_feedback = ""
                if decision == "major_revision" and self._config.orchestrator.enable_reflection:
                    extra_feedback = await self._run_deep_revision_loop(reviews)
                paper_draft = await self._review.run_revision_phase(
                    paper_draft, reviews, extra_feedback=extra_feedback
                )
                decision, reviews = await self._review.run_peer_review_phase(paper_draft)
                revision_count += 1

            thread = self._db.get_thread(self.state.thread_id)
            paper_id = thread["current_draft_id"] if thread else None
            if paper_id and decision in ("accept", "minor_revision"):
                # Advance the live UI to the terminal phase BEFORE the
                # (potentially slow) publish work, so the phase bar reaches
                # "Published" and the terminal screen renders promptly even
                # if corpus ingestion lags. Without this the run looked
                # stuck on "Peer Review" after the decision was made.
                self._display.phase_transition(ResearchPhase.PUBLISHED)
                self.emit_event("review.final", {"outcome": "accepted", "stage": "peer"})
                await publish_paper(paper_id, self._db, self._corpus, self._logger, reviews)
                self._db.update_thread(self.state.thread_id, status="published")
                self._display.paper_published()
            elif paper_id:
                from paradigm.journal.publication import reject_paper

                self._display.phase_transition(ResearchPhase.REJECTED)
                self.emit_event("review.final", {"outcome": "rejected", "stage": "peer"})
                reject_paper(paper_id, self._db, reviews, self._logger)
                self._db.update_thread(self.state.thread_id, status="rejected")
                self._display.paper_rejected()
        else:
            # Desk rejected
            self.emit_event("review.final", {"outcome": "desk_rejected", "stage": "submission"})
            self._db.update_thread(self.state.thread_id, status="rejected")
            self._display.paper_rejected()
        return False

    async def _finalize_cycle(self) -> None:
        """Common cycle tail: auxiliary artifacts, digest, token summary, memories."""
        # Save auxiliary files (search log, review report)
        thread = self._db.get_thread(self.state.thread_id)
        paper_id = thread.get("current_draft_id") if thread else None
        if paper_id:
            # Re-tag from the finished paper (drift + cross-pollination).
            await self._assign_final_topics(paper_id)
            self._save_auxiliary_files(paper_id)
            # Digest from the FINAL paper body — after all review/revision.
            await self._writing.finalize_digest(paper_id)

        # Display token usage summary
        self._print_token_summary()

        # Generate agent episodic memories via reflection
        await self._memory.run_memory_generation()

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

        # Prompt-preprocessing provenance: persist the user's ORIGINAL prompt.
        if self.state.original_prompt:
            self._db.update_thread(thread_id, original_prompt=self.state.original_prompt)

        # Open the per-thread dashboard event stream now that the thread exists
        self._open_event_stream(thread_id)
        self.emit_event(
            "run.started",
            {
                "thread_id": thread_id,
                "prompt": seed_prompt[:500],
                "config": {
                    "rounds": self._config.orchestrator.max_rounds_per_phase,
                    "mode": mode,
                    "agents": participants,
                    "sandbox_enabled": self._config.sandbox.enabled,
                    "sandbox_network_mode": self._config.sandbox.network_mode,
                },
            },
        )
        # Surface the refined brief AFTER the stream opens (an emit before
        # _open_event_stream is silently dropped — caught live in testing).
        if self.state.original_prompt:
            self.emit_event(
                "prompt.refined",
                {
                    "original_chars": len(self.state.original_prompt),
                    "refined_chars": len(seed_prompt),
                    "refined_prompt": seed_prompt[:4000],
                },
            )

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
                        self.emit_event(
                            "resource.ingested",
                            {"url": url, "kind": "paper", "title": paper.title, "saved_pdf": True},
                        )
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
                    self.emit_event(
                        "resource.ingested",
                        {
                            "url": url,
                            "kind": rtype.value,
                            "title": resource.name,
                            "saved_pdf": False,
                        },
                    )
                resolved.append(resource)

        # Stage locally-attached datasets (CLI --data / GUI upload) into the
        # sandbox-visible shared data dir; they join the resolved resources so
        # data_context carries their data cards like any URL-derived dataset.
        for ds_path in self.state.attached_datasets:
            try:
                staged = stage_local_dataset(Path(ds_path), shared_dir)
            except Exception as e:
                self._logger.log_error(e, thread_id=thread_id)
                self._display.resource_error(f"dataset attach failed for {ds_path}: {e}")
                continue
            for resource in staged:
                self._display.resource_resolved(resource.name, "data")
                self.emit_event(
                    "dataset.attached",
                    {
                        "path": str(ds_path),
                        "name": resource.name,
                        "sandbox_path": resource.sandbox_path,
                        "size_bytes": resource.size_bytes,
                    },
                )
            resolved.extend(staged)

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

        # Guidance carried over from a previous phase: treat as drained in
        # "round 0" so it's visible through this phase's first round, then pruned.
        self._pending_guidance = [(g, 0) for g, _ in self._pending_guidance]

        for round_num in range(1, max_rounds + 1):
            # Real pause: block here while the session is paused (GUI-driven). Before
            # blocking, persist a checkpoint so a paused cycle can be resumed LATER —
            # even after a backend restart — from this round, not a stale phase end.
            if self._pause_gate is not None:
                if self._is_paused is not None and self._is_paused():
                    await self._save_checkpoint(phase, round_num, label="pause")
                await self._await_pause_gate(phase, round_num)
            # Pull in any human guidance typed since the last round and inject it
            # into this round's agent prompts (round-boundary steering).
            await self._drain_guidance(phase, round_num)
            self._display.round_start(round_num, max_rounds)
            await self._run_round(phase, round_num, scheduler)
            self.emit_event("round.completed", {"round": round_num})
            # Guidance is embedded in agent responses / thread history after one
            # full round of visibility — prune what's been seen by everyone.
            # (Entries drained DURING round N stay through round N+1.)
            self._pending_guidance = [(g, r) for g, r in self._pending_guidance if r >= round_num]
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
            if round_num % checkpoint_interval == 0:
                await self._save_checkpoint(phase, round_num, label=f"round {round_num}")

        # Final checkpoint at end of phase
        await self._save_checkpoint(phase, max_rounds, label="end of phase")

    async def _save_checkpoint(self, phase: ResearchPhase, round_num: int, *, label: str) -> None:
        """Compress the thread into a checkpoint + persist it (best-effort).

        Used at round intervals, phase ends, and at the pause point. Never breaks a
        run — a failed checkpoint is logged and the cycle continues.
        """
        if not (self.state.messages and self._config.orchestrator.enable_checkpointing):
            return
        try:
            self.state.checkpoint = await self._checkpoint_mgr.create_checkpoint(
                thread_id=self.state.thread_id,
                phase=str(phase),
                round_number=round_num,
                messages=self.state.messages,
                previous_checkpoint=self.state.checkpoint,
            )
            self._display.checkpoint_saved(label)
            self.emit_event("checkpoint.saved", {"phase": str(phase), "label": label})
        except Exception as e:
            self._logger.log_error(e, thread_id=self.state.thread_id)
            self._display.checkpoint_error(e)

    async def _drain_guidance(self, phase: ResearchPhase, round_num: int) -> None:
        """Pull human guidance from the GUI and stage it for this round's prompts.

        No-op when no ``guidance_provider`` was supplied (the CLI). The provider
        returns any messages typed since the last drain; we stage them in
        ``_pending_guidance`` (read by :meth:`_build_agent_prompt`), narrate them,
        and log a ``USER_GUIDANCE`` event so the activity timeline shows them.
        """
        if self._guidance_provider is None:
            return
        try:
            messages = await self._guidance_provider()
        except Exception as e:  # never let a steering hiccup break the cycle
            self._logger.log_error(e, thread_id=self.state.thread_id)
            return
        for msg in messages or []:
            text = (msg or "").strip()
            if not text:
                continue
            self._pending_guidance.append((text, round_num))
            # Structured delivery receipt — the GUI flips the operator's queued
            # bubble to "delivered" off this signal.
            self._display.guidance_delivered(text, str(phase), round_num)
            self._logger.log(
                EventType.USER_GUIDANCE,
                content={"guidance": text, "phase": str(phase), "round": round_num},
                thread_id=self.state.thread_id,
                phase=str(phase),
            )

    async def _await_pause_gate(self, phase: ResearchPhase | str, round_num: int) -> None:
        """Block while paused, with explicit parked/resumed signals for the GUI.

        Without the signals, a pause click looks dead: the status flips to
        "paused" instantly but agents keep streaming until the engine actually
        parks here — the GUI needs to know when that happens.
        """
        if self._pause_gate is None:
            return
        if self._is_paused is not None and self._is_paused():
            self._display.run_parked(str(phase), round_num)
            await self._pause_gate()
            self._display.run_resumed(str(phase), round_num)
        else:
            await self._pause_gate()

    async def _interaction_checkpoint(self, phase: ResearchPhase, round_num: int) -> None:
        """Turn-level responsiveness: park if paused, then drain fresh steering.

        Called before EVERY agent turn, so a pause click or a typed message
        takes effect within one turn (~a minute) instead of one full round
        (potentially 10+). Guidance drained mid-round reaches the remaining
        speakers immediately and stays visible through the next full round.
        """
        await self._await_pause_gate(phase, round_num)
        await self._drain_guidance(phase, round_num)

    async def _execution_checkpoint(self) -> None:
        """Between-experiment responsiveness for the EXECUTION phase.

        EXECUTION runs no discussion rounds, so round-boundary steering never
        landed here — a black hole. Park on pause between experiment rounds and
        turn any steering typed during execution into OPERATOR DIRECTIVE lines
        on ``planning_action_items``, which every experiment prompt re-reads.
        """
        await self._await_pause_gate("execution", 0)
        before = len(self._pending_guidance)
        await self._drain_guidance(ResearchPhase.EXECUTION, 0)
        fresh = [g for g, _ in self._pending_guidance[before:]]
        if fresh:
            directives = "\n".join(f"OPERATOR DIRECTIVE (must be honored): {g}" for g in fresh)
            plan = self.state.planning_action_items.strip()
            self.state.planning_action_items = f"{plan}\n\n{directives}".strip()
            del self._pending_guidance[before:]

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

        if self._events is not None:
            self._events.set_context(round_num=round_num)
        self.emit_event("round.started", {"round": round_num, "active_agents": speaker_order})

        for agent_id in speaker_order:
            # Turn-level pause + steering pickup (see _interaction_checkpoint).
            await self._interaction_checkpoint(phase, round_num)
            agent = self.state.agents[agent_id]
            prompt = self._build_agent_prompt(agent, phase, round_num)

            try:
                response = await agent.generate(prompt)
                # Thin-output retry: some providers intermittently return a
                # near-empty turn from a huge prompt (observed live: 6/12
                # synthesizer turns of 17-57 chars) — one retry usually recovers
                # it. A thin turn that carries action tags ([SEARCH: …], [READ: …],
                # [HYPOTHESIS: …]) is an INTENTIONAL action-only turn, not a dead
                # one — never discard those. The discarded attempt's usage is
                # accounted here; the adopted response through the normal path.
                if not self._is_substantive_contribution(response.content) and not re.search(
                    r"\[[A-Z_]{3,}:", response.content
                ):
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
                    self.emit_event(
                        "warning.emitted",
                        {
                            "kind": "thin_contribution_retry",
                            "message": (
                                f"{agent_id}: {len(response.content)} chars — retrying the turn"
                            ),
                        },
                        agent=agent_id,
                    )
                    response = await agent.generate(prompt)
            except Exception as e:
                self._logger.log_error(e, agent_id=agent_id, thread_id=self.state.thread_id)
                self._display.agent_error(agent_id, e)
                self.emit_event(
                    "warning.emitted",
                    {"kind": "api_error", "message": f"{agent_id}: {e}"[:300]},
                    agent=agent_id,
                )
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

            # Visibility: a thin turn from a big prompt is a (tolerated) provider
            # failure mode — 6 such Gemini turns silently ate 212k input tokens in
            # one run. Surface it so runs can be triaged without event archaeology.
            if not self._is_substantive_contribution(response.content):
                self.emit_event(
                    "warning.emitted",
                    {
                        "kind": "thin_contribution",
                        "message": (
                            f"{agent_id}: {len(response.content)} chars from a "
                            f"{response.usage.input_tokens}-token prompt"
                        ),
                    },
                    agent=agent_id,
                )

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

            # Literature actions are BEST-EFFORT and must never abort the cycle: a
            # flaky provider, a malformed paper URL (e.g. httpx "Invalid IPv6 URL"
            # from a bracketed id), or a CHAIN/FOLLOW/READ hiccup should degrade, not
            # crash. (corpus.search/fetch guard themselves, but the FOLLOW/CHAIN/DATA
            # entry points can still surface an uncaught error here.)
            try:
                # [SEARCH: ...]
                await self._literature.process_search_requests(agent_id, response.content, phase)
                # [FOLLOW:], [CITED_BY:], [READ:], [CHAIN:]
                await self._literature.process_literature_actions(agent_id, response.content, phase)
                # [DATA: url] — pre-stage datasets for the sandbox
                await self._literature.process_data_requests(agent_id, response.content, phase)
                # [DATASEARCH: query] / [FETCHDATA: id] — repository data acquisition
                await self._literature.process_dataset_actions(agent_id, response.content, phase)
            except asyncio.CancelledError:
                raise  # a genuine cycle cancellation must propagate
            except BaseException as e:  # noqa: BLE001 — literature must never be fatal
                self._logger.log_error(
                    e, agent_id=agent_id, thread_id=self.state.thread_id, metadata_key="literature"
                )

            # Process any [CHAIN: id depth=N direction=...] multi-hop graph walks
            await self._literature.process_chain_requests(agent_id, response.content, phase)

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

        # Human guidance typed into the GUI this round goes at the very top — it's
        # a direct instruction from the operator and should outrank prior context.
        if self._pending_guidance:
            guidance_block = (
                "## HUMAN GUIDANCE (from the operator — follow this now)\n"
                + "\n".join(f"- {g}" for g, _ in self._pending_guidance)
                + "\n\n"
            )
            checkpoint_context = guidance_block + checkpoint_context

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

    async def _check_decision(self, decision_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Ask the human for a structured decision (interactive mode).

        Like :meth:`_check_intervention`, the hook may BLOCK on a GUI response,
        so it runs off the event loop. Returns at least ``{"decision":
        continue|pause|abort}``; ``"modifications"``/``"notes"`` carry the
        structured choice. No hook (autonomous run) → continue.
        """
        if self._decision_hook is None:
            return {"decision": "continue"}
        try:
            result = await asyncio.to_thread(
                self._decision_hook, self.state.thread_id, decision_type, payload
            )
        except Exception as e:  # a steering hiccup must never kill the cycle
            self._logger.log_error(e, thread_id=self.state.thread_id)
            return {"decision": "continue"}
        if not isinstance(result, dict) or result.get("decision") not in (
            "continue",
            "pause",
            "abort",
        ):
            return {"decision": "continue"}
        return result

    def _apply_decision_action(self, decision: dict[str, Any]) -> bool:
        """Apply the pause/abort action of a structured decision.

        Returns True when the cycle must stop here (mirrors
        :meth:`_intervention_gate`'s handling of the plain hook).
        """
        action = decision.get("decision", "continue")
        if action == "abort":
            self._db.update_thread(self.state.thread_id, status="aborted")
            self._display.phase_aborted()
            return True
        if action == "pause":
            self._db.update_thread(self.state.thread_id, status="paused")
            self._display.phase_paused()
            return True
        return False

    async def _decide_hypothesis_selection(self, winners: list[Any]) -> list[Any] | None:
        """Interactive mode: let the human pick which hypotheses to carry forward.

        The tournament's full ranked field is offered with the winners
        preselected; the user may keep, narrow, or broaden the set. Free-text
        notes are staged as guidance for the next discussion round. Returns the
        selection, or None when the user paused/aborted the cycle. Autonomous
        runs (no decision hook) keep the tournament winners untouched.
        """
        if self._decision_hook is None:
            return winners
        ranked = self._tournament.ranked_hypotheses() or list(winners)
        payload: dict[str, Any] = {
            "title": "Choose the hypotheses to investigate",
            "description": (
                "The tournament ranked the team's hypotheses by Elo. The winners "
                "are preselected — keep them, or change the set to carry forward."
            ),
            "from_phase": "ideation",
            "to_phase": "planning",
            "multi_select": True,
            "default_ids": [h.id for h in winners],
            "choices": [
                {
                    "id": h.id,
                    "label": h.statement,
                    "detail": (h.rationale or "")[:280],
                    "score": round(h.elo_rating),
                }
                for h in ranked
            ],
        }
        decision = await self._check_decision("hypothesis_selection", payload)
        if self._apply_decision_action(decision):
            return None
        modifications = decision.get("modifications") or {}
        selected_ids = modifications.get("selected_ids") if isinstance(modifications, dict) else []
        by_id = {h.id: h for h in ranked}
        chosen = [by_id[i] for i in selected_ids or [] if i in by_id]
        if chosen:
            winners = chosen
            self._display.info(
                f"[your decision] {len(chosen)} hypothesis(es) selected for investigation"
            )
        notes = str(decision.get("notes") or "").strip()
        if notes:
            self._pending_guidance.append((notes, 0))
        self.emit_event(
            "decision.hypothesis_selection",
            {"selected": [h.id for h in winners], "notes": notes[:500]},
        )
        return winners

    async def _decide_experiment_plan(self) -> bool:
        """Interactive mode: present the experiment plan before execution.

        The human sees the action items extracted from PLANNING and can approve,
        add directives (appended to the plan the experimentalist receives),
        pause, or abort. Returns True when the cycle must stop here.
        """
        plan = self.state.planning_action_items.strip()
        payload: dict[str, Any] = {
            "title": "Approve the experiment plan",
            "description": plan
            or (
                "No explicit action items were extracted from PLANNING — the "
                "experimentalist will design experiments from the discussion."
            ),
            "from_phase": "planning",
            "to_phase": "execution",
            "choices": [],
        }
        decision = await self._check_decision("experiment_plan", payload)
        if self._apply_decision_action(decision):
            return True
        notes = str(decision.get("notes") or "").strip()
        if notes:
            # Appended to the plan itself — round-boundary guidance only reaches
            # discussion phases, which EXECUTION doesn't run.
            prefix = f"{self.state.planning_action_items}\n\n" if plan else ""
            self.state.planning_action_items = (
                f"{prefix}OPERATOR DIRECTIVE (must be honored): {notes}"
            )
            self._display.info(f"[your directive] {notes}")
        self.emit_event("decision.experiment_plan", {"notes": notes[:500]})
        return False

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

        # Parse JSON response — tolerant of markdown fences and prose-wrapped
        # objects (weaker open-weight models often add both).
        cleaned = strip_fences(text)
        result = first_json_object(cleaned)

        if result is None:
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

    def _log_phase_transition(
        self,
        from_phase: ResearchPhase,
        to_phase: ResearchPhase,
        *,
        rounds_planned: int | None = None,
    ) -> None:
        """Log a phase transition event."""
        self._logger.log(
            EventType.PHASE_TRANSITION,
            content={"from": str(from_phase), "to": str(to_phase)},
            thread_id=self.state.thread_id,
            phase=str(to_phase),
        )
        self.emit_event("phase.completed", {"phase": str(from_phase)})
        if self._events is not None:
            self._events.set_context(phase=str(to_phase), round_num=None)
        self.emit_event("phase.started", {"phase": str(to_phase), "rounds_planned": rounds_planned})
        self._db.update_thread(self.state.thread_id, current_phase=str(to_phase))

    async def _classify(self, text: str, *, max_topics: int) -> list[str] | None:
        """Classify ``text`` into broad fields. Tries the theorist's brain ("the agent
        who reads the prompt first") then the config default provider as a reliable
        fallback, bounding each attempt. Returns None only if every attempt fails."""
        from paradigm.agents.topics import classify_topics

        candidates: list[tuple[Any, str]] = []
        theorist = self._find_agent_by_role("theorist")
        if theorist is not None:
            candidates.append((theorist.provider, theorist.model))
        try:  # default provider — a reliable fallback (and the only try if no theorist)
            dp = self._config.get_provider()
            candidates.append((dp, dp.default_model))
        except Exception:
            pass

        for provider, model in candidates:
            try:
                topics = await asyncio.wait_for(
                    classify_topics(text, provider=provider, model=model, max_topics=max_topics),
                    timeout=45.0,
                )
                if topics:
                    return topics
            except Exception as e:  # try the next candidate
                self._logger.log_error(
                    e, thread_id=self.state.thread_id, metadata_key="topics_classify"
                )
        return None

    def _thread_topics(self) -> list[str]:
        """The cycle's currently-stored topics (the initial badge), or []."""
        thread = self._db.get_thread(self.state.thread_id)
        raw = thread.get("topics") if thread else None
        if not raw:
            return []
        try:
            val = json.loads(raw) if isinstance(raw, str) else raw
            return val if isinstance(val, list) else []
        except (ValueError, TypeError):
            return []

    async def _assign_topics(self, text: str, *, stage: str, paper_id: str | None) -> None:
        """Classify ``text`` into broad fields and persist + broadcast the tags.

        Best-effort and bounded: topic tagging must never block, break, or stall a
        cycle. ``stage`` is "initial" (seed prompt) or "final" (finished paper); the
        final pass allows MULTIPLE tags so cross-disciplinary work earns multiple
        badges (cross-pollination). A finished paper ALWAYS ends up with a badge: if
        classification fails it inherits the cycle's initial topics (or "other").
        """
        try:
            max_topics = 3 if stage == "final" else 2
            topics = await self._classify(text, max_topics=max_topics)
            if not topics and stage == "final" and paper_id is not None:
                topics = self._thread_topics() or ["other"]
            if not topics:
                return
            self._db.update_thread(self.state.thread_id, topics=topics)
            if paper_id is not None:
                self._db.update_paper(paper_id, topics=topics)
            self._display.topics_assigned(topics, stage=stage)
        except Exception as e:  # never let tagging break the cycle
            self._logger.log_error(
                e, thread_id=self.state.thread_id, metadata_key=f"topics_{stage}"
            )

    async def _assign_final_topics(self, paper_id: str) -> None:
        """Re-classify the FINISHED paper (drift check + cross-pollination)."""
        paper = self._db.get_paper(paper_id)
        if not paper:
            return
        text = "\n\n".join(
            part
            for part in (
                paper.get("title", ""),
                paper.get("abstract", ""),
                (paper.get("body", "") or "")[:6000],
            )
            if part
        )
        await self._assign_topics(text, stage="final", paper_id=paper_id)

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

    # ------------------------------------------------------------------
    # Artifact persistence + token logging — thin delegates to ArtifactsHandler
    # (orchestrator/artifacts.py). Kept under the original names so the many
    # handler call sites (self._engine._log_agent_response, ...) are unchanged.
    # ------------------------------------------------------------------

    def _log_agent_response(
        self,
        agent_id: str,
        response: Any,
        phase: ResearchPhase,
        message_type: str,
    ) -> None:
        self._artifacts.log_agent_response(agent_id, response, phase, message_type)

    async def _save_pdf_for_sandbox(self, url: str) -> None:
        await self._artifacts.save_pdf_for_sandbox(url)

    def _save_search_log(self, paper_id: str) -> None:
        self._artifacts.save_search_log(paper_id)

    def _save_review_log(self, paper_id: str) -> None:
        self._artifacts.save_review_log(paper_id)

    def _save_transcript(self, paper_id: str) -> None:
        self._artifacts.save_transcript(paper_id)

    def _save_experiment_code(self, paper_id: str) -> None:
        self._artifacts.save_experiment_code(paper_id)

    def _get_token_summary(self) -> dict[str, int]:
        return self._artifacts.get_token_summary()

    def _print_token_summary(self) -> None:
        self._artifacts.print_token_summary()

    def _save_auxiliary_files(self, paper_id: str) -> None:
        self._artifacts.save_auxiliary_files(paper_id)
