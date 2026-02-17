"""Writing-phase handler for the orchestration engine."""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from paradigm.journal.paper import (
    SECTION_ASSIGNMENTS,
    PaperDraft,
    PaperSection,
    SectionDraft,
    parse_sections_from_markdown,
    sanitize_unicode_math,
    strip_agent_scaffolding,
)
from paradigm.orchestrator.constants import (
    _MIN_PAPER_LENGTH,
    _PHASE_INSTRUCTIONS,
    _WRITING_MAX_TOKENS,
)
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


class WritingHandler:
    """Encapsulates writing-phase logic extracted from OrchestrationEngine."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    async def run_writing_phase(self) -> PaperDraft | None:
        """Run the WRITING phase: section drafting, assembly, optional refinement.

        Returns:
            PaperDraft with assembled paper, or None if writing failed
            (e.g. all agents errored and the paper is empty/too short).
        """
        draft = PaperDraft()

        # Round 1: Section Drafting — each agent drafts their assigned sections
        self._engine._display.writing_section_drafting()
        await self.run_section_drafting(draft)

        # Round 2: Assembly — writer combines all sections
        self._engine._display.writing_assembly()
        assembled_body = await self.run_assembly(draft)

        # Post-process: ensure figure image tags are embedded inline
        assembled_body = self.embed_figures_inline(assembled_body)
        draft.assembled_body = assembled_body

        # Citation grounding (non-fatal on failure)
        if self._engine._config.citation.enable_citation_grounding:
            try:
                draft = await self._engine._citation_handler.run_citation_grounding(draft)
            except Exception as e:
                self._engine._logger.log_error(e, thread_id=self._engine._thread_id)
                self._engine._display.citation_grounding_error(e)

        # Validate paper length — if all agents failed, the draft is empty
        if len(draft.assembled_body) < _MIN_PAPER_LENGTH:
            self._engine._display.paper_too_short(len(draft.assembled_body), _MIN_PAPER_LENGTH)
            self._engine._logger.log_error(
                ValueError(
                    f"Writing phase produced insufficient content "
                    f"({len(draft.assembled_body)} chars < {_MIN_PAPER_LENGTH})"
                ),
                thread_id=self._engine._thread_id,
            )
            self._engine._db.update_thread(self._engine._thread_id, status="writing_failed")
            return None

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

        authors = list(self._engine._agents.keys())
        self._engine._db.create_paper(
            paper_id=paper_id,
            title=draft.title or self._engine._seed_prompt[:200],
            abstract=abstract,
            authors=authors,
            body=draft.assembled_body,
            status="draft",
        )
        self._engine._db.update_thread(self._engine._thread_id, current_draft_id=paper_id)

        # Write markdown file to papers directory
        self.save_paper_file(paper_id, draft.assembled_body)

        paper_path = ""
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is not None:
            paper_path = str(papers_dir / paper_id / f"{paper_id}.md")
        self._engine._display.paper_saved(paper_id, paper_path=paper_path)
        return draft

    async def run_section_drafting(self, draft: PaperDraft) -> None:
        """Round 1 of writing: each agent drafts their assigned sections.

        Args:
            draft: PaperDraft to populate with section drafts.
        """
        self._engine._literature.search_count_this_round = 0
        checkpoint_context = ""
        if self._engine._checkpoint:
            checkpoint_context = self._engine._checkpoint.to_context_string() + "\n\n"

        template = _PHASE_INSTRUCTIONS[ResearchPhase.WRITING]["section_drafting"]

        for agent_id, agent in self._engine._agents.items():
            role = agent.skill_profile
            assigned = SECTION_ASSIGNMENTS.get(role)
            if not assigned:
                continue  # Roles without section assignments skip this round

            section_list = ", ".join(s.value.title() for s in assigned)
            prompt = template.format(
                seed_prompt=self._engine._seed_prompt,
                checkpoint_context=checkpoint_context,
                assigned_sections=section_list,
            )

            # Inject execution context for RESULTS and METHODS sections
            if self._engine._execution_context and any(
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
                    f"EXECUTION phase. You MUST thoroughly discuss these results "
                    f"in your section. Include specific numbers, statistical "
                    f"measures, and quantitative comparisons. Do NOT merely "
                    f"summarize — analyze and interpret the data:\n\n"
                    f"{self._engine._execution_context}"
                )

            # Inject execution caveats for all sections that touch results
            if self._engine._execution_caveats and any(
                s in (PaperSection.RESULTS, PaperSection.METHODS, PaperSection.DISCUSSION)
                for s in assigned
            ):
                prompt += (
                    "\n\n## Execution Caveats\n"
                    "The following limitations were identified during the EXECUTION phase. "
                    "You MUST acknowledge these in the paper (e.g., in Methods, Results, "
                    "or a Limitations section):\n"
                    + "\n".join(f"- {c}" for c in self._engine._execution_caveats)
                )

            try:
                response = await agent.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent_id, thread_id=self._engine._thread_id
                )
                self._engine._display.agent_error(agent_id, e)
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

            self._engine._log_agent_response(
                agent_id, response, ResearchPhase.WRITING, "section_draft"
            )
            await self._engine._literature.process_search_requests(
                agent_id, response.content, ResearchPhase.WRITING
            )
            await self._engine._literature.process_literature_actions(
                agent_id, response.content, ResearchPhase.WRITING
            )

    async def run_assembly(self, draft: PaperDraft) -> str:
        """Round 2 of writing: writer assembles all sections into a coherent paper.

        Args:
            draft: PaperDraft with section drafts.

        Returns:
            Assembled paper body as markdown.
        """
        # Find writer agent
        writer_agent = self._engine._find_agent_by_role("writer")
        if writer_agent is None:
            # Fallback: render from sections directly
            self._engine._display.writing_no_writer()
            return draft.to_markdown()

        checkpoint_context = ""
        if self._engine._checkpoint:
            checkpoint_context = self._engine._checkpoint.to_context_string() + "\n\n"

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
            seed_prompt=self._engine._seed_prompt,
            checkpoint_context=checkpoint_context,
            section_drafts=section_drafts_text,
        )

        # Add figure references if experiments produced output files
        if self._engine._execution_figures:
            fig_lines = ["\n\n## Figures from Computational Experiments"]
            fig_lines.append("Include these figures in the paper using the markdown syntax shown:")
            for i, (exp_name, fpath) in enumerate(self._engine._execution_figures, 1):
                dest_name = self.figure_dest_name(exp_name, fpath)
                fig_lines.append(f"- Figure {i} ({exp_name}): `![Figure {i}](figures/{dest_name})`")
            prompt += "\n".join(fig_lines)

        try:
            response = await writer_agent.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            self._engine._log_agent_response(
                writer_agent.agent_id, response, ResearchPhase.WRITING, "assembly"
            )
            return strip_agent_scaffolding(response.content)
        except Exception as e:
            self._engine._logger.log_error(
                e, agent_id=writer_agent.agent_id, thread_id=self._engine._thread_id
            )
            self._engine._display.writing_assembly_error(e)
            return draft.to_markdown()

    def embed_figures_inline(self, body: str) -> str:
        """Post-process paper markdown to embed figure image tags inline.

        The writer agent is asked to include ``![Figure N](figures/...)``
        tags, but may omit them or use the wrong filename.  This method
        scans the body for textual "Figure N" references and, when no
        corresponding image tag already exists nearby, inserts one after
        the paragraph that first references it.

        Args:
            body: Paper markdown body.

        Returns:
            Body with ``![Figure N](figures/...)`` tags embedded.
        """
        if not self._engine._execution_figures:
            return body

        # Build ordered mapping: figure number -> destination filename
        fig_map: dict[int, str] = {}
        for i, (exp_name, fpath) in enumerate(self._engine._execution_figures, 1):
            fig_map[i] = self.figure_dest_name(exp_name, fpath)

        # Regex to detect existing image tags like ![Figure 1](figures/...)
        existing_img_re = re.compile(r"!\[(?:Figure|Fig\.?)\s*(\d+)[^\]]*\]\(figures/[^)]+\)")

        # Which figures already have image tags?
        already_embedded: set[int] = set()
        for m in existing_img_re.finditer(body):
            already_embedded.add(int(m.group(1)))

        # For each figure not yet embedded, find its first textual reference
        # and insert the image tag after that paragraph.
        for fig_num, dest_name in fig_map.items():
            if fig_num in already_embedded:
                continue

            # Pattern to match "Figure N" or "Fig. N" (not inside an image tag)
            ref_pattern = re.compile(rf"(?<!!)(?<!\[)\b(?:Figure|Fig\.?)\s*{fig_num}\b")

            match = ref_pattern.search(body)
            if match is None:
                # No textual reference — append at end of body
                body = body.rstrip() + f"\n\n![Figure {fig_num}](figures/{dest_name})\n"
                continue

            # Find the end of the paragraph containing the reference
            pos = match.end()
            # Look for the next blank line (paragraph boundary)
            next_blank = body.find("\n\n", pos)
            if next_blank == -1:
                # Reference is in the last paragraph
                body = body.rstrip() + f"\n\n![Figure {fig_num}](figures/{dest_name})\n"
            else:
                # Insert after the blank line
                insert_pos = next_blank + 2  # after the \n\n
                tag = f"![Figure {fig_num}](figures/{dest_name})\n\n"
                body = body[:insert_pos] + tag + body[insert_pos:]

        return body

    def save_paper_file(self, paper_id: str, body: str) -> None:
        """Write paper markdown to the papers directory.

        Always uses subdirectory layout: papers/paper_id/paper_id.md
        Figures (if any) go into papers/paper_id/figures/

        Args:
            paper_id: Paper identifier (used as filename).
            body: Paper markdown content.
        """
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return

        paper_dir = papers_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / f"{paper_id}.md"
        # Ensure figure image tags are embedded before writing
        body = self.embed_figures_inline(body)
        # Convert any remaining Unicode math to LaTeX
        body = sanitize_unicode_math(body)
        path.write_text(body)
        if self._engine._execution_figures:
            self.copy_figures_to_paper_dir(paper_id)

    def copy_figures_to_paper_dir(self, paper_id: str) -> None:
        """Copy execution output figures to the paper's figures/ directory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return

        figures_dir = papers_dir / paper_id / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)

        for exp_name, src_path in self._engine._execution_figures:
            if not src_path.exists():
                continue
            dest_name = self.figure_dest_name(exp_name, src_path)
            dest_path = figures_dir / dest_name
            shutil.copy2(src_path, dest_path)
            self._engine._display.figure_copied(dest_path.name)

    @staticmethod
    def figure_dest_name(exp_name: str, src_path: Path) -> str:
        """Compute the destination filename for a figure.

        This must match the naming logic in ``copy_figures_to_paper_dir``
        so that the markdown image tags point to the correct files.

        Args:
            exp_name: Experiment name.
            src_path: Original source path of the figure.

        Returns:
            Sanitised destination filename.
        """
        safe_name = re.sub(r"[^\w\-.]", "_", exp_name)
        return f"{safe_name}_{src_path.name}"
