"""Citation grounding and novelty checking handler for the orchestrator."""

from __future__ import annotations

import asyncio
import os
import re
from typing import TYPE_CHECKING

from paradigm.journal.paper import PaperDraft, parse_sections_from_markdown
from paradigm.literature.bibliography import BibliographyBuilder, extract_arxiv_id_from_url
from paradigm.literature.novelty import (
    NoveltyResult,
    check_novelty_futurehouse,
    check_novelty_semantic_scholar,
)
from paradigm.literature.perplexity import PerplexityClient
from paradigm.logging.events import EventType

if TYPE_CHECKING:
    from paradigm.orchestrator.engine import OrchestrationEngine

# Hard wall-clock cap on the whole citation-grounding pass. Grounding is a
# best-effort enhancement — if Perplexity is slow/rate-limited past this, leave the
# paper ungrounded rather than stall the cycle.
_GROUNDING_BUDGET_S = 240.0

_MARKER_RE = re.compile(r"\[(\d+)\]")
# An existing References / Bibliography section (writer-authored) conventionally
# ends the paper; the grounded bibliography replaces it (the inline [N] markers are
# the grounded numbering, so a leftover writer section would mismatch + duplicate).
_REFS_SECTION_RE = re.compile(
    r"\n#{1,3}\s*(references|bibliography|works\s+cited)\b.*\Z",
    re.IGNORECASE | re.DOTALL,
)


def _is_citable_url(url: str) -> bool:
    """Reject arXiv listing/browse pages (``/list/``, ``/recent``, ``?skip=``, …)
    that Perplexity sometimes returns — they aren't papers. Keep specific arXiv
    paper URLs and any non-arXiv URL (e.g. a DOI)."""
    u = (url or "").lower().strip()
    if not u:
        return False
    if "arxiv.org" in u:
        return bool(extract_arxiv_id_from_url(url))  # only a concrete paper id
    return True


def _filter_section_citations(cited_text: str, urls: list[str]) -> tuple[str, list[str]]:
    """Drop non-citable URLs from one section and remap its local ``[N]`` markers
    so none dangle. Runs BEFORE global renumbering."""
    keep = [i for i, u in enumerate(urls) if _is_citable_url(u)]
    if len(keep) == len(urls):
        return cited_text, urls
    remap = {old + 1: new + 1 for new, old in enumerate(keep)}  # 1-based local indices
    new_urls = [urls[i] for i in keep]

    def _sub(m: re.Match) -> str:
        n = int(m.group(1))
        return f"[{remap[n]}]" if n in remap else ""

    return _MARKER_RE.sub(_sub, cited_text), new_urls


def _strip_references_section(body: str) -> str:
    """Remove a trailing writer-authored References/Bibliography section."""
    return _REFS_SECTION_RE.sub("", body).rstrip()


class CitationHandler:
    """Handles citation grounding and novelty checking for the orchestrator."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    async def run_citation_grounding(self, draft: PaperDraft) -> PaperDraft:
        """Post-process a paper draft to insert [N] citation markers and references.

        Args:
            draft: PaperDraft with assembled_body.

        Returns:
            Updated PaperDraft with citations and references.
        """
        config = self._engine._config.citation

        # Check if enabled
        if not config.enable_citation_grounding:
            return draft

        # Check API key availability
        api_key = os.getenv(config.perplexity_api_key_env)
        if not api_key:
            self._engine._logger.log_error(
                ValueError(
                    f"Citation grounding enabled but {config.perplexity_api_key_env} "
                    "not set in environment"
                ),
                thread_id=self._engine.state.thread_id,
            )
            return draft

        self._engine._display.citation_grounding_start()

        # Parse assembled body into sections
        sections = parse_sections_from_markdown(draft.assembled_body)

        # Determine which sections to cite
        citable_sections = config.citation_sections

        # Process each citable section
        section_texts: list[str] = []
        section_url_lists: list[list[str]] = []
        cited_section_names: list[str] = []

        async with PerplexityClient(
            api_key=api_key,
            event_logger=self._engine._logger,
            timeout=config.perplexity_timeout,
            max_retries=config.max_retries_per_paragraph,
        ) as client:
            citable = [
                (name, content)
                for name, content in sections.items()
                if name.lower() in citable_sections
            ]
            try:
                # Ground all citable sections CONCURRENTLY, under an overall budget so
                # a slow/rate-limited Perplexity can never stall the cycle (grounding
                # is best-effort — leave the paper ungrounded if it overruns).
                results = await asyncio.wait_for(
                    asyncio.gather(*(client.cite_section(c, n) for n, c in citable)),
                    timeout=_GROUNDING_BUDGET_S,
                )
            except TimeoutError:
                self._engine._logger.log_error(
                    RuntimeError(
                        "citation grounding exceeded its budget — leaving paper ungrounded"
                    ),
                    thread_id=self._engine.state.thread_id,
                    metadata_key="citation_grounding",
                )
                self._engine._display.citation_grounding_complete(0)
                return draft
            for (name, _content), (cited_text, urls) in zip(citable, results, strict=True):
                section_texts.append(cited_text)
                section_url_lists.append(urls)
                cited_section_names.append(name)

        if not section_texts:
            self._engine._display.citation_grounding_complete(0)
            return draft

        # Drop non-paper "citations" (arXiv listing/browse pages) per section, remapping
        # each section's local [N] markers, BEFORE global renumbering.
        filtered_texts: list[str] = []
        filtered_urls: list[list[str]] = []
        for text, urls in zip(section_texts, section_url_lists, strict=True):
            ft, fu = _filter_section_citations(text, urls)
            filtered_texts.append(ft)
            filtered_urls.append(fu)
        section_texts, section_url_lists = filtered_texts, filtered_urls

        # Renumber citations globally
        _, global_urls = BibliographyBuilder.renumber_citations(section_texts, section_url_lists)

        # Replace sections in assembled body with cited versions
        # We need to re-renumber each section individually
        updated_body = draft.assembled_body
        url_to_global: dict[str, int] = {}
        global_url_list: list[str] = []

        for url in global_urls:
            if url not in url_to_global:
                url_to_global[url] = len(global_url_list) + 1
                global_url_list.append(url)

        for _name, original_content, cited_text, urls in zip(
            cited_section_names,
            [sections[name] for name in cited_section_names],
            section_texts,
            section_url_lists,
            strict=False,
        ):
            # Build local->global mapping for this section
            local_to_global: dict[int, int] = {}
            for local_idx, url in enumerate(urls):
                local_to_global[local_idx + 1] = url_to_global.get(url, local_idx + 1)

            mapping = local_to_global

            def _replace_marker(match: re.Match, _m: dict[int, int] = mapping) -> str:
                local_num = int(match.group(1))
                global_num = _m.get(local_num, local_num)
                return f"[{global_num}]"

            renumbered = re.sub(r"\[(\d+)\]", _replace_marker, cited_text)
            updated_body = updated_body.replace(original_content, renumbered, 1)

        # Build bibliography
        bib_builder = BibliographyBuilder(
            arxiv_client=self._engine._corpus._arxiv
            if hasattr(self._engine._corpus, "_arxiv")
            else None,
            s2_client=None,
            event_logger=self._engine._logger,
        )
        references = await bib_builder.build_references(global_url_list)
        # Resolve-or-drop (Phase 2): optionally drop references that didn't resolve to
        # real metadata (would render as bare URLs the editor rejects) and rewrite the
        # in-text [N] markers so no citation dangles.
        if self._engine._config.citation.drop_unresolved_citations:
            references, remap = BibliographyBuilder.drop_unresolved_references(references)
            updated_body = BibliographyBuilder.remap_citation_markers(updated_body, remap)
        bibliography = BibliographyBuilder.format_bibliography_markdown(references)

        # Append the grounded References section, REPLACING any writer-authored one
        # (the inline [N] markers now use the grounded numbering, so a leftover
        # writer-written References section would both duplicate and mismatch).
        if bibliography:
            updated_body = _strip_references_section(updated_body) + "\n\n" + bibliography

        # Update draft
        draft.assembled_body = updated_body
        draft.references = [
            {
                "index": ref.index,
                "url": ref.url,
                "arxiv_id": ref.arxiv_id,
                "title": ref.title,
                "authors": ref.authors,
                "year": ref.year,
            }
            for ref in references
        ]

        # Log
        num_citations = len(global_url_list)
        self._engine._logger.log(
            EventType.CITATION_GROUNDING,
            content={
                "num_citations": num_citations,
                "sections_cited": cited_section_names,
            },
            thread_id=self._engine.state.thread_id,
        )
        self._engine._display.citation_grounding_complete(num_citations)

        return draft

    async def check_novelty(self, idea_text: str, mode: str = "semantic_scholar") -> NoveltyResult:
        """Check idea novelty using configured backend.

        Args:
            idea_text: Research idea description.
            mode: "semantic_scholar" or "futurehouse".

        Returns:
            NoveltyResult.
        """
        config = self._engine._config.citation

        self._engine._display.novelty_check_start(mode)

        if mode == "futurehouse":
            api_key = os.getenv(config.futurehouse_api_key_env)
            if not api_key:
                self._engine._logger.log_error(
                    ValueError(
                        f"FutureHouse novelty check enabled but "
                        f"{config.futurehouse_api_key_env} not set"
                    ),
                    thread_id=self._engine.state.thread_id,
                )
                return NoveltyResult(is_novel=True, confidence=0.0, source="futurehouse")

            result = await check_novelty_futurehouse(idea_text, api_key, self._engine._logger)
        else:
            # Semantic Scholar mode
            from paradigm.literature.semantic_scholar import SemanticScholarClient

            s2_client = SemanticScholarClient(logger=self._engine._logger)
            provider = self._engine._config.get_provider()
            model = self._engine._config.agent.default_model

            try:
                result = await check_novelty_semantic_scholar(
                    idea_text,
                    s2_client,
                    provider,
                    model,
                    max_iterations=config.novelty_max_iterations,
                    event_logger=self._engine._logger,
                )
            finally:
                await s2_client.close()

        # Log result
        self._engine._logger.log(
            EventType.NOVELTY_CHECK,
            content={
                "is_novel": result.is_novel,
                "confidence": result.confidence,
                "papers_found": result.papers_found,
                "source": result.source,
            },
            thread_id=self._engine.state.thread_id,
        )

        if result.is_novel:
            self._engine._display.novelty_confirmed()
        else:
            self._engine._display.novelty_warning(result)

        return result
