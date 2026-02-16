"""Review and peer-review handler for the orchestration engine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import click

from paradigm.journal.paper import (
    PaperDraft,
    parse_review_feedback,
    parse_sections_from_markdown,
    strip_agent_scaffolding,
)
from paradigm.journal.publication import reject_paper
from paradigm.journal.review import PeerReview, parse_peer_review, synthesize_decision
from paradigm.orchestrator.constants import (
    _MIN_PAPER_LENGTH,
    _PAPER_CONTEXT_LIMIT,
    _PHASE_INSTRUCTIONS,
    _WRITING_MAX_TOKENS,
)
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


class ReviewHandler:
    """Handles internal review, submission, peer review, and revision phases."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine
        self.review_log: list[dict[str, Any]] = []

    def reset_cycle(self) -> None:
        """Reset review state for a new cycle."""
        self.review_log = []

    async def run_review_phase(self, draft: PaperDraft) -> None:
        """Run the INTERNAL_REVIEW phase: editor reviews, optionally loop back.

        Args:
            draft: PaperDraft to review.
        """
        # Belt-and-suspenders: don't review empty/tiny papers
        current_body = draft.assembled_body or draft.to_markdown()
        if len(current_body) < _MIN_PAPER_LENGTH:
            click.echo(
                f"  [!] Paper body too short for review ({len(current_body)} chars), skipping"
            )
            return

        max_iterations = self._engine._config.orchestrator.max_review_iterations

        for iteration in range(1, max_iterations + 1):
            click.echo(f"  Review iteration {iteration}/{max_iterations}...")
            self._engine._literature.search_count_this_round = 0

            # Editor reviews
            editor = self._engine._find_agent_by_role("editor")
            if editor is None:
                click.echo("    [!] No editor agent found, skipping review")
                return

            template = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["editor_review"]
            prompt = template.format(
                seed_prompt=self._engine._seed_prompt,
                current_draft=current_body[:_PAPER_CONTEXT_LIMIT],  # Truncate for context window
            )

            try:
                response = await editor.generate(prompt)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=editor.agent_id, thread_id=self._engine._thread_id
                )
                click.echo(f"    [!] Editor review failed: {e}")
                return

            self._engine._log_agent_response(
                editor.agent_id, response, ResearchPhase.INTERNAL_REVIEW, "review"
            )
            await self._engine._literature.process_search_requests(
                editor.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            await self._engine._literature.process_literature_actions(
                editor.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            self.review_log.append(
                {
                    "type": "internal_review",
                    "reviewer_id": editor.agent_id,
                    "text": response.content,
                    "iteration": iteration,
                }
            )

            # Parse review feedback
            feedback = parse_review_feedback(response.content)
            click.echo(
                f"    Editor recommendation: {feedback.recommendation} "
                f"({len(feedback.required_changes)} required changes)"
            )

            if feedback.recommendation == "accept":
                # Paper accepted — update status
                thread = self._engine._db.get_thread(self._engine._thread_id)
                if thread and thread.get("current_draft_id"):
                    self._engine._db.update_paper(thread["current_draft_id"], status="reviewed")
                return

            # Revision needed — writer revises
            if iteration < max_iterations:
                click.echo("    Revising...")
                current_body = await self.run_revision(current_body, response.content)
                draft.assembled_body = current_body

                # Update paper in database and on disk
                thread = self._engine._db.get_thread(self._engine._thread_id)
                if thread and thread.get("current_draft_id"):
                    paper_id = thread["current_draft_id"]
                    self._engine._db.update_paper(
                        paper_id,
                        body=current_body,
                        status="revised",
                    )
                    self._engine._writing.save_paper_file(paper_id, current_body)

        # Max iterations reached without editor acceptance — writing failed
        click.echo("  [!] Max review iterations reached without editor acceptance")
        thread = self._engine._db.get_thread(self._engine._thread_id)
        if thread and thread.get("current_draft_id"):
            self._engine._db.update_paper(thread["current_draft_id"], status="writing_failed")
        self._engine._db.update_thread(self._engine._thread_id, status="writing_failed")

    async def run_revision(self, current_body: str, review_text: str) -> str:
        """Writer revises the paper based on review feedback.

        Args:
            current_body: Current paper markdown.
            review_text: Editor's review text.

        Returns:
            Revised paper body.
        """
        writer = self._engine._find_agent_by_role("writer")
        if writer is None:
            return current_body

        checkpoint_context = ""
        if self._engine._checkpoint:
            checkpoint_context = self._engine._checkpoint.to_context_string() + "\n\n"

        template = _PHASE_INSTRUCTIONS[ResearchPhase.INTERNAL_REVIEW]["revision"]
        prompt = template.format(
            seed_prompt=self._engine._seed_prompt,
            checkpoint_context=checkpoint_context,
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
            review_feedback=review_text[:_PAPER_CONTEXT_LIMIT],
        )

        try:
            response = await writer.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
            self._engine._log_agent_response(
                writer.agent_id, response, ResearchPhase.INTERNAL_REVIEW, "revision"
            )
            await self._engine._literature.process_search_requests(
                writer.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            await self._engine._literature.process_literature_actions(
                writer.agent_id, response.content, ResearchPhase.INTERNAL_REVIEW
            )
            return strip_agent_scaffolding(response.content)
        except Exception as e:
            self._engine._logger.log_error(
                e, agent_id=writer.agent_id, thread_id=self._engine._thread_id
            )
            click.echo(f"    [!] Revision failed: {e}")
            return current_body

    async def run_submission_phase(self, draft: PaperDraft) -> bool:
        """Run the SUBMITTED phase: desk review by editor-in-chief.

        Args:
            draft: Paper draft to submit.

        Returns:
            True if paper passes desk review, False if desk-rejected.
        """
        self._engine._phase_manager.transition_to(ResearchPhase.SUBMITTED)
        self._engine._log_phase_transition(ResearchPhase.INTERNAL_REVIEW, ResearchPhase.SUBMITTED)
        self._engine._messages = []
        click.echo("Phase: SUBMITTED (desk review)")

        # Update submitted_at in database
        thread = self._engine._db.get_thread(self._engine._thread_id)
        if thread and thread.get("current_draft_id"):
            self._engine._db.update_paper(
                thread["current_draft_id"],
                status="submitted",
                submitted_at=datetime.now(UTC).isoformat(),
            )

        # Editor desk review
        editor = self._engine._find_agent_by_role("editor")
        if editor is None:
            click.echo("  [!] No editor agent found, auto-accepting for desk review")
            return True

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.SUBMITTED]["desk_review"]
        prompt = template.format(
            seed_prompt=self._engine._seed_prompt,
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
        )

        try:
            response = await editor.generate(prompt)
        except Exception as e:
            self._engine._logger.log_error(
                e, agent_id=editor.agent_id, thread_id=self._engine._thread_id
            )
            click.echo(f"  [!] Desk review failed: {e}, auto-accepting")
            return True

        self._engine._log_agent_response(
            editor.agent_id, response, ResearchPhase.SUBMITTED, "desk_review"
        )

        # Parse desk review decision from ## Decision section only
        sections = parse_sections_from_markdown(response.content)
        decision_text = sections.get("decision", "").strip().lower()

        # Fall back to full-text scan only if no ## Decision section found
        if not decision_text:
            decision_text = response.content.lower()

        is_desk_reject = "desk_reject" in decision_text or "desk reject" in decision_text

        _desk_decision = "desk_reject" if is_desk_reject else "send_to_review"
        self.review_log.append(
            {
                "type": "desk_review",
                "reviewer_id": editor.agent_id,
                "text": response.content,
                "decision": _desk_decision,
            }
        )

        if is_desk_reject:
            click.echo("  Desk REJECTED")
            # Desk rejection — create a minimal review for graveyard
            desk_review = PeerReview(
                reviewer_id=editor.agent_id,
                summary="Desk rejection by editor-in-chief.",
                weaknesses=["Did not pass desk review"],
                recommendation="reject",
            )
            thread = self._engine._db.get_thread(self._engine._thread_id)
            if thread and thread.get("current_draft_id"):
                reject_paper(
                    thread["current_draft_id"],
                    self._engine._db,
                    [desk_review],
                    self._engine._logger,
                )
            self._engine._phase_manager.transition_to(ResearchPhase.REJECTED)
            self._engine._log_phase_transition(ResearchPhase.SUBMITTED, ResearchPhase.REJECTED)
            return False

        click.echo("  Desk review passed — sending to peer review")
        return True

    async def run_peer_review_phase(self, draft: PaperDraft) -> tuple[str, list[PeerReview]]:
        """Run the PEER_REVIEW phase: create reviewers, collect reviews, synthesize decision.

        Args:
            draft: Paper draft to review.

        Returns:
            Tuple of (decision string, list of PeerReview objects).
        """
        self._engine._phase_manager.transition_to(ResearchPhase.PEER_REVIEW)
        self._engine._log_phase_transition(ResearchPhase.SUBMITTED, ResearchPhase.PEER_REVIEW)
        self._engine._messages = []
        num_reviewers = self._engine._config.orchestrator.num_reviewers
        click.echo(f"Phase: PEER_REVIEW ({num_reviewers} reviewers)")

        # Create fresh reviewer agents (not reusing team agents)
        reviewer_roles = ["reviewer"] * num_reviewers
        reviewer_agents = self._engine._factory.create_team(reviewer_roles, skill_mode="default")

        # Give each reviewer a unique ID to avoid collision with team IDs
        for i, agent in enumerate(reviewer_agents):
            agent.agent_id = f"peer-reviewer-{i}"

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.PEER_REVIEW]["review"]

        self._engine._literature.search_count_this_round = 0
        reviews: list[PeerReview] = []
        for agent in reviewer_agents:
            prompt = template.format(
                seed_prompt=self._engine._seed_prompt,
                current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
            )

            try:
                response = await agent.generate(prompt)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent.agent_id, thread_id=self._engine._thread_id
                )
                click.echo(f"    [!] {agent.agent_id} review failed: {e}")
                continue

            self._engine._log_agent_response(
                agent.agent_id, response, ResearchPhase.PEER_REVIEW, "review"
            )
            await self._engine._literature.process_search_requests(
                agent.agent_id, response.content, ResearchPhase.PEER_REVIEW
            )
            await self._engine._literature.process_literature_actions(
                agent.agent_id, response.content, ResearchPhase.PEER_REVIEW
            )

            review = parse_peer_review(agent.agent_id, response.content)
            reviews.append(review)
            self.review_log.append(
                {
                    "type": "peer_review",
                    "reviewer_id": agent.agent_id,
                    "text": response.content,
                    "review": review,
                }
            )
            avg_score = sum(review.scores.values()) / len(review.scores) if review.scores else 0
            click.echo(
                f"    {agent.agent_id}: {review.recommendation} (avg score: {avg_score:.1f})"
            )

        # Synthesize decision
        decision = synthesize_decision(reviews)
        self.review_log.append(
            {
                "type": "decision",
                "decision": decision,
            }
        )
        click.echo(f"  Decision: {decision}")

        return decision, reviews

    async def run_revision_phase(self, draft: PaperDraft, reviews: list[PeerReview]) -> PaperDraft:
        """Run the REVISION phase: writer revises based on peer feedback.

        Args:
            draft: Current paper draft.
            reviews: Peer reviews with feedback.

        Returns:
            Updated PaperDraft with revised body.
        """
        self._engine._phase_manager.transition_to(ResearchPhase.REVISION)
        self._engine._log_phase_transition(ResearchPhase.PEER_REVIEW, ResearchPhase.REVISION)
        self._engine._messages = []
        self._engine._literature.search_count_this_round = 0
        click.echo("Phase: REVISION")

        writer = self._engine._find_agent_by_role("writer")
        if writer is None:
            click.echo("  [!] No writer agent found, skipping revision")
            # Re-submit without changes
            self._engine._phase_manager.transition_to(ResearchPhase.SUBMITTED)
            self._engine._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)
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
        if self._engine._checkpoint:
            checkpoint_context = self._engine._checkpoint.to_context_string() + "\n\n"

        current_body = draft.assembled_body or draft.to_markdown()
        template = _PHASE_INSTRUCTIONS[ResearchPhase.REVISION]["revise"]
        prompt = template.format(
            seed_prompt=self._engine._seed_prompt,
            checkpoint_context=checkpoint_context,
            current_draft=current_body[:_PAPER_CONTEXT_LIMIT],
            review_feedback=review_feedback[:_PAPER_CONTEXT_LIMIT],
        )

        try:
            response = await writer.generate(prompt, max_tokens=_WRITING_MAX_TOKENS)
        except Exception as e:
            self._engine._logger.log_error(
                e, agent_id=writer.agent_id, thread_id=self._engine._thread_id
            )
            click.echo(f"  [!] Revision failed: {e}")
            # Transition back to SUBMITTED so peer review can re-run
            self._engine._phase_manager.transition_to(ResearchPhase.SUBMITTED)
            self._engine._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)
            return draft

        self._engine._log_agent_response(
            writer.agent_id, response, ResearchPhase.REVISION, "revision"
        )
        await self._engine._literature.process_search_requests(
            writer.agent_id, response.content, ResearchPhase.REVISION
        )
        await self._engine._literature.process_literature_actions(
            writer.agent_id, response.content, ResearchPhase.REVISION
        )
        self.review_log.append(
            {
                "type": "revision",
                "reviewer_id": writer.agent_id,
            }
        )

        # Update draft (strip any agent meta-text before saving)
        revised_body = strip_agent_scaffolding(response.content)
        draft.assembled_body = revised_body

        # Update paper in database and on disk
        thread = self._engine._db.get_thread(self._engine._thread_id)
        if thread and thread.get("current_draft_id"):
            paper_id = thread["current_draft_id"]
            self._engine._db.update_paper(paper_id, body=revised_body, status="revised")
            self._engine._writing.save_paper_file(paper_id, revised_body)

        click.echo("  Revision complete")

        # Transition back to SUBMITTED for re-review
        self._engine._phase_manager.transition_to(ResearchPhase.SUBMITTED)
        self._engine._log_phase_transition(ResearchPhase.REVISION, ResearchPhase.SUBMITTED)

        return draft
