"""Literature search handler — extracted from OrchestrationEngine."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any

import httpx

from paradigm.domains.base import arxiv_paper_to_source_result
from paradigm.literature.bibliography import extract_arxiv_id_from_url
from paradigm.literature.citation_chains import follow_citation_chain
from paradigm.literature.perplexity import PerplexityClient
from paradigm.literature.prompt_utils import (
    format_chain_results,
    format_cited_by_results,
    format_follow_results,
    format_read_result,
    format_search_results,
    parse_chain_requests,
    parse_cited_by_requests,
    parse_data_requests,
    parse_follow_requests,
    parse_read_requests,
    parse_search_requests,
)
from paradigm.literature.resources import ResourceType, classify_resource, resolve_resource
from paradigm.logging.events import EventType
from paradigm.orchestrator.constants import (
    _CONSECUTIVE_STALE_LIMIT,
    _DATA_REQUESTS_PER_ROUND,
    _FOLLOW_EXAMPLES_COUNT,
    _LITERATURE_CONTEXT_LIMIT,
    _PER_AGENT_CAP_DENOMINATOR,
    _PER_AGENT_CAP_MIN,
    _PER_AGENT_CAP_NUMERATOR,
    _SEARCH_ENABLED_PHASES,
    _STALE_SEARCH_THRESHOLD,
    _TITLE_TRUNCATION_INDEX,
    _TITLE_TRUNCATION_SHORT,
    _extract_topic_keywords,
    _filter_relevant_papers,
    _is_duplicate_query,
    _normalize_query_keywords,
)
from paradigm.orchestrator.phases import ResearchPhase

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine

_logger = logging.getLogger(__name__)

# An arXiv-id lookup disguised as a keyword query (new-style 2509.12411[v2] or
# old-style astro-ph/0601001), optionally `id:`/`arxiv:` prefixed. The whole query
# must be the id — normal keyword queries never match (anchored).
_ARXIV_ID_QUERY_RE = re.compile(
    r"^(?:id:\s*|arxiv:\s*)?"
    r"(?P<id>\d{4}\.\d{4,5}(?:v\d+)?|[a-z][a-z\-]+(?:\.[A-Za-z]{2})?/\d{7}(?:v\d+)?)$",
    re.IGNORECASE,
)


def _is_transient_source_error(error: BaseException) -> bool:
    """True if ``error`` is an expected, recoverable external-source failure.

    Rate-limits (HTTP 429), timeouts, and dropped connections are routine when
    hitting public APIs (arXiv, Semantic Scholar) — the research proceeds on
    cached corpus + other sources, so they warrant a calm notice rather than a
    red error. Anything else (e.g. a code regression) is treated as a genuine
    fault and surfaced loudly.
    """
    if isinstance(error, httpx.HTTPError):
        # Covers timeouts, connect/protocol errors, and HTTPStatusError (429/5xx/4xx):
        # all of these mean "this lookup didn't work", not a platform bug.
        return True
    # Some clients (e.g. Semantic Scholar) raise a bare Exception("... 429 ...").
    text = str(error).lower()
    return "429" in text or "rate exceeded" in text or "timeout" in text or "timed out" in text


def _extract_arxiv_id_query(query: str) -> str | None:
    """Return the bare arXiv id if a search query is really an id lookup, else None.

    Catches the common token-waste pattern where agents issue ``[SEARCH: id:2509.12411]``
    (or a bare id) into the keyword interface, which can never satisfy it.
    """
    match = _ARXIV_ID_QUERY_RE.match(query.strip())
    return match.group("id") if match else None


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
        self.chain_count_this_round: int = 0
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
        self.read_paper_ids: set[str] = set()  # Papers already read (cross-round dedup)
        self.followed_paper_ids: set[str] = set()  # Papers whose refs already fetched
        self.cited_by_paper_ids: set[str] = set()  # Papers whose citations already fetched

        # Data staging state
        self.resolved_data_urls: set[str] = set()  # Cross-round dedup for [DATA:] requests
        self.data_count_this_round: int = 0

        # External-source degradation: track which literature sources have already
        # emitted a calm "rate-limited / unavailable" notice this cycle, so a flaky
        # arXiv/S2 surfaces ONE informative row instead of a red error per request.
        self.degraded_sources: set[str] = set()

    # ------------------------------------------------------------------
    # Reset helpers
    # ------------------------------------------------------------------

    def reset_round_counters(self) -> None:
        """Reset per-round state at the start of each round."""
        self.search_count_this_round = 0
        self.follow_count_this_round = 0
        self.cited_by_count_this_round = 0
        self.read_count_this_round = 0
        self.data_count_this_round = 0
        self.chain_count_this_round = 0
        self.agent_search_count = {}

    def reset_cycle(self) -> None:
        """Reset all state for a new research cycle."""
        self.search_count_this_round = 0
        self.follow_count_this_round = 0
        self.cited_by_count_this_round = 0
        self.read_count_this_round = 0
        self.data_count_this_round = 0
        self.chain_count_this_round = 0
        self.agent_search_count = {}
        self.searched_queries = set()
        self.searched_query_keywords = []
        self.seen_paper_ids = set()
        self.total_stale_keyword_searches = 0
        self.search_log = []
        self.literature_context = ""
        self.discovered_papers = []
        self._discovered_ids = set()
        self.read_paper_ids = set()
        self.followed_paper_ids = set()
        self.cited_by_paper_ids = set()
        self.degraded_sources = set()

    def _handle_source_failure(self, source: str, agent_id: str, error: Exception) -> bool:
        """Record a literature-source failure; return True if handled calmly.

        Always logs the error to the structured event log (forensics). For an
        expected, recoverable failure (rate-limit / timeout / dropped connection)
        it surfaces ONE calm, deduped notice per source per cycle and returns
        True, so the caller skips the red per-action error. For an unexpected
        error it returns False, letting the caller surface it loudly — real
        regressions stay visible.
        """
        self._engine._logger.log_error(
            error, agent_id=agent_id, thread_id=self._engine.state.thread_id
        )
        if not _is_transient_source_error(error):
            return False
        if source not in self.degraded_sources:
            self.degraded_sources.add(source)
            self._engine._display.source_degraded(source)
        return True
        self.resolved_data_urls = set()

    # ------------------------------------------------------------------
    # Context accumulation helper
    # ------------------------------------------------------------------

    def _append_to_context(self, content: str, *, trim: bool = True) -> None:
        """Append content to literature_context, optionally trimming to limit."""
        lit = self.literature_context
        self.literature_context = lit + "\n" + content if lit else content
        if trim and len(self.literature_context) > _LITERATURE_CONTEXT_LIMIT:
            self.literature_context = self.literature_context[-_LITERATURE_CONTEXT_LIMIT:]

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
            short_title = (
                title[:_TITLE_TRUNCATION_INDEX] + "..."
                if len(title) > _TITLE_TRUNCATION_INDEX
                else title
            )
            lines.append(f"- [{arxiv_id}] {first_author}: {short_title}")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Seed discovery (Perplexity-based pre-seeding)
    # ------------------------------------------------------------------

    async def run_seed_discovery(self, seed_prompt: str) -> int:
        """Query Perplexity to discover foundational papers before IDEATION.

        Args:
            seed_prompt: The research topic / seed prompt.

        Returns:
            Number of papers successfully ingested.
        """
        config = self._engine._config
        if not config.citation.enable_seed_discovery:
            return 0

        api_key = os.environ.get(config.citation.perplexity_api_key_env)
        if not api_key:
            self._engine._logger.log_error(
                "Seed discovery: PERPLEXITY_API_KEY not set",
                thread_id=self._engine.state.thread_id,
            )
            return 0

        self._engine._display.seed_discovery_start()

        max_papers = config.citation.seed_discovery_max_papers
        client = PerplexityClient(
            api_key=api_key,
            event_logger=self._engine._logger,
            timeout=config.citation.perplexity_timeout,
        )

        try:
            urls = await client.discover_papers(seed_prompt)
        except Exception as e:
            _logger.warning("Seed discovery Perplexity call failed: %s", e)
            await client.close()
            return 0

        # Collect unique, not-yet-seen arXiv IDs from the discovered URLs.
        ids: list[str] = []
        for url in urls[:max_papers]:
            arxiv_id = extract_arxiv_id_from_url(url)
            if arxiv_id and arxiv_id not in self.seen_paper_ids and arxiv_id not in ids:
                ids.append(arxiv_id)

        # Fetch them ALL in one arXiv request. Firing N rate-limited single fetches
        # here trips arXiv's 429 + the circuit breaker on cloud IPs, which would
        # then disable arXiv for the agents' searches too.
        papers = []
        try:
            fetched = await self._engine._corpus._arxiv.get_papers(ids)
        except Exception as e:
            _logger.warning("Seed discovery: arXiv batch fetch failed: %s", e)
            fetched = []
        for paper in fetched:
            try:
                await self._engine._corpus.ingest_paper(paper)
                pid = getattr(paper, "arxiv_id", "") or ""
                if pid:
                    self.seen_paper_ids.add(pid)
                    first_author = paper.authors[0] if paper.authors else "Unknown"
                    self._track_paper(pid, paper.title, first_author)
                papers.append(paper)
            except Exception as e:
                _logger.warning(
                    "Seed discovery: failed to ingest %s: %s",
                    getattr(paper, "arxiv_id", "?"),
                    e,
                )
                continue

        if papers:
            source_results = [arxiv_paper_to_source_result(p) for p in papers]
            formatted = format_search_results("Seed discovery", source_results)
            self.literature_context = formatted

        await client.close()

        self._engine._logger.log(
            EventType.SEED_DISCOVERY,
            content={
                "seed_prompt": seed_prompt[:200],
                "urls_found": len(urls),
                "papers_ingested": len(papers),
            },
            thread_id=self._engine.state.thread_id,
        )

        return len(papers)

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
        if self.total_stale_keyword_searches >= _STALE_SEARCH_THRESHOLD:
            max_searches = min(max_searches, 1)

        # Per-agent cap: no single agent monopolizes the round's budget
        per_agent_cap = max(
            _PER_AGENT_CAP_MIN,
            self._engine._config.orchestrator.max_searches_per_round
            * _PER_AGENT_CAP_NUMERATOR
            // _PER_AGENT_CAP_DENOMINATOR,
        )

        search_requests = parse_search_requests(response_text)
        if not search_requests:
            return

        consecutive_stale = 0  # Track consecutive 0-new results within this agent's batch

        for query, provider in search_requests:
            # Global exact dedup: skip queries already executed in this cycle
            query_key = query.lower().strip()
            if query_key in self.searched_queries:
                continue

            # Fuzzy dedup: skip queries that are near-duplicates of previous ones
            new_kw = _normalize_query_keywords(query)
            if _is_duplicate_query(new_kw, self.searched_query_keywords):
                self._engine._display.search_skipped(query, reason="similar")
                continue

            # Check per-round budget
            if self.search_count_this_round >= max_searches:
                self._engine._display.search_budget_exhausted(max_searches, query)
                break

            # Check per-agent cap
            agent_count = self.agent_search_count.get(agent_id, 0)
            if agent_count >= per_agent_cap:
                self._engine._display.search_agent_cap(agent_id, per_agent_cap, query)
                break

            # Interop slice: route arXiv-id lookups to a direct fetch-by-id instead of
            # keyword search (which can never satisfy them) — eliminates guaranteed-zero
            # `id:<arxiv-id>` queries that otherwise waste the search budget.
            arxiv_id = _extract_arxiv_id_query(query)
            if arxiv_id is not None:
                await self._resolve_id_query(agent_id, query, query_key, arxiv_id, new_kw, phase)
                continue

            try:
                papers = await self._engine._corpus.search(
                    query,
                    max_results=self._engine._config.literature.max_results_per_search,
                    provider=provider,
                )
            except Exception as e:
                if not self._handle_source_failure("arXiv", agent_id, e):
                    self._engine._display.search_error(query, e)
                continue

            # Filter irrelevant papers by keyword overlap with query
            relevance_threshold = self._engine._config.orchestrator.search_relevance_threshold
            pre_filter_count = len(papers)
            topic_kw = _extract_topic_keywords(self._engine.state.seed_prompt)
            papers = _filter_relevant_papers(
                query, papers, threshold=relevance_threshold, topic_keywords=topic_kw
            )
            filtered_count = pre_filter_count - len(papers)
            if filtered_count > 0:
                _logger.info(
                    "Relevance filter removed %d/%d papers for query '%s'",
                    filtered_count,
                    pre_filter_count,
                    query[:60],
                )

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
                            "arxiv_id": p.id,
                            "title": p.title,
                            "authors": p.authors[:3],
                            "year": p.date.strftime("%Y") if p.date else "?",
                        }
                        for p in papers
                    ],
                }
            )

            # Filter out papers already shown to agents in previous searches
            new_papers = [p for p in papers if p.id not in self.seen_paper_ids]
            for p in new_papers:
                self.seen_paper_ids.add(p.id)
                first_author = p.authors[0] if p.authors else "Unknown"
                self._track_paper(p.id, p.title, first_author)

            if new_papers:
                consecutive_stale = 0
                formatted = format_search_results(query, new_papers)
                self._append_to_context(formatted)
            else:
                consecutive_stale += 1
                self.total_stale_keyword_searches += 1

            self.search_count_this_round += 1
            self.agent_search_count[agent_id] = self.agent_search_count.get(agent_id, 0) + 1

            display_query = f"[{provider}] {query}" if provider else query
            paper_dicts = [
                {
                    "arxiv_id": p.id,
                    "title": p.title,
                    "authors": p.authors[:3],
                    "year": p.date.strftime("%Y") if p.date else "?",
                }
                for p in papers
            ]
            self._engine._display.search_result(
                agent_id,
                display_query,
                len(papers),
                len(new_papers),
                papers=paper_dicts,
                phase=str(phase),
            )

            log_content: dict[str, Any] = {
                "query": query,
                "agent_id": agent_id,
                "results": len(papers),
                "phase": str(phase),
                "search_num": self.search_count_this_round,
            }
            if provider:
                log_content["provider"] = provider
            self._engine._logger.log(
                EventType.LITERATURE_SEARCH,
                content=log_content,
                thread_id=self._engine.state.thread_id,
                phase=str(phase),
            )

            # Stall hint: always inject when keyword search returns 0 new papers
            if not new_papers:
                hint = self._build_stall_hint()
                self._append_to_context(hint, trim=False)

            # Early termination: 2 consecutive stale searches from this agent
            if consecutive_stale >= _CONSECUTIVE_STALE_LIMIT:
                self._engine._display.search_stale(agent_id, _CONSECUTIVE_STALE_LIMIT)
                self._append_to_context(self._build_exhaustion_warning(), trim=False)
                break

        # Cross-round exhaustion warning: inject persistent warning
        if self.total_stale_keyword_searches >= _STALE_SEARCH_THRESHOLD:
            if "Keyword searches are exhausted" not in self.literature_context and (
                "Literature search has returned no usable results" not in self.literature_context
            ):
                self._append_to_context(self._build_exhaustion_warning(), trim=False)

    async def _resolve_id_query(
        self,
        agent_id: str,
        query: str,
        query_key: str,
        arxiv_id: str,
        new_kw: frozenset[str],
        phase: ResearchPhase,
    ) -> None:
        """Resolve an ``id:<arxiv-id>`` query via a direct fetch-by-id (not keyword search).

        Counts against the per-round/per-agent search budget (so it can't be abused)
        but NOT against the keyword-stale throttle, since a precise id lookup is a
        legitimate, non-keyword request.
        """
        self.searched_queries.add(query_key)
        if new_kw:
            self.searched_query_keywords.append(new_kw)
        self.search_count_this_round += 1
        self.agent_search_count[agent_id] = self.agent_search_count.get(agent_id, 0) + 1

        lit_config = self._engine._config.literature
        try:
            result = await self._engine._corpus.read_paper(
                arxiv_id, max_chars=lit_config.max_read_chars
            )
        except Exception as e:
            if not self._handle_source_failure("arXiv", agent_id, e):
                self._engine._display.read_error(arxiv_id, e)
            return

        found = result is not None
        title = result[0] if found else ""
        if found:
            _, extracted_text = result
            self._append_to_context(format_read_result(arxiv_id, title, extracted_text))
            self.seen_paper_ids.add(arxiv_id)
            self._engine._display.read_result(agent_id, arxiv_id, title, len(extracted_text))
        else:
            self._engine._display.read_not_found(arxiv_id)

        self._engine._logger.log(
            EventType.LITERATURE_SEARCH,
            content={
                "query": query,
                "agent_id": agent_id,
                "results": 1 if found else 0,
                "phase": str(phase),
                "resolved_as": "fetch_by_id",
                "arxiv_id": arxiv_id,
                "found": found,
            },
            thread_id=self._engine.state.thread_id,
            phase=str(phase),
        )

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
                self._engine._display.follow_budget_exhausted(arxiv_id)
                break

            if arxiv_id in self.followed_paper_ids:
                self._engine._display.follow_skipped(arxiv_id)
                continue

            if not self._is_discovered_id(arxiv_id):
                self._note_rejected_id("FOLLOW", arxiv_id)
                self._engine._display.follow_skipped(arxiv_id)
                continue

            try:
                papers = await self._engine._corpus.get_references(
                    arxiv_id, max_results=lit_config.max_reference_results
                )
            except Exception as e:
                if not self._handle_source_failure("arXiv", agent_id, e):
                    self._engine._display.follow_error(arxiv_id, e)
                continue

            # Track discovered paper IDs
            for p in papers:
                if p.id:
                    self.seen_paper_ids.add(p.id)
                    first_author = p.authors[0] if p.authors else "Unknown"
                    self._track_paper(p.id, p.title, first_author)

            formatted = format_follow_results(
                arxiv_id, papers, max_papers=lit_config.max_reference_results
            )
            self._append_to_context(formatted)

            self.follow_count_this_round += 1
            self.followed_paper_ids.add(arxiv_id)
            self.search_log.append(
                {
                    "query": f"[FOLLOW: {arxiv_id}]",
                    "agent_id": agent_id,
                    "phase": str(phase),
                    "papers": [
                        {
                            "arxiv_id": p.id,
                            "title": p.title,
                            "authors": p.authors[:3],
                            "year": p.date.strftime("%Y") if p.date else "?",
                        }
                        for p in papers
                    ],
                }
            )

            self._engine._display.follow_result(agent_id, arxiv_id, len(papers))

            self._engine._logger.log(
                EventType.LITERATURE_FOLLOW,
                content={
                    "arxiv_id": arxiv_id,
                    "agent_id": agent_id,
                    "references_found": len(papers),
                    "phase": str(phase),
                },
                thread_id=self._engine.state.thread_id,
                phase=str(phase),
            )

        # Process [CITED_BY: arxiv_id] requests
        for arxiv_id in parse_cited_by_requests(response_text):
            if self.cited_by_count_this_round >= lit_config.cited_by_budget_per_round:
                self._engine._display.cited_by_budget_exhausted(arxiv_id)
                break

            if arxiv_id in self.cited_by_paper_ids:
                self._engine._display.cited_by_skipped(arxiv_id)
                continue

            if not self._is_discovered_id(arxiv_id):
                self._note_rejected_id("CITED_BY", arxiv_id)
                self._engine._display.cited_by_skipped(arxiv_id)
                continue

            try:
                papers = await self._engine._corpus.get_citations(
                    arxiv_id, max_results=lit_config.max_citation_results
                )
            except Exception as e:
                if not self._handle_source_failure("arXiv", agent_id, e):
                    self._engine._display.cited_by_error(arxiv_id, e)
                continue

            # Track discovered paper IDs
            for p in papers:
                if p.id:
                    self.seen_paper_ids.add(p.id)
                    first_author = p.authors[0] if p.authors else "Unknown"
                    self._track_paper(p.id, p.title, first_author)

            formatted = format_cited_by_results(
                arxiv_id, papers, max_papers=lit_config.max_citation_results
            )
            self._append_to_context(formatted)

            self.cited_by_count_this_round += 1
            self.cited_by_paper_ids.add(arxiv_id)
            self.search_log.append(
                {
                    "query": f"[CITED_BY: {arxiv_id}]",
                    "agent_id": agent_id,
                    "phase": str(phase),
                    "papers": [
                        {
                            "arxiv_id": p.id,
                            "title": p.title,
                            "authors": p.authors[:3],
                            "year": p.date.strftime("%Y") if p.date else "?",
                        }
                        for p in papers
                    ],
                }
            )

            self._engine._display.cited_by_result(agent_id, arxiv_id, len(papers))

            self._engine._logger.log(
                EventType.LITERATURE_CITED_BY,
                content={
                    "arxiv_id": arxiv_id,
                    "agent_id": agent_id,
                    "citations_found": len(papers),
                    "phase": str(phase),
                },
                thread_id=self._engine.state.thread_id,
                phase=str(phase),
            )

        # Process [READ: arxiv_id] requests
        for arxiv_id in parse_read_requests(response_text):
            if self.read_count_this_round >= lit_config.read_budget_per_round:
                self._engine._display.read_budget_exhausted(arxiv_id)
                break

            if arxiv_id in self.read_paper_ids:
                self._engine._display.read_skipped(arxiv_id)
                continue

            if not self._is_discovered_id(arxiv_id):
                self._note_rejected_id("READ", arxiv_id)
                self._engine._display.read_skipped(arxiv_id)
                continue

            try:
                result = await self._engine._corpus.read_paper(
                    arxiv_id, max_chars=lit_config.max_read_chars
                )
            except Exception as e:
                if not self._handle_source_failure("arXiv", agent_id, e):
                    self._engine._display.read_error(arxiv_id, e)
                continue

            if result is None:
                self._engine._display.read_not_found(arxiv_id)
                continue

            title, extracted_text = result
            formatted = format_read_result(arxiv_id, title, extracted_text)
            self._append_to_context(formatted)

            self.read_count_this_round += 1
            self.read_paper_ids.add(arxiv_id)

            self._engine._display.read_result(agent_id, arxiv_id, title, len(extracted_text))

            self._engine._logger.log(
                EventType.LITERATURE_READ,
                content={
                    "arxiv_id": arxiv_id,
                    "agent_id": agent_id,
                    "title": title,
                    "chars_extracted": len(extracted_text),
                    "phase": str(phase),
                },
                thread_id=self._engine.state.thread_id,
                phase=str(phase),
            )

    # ------------------------------------------------------------------
    # Citation chain traversal ([CHAIN: ...])
    # ------------------------------------------------------------------

    async def process_chain_requests(
        self, agent_id: str, response_text: str, phase: ResearchPhase
    ) -> None:
        """Parse [CHAIN: paper_id depth=N direction=refs|cites|both] and execute.

        Results are appended to self.literature_context for all subsequent agents.

        Args:
            agent_id: ID of the agent whose response contains chain requests.
            response_text: The agent's response text.
            phase: Current research phase.
        """
        if phase not in _SEARCH_ENABLED_PHASES:
            return

        chain_reqs = parse_chain_requests(response_text)
        if not chain_reqs:
            return

        lit_config = self._engine._config.literature
        # The corpus exposes its SourceProviders as ``_providers`` (get_references/
        # get_citations route through them). Without providers there's nothing to walk.
        providers = getattr(self._engine._corpus, "_providers", None) or {}
        if not providers:
            return

        for req in chain_reqs:
            if self.chain_count_this_round >= lit_config.chain_budget_per_round:
                break
            # Gate: only walk from a paper actually discovered via search. A depth-N
            # BFS from a hallucinated seed would amplify contamination across levels.
            if not self._is_discovered_id(req.paper_id):
                self._note_rejected_id("CHAIN", req.paper_id)
                continue
            try:
                papers = await follow_citation_chain(
                    providers=providers,
                    seed_id=req.paper_id,
                    direction=req.direction,
                    max_depth=req.depth,
                    max_papers_per_level=10,
                )
            except Exception as e:
                self._engine._logger.log_error(
                    e, agent_id=agent_id, thread_id=self._engine.state.thread_id
                )
                continue

            self.chain_count_this_round += 1

            # Track discovered papers
            for p in papers:
                if p.id:
                    self.seen_paper_ids.add(p.id)
                    first_author = p.authors[0] if p.authors else "Unknown"
                    self._track_paper(p.id, p.title, first_author)

            formatted = format_chain_results(req.paper_id, papers, req.direction, req.depth)
            self._append_to_context(formatted)

            self._engine._logger.log(
                EventType.LITERATURE_SEARCH,
                content={
                    "query": f"[CHAIN: {req.paper_id} depth={req.depth} direction={req.direction}]",
                    "agent_id": agent_id,
                    "papers_found": len(papers),
                    "phase": str(phase),
                },
                thread_id=self._engine.state.thread_id,
                phase=str(phase),
            )

    # ------------------------------------------------------------------
    # Data staging ([DATA: url])
    # ------------------------------------------------------------------

    async def process_data_requests(
        self, agent_id: str, response_text: str, phase: ResearchPhase
    ) -> None:
        """Parse [DATA: url] markers and download datasets for sandbox use.

        Downloads data files outside the sandbox and appends them to the
        engine's resolved_resources list so they appear in the file listing
        during EXECUTION.

        Args:
            agent_id: ID of the agent whose response contains data requests.
            response_text: The agent's response text.
            phase: Current research phase.
        """
        if phase not in _SEARCH_ENABLED_PHASES:
            return

        urls = parse_data_requests(response_text)
        if not urls:
            return

        shared_dir = self._engine._config.storage.data_dir / "shared"

        for url in urls:
            # Cross-round dedup
            if url in self.resolved_data_urls:
                self._engine._display.data_stage_skipped(url, reason="already downloaded")
                continue

            # Per-round budget
            if self.data_count_this_round >= _DATA_REQUESTS_PER_ROUND:
                self._engine._display.data_stage_skipped(
                    url, reason=f"budget exhausted ({_DATA_REQUESTS_PER_ROUND}/round)"
                )
                break

            # Classify URL — only accept DATA type
            rtype = classify_resource(url)
            if rtype != ResourceType.DATA:
                self._engine._display.data_stage_skipped(
                    url,
                    reason=f"URL classified as {rtype.value}, not data",
                )
                continue

            # Download via existing resolve_resource pipeline
            try:
                resource = await resolve_resource(url, rtype, shared_dir, self._engine._logger)
            except Exception as e:
                self._engine._display.data_stage_error(url, e)
                continue

            if resource.error:
                self._engine._display.data_stage_error(url, resource.error)
                continue

            # Track
            self.resolved_data_urls.add(url)
            self.data_count_this_round += 1
            self._engine.state.resolved_resources.append(resource)

            # Inject confirmation into literature context
            size_str = ""
            if resource.size_bytes is not None:
                if resource.size_bytes > 1024 * 1024:
                    size_str = f" ({resource.size_bytes / (1024 * 1024):.1f} MB)"
                elif resource.size_bytes > 1024:
                    size_str = f" ({resource.size_bytes / 1024:.1f} KB)"
                else:
                    size_str = f" ({resource.size_bytes} bytes)"
            confirmation = (
                f"Downloaded dataset: {resource.name}{size_str} \u2192 {resource.sandbox_path}"
            )
            self._append_to_context(confirmation)

            self._engine._display.data_staged(resource.name, resource.size_bytes or 0, url)

            self._engine._logger.log(
                EventType.STATE_CHANGE,
                content={
                    "event": "data_staged",
                    "url": url,
                    "filename": resource.name,
                    "size_bytes": resource.size_bytes,
                    "agent_id": agent_id,
                    "phase": str(phase),
                },
                thread_id=self._engine.state.thread_id,
                phase=str(phase),
            )

    # ------------------------------------------------------------------
    # Stall hint helpers
    # ------------------------------------------------------------------

    def _build_follow_examples(self, n: int = _FOLLOW_EXAMPLES_COUNT) -> str:
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
            short = (
                title[:_TITLE_TRUNCATION_SHORT] + "..."
                if len(title) > _TITLE_TRUNCATION_SHORT
                else title
            )
            lines.append(f'>   [FOLLOW: {arxiv_id}]  — refs of "{short}"')
        lines.append("")
        return "\n".join(lines)

    def _build_stall_hint(self) -> str:
        """Build a stall hint with concrete paper IDs when available.

        Returns:
            Formatted hint string.
        """
        examples = self._build_follow_examples(_FOLLOW_EXAMPLES_COUNT)
        if examples:
            return (
                "\n\n> **Hint:** Your keyword searches are returning no new results. "
                "Use [FOLLOW: arxiv_id] to explore references of papers "
                "you've already found, or [CITED_BY: arxiv_id] to find recent work "
                "building on foundational papers. Only use IDs from the discovered "
                "list — never invent or guess arXiv IDs.\n" + examples
            )
        # No papers discovered yet: forcing [FOLLOW:] would only invite invented
        # IDs, which resolve to real-but-unrelated papers and poison the context.
        return (
            "\n\n> **Hint:** Literature search is returning no results for this topic "
            "so far. Try ONE broader, simpler [SEARCH:] (fewer terms, no boolean AND) "
            "before giving up. Do NOT invent or guess arXiv IDs for "
            "[FOLLOW:]/[CITED_BY:]/[READ:] — IDs that were never returned by a real "
            "search will be rejected. If searches keep coming up empty, proceed with "
            "your analysis and explicitly note the literature gap.\n"
        )

    def _build_exhaustion_warning(self) -> str:
        """Warning injected when keyword searches are exhausted.

        Only pushes [FOLLOW:]/[CITED_BY:] when there are real discovered IDs to
        traverse; otherwise it would force agents to hallucinate IDs.
        """
        examples = self._build_follow_examples(_FOLLOW_EXAMPLES_COUNT)
        if examples:
            return (
                "\n\n> ⚠ Keyword searches are exhausted for this topic. Use "
                "[FOLLOW: arxiv_id] or [CITED_BY: arxiv_id] on the discovered papers "
                "below to find more — do NOT issue [SEARCH:] requests, and do NOT "
                "invent arXiv IDs (only IDs from the discovered list work).\n" + examples
            )
        return (
            "\n\n> ⚠ Literature search has returned no usable results for this "
            "topic — the external sources may be unavailable. Do NOT invent arXiv IDs "
            "for [FOLLOW:]/[CITED_BY:]/[READ:] (they will be rejected). Proceed with "
            "the analysis and explicitly note the literature gap.\n"
        )

    def _is_discovered_id(self, arxiv_id: str) -> bool:
        """True if this arXiv ID was actually returned by a real search/traversal.

        Agents sometimes invent plausible-looking arXiv IDs (e.g. ``2303.11111``)
        when no real papers were found. Those IDs resolve to real-but-unrelated
        papers (we have seen XAI papers surface for an astrophysics topic), which
        then poison the shared literature context. Gating graph actions to
        previously-discovered IDs blocks that contamination at the source.
        """
        return arxiv_id in self.seen_paper_ids

    def _note_rejected_id(self, action: str, arxiv_id: str) -> None:
        """Tell the agent (via shared context) why an invented ID was rejected."""
        self._append_to_context(
            f"\n> [{action}: {arxiv_id}] rejected — that arXiv ID was never returned by "
            "a search, so it cannot be trusted to be the paper you intend. Use "
            "[SEARCH:] to find real papers, then [FOLLOW:]/[CITED_BY:] only IDs from "
            "the discovered list.\n",
            trim=False,
        )
