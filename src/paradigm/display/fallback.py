"""PlainTextFallback — click.echo-based display for non-TTY and verbose mode.

Every method produces output identical to the original click.echo() calls
throughout the codebase, providing behavioral parity with the pre-Rich UI.
"""

from __future__ import annotations

import click


class PlainTextFallback:
    """Plain-text display backend using click.echo().

    Matches the exact formatting of the original click.echo() calls
    that were scattered across engine.py, literature.py, debate.py,
    writing.py, review.py, and main.py.
    """

    # ------------------------------------------------------------------
    # Lifecycle (no-ops for plain text)
    # ------------------------------------------------------------------

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Phase transitions
    # ------------------------------------------------------------------

    def phase_transition(
        self,
        phase_name: str,
        *,
        max_rounds: int | None = None,
        active_agents: int | None = None,
        total_agents: int | None = None,
    ) -> None:
        if max_rounds is not None and active_agents is not None and total_agents is not None:
            click.echo(
                f"Phase: {phase_name} ({max_rounds} rounds, "
                f"{active_agents}/{total_agents} agents active)"
            )
        else:
            click.echo(f"Phase: {phase_name}")

    def phase_aborted(self) -> None:
        click.echo("Research cycle aborted by intervention hook.")

    def phase_paused(self) -> None:
        click.echo("Research cycle paused by intervention hook.")

    # ------------------------------------------------------------------
    # Rounds
    # ------------------------------------------------------------------

    def round_start(self, round_num: int, max_rounds: int) -> None:
        click.echo(f"  Round {round_num}/{max_rounds}...")

    # ------------------------------------------------------------------
    # Convergence detection
    # ------------------------------------------------------------------

    def convergence_detected(self, phase: str, round_num: int, max_rounds: int) -> None:
        rounds_skipped = max_rounds - round_num
        click.echo(
            f"  [convergence] Agents converged after round {round_num}, "
            f"skipping {rounds_skipped} remaining round(s)"
        )

    # ------------------------------------------------------------------
    # Agent activity
    # ------------------------------------------------------------------

    def agent_response(self, agent_id: str, total_tokens: int) -> None:
        click.echo(f"    {agent_id}: {total_tokens} tokens")

    def agent_error(self, agent_id: str, error: str | Exception) -> None:
        click.echo(f"    [!] {agent_id} failed: {error}")

    # ------------------------------------------------------------------
    # Literature / search
    # ------------------------------------------------------------------

    def search_result(
        self,
        agent_id: str,
        query: str,
        total_results: int,
        new_results: int,
    ) -> None:
        click.echo(
            f"    {agent_id} searched: '{query[:60]}' \u2192 "
            f"{total_results} results ({new_results} new)"
        )

    def search_skipped(self, query: str, *, reason: str = "similar") -> None:
        click.echo(f"    [~] Skipping {reason} query: {query[:60]}")

    def search_budget_exhausted(self, budget: int, query: str) -> None:
        click.echo(f"    [!] Search budget exhausted ({budget}/round), skipping: {query[:60]}")

    def search_agent_cap(self, agent_id: str, cap: int, query: str) -> None:
        click.echo(f"    [!] {agent_id}: per-agent cap reached ({cap}), skipping: {query[:60]}")

    def search_error(self, query: str, error: str | Exception) -> None:
        click.echo(f"    [!] Search failed for '{query[:60]}': {error}")

    def source_degraded(self, source: str) -> None:
        click.echo(f"    [i] {source} rate-limited — using cached corpus + other sources")

    def draft_section(
        self, section: str, title: str, content: str, author: str, status: str
    ) -> None:
        if status == "drafted":
            click.echo(f"    [§] {title or section} drafted ({len(content)} chars)")

    def experiment_update(
        self,
        experiment_id: str,
        name: str,
        agent_id: str,
        status: str,
        *,
        code: str = "",
        stdout: str = "",
        results: dict[str, float] | None = None,
        has_figures: bool = False,
    ) -> None:
        return None

    def search_stale(self, agent_id: str, count: int = 2) -> None:
        click.echo(f"    [!] {agent_id}: {count} consecutive stale searches, stopping keywords")

    def follow_result(self, agent_id: str, arxiv_id: str, count: int) -> None:
        click.echo(f"    {agent_id} followed refs of {arxiv_id} \u2192 {count} references")

    def follow_budget_exhausted(self, arxiv_id: str) -> None:
        click.echo(f"    [!] Follow budget exhausted, skipping: {arxiv_id}")

    def follow_skipped(self, arxiv_id: str) -> None:
        click.echo(f"    [skip] Already followed refs of {arxiv_id}, skipping duplicate")

    def follow_error(self, arxiv_id: str, error: str | Exception) -> None:
        click.echo(f"    [!] Follow failed for '{arxiv_id}': {error}")

    def cited_by_result(self, agent_id: str, arxiv_id: str, count: int) -> None:
        click.echo(f"    {agent_id} cited-by {arxiv_id} \u2192 {count} citations")

    def cited_by_budget_exhausted(self, arxiv_id: str) -> None:
        click.echo(f"    [!] Cited-by budget exhausted, skipping: {arxiv_id}")

    def cited_by_skipped(self, arxiv_id: str) -> None:
        click.echo(f"    [skip] Already fetched citations of {arxiv_id}, skipping duplicate")

    def cited_by_error(self, arxiv_id: str, error: str | Exception) -> None:
        click.echo(f"    [!] Cited-by failed for '{arxiv_id}': {error}")

    def read_result(self, agent_id: str, arxiv_id: str, title: str, chars: int) -> None:
        click.echo(f"    {agent_id} read {arxiv_id}: {title[:60]} ({chars} chars)")

    def read_budget_exhausted(self, arxiv_id: str) -> None:
        click.echo(f"    [!] Read budget exhausted, skipping: {arxiv_id}")

    def read_skipped(self, arxiv_id: str) -> None:
        click.echo(f"    [skip] Already read {arxiv_id}, skipping duplicate")

    def read_error(self, arxiv_id: str, error: str | Exception) -> None:
        click.echo(f"    [!] Read failed for '{arxiv_id}': {error}")

    def read_not_found(self, arxiv_id: str) -> None:
        click.echo(f"    [!] Could not read paper {arxiv_id}")

    # ------------------------------------------------------------------
    # Data staging
    # ------------------------------------------------------------------

    def data_staged(self, filename: str, size_bytes: int, url: str) -> None:
        size_str = f"{size_bytes / 1024:.1f} KB" if size_bytes > 1024 else f"{size_bytes} B"
        click.echo(f"    [data] Staged: {filename} ({size_str}) from {url[:60]}")

    def data_stage_error(self, url: str, error: str | Exception) -> None:
        click.echo(f"    [!] Data staging failed for {url[:60]}: {error}")

    def data_stage_skipped(self, url: str, reason: str) -> None:
        click.echo(f"    [skip] Data staging skipped for {url[:60]}: {reason}")

    def network_access_warning(self) -> None:
        click.echo("WARNING: --network-access enabled. Sandbox containers have internet access.")

    # ------------------------------------------------------------------
    # Resources (seeding phase)
    # ------------------------------------------------------------------

    def resource_detected(self, url: str, resource_type: str) -> None:
        click.echo(f"  Resource: {url} \u2192 {resource_type}")

    def resource_ingested(self, title: str) -> None:
        click.echo(f"  Ingested external paper: {title[:80]}")

    def resource_resolved(self, name: str, resource_type: str) -> None:
        click.echo(f"  Resolved: {name} ({resource_type})")

    def resource_error(self, message: str) -> None:
        click.echo(f"  [!] Resource error: {message}")

    def resource_fetch_error(self, url: str, error: str | Exception) -> None:
        click.echo(f"  [!] Failed to fetch URL: {url} ({error})")

    def resource_extract_error(self, url: str) -> None:
        click.echo(f"  [!] Could not extract PDF from: {url}")

    def pdf_saved(self, name: str) -> None:
        click.echo(f"  Saved PDF for sandbox: {name}")

    def pdf_save_error(self, error: str | Exception) -> None:
        click.echo(f"  [!] Could not save PDF for sandbox: {error}")

    def graveyard_error(self, error: str | Exception) -> None:
        click.echo(f"  [!] Graveyard search failed: {error}")

    # ------------------------------------------------------------------
    # Debates
    # ------------------------------------------------------------------

    def debate_start(self, challenger_id: str, defender_id: str, topic: str) -> None:
        click.echo(f"    >>> Debate: {challenger_id} vs {defender_id} \u2014 {topic[:60]}")

    def debate_turn(self, agent_id: str, event: str) -> None:
        click.echo(f"    <<< {event}")

    def debate_resolved(self, agent_id: str) -> None:
        click.echo(f"    <<< Debate resolved by {agent_id}")

    def debate_concede(self, agent_id: str) -> None:
        click.echo(f"    <<< {agent_id} concedes")

    def debate_error(self, agent_id: str, error: str | Exception) -> None:
        click.echo(f"    [!] Debate error ({agent_id}): {error}")

    def debate_complete(self, resolution_type: str, num_turns: int) -> None:
        click.echo(f"    <<< Debate complete ({resolution_type}, {num_turns} turns)")

    def debate_skipped(self, target_id: str, reason: str) -> None:
        click.echo(f"    [!] Debate skipped: {reason}")

    def debate_budget_exhausted(self, max_debates: int, phase: str) -> None:
        click.echo(f"    [!] Debate budget exhausted ({max_debates}/{phase}), skipping")

    def synthesis_error(self, error: str | Exception) -> None:
        click.echo(f"    [!] Synthesis failed, using mechanical fallback: {error}")

    # ------------------------------------------------------------------
    # Execution / experiments
    # ------------------------------------------------------------------

    def experiment_round(self, round_num: int, max_rounds: int) -> None:
        click.echo(f"  Experiment round {round_num}/{max_rounds}...")

    def experiment_no_agent(self) -> None:
        click.echo("    [!] No experimentalist or analyst found, skipping")

    def experiment_declared_sufficient(self) -> None:
        click.echo("    Agent declared experiments sufficient")

    def experiment_no_code(self) -> None:
        click.echo("    No code blocks proposed, skipping execution")

    def experiment_running(self, exp_name: str) -> None:
        click.echo(f"    Running: {exp_name}")

    def experiment_result(self, exp_name: str, status: str) -> None:
        click.echo(f"    {exp_name}: {status}")

    def experiment_retry(self, attempt: int, max_retries: int) -> None:
        click.echo(f"    Retry {attempt}/{max_retries}...")

    def experiment_high_failure_rate(self, failures: int, total: int) -> None:
        click.echo(f"    [!] High failure rate ({failures}/{total}), stopping experiments")

    def experiment_strategy_redirect(self, category: str, count: int) -> None:
        click.echo(
            f"    [!] Strategy redirect: {count} failures in category '{category}', "
            f"trying fundamentally different approach"
        )

    def experiment_advisory_requested(self) -> None:
        click.echo("    [advisory] Requesting team advisory on alternative approaches")

    def experiment_cross_round_breaker(self, failures: int, total: int) -> None:
        click.echo(
            f"    [!] Cross-round circuit breaker fired ({failures}/{total} failed), "
            f"stopping experiments"
        )

    def experiment_budget_exhausted(self, total: int) -> None:
        click.echo(f"    [!] Experiment budget exhausted ({total} experiments), stopping execution")

    def experiment_skipped(self, exp_name: str, failed_deps: list[str]) -> None:
        click.echo(f"    [skip] {exp_name}: dependency failed ({', '.join(failed_deps)})")

    def experiment_review_requested(self, exp_name: str, reviewer_role: str) -> None:
        click.echo(f"    [review] {exp_name}: requesting pre-execution review from {reviewer_role}")

    def experiment_review_passed(self, exp_name: str) -> None:
        click.echo(f"    [review] {exp_name}: PASS")

    def experiment_review_issues(self, exp_name: str) -> None:
        click.echo(f"    [review] {exp_name}: issues found, requesting fixes")

    def sprint_start(self, sprint_num: int, num_sprints: int) -> None:
        click.echo(f"  === Sprint {sprint_num}/{num_sprints} ===")

    def sprint_design_proposed(self, sprint_num: int) -> None:
        click.echo(f"    [design] Sprint {sprint_num}: experiment plan proposed")

    def sprint_design_review(self, sprint_num: int, reviewer_role: str) -> None:
        click.echo(f"    [review] Sprint {sprint_num}: {reviewer_role} reviewing design")

    def sprint_checkpoint(self, sprint_num: int, agent_role: str) -> None:
        click.echo(f"    [checkpoint] Sprint {sprint_num}: {agent_role} assessing results")

    def sprint_early_stop(self, sprint_num: int) -> None:
        click.echo("    [sprint] Team declares experiments sufficient")

    def sprint_pivot_stop(self, sprint_num: int) -> None:
        click.echo("    [sprint] Team recommends STOP AND PIVOT — halting execution")

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def writing_round(self, round_name: str) -> None:
        click.echo(f"  Round {round_name}...")

    def writing_section_drafting(self) -> None:
        click.echo("  Round 1: Section drafting...")

    def writing_assembly(self) -> None:
        click.echo("  Round 2: Assembly...")

    def writing_no_writer(self) -> None:
        click.echo("    [!] No writer agent found, assembling from sections")

    def writing_assembly_retry(self, attempt: int, error: Exception) -> None:
        click.echo(f"    [assembly] API error, retrying ({attempt})...")

    def writing_assembly_error(self, error: str | Exception) -> None:
        click.echo(f"    [!] Writer assembly failed: {error}")

    def paper_saved(self, paper_id: str) -> None:
        click.echo(f"  Paper saved: {paper_id}")

    def paper_too_short(self, length: int, minimum: int) -> None:
        click.echo(
            f"  [!] Paper too short ({length} chars, minimum {minimum}). Writing phase failed."
        )

    def figure_copied(self, filename: str) -> None:
        click.echo(f"  Figure copied: {filename}")

    def conceptual_figures_start(self, count: int) -> None:
        click.echo(f"  Generating {count} conceptual figure(s)...")

    def conceptual_figure_generating(self, fig_num: int) -> None:
        click.echo(f"    Generating Figure {fig_num}...")

    def conceptual_figure_success(self, fig_num: int) -> None:
        click.echo(f"    Figure {fig_num} generated")

    def conceptual_figure_error(self, fig_num: int, error: str | Exception) -> None:
        click.echo(f"    [!] Figure {fig_num} error: {error}")

    def conceptual_figure_failed(self, fig_num: int, reason: str) -> None:
        click.echo(f"    [!] Figure {fig_num} failed: {reason}")

    def conceptual_figure_no_code(self, fig_num: int) -> None:
        click.echo(f"    [!] Figure {fig_num}: no code block in response")

    def conceptual_figure_no_output(self, fig_num: int) -> None:
        click.echo(f"    [!] Figure {fig_num}: code ran but no PNG produced")

    def conceptual_figures_complete(self, count: int) -> None:
        click.echo(f"  Conceptual figures complete: {count} generated")

    def code_saved(self, count: int) -> None:
        click.echo(f"  Saved {count} code file(s) to code/")

    def conceptual_figures_none(self) -> None:
        click.echo("  [!] All conceptual figure attempts failed, stripping references")

    def execution_failed_abort(self, caveats: list[str]) -> None:
        click.echo("  Aborting before writing \u2014 experiments produced no usable output.")
        for c in caveats:
            click.echo(f"    - {c}")

    def writing_failed_skip_review(self) -> None:
        click.echo("  Skipping review/submission \u2014 writing produced too little content.")

    def writing_failed_review_exhausted(self, status: str = "revision_exhausted") -> None:
        if status == "review_rejected":
            click.echo("  Internal review rejected the paper.")
        else:
            click.echo("  Internal review never accepted the paper after revisions.")

    # ------------------------------------------------------------------
    # Review
    # ------------------------------------------------------------------

    def review_iteration(self, iteration: int, max_iterations: int) -> None:
        click.echo(f"  Review iteration {iteration}/{max_iterations}...")

    def review_no_editor(self) -> None:
        click.echo("    [!] No editor agent found, skipping review")

    def review_editor_retry(self, attempt: int, error: Exception) -> None:
        click.echo(f"    [review] Editor API error, retrying ({attempt})...")

    def review_editor_error(self, error: str | Exception) -> None:
        click.echo(f"    [!] Editor review failed: {error}")

    def review_recommendation(self, recommendation: str, num_changes: int) -> None:
        click.echo(f"    Editor recommendation: {recommendation} ({num_changes} required changes)")

    def review_rejected(self) -> None:
        click.echo("  [!] Editor REJECTED paper — fundamentally flawed, stopping review")

    def review_revising(self) -> None:
        click.echo("    Revising...")

    def review_max_iterations(self) -> None:
        click.echo("  [!] Max review iterations reached without editor acceptance")

    def review_too_short(self, length: int) -> None:
        click.echo(f"  [!] Paper body too short for review ({length} chars), skipping")

    def revision_error(self, error: str | Exception) -> None:
        click.echo(f"    [!] Revision failed: {error}")

    # ------------------------------------------------------------------
    # Submission / desk review
    # ------------------------------------------------------------------

    def desk_review_result(self, passed: bool) -> None:
        if passed:
            click.echo("  Desk review passed \u2014 sending to peer review")
        else:
            click.echo("  Desk REJECTED")

    def desk_review_no_editor(self) -> None:
        click.echo("  [!] No editor agent found, auto-accepting for desk review")

    def desk_review_error(self, error: str | Exception) -> None:
        click.echo(f"  [!] Desk review failed: {error}, auto-accepting")

    # ------------------------------------------------------------------
    # Peer review
    # ------------------------------------------------------------------

    def peer_review_start(self, num_reviewers: int) -> None:
        click.echo(f"Phase: PEER_REVIEW ({num_reviewers} reviewers)")

    def peer_review_result(self, reviewer_id: str, recommendation: str, avg_score: float) -> None:
        click.echo(f"    {reviewer_id}: {recommendation} (avg score: {avg_score:.1f})")

    def peer_review_error(self, reviewer_id: str, error: str | Exception) -> None:
        click.echo(f"    [!] {reviewer_id} review failed: {error}")

    def peer_review_decision(self, decision: str) -> None:
        click.echo(f"  Decision: {decision}")

    # ------------------------------------------------------------------
    # Revision (peer review)
    # ------------------------------------------------------------------

    def revision_start(self) -> None:
        click.echo("Phase: REVISION")

    def revision_no_writer(self) -> None:
        click.echo("  [!] No writer agent found, skipping revision")

    def revision_complete(self) -> None:
        click.echo("  Revision complete")

    def revision_phase_error(self, error: str | Exception) -> None:
        click.echo(f"  [!] Revision failed: {error}")

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------

    def topics_assigned(
        self, topics: list[str], *, stage: str = "final", agent_id: str = ""
    ) -> None:
        click.echo(f"  Topics ({stage}): {', '.join(topics)}")

    def paper_published(self) -> None:
        click.echo("  Paper PUBLISHED")

    def paper_rejected(self) -> None:
        click.echo("  Paper REJECTED")

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def checkpoint_saved(self, label: str) -> None:
        click.echo(f"  Checkpoint saved ({label})")

    def checkpoint_error(self, error: str | Exception) -> None:
        click.echo(f"  [!] Checkpoint failed: {error}")

    # ------------------------------------------------------------------
    # Token usage / summary
    # ------------------------------------------------------------------

    def token_summary(
        self,
        total_k: float,
        input_k: float,
        output_k: float,
        time_str: str,
    ) -> None:
        click.echo(
            f"\nToken usage: {total_k:.1f}K total ({input_k:.1f}K input, {output_k:.1f}K output)"
        )
        click.echo(f"Elapsed time: {time_str}")

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def memory_generating(self) -> None:
        click.echo("Generating agent memories via reflection...")

    def memory_stored(self, total: int, agent_count: int) -> None:
        click.echo(f"  Stored {total} memories across {agent_count} agents.")

    def memory_error(self, error: str | Exception) -> None:
        click.echo(f"  Warning: memory reflection failed ({error}), continuing.")

    # ------------------------------------------------------------------
    # General info / warning / error
    # ------------------------------------------------------------------

    def info(self, message: str) -> None:
        click.echo(message)

    def warning(self, message: str) -> None:
        click.echo(message)

    def error(self, message: str, *, err: bool = False) -> None:
        click.echo(message, err=err)

    # ------------------------------------------------------------------
    # Main.py specific
    # ------------------------------------------------------------------

    def testing_mode(self) -> None:
        click.echo("Testing mode: all agents using open-weight models via Together.ai")

    def cycle_complete(self, thread_id: str) -> None:
        click.echo(f"Research cycle complete. Thread ID: {thread_id}")

    def cycle_interrupted(self) -> None:
        click.echo("\nResearch cycle interrupted.", err=True)

    def cycle_error(self, error: str | Exception) -> None:
        click.echo(f"Error during research cycle: {error}", err=True)

    def prompt_loaded(self, path: str, length: int) -> None:
        click.echo(f"Loaded prompt from {path} ({length} chars)")

    def fresh_corpus(self, path: object) -> None:
        click.echo(f"Fresh corpus: using isolated vector DB at {path}")

    def starting_cycle(self, mode: str) -> None:
        click.echo(f"Starting {mode} research cycle...")

    def rounds_override(self, rounds: int) -> None:
        click.echo(f"Rounds per phase: {rounds} (override)")

    def interactive_mode(self) -> None:
        click.echo("Interactive mode: will pause before major phase transitions")

    # ------------------------------------------------------------------
    # Seed discovery
    # ------------------------------------------------------------------

    def seed_discovery_start(self) -> None:
        click.echo("  Seed discovery: querying Perplexity for initial literature...")

    def seed_discovery_complete(self, num_papers: int) -> None:
        click.echo(f"  Seed discovery complete: {num_papers} papers found")

    def seed_discovery_error(self, error: str | Exception) -> None:
        click.echo(f"  [!] Seed discovery failed: {error}")

    # ------------------------------------------------------------------
    # Citation grounding
    # ------------------------------------------------------------------

    def citation_grounding_start(self) -> None:
        click.echo("  Citation grounding: processing sections...")

    def citation_grounding_complete(self, num_citations: int) -> None:
        click.echo(f"  Citation grounding complete: {num_citations} citations added")

    def citation_grounding_error(self, error: str | Exception) -> None:
        click.echo(f"  [!] Citation grounding failed: {error}")

    # ------------------------------------------------------------------
    # Novelty checking
    # ------------------------------------------------------------------

    def novelty_check_start(self, mode: str) -> None:
        click.echo(f"  Novelty check ({mode})...")

    def novelty_warning(self, result: object) -> None:
        click.echo("  [!] Novelty check: idea may not be novel")

    def novelty_confirmed(self) -> None:
        click.echo("  Novelty check: idea appears novel")
