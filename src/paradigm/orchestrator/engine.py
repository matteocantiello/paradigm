"""Main orchestration engine for research cycles."""

import re
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
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
from paradigm.journal.publication import publish_paper, reject_paper
from paradigm.journal.review import PeerReview, parse_peer_review, synthesize_decision
from paradigm.literature.corpus import Corpus
from paradigm.literature.prompt_utils import (
    extract_urls,
    format_search_results,
    parse_search_requests,
)
from paradigm.logging.events import EventLogger, EventType
from paradigm.orchestrator.phases import PhaseManager, ResearchPhase
from paradigm.orchestrator.scheduler import Scheduler
from paradigm.sandbox.executor import CodeExecutor
from paradigm.sandbox.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from paradigm.storage.checkpoints import Checkpoint, CheckpointManager
from paradigm.storage.database import Database

# Intervention hook type: called with (thread_id, from_phase, to_phase) → "continue"|"pause"|"abort"
InterventionHook = Callable[[str, str, str], str]

# Default team composition
DEFAULT_TEAM_ROLES = ["theorist", "analyst", "synthesizer", "skeptic", "writer", "editor"]

# Mode-specific team compositions
MODE_TEAM_ROLES: dict[str, list[str]] = {
    "directed": ["theorist", "analyst", "synthesizer", "skeptic", "writer", "editor"],
    "explore": ["theorist", "analyst", "synthesizer", "skeptic", "writer", "editor"],
    "hypothesis": ["theorist", "skeptic", "analyst", "writer", "editor"],
    "experimental": ["experimentalist", "analyst", "theorist", "writer", "editor"],
    "replication": ["analyst", "experimentalist", "skeptic", "writer", "editor"],
}

# Mode-specific IDEATION prompt overrides (round_1 only)
_MODE_PROMPT_OVERRIDES: dict[str, dict[str, str]] = {
    "explore": {
        "round_1": (
            "You are participating in an open-ended exploratory research session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "This is an exploration session — there is no single hypothesis to test. "
            "Instead, survey the landscape of this topic broadly. Identify interesting "
            "open questions, unexplored connections between subfields, and surprising "
            "gaps in the literature. Propose 2-3 diverse research directions worth pursuing."
        ),
    },
    "hypothesis": {
        "round_1": (
            "You are participating in a rigorous hypothesis-testing session.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "Focus on formulating precise, falsifiable hypotheses. For each hypothesis:\n"
            "1. State it clearly and unambiguously\n"
            "2. Describe what evidence would confirm or refute it\n"
            "3. Identify potential confounding factors\n"
            "4. Propose the simplest experiment that could test it\n\n"
            "Rigor over creativity — every hypothesis must be testable."
        ),
    },
}

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
    ResearchPhase.EXECUTION: {
        "propose_experiment": (
            "You are designing and running computational experiments.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "{previous_results}"
            "Write Python code to test the hypotheses and plans from prior discussion. "
            "Wrap each experiment in a fenced ```python block with a "
            "`# EXPERIMENT: <name>` comment on the first line.\n\n"
            "**Available libraries:** numpy, scipy, matplotlib, pandas, scikit-learn, "
            "sympy, astropy.\n"
            "**Safety constraints:** Do NOT use os, subprocess, open() for writing, "
            "or network access. Read-only file access is allowed via provided shared data.\n"
            "**Output:** Print results to stdout. Save figures as .png files using "
            "matplotlib (plt.savefig('figure_name.png')). All .png/.pdf files in the "
            "working directory will be collected.\n\n"
            "Focus on producing clear, reproducible computational results."
        ),
        "analyze_results": (
            "You are reviewing computational experiment results.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Previous Experiment Results\n{previous_results}\n\n"
            "Analyze the results above. You may either:\n"
            "1. Propose a follow-up experiment by writing a ```python block "
            "(with `# EXPERIMENT: <name>` header)\n"
            "2. Declare experiments sufficient by NOT including any code block "
            "(just provide your analysis)\n\n"
            "If proposing follow-up experiments, explain what additional question "
            "they address."
        ),
        "retry_after_failure": (
            "Your previous experiment failed or was rejected.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Error Feedback\n{error_feedback}\n\n"
            "Fix the code and resubmit in a ```python block with "
            "`# EXPERIMENT: <name>` header. Address the specific error above."
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
    ResearchPhase.SUBMITTED: {
        "desk_review": (
            "You are the editor-in-chief performing a desk review of a submitted paper.\n"
            "Topic: {seed_prompt}\n\n"
            "## Submitted Paper\n{current_draft}\n\n"
            "Perform a quick quality check:\n"
            "- Is the paper coherent and on-topic?\n"
            "- Does it have the basic structure of a research paper?\n"
            "- Is it written in intelligible prose?\n\n"
            "Respond with:\n"
            "## Decision\nEither 'send_to_review' (paper is suitable for peer review) "
            "or 'desk_reject' (paper has fundamental issues)\n\n"
            "## Reason\nBrief explanation of your decision."
        ),
    },
    ResearchPhase.PEER_REVIEW: {
        "review": (
            "You are an independent peer reviewer evaluating a submitted manuscript.\n"
            "Topic: {seed_prompt}\n\n"
            "## Manuscript\n{current_draft}\n\n"
            "Provide your review in this exact format using ## headers:\n\n"
            "## Summary\nBrief summary of the paper.\n\n"
            "## Strengths\n- Key strengths as bullet points\n\n"
            "## Weaknesses\n- Key weaknesses as bullet points\n\n"
            "## Questions\n- Questions for the authors\n\n"
            "## Suggestions\n- Specific suggestions for improvement\n\n"
            "## Scores\nNovelty: X/10\nRigor: X/10\nClarity: X/10\nSignificance: X/10\n\n"
            "## Recommendation\nOne of: accept, minor_revision, major_revision, reject"
        ),
    },
    ResearchPhase.REVISION: {
        "revise": (
            "You are revising a research paper based on peer review feedback.\n"
            "Topic: {seed_prompt}\n\n"
            "{checkpoint_context}"
            "## Current Draft\n{current_draft}\n\n"
            "## Peer Review Feedback\n{review_feedback}\n\n"
            "Revise the paper to address the reviewer concerns and suggestions. "
            "Output the complete revised paper in markdown."
        ),
    },
}

# How many recent messages to include in agent context
_RECENT_MESSAGES_LIMIT = 10

# Search instruction appended to agent prompts in search-enabled phases
_SEARCH_INSTRUCTION = (
    "\n\n## Literature Search\n"
    "You may request literature searches at any time by writing:\n"
    "  [SEARCH: your query here]\n\n"
    "You may include multiple search requests. Be specific to get relevant results "
    "(e.g., [SEARCH: Cepheid period-luminosity relation metallicity dependence]).\n"
)

# Phases where agents can request literature searches
_SEARCH_ENABLED_PHASES: set[ResearchPhase] = {
    ResearchPhase.IDEATION,
    ResearchPhase.PLANNING,
    ResearchPhase.EXECUTION,
    ResearchPhase.WRITING,
    ResearchPhase.INTERNAL_REVIEW,
    ResearchPhase.PEER_REVIEW,
    ResearchPhase.REVISION,
}

# Max tokens for writing/assembly/revision calls (papers need much more than default 4096)
_WRITING_MAX_TOKENS = 32768

# Max characters of paper body to include in agent prompts
_PAPER_CONTEXT_LIMIT = 50000

# Execution phase limits
_EXECUTION_OUTPUT_LIMIT = 4000
_EXECUTION_STDERR_LIMIT = 2000
_MAX_RETRIES_PER_EXPERIMENT = 2

# Regex to extract fenced python code blocks
_CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
_EXPERIMENT_NAME_RE = re.compile(r"^#\s*EXPERIMENT:\s*(.+)", re.MULTILINE)


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Extract Python code blocks from agent response text.

    Looks for fenced ```python blocks. Extracts experiment name from
    a ``# EXPERIMENT: name`` comment on the first line.

    Args:
        text: Agent response text.

    Returns:
        List of (experiment_name, code) tuples.
    """
    blocks: list[tuple[str, str]] = []
    for match in _CODE_BLOCK_RE.finditer(text):
        code = match.group(1).strip()
        if not code:
            continue
        # Try to extract experiment name from first line
        name_match = _EXPERIMENT_NAME_RE.match(code)
        name = name_match.group(1).strip() if name_match else "unnamed_experiment"
        blocks.append((name, code))
    return blocks


def _format_execution_result(experiment_name: str, result: ExecutionResult) -> str:
    """Format an execution result as markdown for agent context.

    Args:
        experiment_name: Name of the experiment.
        result: Execution result.

    Returns:
        Markdown-formatted result string.
    """
    parts = [f"### Experiment: {experiment_name}"]
    parts.append(f"**Status:** {result.status.value}")
    if result.duration_seconds is not None:
        parts.append(f"**Duration:** {result.duration_seconds:.1f}s")
    if result.stdout:
        stdout = result.stdout[:_EXECUTION_OUTPUT_LIMIT]
        if len(result.stdout) > _EXECUTION_OUTPUT_LIMIT:
            stdout += "\n... (output truncated)"
        parts.append(f"**Output:**\n```\n{stdout}\n```")
    if result.stderr:
        stderr = result.stderr[:_EXECUTION_STDERR_LIMIT]
        if len(result.stderr) > _EXECUTION_STDERR_LIMIT:
            stderr += "\n... (stderr truncated)"
        parts.append(f"**Errors:**\n```\n{stderr}\n```")
    if result.error_message:
        parts.append(f"**Error:** {result.error_message}")
    if result.output_files:
        file_list = ", ".join(f"`{f.filename}`" for f in result.output_files)
        parts.append(f"**Output files:** {file_list}")
    return "\n\n".join(parts)


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
        """
        self._config = config
        self._db = database
        self._corpus = corpus
        self._logger = logger
        self._factory = agent_factory
        self._intervention_hook = intervention_hook
        self._checkpoint_mgr = CheckpointManager(
            database=database,
            api_key=config.api_key or "",
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
        self._search_count_this_round: int = 0

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

        # Phase 3: PLANNING (intervention check)
        intervention = self._check_intervention("ideation", "planning")
        if intervention == "abort":
            self._db.update_thread(self._thread_id, status="aborted")
            click.echo("Research cycle aborted by intervention hook.")
            return self._thread_id
        if intervention == "pause":
            self._db.update_thread(self._thread_id, status="paused")
            click.echo("Research cycle paused by intervention hook.")
            return self._thread_id

        self._phase_manager.transition_to(ResearchPhase.PLANNING)
        self._log_phase_transition(ResearchPhase.IDEATION, ResearchPhase.PLANNING)
        self._messages = []  # Reset messages for new phase
        click.echo(f"Phase: PLANNING ({max_rounds} rounds, {agent_count} agents)")
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
                click.echo("Research cycle aborted by intervention hook.")
                return self._thread_id
            if intervention == "pause":
                self._db.update_thread(self._thread_id, status="paused")
                click.echo("Research cycle paused by intervention hook.")
                return self._thread_id

            self._phase_manager.transition_to(ResearchPhase.EXECUTION)
            self._log_phase_transition(ResearchPhase.PLANNING, ResearchPhase.EXECUTION)
            self._messages = []
            click.echo("Phase: EXECUTION")
            await self._run_experimentation_phase()

        # Phase 4: WRITING (optional, controlled by config)
        if self._config.orchestrator.enable_writing:
            from_phase = ResearchPhase.EXECUTION if should_experiment else ResearchPhase.PLANNING
            from_label = "execution" if should_experiment else "planning"

            # Intervention check before WRITING
            intervention = self._check_intervention(from_label, "writing")
            if intervention == "abort":
                self._db.update_thread(self._thread_id, status="aborted")
                click.echo("Research cycle aborted by intervention hook.")
                return self._thread_id
            if intervention == "pause":
                self._db.update_thread(self._thread_id, status="paused")
                click.echo("Research cycle paused by intervention hook.")
                return self._thread_id

            self._phase_manager.transition_to(ResearchPhase.WRITING)
            self._log_phase_transition(from_phase, ResearchPhase.WRITING)
            self._messages = []
            click.echo("Phase: WRITING")
            paper_draft = await self._run_writing_phase()

            # Phase 5: INTERNAL REVIEW
            self._phase_manager.transition_to(ResearchPhase.INTERNAL_REVIEW)
            self._log_phase_transition(ResearchPhase.WRITING, ResearchPhase.INTERNAL_REVIEW)
            self._messages = []
            click.echo("Phase: INTERNAL_REVIEW")
            await self._run_review_phase(paper_draft)

            # Phase 6: PEER REVIEW PIPELINE (optional)
            if self._config.orchestrator.enable_peer_review:
                # Intervention check before SUBMITTED
                intervention = self._check_intervention("internal", "submitted")
                if intervention == "abort":
                    self._db.update_thread(self._thread_id, status="aborted")
                    click.echo("Research cycle aborted by intervention hook.")
                    return self._thread_id
                if intervention == "pause":
                    self._db.update_thread(self._thread_id, status="paused")
                    click.echo("Research cycle paused by intervention hook.")
                    return self._thread_id

                accepted = await self._run_submission_phase(paper_draft)
                if accepted:
                    decision, reviews = await self._run_peer_review_phase(paper_draft)
                    revision_count = 0
                    max_revisions = self._config.orchestrator.max_revision_rounds
                    while (
                        decision in ("minor_revision", "major_revision")
                        and revision_count < max_revisions
                    ):
                        paper_draft = await self._run_revision_phase(paper_draft, reviews)
                        decision, reviews = await self._run_peer_review_phase(paper_draft)
                        revision_count += 1

                    thread = self._db.get_thread(self._thread_id)
                    paper_id = thread["current_draft_id"] if thread else None
                    if paper_id and decision in ("accept", "minor_revision"):
                        await publish_paper(paper_id, self._db, self._corpus, self._logger, reviews)
                        self._db.update_thread(self._thread_id, status="published")
                        click.echo("  Paper PUBLISHED")
                    elif paper_id:
                        reject_paper(paper_id, self._db, reviews, self._logger)
                        self._db.update_thread(self._thread_id, status="rejected")
                        click.echo("  Paper REJECTED")
                else:
                    # Desk rejected
                    self._db.update_thread(self._thread_id, status="rejected")
            else:
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

        # Write markdown file to papers directory
        self._save_paper_file(paper_id, draft.assembled_body)

        click.echo(f"  Paper saved: {paper_id}")
        return draft

    async def _run_section_drafting(self, draft: PaperDraft) -> None:
        """Round 1 of writing: each agent drafts their assigned sections.

        Args:
            draft: PaperDraft to populate with section drafts.
        """
        self._search_count_this_round = 0
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

            # Inject execution context for RESULTS and METHODS sections
            if self._execution_context and any(
                s in (PaperSection.RESULTS, PaperSection.METHODS) for s in assigned
            ):
                exec_label = (
                    "computational results"
                    if PaperSection.RESULTS in assigned
                    else "computational methods"
                )
                prompt += (
                    f"\n\n## Computational Experiment Results\n"
                    f"The following {exec_label} were produced during the "
                    f"EXECUTION phase. Incorporate them into your section:\n\n"
                    f"{self._execution_context}"
                )

            try:
                response = await agent.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
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
            await self._process_search_requests(agent_id, response.content, ResearchPhase.WRITING)

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

        # Add figure references if experiments produced output files
        if self._execution_figures:
            fig_lines = ["\n\n## Figures from Computational Experiments"]
            fig_lines.append("Include these figures in the paper using the markdown syntax shown:")
            for i, (exp_name, fpath) in enumerate(self._execution_figures, 1):
                fig_lines.append(
                    f"- Figure {i} ({exp_name}): `![Figure {i}](figures/{fpath.name})`"
                )
            prompt += "\n".join(fig_lines)

        try:
            response = await writer_agent.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            self._log_agent_response(
                writer_agent.agent_id, response, ResearchPhase.WRITING, "assembly"
            )
            return response.content
        except Exception as e:
            self._logger.log_error(e, agent_id=writer_agent.agent_id, thread_id=self._thread_id)
            click.echo(f"    [!] Writer assembly failed: {e}")
            return draft.to_markdown()

    async def _run_experimentation_phase(self) -> None:
        """Run the EXECUTION phase: agents propose and run computational experiments."""
        max_rounds = self._config.orchestrator.max_experiment_rounds

        executor = CodeExecutor(
            config=self._config.sandbox,
            logger=self._logger,
            data_dir=self._config.storage.data_dir,
        )

        all_results: list[str] = []
        self._execution_figures = []

        try:
            for round_num in range(1, max_rounds + 1):
                click.echo(f"  Experiment round {round_num}/{max_rounds}...")
                self._search_count_this_round = 0

                # Find experimenter (prefer experimentalist, fallback to analyst)
                experimenter = self._find_agent_by_role("experimentalist")
                if experimenter is None:
                    experimenter = self._find_agent_by_role("analyst")
                if experimenter is None:
                    click.echo("    [!] No experimentalist or analyst found, skipping")
                    break

                # Build prompt
                checkpoint_context = ""
                if self._checkpoint:
                    checkpoint_context = self._checkpoint.to_context_string() + "\n\n"

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
                    click.echo(f"    [!] {experimenter.agent_id} failed: {e}")
                    break

                self._log_agent_response(
                    experimenter.agent_id, response, ResearchPhase.EXECUTION, "experiment_proposal"
                )

                await self._process_search_requests(
                    experimenter.agent_id, response.content, ResearchPhase.EXECUTION
                )

                # Extract code blocks
                code_blocks = _extract_code_blocks(response.content)
                if not code_blocks and round_num > 1:
                    click.echo("    Agent declared experiments sufficient")
                    break
                if not code_blocks:
                    click.echo("    No code blocks proposed, skipping execution")
                    continue

                # Execute each code block
                for exp_name, code in code_blocks:
                    click.echo(f"    Running: {exp_name}")
                    result = await self._execute_with_retry(
                        executor, experimenter, exp_name, code, checkpoint_context
                    )
                    formatted = _format_execution_result(exp_name, result)
                    all_results.append(formatted)

                    # Track output figures
                    for output_file in result.output_files:
                        if output_file.filename.endswith((".png", ".pdf")):
                            self._execution_figures.append((exp_name, Path(output_file.path)))

                    status_str = result.status.value
                    click.echo(f"    {exp_name}: {status_str}")

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
                    click.echo("  Checkpoint saved (end of execution)")
                except Exception as e:
                    self._logger.log_error(e, thread_id=self._thread_id)
                    click.echo(f"  [!] Checkpoint failed: {e}")

        finally:
            await executor.cleanup()

    async def _execute_with_retry(
        self,
        executor: CodeExecutor,
        experimenter: Agent,
        experiment_name: str,
        code: str,
        checkpoint_context: str,
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
            result = await executor.execute(request)

            # Success or timeout — return immediately
            if result.status in (ExecutionStatus.SUCCESS, ExecutionStatus.TIMEOUT):
                return result

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

            error_feedback = "\n\n".join(error_parts)
            click.echo(f"    Retry {attempt + 1}/{_MAX_RETRIES_PER_EXPERIMENT}...")

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

    async def _run_review_phase(self, draft: PaperDraft) -> None:
        """Run the INTERNAL_REVIEW phase: editor reviews, optionally loop back.

        Args:
            draft: PaperDraft to review.
        """
        max_iterations = self._config.orchestrator.max_review_iterations
        current_body = draft.assembled_body or draft.to_markdown()

        for iteration in range(1, max_iterations + 1):
            click.echo(f"  Review iteration {iteration}/{max_iterations}...")
            self._search_count_this_round = 0

            # Editor reviews
            editor = self._find_agent_by_role("editor")
            if editor is None:
                click.echo("    [!] No editor agent found, skipping review")
                return

            template = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["editor_review"]
            prompt = template.format(
                seed_prompt=self._seed_prompt,
                current_draft=current_body[:_PAPER_CONTEXT_LIMIT],  # Truncate for context window
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
            await self._process_search_requests(
                editor.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
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

                # Update paper in database and on disk
                thread = self._db.get_thread(self._thread_id)
                if thread and thread.get("current_draft_id"):
                    paper_id = thread["current_draft_id"]
                    self._db.update_paper(
                        paper_id,
                        body=current_body,
                        status="revised",
                    )
                    self._save_paper_file(paper_id, current_body)

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
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
            review_feedback=review_text[:_PAPER_CONTEXT_LIMIT],
        )

        try:
            response = await writer.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            self._log_agent_response(
                writer.agent_id, response, ResearchPhase.INTERNAL_REVIEW, "revision"
            )
            await self._process_search_requests(
                writer.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            return response.content
        except Exception as e:
            self._logger.log_error(e, agent_id=writer.agent_id, thread_id=self._thread_id)
            click.echo(f"    [!] Revision failed: {e}")
            return current_body

    async def _run_submission_phase(self, draft: PaperDraft) -> bool:
        """Run the SUBMITTED phase: desk review by editor-in-chief.

        Args:
            draft: Paper draft to submit.

        Returns:
            True if paper passes desk review, False if desk-rejected.
        """
        self._phase_manager.transition_to(ResearchPhase.SUBMITTED)
        self._log_phase_transition(ResearchPhase.INTERNAL_REVIEW, ResearchPhase.SUBMITTED)
        self._messages = []
        click.echo("Phase: SUBMITTED (desk review)")

        # Update submitted_at in database
        from datetime import UTC, datetime

        thread = self._db.get_thread(self._thread_id)
        if thread and thread.get("current_draft_id"):
            self._db.update_paper(
                thread["current_draft_id"],
                status="submitted",
                submitted_at=datetime.now(UTC).isoformat(),
            )

        # Editor desk review
        editor = self._find_agent_by_role("editor")
        if editor is None:
            click.echo("  [!] No editor agent found, auto-accepting for desk review")
            return True

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.SUBMITTED]["desk_review"]
        prompt = template.format(
            seed_prompt=self._seed_prompt,
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
        )

        try:
            response = await editor.generate(prompt)
        except Exception as e:
            self._logger.log_error(e, agent_id=editor.agent_id, thread_id=self._thread_id)
            click.echo(f"  [!] Desk review failed: {e}, auto-accepting")
            return True

        self._log_agent_response(editor.agent_id, response, ResearchPhase.SUBMITTED, "desk_review")

        # Parse decision
        response_lower = response.content.lower()
        if "desk_reject" in response_lower or "desk reject" in response_lower:
            click.echo("  Desk REJECTED")
            # Desk rejection — create a minimal review for graveyard
            desk_review = PeerReview(
                reviewer_id=editor.agent_id,
                summary="Desk rejection by editor-in-chief.",
                weaknesses=["Did not pass desk review"],
                recommendation="reject",
            )
            thread = self._db.get_thread(self._thread_id)
            if thread and thread.get("current_draft_id"):
                reject_paper(thread["current_draft_id"], self._db, [desk_review], self._logger)
            self._phase_manager.transition_to(ResearchPhase.REJECTED)
            self._log_phase_transition(ResearchPhase.SUBMITTED, ResearchPhase.REJECTED)
            return False

        click.echo("  Desk review passed — sending to peer review")
        return True

    async def _run_peer_review_phase(self, draft: PaperDraft) -> tuple[str, list[PeerReview]]:
        """Run the PEER_REVIEW phase: create reviewers, collect reviews, synthesize decision.

        Args:
            draft: Paper draft to review.

        Returns:
            Tuple of (decision string, list of PeerReview objects).
        """
        self._phase_manager.transition_to(ResearchPhase.PEER_REVIEW)
        self._log_phase_transition(ResearchPhase.SUBMITTED, ResearchPhase.PEER_REVIEW)
        self._messages = []
        num_reviewers = self._config.orchestrator.num_reviewers
        click.echo(f"Phase: PEER_REVIEW ({num_reviewers} reviewers)")

        # Create fresh reviewer agents (not reusing team agents)
        reviewer_roles = ["reviewer"] * num_reviewers
        reviewer_agents = self._factory.create_team(reviewer_roles, skill_mode="default")

        # Give each reviewer a unique ID to avoid collision with team IDs
        for i, agent in enumerate(reviewer_agents):
            agent.agent_id = f"peer-reviewer-{i}"

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.PEER_REVIEW]["review"]

        self._search_count_this_round = 0
        reviews: list[PeerReview] = []
        for agent in reviewer_agents:
            prompt = template.format(
                seed_prompt=self._seed_prompt,
                current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
            )

            try:
                response = await agent.generate(prompt)
            except Exception as e:
                self._logger.log_error(e, agent_id=agent.agent_id, thread_id=self._thread_id)
                click.echo(f"    [!] {agent.agent_id} review failed: {e}")
                continue

            self._log_agent_response(agent.agent_id, response, ResearchPhase.PEER_REVIEW, "review")
            await self._process_search_requests(
                agent.agent_id, response.content, ResearchPhase.PEER_REVIEW
            )

            review = parse_peer_review(agent.agent_id, response.content)
            reviews.append(review)
            avg_score = sum(review.scores.values()) / len(review.scores) if review.scores else 0
            click.echo(
                f"    {agent.agent_id}: {review.recommendation} (avg score: {avg_score:.1f})"
            )

        # Synthesize decision
        decision = synthesize_decision(reviews)
        click.echo(f"  Decision: {decision}")

        return decision, reviews

    async def _run_revision_phase(self, draft: PaperDraft, reviews: list[PeerReview]) -> PaperDraft:
        """Run the REVISION phase: writer revises based on peer feedback.

        Args:
            draft: Current paper draft.
            reviews: Peer reviews with feedback.

        Returns:
            Updated PaperDraft with revised body.
        """
        self._phase_manager.transition_to(ResearchPhase.REVISION)
        self._log_phase_transition(ResearchPhase.PEER_REVIEW, ResearchPhase.REVISION)
        self._messages = []
        self._search_count_this_round = 0
        click.echo("Phase: REVISION")

        writer = self._find_agent_by_role("writer")
        if writer is None:
            click.echo("  [!] No writer agent found, skipping revision")
            # Re-submit without changes
            self._phase_manager.transition_to(ResearchPhase.SUBMITTED)
            self._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)
            return draft

        # Build review feedback text
        review_parts = []
        for review in reviews:
            parts = [f"### Reviewer: {review.reviewer_id}"]
            if review.summary:
                parts.append(f"Summary: {review.summary}")
            if review.weaknesses:
                parts.append("Weaknesses:\n" + "\n".join(f"- {w}" for w in review.weaknesses))
            if review.suggestions:
                parts.append("Suggestions:\n" + "\n".join(f"- {s}" for s in review.suggestions))
            if review.scores:
                scores_str = ", ".join(f"{k}: {v}/10" for k, v in review.scores.items())
                parts.append(f"Scores: {scores_str}")
            parts.append(f"Recommendation: {review.recommendation}")
            review_parts.append("\n".join(parts))
        review_feedback = "\n\n".join(review_parts)

        checkpoint_context = ""
        if self._checkpoint:
            checkpoint_context = self._checkpoint.to_context_string() + "\n\n"

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.REVISION]["revise"]
        prompt = template.format(
            seed_prompt=self._seed_prompt,
            checkpoint_context=checkpoint_context,
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
            review_feedback=review_feedback[:_PAPER_CONTEXT_LIMIT],
        )

        try:
            response = await writer.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
        except Exception as e:
            self._logger.log_error(e, agent_id=writer.agent_id, thread_id=self._thread_id)
            click.echo(f"  [!] Revision failed: {e}")
            # Transition back to SUBMITTED so peer review can re-run
            self._phase_manager.transition_to(ResearchPhase.SUBMITTED)
            self._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)
            return draft

        self._log_agent_response(writer.agent_id, response, ResearchPhase.REVISION, "revision")
        await self._process_search_requests(
            writer.agent_id, response.content, ResearchPhase.REVISION
        )

        # Update draft
        draft.assembled_body = response.content

        # Update paper in database and on disk
        thread = self._db.get_thread(self._thread_id)
        if thread and thread.get("current_draft_id"):
            paper_id = thread["current_draft_id"]
            self._db.update_paper(paper_id, body=response.content, status="revised")
            self._save_paper_file(paper_id, response.content)

        click.echo("  Revision complete")

        # Transition back to SUBMITTED for re-review
        self._phase_manager.transition_to(ResearchPhase.SUBMITTED)
        self._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)

        return draft

    def _save_paper_file(self, paper_id: str, body: str) -> None:
        """Write paper markdown to the papers directory.

        When figures exist, saves into a subdirectory structure:
        papers/paper_id/paper_id.md + papers/paper_id/figures/

        Args:
            paper_id: Paper identifier (used as filename).
            body: Paper markdown content.
        """
        papers_dir = self._config.storage.papers_dir
        if papers_dir is None:
            return

        if self._execution_figures:
            # Use subdirectory layout for papers with figures
            paper_dir = papers_dir / paper_id
            paper_dir.mkdir(parents=True, exist_ok=True)
            path = paper_dir / f"{paper_id}.md"
            path.write_text(body)
            self._copy_figures_to_paper_dir(paper_id)
        else:
            path = papers_dir / f"{paper_id}.md"
            path.write_text(body)

    def _copy_figures_to_paper_dir(self, paper_id: str) -> None:
        """Copy execution output figures to the paper's figures/ directory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._config.storage.papers_dir
        if papers_dir is None:
            return

        figures_dir = papers_dir / paper_id / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)

        for exp_name, src_path in self._execution_figures:
            if not src_path.exists():
                continue
            # Prefix with experiment name to avoid collisions
            safe_name = re.sub(r"[^\w\-.]", "_", exp_name)
            dest_name = f"{safe_name}_{src_path.name}"
            dest_path = figures_dir / dest_name
            shutil.copy2(src_path, dest_path)
            click.echo(f"  Figure copied: {dest_path.name}")

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

    async def _process_search_requests(
        self, agent_id: str, response_text: str, phase: ResearchPhase
    ) -> None:
        """Parse [SEARCH: query] markers from an agent's response and execute searches.

        Results are appended to self._literature_context for all subsequent agents.
        Respects the per-round budget from config.

        Args:
            agent_id: ID of the agent whose response contains search requests.
            response_text: The agent's response text.
            phase: Current research phase.
        """
        if phase not in _SEARCH_ENABLED_PHASES:
            return

        max_searches = self._config.orchestrator.max_searches_per_round
        queries = parse_search_requests(response_text)
        if not queries:
            return

        for query in queries:
            if self._search_count_this_round >= max_searches:
                click.echo(
                    f"    [!] Search budget exhausted ({max_searches}/round), "
                    f"skipping: {query[:60]}"
                )
                break

            try:
                papers = await self._corpus.search(query, max_results=5)
            except Exception as e:
                self._logger.log_error(e, agent_id=agent_id, thread_id=self._thread_id)
                click.echo(f"    [!] Search failed for '{query[:60]}': {e}")
                continue

            formatted = format_search_results(query, papers)
            lit = getattr(self, "_literature_context", "")
            self._literature_context = lit + "\n" + formatted if lit else formatted
            self._search_count_this_round += 1

            click.echo(f"    {agent_id} searched: '{query[:60]}' → {len(papers)} results")

            self._logger.log(
                EventType.LITERATURE_SEARCH,
                content={
                    "query": query,
                    "agent_id": agent_id,
                    "results": len(papers),
                    "phase": str(phase),
                    "search_num": self._search_count_this_round,
                },
                thread_id=self._thread_id,
                phase=str(phase),
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

        # Extract and ingest any URLs referenced in the prompt
        prompt_urls = extract_urls(seed_prompt)
        for url in prompt_urls:
            try:
                paper = await self._corpus.fetch_and_ingest_url(url)
                if paper:
                    click.echo(f"  Ingested external paper: {paper.title[:80]}")
                else:
                    click.echo(f"  [!] Could not extract PDF from: {url}")
            except Exception as e:
                self._logger.log_error(e, thread_id=thread_id)
                click.echo(f"  [!] Failed to fetch URL: {url} ({e})")

        # Literature context starts empty — agents populate it via [SEARCH:] requests
        self._literature_context = ""

        # Fetch graveyard context (lessons from past failures)
        try:
            graveyard_entries = self._db.search_graveyard(keyword=seed_prompt[:100], limit=5)
            if graveyard_entries:
                lines = ["## Lessons from Failed Research Attempts\n"]
                lines.append(
                    "_The following are summaries of past failed research attempts. "
                    "These are NOT citable papers — use them only to avoid repeating "
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
            click.echo(f"  [!] Graveyard search failed: {e}")
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
        self._search_count_this_round = 0
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

            # Process any [SEARCH: ...] requests in the agent's response
            await self._process_search_requests(agent_id, response.content, phase)

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

        # Include accumulated literature context (all phases)
        lit = getattr(self, "_literature_context", "")
        if lit:
            checkpoint_context = "## Literature Context\n" + lit + "\n\n" + checkpoint_context

        # Graveyard context stays IDEATION round 1 only
        if phase == ResearchPhase.IDEATION and round_num == 1:
            graveyard = getattr(self, "_graveyard_context", "")
            if graveyard:
                checkpoint_context = checkpoint_context + graveyard + "\n\n"

        formatted = template.format(
            seed_prompt=self._seed_prompt,
            checkpoint_context=checkpoint_context,
            recent_messages=recent_messages,
        )

        # Append search instructions for search-enabled phases
        if phase in _SEARCH_ENABLED_PHASES:
            formatted += _SEARCH_INSTRUCTION

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
