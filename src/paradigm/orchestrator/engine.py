"""Main orchestration engine for research cycles."""

import uuid
from typing import Any

import click

from paradigm.agents.base import Agent
from paradigm.agents.factory import AgentFactory
from paradigm.config import Config
from paradigm.journal.paper import (
    SECTION_ASSIGNMENTS,
    PaperDraft,
    PaperSection,
    SectionDraft,
    parse_review_feedback,
    parse_sections_from_markdown,
)
from paradigm.literature.corpus import Corpus
from paradigm.logging.events import EventLogger, EventType
from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.scheduler import Scheduler
from paradigm.storage.checkpoints import Checkpoint, CheckpointManager
from paradigm.storage.database import Database

# Default team composition
DEFAULT_TEAM_ROLES = ["theorist", "analyst", "synthesizer", "skeptic", "writer", "editor"]

# Phase-specific prompt templates
_PHASE_INSTRUCTIONS: dict[ResearchPhase, dict[str, str]] = {
    ResearchPhase.IDEATION: {
        "round_1": (
            "You are participating in a collaborative research ideation session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "This is the opening round. Propose 1-2 concrete, testable hypotheses "
            "related to this topic. Be specific about what you'd predict and why."
        ),
        "later_rounds": (
            "You are participating in a collaborative research ideation session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Recent Discussion\n{recent_messages}\n\n"
            "Respond to your colleagues: critique ideas, build on promising hypotheses, "
            "draw connections between proposals, and help prioritize. "
            "Be constructive but rigorous."
        ),
    },
    ResearchPhase.PLANNING: {
        "round_1": (
            "You are developing a concrete research plan.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "Based on the ideation phase, propose specific:\n"
            "- Experiments or analyses to run\n"
            "- Data requirements and sources\n"
            "- Success criteria and expected outcomes\n"
            "- Potential pitfalls and how to address them"
        ),
        "later_rounds": (
            "You are refining a research plan.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Recent Discussion\n{recent_messages}\n\n"
            "Refine the plan: challenge assumptions, identify dependencies between "
            "experiments, suggest controls, and ensure the plan is feasible. "
            "Focus on making the plan actionable."
        ),
    },
    ResearchPhase.WRITING: {
        "section_drafting": (
            "You are writing sections of a research paper.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "Draft the following sections in markdown, using ## headers for each:\n"
            "{assigned_sections}\n\n"
            "Write clear, precise scientific prose. Every claim should be supported "
            "by evidence from the research. Use active voice where possible."
        ),
        "assembly": (
            "You are assembling a research paper from section drafts.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Section Drafts\n{section_drafts}\n\n"
            "Combine all section drafts into a single coherent paper. "
            "Harmonize writing style, ensure smooth transitions between sections, "
            "add a title, and make sure the paper tells a complete story. "
            "Output the full paper in markdown with ## section headers."
        ),
        "refinement": (
            "You are refining a research paper.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Current Draft\n{current_draft}\n\n"
            "## Recent Discussion\n{recent_messages}\n\n"
            "Provide specific suggestions to improve the paper. "
            "Focus on clarity, accuracy, and completeness."
        ),
    },
    ResearchPhase.INTERNAL_REVIEW: {
        "editor_review": (
            "You are reviewing a research paper for internal quality control.\n"
            "Topic: {seed_prompt}\n\n"
            "## Paper Draft\n{current_draft}\n\n"
            "Provide a structured review with these sections (use ## headers):\n"
            "## Strengths\n- What works well\n\n"
            "## Weaknesses\n- What needs improvement\n\n"
            "## Required Changes\n- Specific changes needed before submission\n\n"
            "## Recommendation\n- Either 'accept' (ready for submission) or "
            "'revise' (needs another round of revisions)"
        ),
        "revision": (
            "You are revising a research paper based on internal review feedback.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Current Draft\n{current_draft}\n\n"
            "## Review Feedback\n{review_feedback}\n\n"
            "Revise the paper to address the required changes. "
            "Output the complete revised paper in markdown."
        ),
    },
}

# How many recent messages to include in agent context
_RECENT_MESSAGES_LIMIT = 10


class OrchestrationEngine:
    """Orchestrates multi-agent research cycles through structured phases."""

    def __init__(
        self,
        config: Config,
        database: Database,
        corpus: Corpus,
        logger: EventLogger,
        agent_factory: AgentFactory,
    ) -> None:
        """Initialize the orchestration engine.

        Args:
            config: Application configuration.
            database: Database for persistence.
            corpus: Literature corpus for context.
            logger: Event logger.
            agent_factory: Factory for creating agents.
        """
        self._config = config
        self._db = database
        self._corpus = corpus
        self._logger = logger
        self._factory = agent_factory
        self._checkpoint_mgr = CheckpointManager(
            database=database,
            api_key=config.api_key or "",
            event_logger=logger,
        )

        # State set during run
        self._thread_id: str = ""
        self._seed_prompt: str = ""
        self._agents: dict[str, Agent] = {}
        self._messages: list[dict[str, Any]] = []
        self._phase_manager: PhaseManager | None = None
        self._checkpoint: Checkpoint | None = None

    async def run_research_cycle(
        self,
        seed_prompt: str,
        mode: str = "directed",
        team_roles: list[str] | None = None,
    ) -> str:
        """Run a full research cycle: SEEDING -> IDEATION -> PLANNING -> WRITING -> REVIEW.

        Args:
            seed_prompt: The research question or topic.
            mode: Operating mode (directed, explore, etc.).
            team_roles: Agent roles to include. Defaults to DEFAULT_TEAM_ROLES.

        Returns:
            Thread ID of the completed cycle.
        """
        if team_roles is None:
            team_roles = list(DEFAULT_TEAM_ROLES)

        self._seed_prompt = seed_prompt
        self._messages = []

        # Create agent team
        agents = self._factory.create_team(team_roles, skill_mode="default")
        self._agents = {a.agent_id: a for a in agents}

        # Phase 1: SEEDING
        self._thread_id = await self._run_seeding_phase(seed_prompt, mode)

        # Initialize phase manager (starts at SEEDING, transition to IDEATION)
        self._phase_manager = PhaseManager(ResearchPhase.SEEDING)

        # Phase 2: IDEATION
        max_rounds = self._config.orchestrator.max_rounds_per_phase
        checkpoint_interval = self._config.orchestrator.checkpoint_interval
        agent_count = len(self._agents)

        self._phase_manager.transition_to(ResearchPhase.IDEATION)
        self._log_phase_transition(ResearchPhase.SEEDING, ResearchPhase.IDEATION)
        click.echo(f"Phase: IDEATION ({max_rounds} rounds, {agent_count} agents)")
        await self._run_phase(
            ResearchPhase.IDEATION,
            max_rounds=max_rounds,
            checkpoint_interval=checkpoint_interval,
        )

        # Phase 3: PLANNING
        self._phase_manager.transition_to(ResearchPhase.PLANNING)
        self._log_phase_transition(ResearchPhase.IDEATION, ResearchPhase.PLANNING)
        self._messages = []  # Reset messages for new phase
        click.echo(f"Phase: PLANNING ({max_rounds} rounds, {agent_count} agents)")
        await self._run_phase(
            ResearchPhase.PLANNING,
            max_rounds=max_rounds,
            checkpoint_interval=checkpoint_interval,
        )

        # Phase 4: WRITING (optional, controlled by config)
        if self._config.orchestrator.enable_writing:
            self._phase_manager.transition_to(ResearchPhase.WRITING)
            self._log_phase_transition(ResearchPhase.PLANNING, ResearchPhase.WRITING)
            self._messages = []
            click.echo("Phase: WRITING")
            paper_draft = await self._run_writing_phase()

            # Phase 5: INTERNAL REVIEW
            self._phase_manager.transition_to(ResearchPhase.INTERNAL_REVIEW)
            self._log_phase_transition(ResearchPhase.WRITING, ResearchPhase.INTERNAL_REVIEW)
            self._messages = []
            click.echo("Phase: INTERNAL_REVIEW")
            await self._run_review_phase(paper_draft)

            self._db.update_thread(self._thread_id, status="reviewed")
        else:
            self._db.update_thread(self._thread_id, status="planning_complete")

        return self._thread_id

    async def _run_writing_phase(self) -> PaperDraft:
        """Run the WRITING phase: section drafting, assembly, optional refinement.

        Returns:
            PaperDraft with assembled paper.
        """
        draft = PaperDraft()

        # Round 1: Section Drafting — each agent drafts their assigned sections
        click.echo("  Round 1: Section drafting...")
        await self._run_section_drafting(draft)

        # Round 2: Assembly — writer combines all sections
        click.echo("  Round 2: Assembly...")
        assembled_body = await self._run_assembly(draft)
        draft.assembled_body = assembled_body

        # Extract title from assembled body
        for line in assembled_body.split("\n"):
            if line.startswith("# "):
                draft.title = line[2:].strip()
                break

        # Persist paper to database
        paper_id = f"paper-{uuid.uuid4().hex[:12]}"
        abstract = ""
        if PaperSection.ABSTRACT in draft.sections:
            abstract = draft.sections[PaperSection.ABSTRACT].content[:1000]

        authors = list(self._agents.keys())
        self._db.create_paper(
            paper_id=paper_id,
            title=draft.title or self._seed_prompt[:200],
            abstract=abstract,
            authors=authors,
            body=draft.assembled_body,
            status="draft",
        )
        self._db.update_thread(self._thread_id, current_draft_id=paper_id)

        click.echo(f"  Paper saved: {paper_id}")
        return draft

    async def _run_section_drafting(self, draft: PaperDraft) -> None:
        """Round 1 of writing: each agent drafts their assigned sections.

        Args:
            draft: PaperDraft to populate with section drafts.
        """
        checkpoint_context = ""
        if self._checkpoint:
            checkpoint_context = self._checkpoint.to_context_string() + "\n\n"

        template = _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["section_drafting"]

        for agent_id, agent in self._agents.items():
            role = agent.skill_profile
            assigned = SECTION_ASSIGNMENTS.get(role)
            if not assigned:
                continue  # Roles without section assignments skip this round

            section_list = ", ".join(s.value.title() for s in assigned)
            prompt = template.format(
                seed_prompt=self._seed_prompt,
                checkpoint_context=checkpoint_context,
                assigned_sections=section_list,
            )

            try:
                response = await agent.generate(prompt)
            except Exception as e:
                self._logger.log_error(e, agent_id=agent_id, thread_id=self._thread_id)
                click.echo(f"    [!] {agent_id} failed: {e}")
                continue

            # Parse sections from response
            parsed = parse_sections_from_markdown(response.content)
            for section in assigned:
                content = parsed.get(section.value, "")
                if not content:
                    # Try title-cased header
                    content = parsed.get(section.value.title().lower(), "")
                if content:
                    draft.add_section(
                        SectionDraft(section=section, content=content, author=agent_id)
                    )

            self._log_agent_response(agent_id, response, ResearchPhase.WRITING, "section_draft")

    async def _run_assembly(self, draft: PaperDraft) -> str:
        """Round 2 of writing: writer assembles all sections into a coherent paper.

        Args:
            draft: PaperDraft with section drafts.

        Returns:
            Assembled paper body as markdown.
        """
        # Find writer agent
        writer_agent = self._find_agent_by_role("writer")
        if writer_agent is None:
            # Fallback: render from sections directly
            click.echo("    [!] No writer agent found, assembling from sections")
            return draft.to_markdown()

        checkpoint_context = ""
        if self._checkpoint:
            checkpoint_context = self._checkpoint.to_context_string() + "\n\n"

        # Build section drafts text
        section_drafts_text = ""
        for section in PaperSection:
            if section in draft.sections:
                sd = draft.sections[section]
                section_drafts_text += (
                    f"## {section.value.title()} (by {sd.author})\n\n{sd.content}\n\n"
                )

        template = _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["assembly"]
        prompt = template.format(
            seed_prompt=self._seed_prompt,
            checkpoint_context=checkpoint_context,
            section_drafts=section_drafts_text,
        )

        try:
            response = await writer_agent.generate(prompt)
            self._log_agent_response(
                writer_agent.agent_id, response, ResearchPhase.WRITING, "assembly"
            )
            return response.content
        except Exception as e:
            self._logger.log_error(e, agent_id=writer_agent.agent_id, thread_id=self._thread_id)
            click.echo(f"    [!] Writer assembly failed: {e}")
            return draft.to_markdown()

    async def _run_review_phase(self, draft: PaperDraft) -> None:
        """Run the INTERNAL_REVIEW phase: editor reviews, optionally loop back.

        Args:
            draft: PaperDraft to review.
        """
        max_iterations = self._config.orchestrator.max_review_iterations
        current_body = draft.assembled_body or draft.to_markdown()

        for iteration in range(1, max_iterations + 1):
            click.echo(f"  Review iteration {iteration}/{max_iterations}...")

            # Editor reviews
            editor = self._find_agent_by_role("editor")
            if editor is None:
                click.echo("    [!] No editor agent found, skipping review")
                return

            template = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["editor_review"]
            prompt = template.format(
                seed_prompt=self._seed_prompt,
                current_draft=current_body[:8000],  # Truncate for context window
            )

            try:
                response = await editor.generate(prompt)
            except Exception as e:
                self._logger.log_error(e, agent_id=editor.agent_id, thread_id=self._thread_id)
                click.echo(f"    [!] Editor review failed: {e}")
                return

            self._log_agent_response(
                editor.agent_id, response, ResearchPhase.INTERNAL_REVIEW, "review"
            )

            # Parse review feedback
            feedback = parse_review_feedback(response.content)
            click.echo(
                f"    Editor recommendation: {feedback.recommendation} "
                f"({len(feedback.required_changes)} required changes)"
            )

            if feedback.recommendation == "accept":
                # Paper accepted — update status
                thread = self._db.get_thread(self._thread_id)
                if thread and thread.get("current_draft_id"):
                    self._db.update_paper(thread["current_draft_id"], status="reviewed")
                return

            # Revision needed — writer revises
            if iteration < max_iterations:
                click.echo("    Revising...")
                current_body = await self._run_revision(current_body, response.content)
                draft.assembled_body = current_body

                # Update paper in database
                thread = self._db.get_thread(self._thread_id)
                if thread and thread.get("current_draft_id"):
                    self._db.update_paper(
                        thread["current_draft_id"],
                        body=current_body,
                        status="revised",
                    )

        # Max iterations reached, mark as reviewed regardless
        thread = self._db.get_thread(self._thread_id)
        if thread and thread.get("current_draft_id"):
            self._db.update_paper(thread["current_draft_id"], status="reviewed")

    async def _run_revision(self, current_body: str, review_text: str) -> str:
        """Writer revises the paper based on review feedback.

        Args:
            current_body: Current paper markdown.
            review_text: Editor's review text.

        Returns:
            Revised paper body.
        """
        writer = self._find_agent_by_role("writer")
        if writer is None:
            return current_body

        checkpoint_context = ""
        if self._checkpoint:
            checkpoint_context = self._checkpoint.to_context_string() + "\n\n"

        template = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["revision"]
        prompt = template.format(
            seed_prompt=self._seed_prompt,
            checkpoint_context=checkpoint_context,
            current_draft=current_body[:8000],
            review_feedback=review_text[:4000],
        )

        try:
            response = await writer.generate(prompt)
            self._log_agent_response(
                writer.agent_id, response, ResearchPhase.INTERNAL_REVIEW, "revision"
            )
            return response.content
        except Exception as e:
            self._logger.log_error(e, agent_id=writer.agent_id, thread_id=self._thread_id)
            click.echo(f"    [!] Revision failed: {e}")
            return current_body

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
        click.echo(f"    {agent_id}: {total_tokens} tokens")

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

        # Optionally fetch literature context
        try:
            lit_context = await self._corpus.build_literature_context(
                seed_prompt, max_papers=5, include_arxiv=True
            )
            if lit_context and "No relevant papers found" not in lit_context:
                self._db.update_thread(
                    thread_id,
                    literature_reviewed=[seed_prompt],
                )
                # Store literature context for later use in agent prompts
                self._literature_context = lit_context
            else:
                self._literature_context = ""
        except Exception as e:
            self._logger.log_error(e, thread_id=thread_id)
            click.echo(f"  [!] Literature search failed: {e}")
            self._literature_context = ""

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
            click.echo(f"  Round {round_num}/{max_rounds}...")
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
                    click.echo(f"  Checkpoint saved (round {round_num})")
                except Exception as e:
                    self._logger.log_error(e, thread_id=self._thread_id)
                    click.echo(f"  [!] Checkpoint failed: {e}")

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
                click.echo("  Checkpoint saved (end of phase)")
            except Exception as e:
                self._logger.log_error(e, thread_id=self._thread_id)
                click.echo(f"  [!] Final checkpoint failed: {e}")

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
        speaker_order = scheduler.get_speaker_order(phase)

        for agent_id in speaker_order:
            agent = self._agents[agent_id]
            prompt = self._build_agent_prompt(agent, phase, round_num)

            try:
                response = await agent.generate(prompt)
            except Exception as e:
                self._logger.log_error(e, agent_id=agent_id, thread_id=self._thread_id)
                click.echo(f"    [!] {agent_id} failed: {e}")
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
            click.echo(f"    {agent_id}: {total_tokens} tokens")

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

        # Add literature context if available (first round of ideation only)
        if phase == ResearchPhase.IDEATION and round_num == 1:
            lit = getattr(self, "_literature_context", "")
            if lit:
                checkpoint_context = lit + "\n\n" + checkpoint_context

        return template.format(
            seed_prompt=self._seed_prompt,
            checkpoint_context=checkpoint_context,
            recent_messages=recent_messages,
        )

    def _log_phase_transition(self, from_phase: ResearchPhase, to_phase: ResearchPhase) -> None:
        """Log a phase transition event."""
        self._logger.log(
            EventType.PHASE_TRANSITION,
            content={"from": str(from_phase), "to": str(to_phase)},
            thread_id=self._thread_id,
            phase=str(to_phase),
        )
        self._db.update_thread(self._thread_id, current_phase=str(to_phase))
