"""Literature search handler — extracted from OrchestrationEngine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import click

from paradigm.literature.prompt_utils import (
    format_cited_by_results,
    format_follow_results,
    format_read_result,
    format_search_results,
    parse_cited_by_requests,
    parse_follow_requests,
    parse_read_requests,
    parse_search_requests,
)
from paradigm.logging.events import EventType
from paradigm.orchestrator.constants import (
    _LITERATURE_CONTEXT_LIMIT,
    _SEARCH_ENABLED_PHASES,
    _is_duplicate_query,
    _normalize_query_keywords,
)
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine


class LiteratureHandler:
    """Handles literature search, follow, cited-by, and read actions.

    Owns all per-round and per-cycle literature counters.  Delegates to the
    engine for configuration, corpus access, logging, and thread ID.
    """

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

        # Per-round counters (reset between rounds)
        self.search_count_this_round: int = 0
        self.follow_count_this_round: int = 0
        self.cited_by_count_this_round: int = 0
        self.read_count_this_round: int = 0
        self.agent_search_count: dict[str, int] = {}

        # Per-cycle state (reset between research cycles)
        self.searched_queries: set[str] = set()
        self.searched_query_keywords: list[frozenset[str]] = []
        self.seen_paper_ids: set[str] = set()
        self.total_stale_keyword_searches: int = 0
        self.search_log: list[dict[str, Any]] = []
        self.literature_context: str = ""
        # Compact index of all discovered papers (not subject to context truncation)
        self.discovered_papers: list[tuple[str, str, str]] = []  # (arxiv_id, title, first_author)
        self._discovered_ids: set[str] = set()  # Fast lookup to avoid duplicates

    # ------------------------------------------------------------------
    # Reset helpers
    # ------------------------------------------------------------------

    def reset_round_counters(self) -> None:
        """Reset per-round state at the start of each round."""
        self.search_count_this_round = 0
        self.follow_count_this_round = 0
        self.cited_by_count_this_round = 0
        self.read_count_this_round = 0
        self.agent_search_count = {}

    def reset_cycle(self) -> None:
        """Reset all state for a new research cycle."""
        self.search_count_this_round = 0
        self.follow_count_this_round = 0
        self.cited_by_count_this_round = 0
        self.read_count_this_round = 0
        self.agent_search_count = {}
        self.searched_queries = set()
        self.searched_query_keywords = []
        self.seen_paper_ids = set()
        self.total_stale_keyword_searches = 0
        self.search_log = []
        self.literature_context = ""
        self.discovered_papers = []
        self._discovered_ids = set()

    # ------------------------------------------------------------------
    # Paper index (compact reference list for agent prompts)
    # ------------------------------------------------------------------

    def _track_paper(self, arxiv_id: str, title: str, first_author: str) -> None:
        """Record a discovered paper in the compact index (idempotent)."""
        if not arxiv_id or arxiv_id in self._discovered_ids:
            return
        self._discovered_ids.add(arxiv_id)
        self.discovered_papers.append((arxiv_id, title, first_author))

    def build_paper_index(self) -> str:
        """Render a compact reference list of all discovered papers.

        This index is NOT subject to the literature context truncation limit,
        so agents always have access to paper IDs for graph traversal.

        Returns:
            Formatted markdown string, or empty string if no papers discovered.
        """
        if not self.discovered_papers:
            return ""
        lines = [
            "## Discovered Papers (use these IDs for [FOLLOW:] and [CITED_BY:])",
        ]
        for arxiv_id, title, first_author in self.discovered_papers:
            # Truncate long titles to keep the index compact
            short_title = title[:80] + "..." if len(title) > 80 else title
            lines.append(f"- [{arxiv_id}] {first_author}: {short_title}")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Search requests ([SEARCH: ...])
    # ------------------------------------------------------------------

    async def process_search_requests(
        self, agent_id: str, response_text: str, phase: ResearchPhase
    ) -> None:
        """Parse [SEARCH: query] markers from an agent's response and execute searches.

        Results are appended to self.literature_context for all subsequent agents.
        Respects per-round budget, per-agent cap, and cross-round stall tracking.

        Args:
            agent_id: ID of the agent whose response contains search requests.
            response_text: The agent's response text.
            phase: Current research phase.
        """
        if phase not in _SEARCH_ENABLED_PHASES:
            return

        max_searches = self._engine._config.orchestrator.max_searches_per_round

        # Cross-round stall: after 5 cumulative stale keyword searches,
        # hard-cap keyword budget to 1 per round for the rest of the phase
        if self.total_stale_keyword_searches >= 5:
            max_searches = min(max_searches, 1)

        # Per-agent cap: no single agent monopolizes the round's budget
        per_agent_cap = max(2, self._engine._config.orchestrator.max_searches_per_round * 2 // 5)

        queries = parse_search_requests(response_text)
        if not queries:
            return

        consecutive_stale = 0  # Track consecutive 0-new results within this agent's batch

        for query in queries:
            # Global exact dedup: skip queries already executed in this cycle
            query_key = query.lower().strip()
            if query_key in self.searched_queries:
                continue

            # Fuzzy dedup: skip queries that are near-duplicates of previous ones
            new_kw = _normalize_query_keywords(query)
            if _is_duplicate_query(new_kw, self.searched_query_keywords):
                click.echo(f"    [~] Skipping similar query: {query[:60]}")
                continue

            # Check per-round budget
            if self.search_count_this_round >= max_searches:
                click.echo(
                    f"    [!] Search budget exhausted ({max_searches}/round), "
                    f"skipping: {query[:60]}"
                )
                break

            # Check per-agent cap
            agent_count = self.agent_search_count.get(agent_id, 0)
            if agent_count >= per_agent_cap:
                click.echo(
                    f"    [!] {agent_id}: per-agent cap reached ({per_agent_cap}), "
                    f"skipping: {query[:60]}"
                )
                break

            try:
                papers = await self._engine._corpus.search(query, max_results=10)
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent_id, thread_id=self._engine._thread_id
                )
                click.echo(f"    [!] Search failed for '{query[:60]}': {e}")
                continue

            self.searched_queries.add(query_key)
            if new_kw:
                self.searched_query_keywords.append(new_kw)
            # Log all raw results (before dedup filtering)
            self.search_log.append(
                {
                    "query": query,
                    "agent_id": agent_id,
                    "phase": str(phase),
                    "papers": [
                        {
                            "arxiv_id": p.arxiv_id,
                            "title": p.title,
                            "authors": p.authors[:3],
                            "year": p.published.strftime("%Y"),
                        }
                        for p in papers
                    ],
                }
            )

            # Filter out papers already shown to agents in previous searches
            new_papers = [p for p in papers if p.arxiv_id not in self.seen_paper_ids]
            for p in new_papers:
                self.seen_paper_ids.add(p.arxiv_id)
                first_author = p.authors[0] if p.authors else "Unknown"
                self._track_paper(p.arxiv_id, p.title, first_author)

            if new_papers:
                consecutive_stale = 0
                formatted = format_search_results(query, new_papers)
                lit = self.literature_context
                self.literature_context = lit + "\n" + formatted if lit else formatted

                # Trim literature context if it exceeds the limit (keep most recent)
                if len(self.literature_context) > _LITERATURE_CONTEXT_LIMIT:
                    self.literature_context = self.literature_context[-_LITERATURE_CONTEXT_LIMIT:]
            else:
                consecutive_stale += 1
                self.total_stale_keyword_searches += 1

            self.search_count_this_round += 1
            self.agent_search_count[agent_id] = self.agent_search_count.get(agent_id, 0) + 1

            click.echo(
                f"    {agent_id} searched: '{query[:60]}' \u2192 "
                f"{len(papers)} results ({len(new_papers)} new)"
            )

            self._engine._logger.log(
                EventType.LITERATURE_SEARCH,
                content={
                    "query": query,
                    "agent_id": agent_id,
                    "results": len(papers),
                    "phase": str(phase),
                    "search_num": self.search_count_this_round,
                },
                thread_id=self._engine._thread_id,
                phase=str(phase),
            )

            # Stall hint: always inject when keyword search returns 0 new papers
            if not new_papers:
                hint = self._build_stall_hint()
                lit = self.literature_context
                self.literature_context = lit + hint if lit else hint

            # Early termination: 2 consecutive stale searches from this agent
            if consecutive_stale >= 2:
                click.echo(f"    [!] {agent_id}: 2 consecutive stale searches, stopping keywords")
                examples = self._build_follow_examples(3)
                stall_warning = (
                    "\n\n> **Warning:** Keyword searches are exhausted for this topic. "
                    "You MUST use [FOLLOW: arxiv_id] or [CITED_BY: arxiv_id] to discover "
                    "new papers. Do NOT issue more [SEARCH:] requests.\n"
                )
                if examples:
                    stall_warning += examples
                lit = self.literature_context
                self.literature_context = lit + stall_warning if lit else stall_warning
                break

        # Cross-round exhaustion warning: inject persistent warning
        if self.total_stale_keyword_searches >= 5:
            examples = self._build_follow_examples(3)
            exhaustion_warning = (
                "\n\n> \u26a0 Keyword searches are exhausted for this topic. You MUST use "
                "[FOLLOW: arxiv_id] or [CITED_BY: arxiv_id] to discover new papers. "
                "Do NOT issue [SEARCH:] requests.\n"
            )
            if examples:
                exhaustion_warning += examples
            lit = self.literature_context
            if "\u26a0 Keyword searches are exhausted" not in lit:
                self.literature_context = lit + exhaustion_warning if lit else exhaustion_warning

    # ------------------------------------------------------------------
    # Literature actions ([FOLLOW:], [CITED_BY:], [READ:])
    # ------------------------------------------------------------------

    async def process_literature_actions(
        self, agent_id: str, response_text: str, phase: ResearchPhase
    ) -> None:
        """Parse [FOLLOW:], [CITED_BY:], [READ:] markers and execute them.

        Results are appended to self.literature_context for all subsequent agents.
        Respects per-action-type budgets from config.

        Args:
            agent_id: ID of the agent whose response contains action markers.
            response_text: The agent's response text.
            phase: Current research phase.
        """
        if phase not in _SEARCH_ENABLED_PHASES:
            return

        lit_config = self._engine._config.literature

        # Process [FOLLOW: arxiv_id] requests
        for arxiv_id in parse_follow_requests(response_text):
            if self.follow_count_this_round >= lit_config.follow_budget_per_round:
                click.echo(f"    [!] Follow budget exhausted, skipping: {arxiv_id}")
                break

            try:
                papers = await self._engine._corpus.get_references(
                    arxiv_id, max_results=lit_config.max_reference_results
                )
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent_id, thread_id=self._engine._thread_id
                )
                click.echo(f"    [!] Follow failed for '{arxiv_id}': {e}")
                continue

            # Track discovered paper IDs
            for p in papers:
                if p.arxiv_id:
                    self.seen_paper_ids.add(p.arxiv_id)
                    first_author = p.authors[0] if p.authors else "Unknown"
                    self._track_paper(p.arxiv_id, p.title, first_author)

            formatted = format_follow_results(
                arxiv_id, papers, max_papers=lit_config.max_reference_results
            )
            lit = self.literature_context
            self.literature_context = lit + "\n" + formatted if lit else formatted

            # Trim if needed
            if len(self.literature_context) > _LITERATURE_CONTEXT_LIMIT:
                self.literature_context = self.literature_context[-_LITERATURE_CONTEXT_LIMIT:]

            self.follow_count_this_round += 1
            self.search_log.append(
                {
                    "query": f"[FOLLOW: {arxiv_id}]",
                    "agent_id": agent_id,
                    "phase": str(phase),
                    "papers": [
                        {
                            "arxiv_id": p.arxiv_id or p.paper_id,
                            "title": p.title,
                            "authors": p.authors[:3],
                            "year": str(p.year or "?"),
                        }
                        for p in papers
                    ],
                }
            )

            click.echo(
                f"    {agent_id} followed refs of {arxiv_id} \u2192 {len(papers)} references"
            )

            self._engine._logger.log(
                EventType.LITERATURE_FOLLOW,
                content={
                    "arxiv_id": arxiv_id,
                    "agent_id": agent_id,
                    "references_found": len(papers),
                    "phase": str(phase),
                },
                thread_id=self._engine._thread_id,
                phase=str(phase),
            )

        # Process [CITED_BY: arxiv_id] requests
        for arxiv_id in parse_cited_by_requests(response_text):
            if self.cited_by_count_this_round >= lit_config.cited_by_budget_per_round:
                click.echo(f"    [!] Cited-by budget exhausted, skipping: {arxiv_id}")
                break

            try:
                papers = await self._engine._corpus.get_citations(
                    arxiv_id, max_results=lit_config.max_citation_results
                )
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent_id, thread_id=self._engine._thread_id
                )
                click.echo(f"    [!] Cited-by failed for '{arxiv_id}': {e}")
                continue

            # Track discovered paper IDs
            for p in papers:
                if p.arxiv_id:
                    self.seen_paper_ids.add(p.arxiv_id)
                    first_author = p.authors[0] if p.authors else "Unknown"
                    self._track_paper(p.arxiv_id, p.title, first_author)

            formatted = format_cited_by_results(
                arxiv_id, papers, max_papers=lit_config.max_citation_results
            )
            lit = self.literature_context
            self.literature_context = lit + "\n" + formatted if lit else formatted

            if len(self.literature_context) > _LITERATURE_CONTEXT_LIMIT:
                self.literature_context = self.literature_context[-_LITERATURE_CONTEXT_LIMIT:]

            self.cited_by_count_this_round += 1
            self.search_log.append(
                {
                    "query": f"[CITED_BY: {arxiv_id}]",
                    "agent_id": agent_id,
                    "phase": str(phase),
                    "papers": [
                        {
                            "arxiv_id": p.arxiv_id or p.paper_id,
                            "title": p.title,
                            "authors": p.authors[:3],
                            "year": str(p.year or "?"),
                        }
                        for p in papers
                    ],
                }
            )

            click.echo(f"    {agent_id} cited-by {arxiv_id} \u2192 {len(papers)} citations")

            self._engine._logger.log(
                EventType.LITERATURE_CITED_BY,
                content={
                    "arxiv_id": arxiv_id,
                    "agent_id": agent_id,
                    "citations_found": len(papers),
                    "phase": str(phase),
                },
                thread_id=self._engine._thread_id,
                phase=str(phase),
            )

        # Process [READ: arxiv_id] requests
        for arxiv_id in parse_read_requests(response_text):
            if self.read_count_this_round >= lit_config.read_budget_per_round:
                click.echo(f"    [!] Read budget exhausted, skipping: {arxiv_id}")
                break

            try:
                result = await self._engine._corpus.read_paper(
                    arxiv_id, max_chars=lit_config.max_read_chars
                )
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent_id, thread_id=self._engine._thread_id
                )
                click.echo(f"    [!] Read failed for '{arxiv_id}': {e}")
                continue

            if result is None:
                click.echo(f"    [!] Could not read paper {arxiv_id}")
                continue

            title, extracted_text = result
            formatted = format_read_result(arxiv_id, title, extracted_text)
            lit = self.literature_context
            self.literature_context = lit + "\n" + formatted if lit else formatted

            if len(self.literature_context) > _LITERATURE_CONTEXT_LIMIT:
                self.literature_context = self.literature_context[-_LITERATURE_CONTEXT_LIMIT:]

            self.read_count_this_round += 1

            click.echo(
                f"    {agent_id} read {arxiv_id}: {title[:60]} ({len(extracted_text)} chars)"
            )

            self._engine._logger.log(
                EventType.LITERATURE_READ,
                content={
                    "arxiv_id": arxiv_id,
                    "agent_id": agent_id,
                    "title": title,
                    "chars_extracted": len(extracted_text),
                    "phase": str(phase),
                },
                thread_id=self._engine._thread_id,
                phase=str(phase),
            )

    # ------------------------------------------------------------------
    # Stall hint helpers
    # ------------------------------------------------------------------

    def _build_follow_examples(self, n: int = 3) -> str:
        """Build concrete [FOLLOW:] example commands from discovered papers.

        Args:
            n: Number of examples to include.

        Returns:
            Formatted string with example commands, or empty string if no papers.
        """
        if not self.discovered_papers:
            return ""
        examples = self.discovered_papers[:n]
        lines = ["\n> **Try these commands:**"]
        for arxiv_id, title, _ in examples:
            short = title[:60] + "..." if len(title) > 60 else title
            lines.append(f'>   [FOLLOW: {arxiv_id}]  — refs of "{short}"')
        lines.append("")
        return "\n".join(lines)

    def _build_stall_hint(self) -> str:
        """Build a stall hint with concrete paper IDs when available.

        Returns:
            Formatted hint string.
        """
        hint = (
            "\n\n> **Hint:** Your keyword searches are returning no new results. "
            "Use [FOLLOW: arxiv_id] to explore references of papers "
            "you've already found, or [CITED_BY: arxiv_id] to find recent work "
            "building on foundational papers.\n"
        )
        examples = self._build_follow_examples(3)
        if examples:
            hint += examples
        return hint
