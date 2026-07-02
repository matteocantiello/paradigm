"""Artifact persistence + response/token logging for the orchestration engine.

Pure I/O extracted from ``engine.py`` (C1 refactor): everything here writes logs,
markdown artifacts, or token accounting — no orchestration control flow. The engine
keeps thin ``_log_agent_response``/``_save_*`` delegates so handler call sites are
unchanged.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from paradigm.logging.events import EventType
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


class ArtifactsHandler:
    """Encapsulates artifact/log persistence extracted from OrchestrationEngine."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    def log_agent_response(
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
        agent = self._engine.state.agents.get(agent_id)
        role = agent.skill_profile if agent else ""
        self._engine._display.agent_response(
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
        self._engine._display.agent_step_complete(
            agent_id, role=role, summary=summary, phase=str(phase), tokens=total_tokens
        )

        self._engine._logger.log_agent_message(
            agent_id=agent_id,
            thread_id=self._engine.state.thread_id,
            phase=str(phase),
            message={
                "from": agent_id,
                "type": message_type,
                "content": response.content,
            },
        )
        self._engine._logger.log_api_call(
            agent_id=agent_id,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            thread_id=self._engine.state.thread_id,
        )
        self._engine._db.record_token_usage(
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_id=agent_id,
            thread_id=self._engine.state.thread_id,
        )

    async def save_pdf_for_sandbox(self, url: str) -> None:
        """Save raw PDF bytes to data/shared/papers/ for sandbox access.

        Non-fatal: if the download or save fails, logs and continues
        (the paper is already in ChromaDB for literature context).

        Args:
            url: URL of the PDF to save.
        """
        try:
            pdf_bytes = await self._engine._corpus._arxiv.fetch_pdf_bytes(url)
            if pdf_bytes is None:
                return

            papers_dir = self._engine._config.storage.data_dir / "shared" / "papers"
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
            self._engine._display.pdf_saved(name)
        except Exception as e:
            self._engine._logger.log_error(e, metadata_key="pdf_sandbox_save", url=url)
            self._engine._display.pdf_save_error(e)

    def save_search_log(self, paper_id: str) -> None:
        """Write literature_searches.md to the paper directory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return

        lines = ["# Literature Searches\n"]
        lines.append(f"Thread: {self._engine.state.thread_id}")
        lines.append(f"Total searches: {len(self._engine._literature.search_log)}\n")
        lines.append("---\n")

        for i, entry in enumerate(self._engine._literature.search_log, 1):
            phase = entry["phase"].upper().replace("RESEARCHPHASE.", "")
            agent_id = entry["agent_id"]
            query = entry["query"]
            papers = entry["papers"]

            lines.append(f"## Search {i} — {phase} ({agent_id})")
            lines.append(f"**Query:** {query}\n")

            if papers:
                for j, p in enumerate(papers, 1):
                    authors_str = ", ".join(p["authors"][:2])
                    if len(p["authors"]) > 2:
                        authors_str += " et al."
                    lines.append(
                        f"{j}. **{p['title']}** — {authors_str} ({p['year']}) [{p['arxiv_id']}]"
                    )
            else:
                lines.append("No results found.")

            lines.append("\n---\n")

        paper_dir = papers_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / "literature_searches.md"
        path.write_text("\n".join(lines))

    def save_review_log(self, paper_id: str) -> None:
        """Write reviews.md to the paper directory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return

        lines = ["# Review Report\n"]
        lines.append(f"Thread: {self._engine.state.thread_id}")
        lines.append(f"Paper: {paper_id}\n")
        lines.append("---\n")

        for entry in self._engine._review.review_log:
            entry_type = entry["type"]

            if entry_type == "internal_review":
                iteration = entry.get("iteration", "")
                reviewer = entry["reviewer_id"]
                lines.append(f"## Internal Review — Iteration {iteration} ({reviewer})\n")
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
        usage = self.get_token_summary()
        elapsed = time.monotonic() - self._engine.state.start_time
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

    def save_transcript(self, paper_id: str) -> None:
        """Write transcript.md — a full conversation log organized by phase.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._engine._config.storage.papers_dir
        if papers_dir is None:
            return

        events = self._engine._logger.read_events(thread_id=self._engine.state.thread_id)
        if not events:
            return

        lines = ["# Research Transcript\n"]
        lines.append(f"Thread: {self._engine.state.thread_id}")
        lines.append(f"Paper: {paper_id}")
        lines.append(f"Seed prompt: {self._engine.state.seed_prompt[:200]}\n")
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

    def save_experiment_code(self, paper_id: str) -> None:
        """Write working code (experiments + conceptual figures) to code/ subdirectory.

        Args:
            paper_id: Paper identifier.
        """
        papers_dir = self._engine._config.storage.papers_dir
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

        for exp_name, code in self._engine.state.successful_code:
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

        self._engine._display.code_saved(len(self._engine.state.successful_code))

    def get_token_summary(self) -> dict[str, int]:
        """Get token usage for the current thread.

        Returns:
            Dict with input_tokens, output_tokens, total_tokens.
        """
        return self._engine._db.get_token_usage(thread_id=self._engine.state.thread_id)

    def print_token_summary(self) -> None:
        """Display token usage and elapsed time at end of research cycle."""
        usage = self.get_token_summary()
        input_k = usage["input_tokens"] / 1000
        output_k = usage["output_tokens"] / 1000
        total_k = usage["total_tokens"] / 1000

        elapsed = time.monotonic() - self._engine.state.start_time
        minutes, seconds = divmod(int(elapsed), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"

        self._engine._display.token_summary(total_k, input_k, output_k, time_str)

        self._engine._logger.log(
            EventType.STATE_CHANGE,
            content={
                "event": "cycle_complete",
                "elapsed_seconds": round(elapsed, 1),
                "total_tokens": usage["total_tokens"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
            },
            thread_id=self._engine.state.thread_id,
        )

    def save_auxiliary_files(self, paper_id: str) -> None:
        """Save auxiliary files alongside the paper.

        Args:
            paper_id: Paper identifier.
        """
        if self._engine._literature.search_log:
            self.save_search_log(paper_id)
        # Always save review log (includes token summary even without reviews)
        self.save_review_log(paper_id)
        self.save_transcript(paper_id)
        if self._engine.state.successful_code:
            self.save_experiment_code(paper_id)
        # Save world model snapshot
        if self._engine.state.world_model is not None:
            self._engine._world_model.save_to_thread(paper_id)
            self._engine._world_model.persist_snapshot()
