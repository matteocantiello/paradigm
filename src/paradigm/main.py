"""CLI entry point for Paradigm."""

import asyncio
import sys
import uuid
from pathlib import Path

import click

from paradigm.config import Config, load_config


def _run_research(
    config: Config,
    seed_prompt: str,
    mode: str,
    rounds: int | None = None,
    interactive: bool = False,
    testing: bool = False,
    verbose: bool = False,
    fresh_corpus: bool = False,
) -> str | None:
    """Run a research cycle synchronously (wraps async engine).

    Args:
        config: Application configuration.
        seed_prompt: Research prompt or topic.
        mode: Operating mode.
        rounds: Optional rounds-per-phase override.
        interactive: Whether to prompt for confirmation before phase transitions.
        testing: Whether to apply testing_overrides (swap to open-weight models).
        verbose: Use plain-text output instead of Rich UI.
        fresh_corpus: Start with an empty internal corpus (avoids cross-domain contamination).
    """
    from paradigm.display import DisplayManager

    display = DisplayManager(verbose=verbose)

    # Apply testing overrides before creating any agents
    if testing:
        config.apply_testing_overrides()
        display.testing_mode()
    from paradigm.agents.factory import AgentFactory
    from paradigm.agents.skills import SkillRegistry
    from paradigm.literature.corpus import Corpus
    from paradigm.logging.events import EventLogger
    from paradigm.orchestrator.engine import InterventionHook, OrchestrationEngine
    from paradigm.storage.database import Database

    # Load domain profile
    domain_profile = config.get_domain_profile()

    database = Database(config.storage.db_path)
    logger = EventLogger(config.storage.log_path)

    # Set up skill registry (optional, may not be available)
    skill_registry = None
    if config.skills.skills_dir.is_dir():
        try:
            skill_registry = SkillRegistry(config.skills.skills_dir)
        except Exception:
            pass

    from paradigm.literature.provider_factory import create_source_providers

    # Fresh corpus: use an isolated temporary vector DB so the internal
    # corpus starts empty (prevents cross-domain contamination).
    _fresh_corpus_dir: Path | None = None
    if fresh_corpus:
        import tempfile

        _fresh_corpus_dir = Path(tempfile.mkdtemp(prefix="paradigm_corpus_"))
        config.storage.vector_db_path = _fresh_corpus_dir / "vector_db"
        display.fresh_corpus(_fresh_corpus_dir)

    factory = AgentFactory(
        config,
        skill_registry=skill_registry,
        prompts_dir=domain_profile.prompts_dir,
    )

    # Generate a cycle-specific ChromaDB collection name to isolate
    # literature embeddings across research cycles.
    cycle_id = uuid.uuid4().hex[:12]
    collection_name = f"paradigm_papers_{cycle_id}"

    source_providers = create_source_providers(
        provider_configs=domain_profile.source_providers,
        literature_config=config.literature,
        storage_config=config.storage,
        database=database,
        logger=logger,
        collection_name=collection_name,
    )
    corpus = Corpus(
        database=database,
        literature_config=config.literature,
        storage_config=config.storage,
        logger=logger,
        source_providers=source_providers or None,
        topic=seed_prompt,
        collection_name=collection_name,
    )
    # Override rounds per phase if specified
    if rounds is not None:
        config.orchestrator.max_rounds_per_phase = rounds

    # Build intervention hook for interactive mode
    hook: InterventionHook | None = None
    if interactive:

        def _interactive_hook(thread_id: str, from_phase: str, to_phase: str) -> str:
            if click.confirm(f"Proceed from {from_phase} to {to_phase}?", default=True):
                return "continue"
            if click.confirm("Abort the research cycle entirely?", default=False):
                return "abort"
            return "pause"

        hook = _interactive_hook

    # Set up agent memory store (optional)
    memory_store = None
    if config.memory.enabled:
        from paradigm.agents.memory import AgentMemoryStore

        memory_store = AgentMemoryStore(
            vector_db_path=config.storage.vector_db_path,
            collection_name=config.memory.collection_name,
        )

    engine = OrchestrationEngine(
        config=config,
        database=database,
        corpus=corpus,
        logger=logger,
        agent_factory=factory,
        intervention_hook=hook,
        memory_store=memory_store,
        display=display,
        domain_profile=domain_profile,
    )

    display.start()
    result_thread_id: str | None = None
    try:
        result_thread_id = asyncio.run(
            engine.run_research_cycle(seed_prompt=seed_prompt, mode=mode)
        )
        display.cycle_complete(result_thread_id)
    except KeyboardInterrupt:
        display.cycle_interrupted()
        sys.exit(130)
    except Exception as e:
        display.cycle_error(e)
        sys.exit(1)
    finally:
        display.stop()
        database.close()
        # Clean up temporary corpus directory
        if _fresh_corpus_dir and _fresh_corpus_dir.exists():
            import shutil

            shutil.rmtree(_fresh_corpus_dir, ignore_errors=True)
    return result_thread_id


@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.pass_context
def cli(ctx: click.Context, config: Path | None) -> None:
    """Paradigm - Agentic science platform.

    Where AI agents collaborate to do research, write papers, and submit to peer review.
    """
    # Load configuration
    try:
        ctx.obj = load_config(config)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--mode",
    type=click.Choice(
        ["directed", "explore", "hypothesis", "experimental", "replication", "review"]
    ),
    default="directed",
    help="Research operating mode",
)
@click.option(
    "--prompt",
    type=str,
    help="Research prompt or question (for directed mode)",
)
@click.option(
    "--prompt-file",
    type=click.Path(exists=True, path_type=Path),
    help="Read research prompt from a file (e.g. prompt.md)",
)
@click.option(
    "--topic",
    type=str,
    help="Research topic (for exploratory mode)",
)
@click.option(
    "--rounds",
    type=int,
    default=None,
    help="Rounds per phase (overrides config)",
)
@click.option(
    "--interactive",
    is_flag=True,
    default=False,
    help="Pause for confirmation before each major phase transition",
)
@click.option(
    "--testing",
    is_flag=True,
    default=False,
    help="Use open-weight models only (no Anthropic API calls)",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Use plain-text output instead of Rich terminal UI",
)
@click.option(
    "--network-access",
    is_flag=True,
    default=False,
    help="Allow sandbox containers to access the network (less secure)",
)
@click.option(
    "--fresh-corpus",
    is_flag=True,
    default=False,
    help="Start with an empty internal corpus (avoids cross-domain contamination)",
)
@click.pass_obj
def run(
    config: Config,
    mode: str,
    prompt: str | None,
    prompt_file: Path | None,
    topic: str | None,
    rounds: int | None,
    interactive: bool,
    testing: bool,
    verbose: bool,
    network_access: bool,
    fresh_corpus: bool,
) -> None:
    """Run a research cycle.

    Examples:
        paradigm run --mode directed --prompt "Explain the period-luminosity relation"
        paradigm run --mode directed --prompt-file prompt.md
        paradigm run --mode explore --topic "massive star variability"
    """
    from paradigm.display import DisplayManager

    display = DisplayManager(verbose=verbose)

    # Read prompt from file if provided
    if prompt_file:
        if prompt:
            click.echo("Error: --prompt and --prompt-file are mutually exclusive", err=True)
            sys.exit(1)
        prompt = prompt_file.read_text().strip()
        if not prompt:
            click.echo(f"Error: prompt file is empty: {prompt_file}", err=True)
            sys.exit(1)
        display.prompt_loaded(str(prompt_file), len(prompt))

    if mode in ("directed", "review") and not prompt:
        click.echo(f"Error: --prompt or --prompt-file required for {mode} mode", err=True)
        sys.exit(1)

    if mode == "explore" and not topic:
        click.echo("Error: --topic required for exploratory mode", err=True)
        sys.exit(1)

    # Override sandbox network mode if --network-access flag is set
    if network_access:
        config.sandbox.network_mode = "bridge"

    seed_prompt = prompt or topic or ""
    display.starting_cycle(mode)
    if network_access:
        display.network_access_warning()
    if rounds is not None:
        display.rounds_override(rounds)
    if interactive:
        display.interactive_mode()
    _run_research(
        config,
        seed_prompt,
        mode,
        rounds=rounds,
        interactive=interactive,
        testing=testing,
        verbose=verbose,
        fresh_corpus=fresh_corpus,
    )


@cli.command()
@click.pass_obj
def status(config: Config) -> None:
    """Show status of active research threads and system statistics."""
    from paradigm.storage.database import Database

    database = Database(config.storage.db_path)
    try:
        usage = database.get_token_usage()
        click.echo("System Status:")
        click.echo(f"  Total tokens used: {usage['total_tokens']:,}")
        click.echo(f"  Input tokens: {usage['input_tokens']:,}")
        click.echo(f"  Output tokens: {usage['output_tokens']:,}")
    finally:
        database.close()


@cli.command()
@click.option(
    "--thread",
    type=str,
    required=True,
    help="Thread ID to inspect",
)
@click.pass_obj
def inspect(config: Config, thread: str) -> None:
    """Inspect a research thread checkpoint.

    Shows the current state, participants, findings, and next steps.
    """
    from paradigm.storage.checkpoints import CheckpointManager
    from paradigm.storage.database import Database

    database = Database(config.storage.db_path)
    try:
        mgr = CheckpointManager(database, provider=config.get_provider())
        checkpoint = mgr.load_checkpoint(thread)
        if checkpoint:
            click.echo(checkpoint.to_context_string())
        else:
            click.echo(f"No checkpoint found for thread: {thread}")
    finally:
        database.close()


@cli.command()
@click.option(
    "--status",
    "paper_status",
    type=click.Choice(["draft", "submitted", "in_review", "published", "rejected"]),
    help="Filter by paper status",
)
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of papers to show",
)
@click.pass_obj
def papers(config: Config, paper_status: str | None, limit: int) -> None:
    """List papers in the system."""
    from paradigm.storage.database import Database

    database = Database(config.storage.db_path)
    try:
        results = database.list_papers(status=paper_status, limit=limit)
        if not results:
            click.echo("No papers found.")
            return
        click.echo(f"{'ID':<25} {'Status':<12} {'Title'}")
        click.echo("-" * 80)
        for p in results:
            title = p["title"][:40] + "..." if len(p["title"]) > 40 else p["title"]
            click.echo(f"{p['id']:<25} {p['status']:<12} {title}")
    finally:
        database.close()


@cli.command()
@click.argument("paper_id")
@click.option(
    "--export",
    type=click.Path(path_type=Path),
    default=None,
    help="Export paper to a markdown file",
)
@click.pass_obj
def paper(config: Config, paper_id: str, export: Path | None) -> None:
    """View a specific paper, or export it to a file.

    Examples:
        paradigm paper paper-abc123
        paradigm paper paper-abc123 --export output.md
    """
    import json

    from paradigm.storage.database import Database

    database = Database(config.storage.db_path)
    try:
        result = database.get_paper(paper_id)
        if result is None:
            click.echo(f"Paper not found: {paper_id}", err=True)
            sys.exit(1)

        if export:
            export.write_text(result["body"])
            click.echo(f"Exported to {export}")
            return

        # Display paper metadata + body
        click.echo(f"Title:    {result['title']}")
        click.echo(f"Status:   {result['status']}")
        authors = json.loads(result["authors"]) if result["authors"] else []
        click.echo(f"Authors:  {', '.join(authors)}")
        click.echo(f"Created:  {result['created_at']}")
        click.echo("-" * 80)
        click.echo(result["body"])
    finally:
        database.close()


@cli.command(name="eval")
@click.option(
    "--judge/--no-judge",
    default=False,
    help="Score with the LLM taste judge in addition to deterministic metrics (costs API tokens).",
)
@click.option(
    "--judge-role",
    default="editor",
    help="Config role used to pick the judge provider/model.",
)
@click.option("--limit", type=int, default=None, help="Max papers to score (most recent first).")
@click.option(
    "--include-external",
    is_flag=True,
    default=False,
    help="Also score ingested external papers (default: only papers this system generated).",
)
@click.option(
    "--live",
    type=int,
    default=0,
    help="Run N live cycles end-to-end (from --split) and score the fresh output.",
)
@click.option(
    "--split",
    type=click.Choice(["train", "selection", "test"]),
    default="selection",
    help="Seed split to draw --live cycles from (default: selection).",
)
@click.pass_obj
def eval_cmd(
    config: Config,
    judge: bool,
    judge_role: str,
    limit: int | None,
    include_external: bool,
    live: int,
    split: str,
) -> None:
    """Score research papers on a deterministic + (optional) LLM rubric.

    Examples:
        paradigm eval
        paradigm eval --judge --limit 20
        paradigm eval --live 3 --split selection --judge
    """
    from paradigm.eval.harness import (
        JudgeContext,
        render_report,
        run_live_eval,
        run_offline_eval,
        write_report,
    )
    from paradigm.storage.database import Database

    judge_ctx = None
    if judge:
        try:
            provider, model, extra_body = config.get_provider_and_model_for_role(judge_role)
            judge_ctx = JudgeContext(provider=provider, model=model, extra_body=extra_body)
        except Exception as e:  # noqa: BLE001 — degrade gracefully without the judge
            click.echo(
                f"[!] Could not initialize the judge ({e}); using deterministic-only scoring.",
                err=True,
            )

    if live:
        from paradigm.eval.seeds import DEFAULT_SEEDS, split_seeds

        chosen = split_seeds(DEFAULT_SEEDS).get(split, [])[:live]
        if not chosen:
            raise click.ClickException(f"No seeds in the '{split}' split to run.")
        click.echo(f"Running {len(chosen)} live cycle(s) from the '{split}' split...")
        database = Database(config.storage.db_path)
        try:
            report = run_live_eval(
                run_cycle=lambda seed: _run_research(config, seed.prompt, mode="directed"),
                seeds=chosen,
                database=database,
                papers_dir=config.storage.papers_dir,
                judge=judge_ctx,
            )
        finally:
            database.close()
    else:
        database = Database(config.storage.db_path)
        try:
            report = run_offline_eval(
                database,
                config.storage.papers_dir,
                limit=limit,
                include_external=include_external,
                judge=judge_ctx,
            )
        finally:
            database.close()

    if report.count == 0:
        click.echo("No papers to score.")
        return

    click.echo(render_report(report))
    out_dir = config.storage.data_dir / "eval"
    json_path, csv_path = write_report(report, out_dir)
    click.echo(f"\nWrote {json_path}\n      {csv_path}")


@cli.command()
@click.pass_obj
def agents(config: Config) -> None:
    """List agents and their statistics."""
    click.echo("Agents:")
    click.echo("(Implementation pending - Phase 2)")


# ---------------------------------------------------------------------------
# Memory CLI group
# ---------------------------------------------------------------------------


@cli.group()
def memory() -> None:
    """Manage agent episodic memories."""


@memory.command("list")
@click.option("--agent", "agent_id", type=str, required=True, help="Agent ID (e.g. theorist-0)")
@click.option("--limit", type=int, default=20, help="Max memories to show")
@click.pass_obj
def memory_list(config: Config, agent_id: str, limit: int) -> None:
    """List memories for an agent, newest first."""
    from paradigm.agents.memory import AgentMemoryStore

    store = AgentMemoryStore(
        vector_db_path=config.storage.vector_db_path,
        collection_name=config.memory.collection_name,
    )
    memories = store.get_memories_for_agent(agent_id, limit=limit)
    if not memories:
        click.echo(f"No memories found for agent: {agent_id}")
        return

    click.echo(f"Memories for {agent_id} ({len(memories)} shown):\n")
    for m in memories:
        meta = m.get("metadata", {})
        mem_type = meta.get("memory_type", "?")
        created = meta.get("created_at", "")[:10]
        doc = m.get("document", "")
        # Strip type prefix from document
        content = doc
        if doc.startswith("[") and "] " in doc:
            content = doc.split("] ", 1)[1]
        click.echo(f"  [{mem_type}] ({created}) {content}")


@memory.command("search")
@click.option("--query", type=str, required=True, help="Search query")
@click.option("--agent", "agent_id", type=str, default=None, help="Filter by agent ID")
@click.option("--limit", type=int, default=10, help="Max results")
@click.pass_obj
def memory_search(config: Config, query: str, agent_id: str | None, limit: int) -> None:
    """Semantic search across agent memories with recency re-ranking."""
    from paradigm.agents.memory import AgentMemoryStore, rank_memories_with_recency

    store = AgentMemoryStore(
        vector_db_path=config.storage.vector_db_path,
        collection_name=config.memory.collection_name,
    )
    raw = store.search(query=query, agent_id=agent_id, n_results=limit * 4)
    ranked = rank_memories_with_recency(
        raw,
        half_life_days=config.memory.recency_half_life_days,
        top_k=limit,
    )
    if not ranked:
        click.echo("No matching memories found.")
        return

    click.echo(f"Search results for '{query}':\n")
    for r in ranked:
        meta = r.get("metadata", {})
        agent = meta.get("agent_id", "?")
        mem_type = meta.get("memory_type", "?")
        created = meta.get("created_at", "")[:10]
        score = r.get("combined_score", 0.0)
        doc = r.get("document", "")
        content = doc
        if doc.startswith("[") and "] " in doc:
            content = doc.split("] ", 1)[1]
        click.echo(f"  {score:.3f} [{agent}/{mem_type}] ({created}) {content}")


@memory.command("clear")
@click.option(
    "--older-than",
    type=str,
    required=True,
    help="Delete memories older than this (e.g. 30d, 90d)",
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
@click.pass_obj
def memory_clear(config: Config, older_than: str, yes: bool) -> None:
    """Prune old memories."""
    from datetime import UTC, datetime, timedelta

    from paradigm.agents.memory import AgentMemoryStore

    # Parse duration string (e.g. "30d")
    if not older_than.endswith("d"):
        click.echo("Error: --older-than must be in days (e.g. 30d)", err=True)
        sys.exit(1)
    try:
        days = int(older_than[:-1])
    except ValueError:
        click.echo(f"Error: invalid duration: {older_than}", err=True)
        sys.exit(1)

    store = AgentMemoryStore(
        vector_db_path=config.storage.vector_db_path,
        collection_name=config.memory.collection_name,
    )

    cutoff = datetime.now(UTC) - timedelta(days=days)
    total = store.count()
    click.echo(f"Total memories: {total}")
    click.echo(f"Will delete memories older than {days} days (before {cutoff.date()})")

    if not yes and not click.confirm("Proceed?"):
        click.echo("Aborted.")
        return

    deleted = store.delete_older_than(cutoff)
    click.echo(f"Deleted {deleted} memories. Remaining: {store.count()}")


@cli.command(name="mcp-login")
@click.pass_obj
def mcp_login(config: Config) -> None:
    """One-time browser login to the configured literature MCP server (OAuth).

    alphaXiv's MCP server is OAuth-gated (no static API key). This opens a browser
    to authenticate, then caches the token under ~/.paradigm/mcp/<name>/ so the
    orchestrator can use it headlessly afterward (auto-refreshed).
    """
    mcp = config.literature.mcp
    if mcp.auth_mode != "oauth":
        click.echo(
            f"MCP provider '{mcp.name}' uses auth_mode={mcp.auth_mode!r} — no OAuth login needed."
        )
        return
    try:
        from paradigm.literature.mcp_auth import interactive_login
    except ImportError:
        click.echo("The 'mcp' package is required. Install: pip install paradigm[mcp]", err=True)
        sys.exit(1)

    click.echo(f"Logging in to MCP server '{mcp.name}' at {mcp.server_url} …")
    try:
        tools = asyncio.run(
            interactive_login(server_url=mcp.server_url, name=mcp.name, scope=mcp.oauth_scope)
        )
    except Exception as e:
        click.echo(f"Login failed: {e}", err=True)
        click.echo(
            "If the server rejects dynamic client registration, it may need a "
            "pre-registered client id — tell me and I'll add that path.",
            err=True,
        )
        sys.exit(1)
    click.echo(f"✓ Logged in to '{mcp.name}'. Token cached. Tools: {', '.join(tools)}")


if __name__ == "__main__":
    cli()
