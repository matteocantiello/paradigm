"""CLI entry point for Paradigm."""

import asyncio
import sys
from pathlib import Path

import click

from paradigm.config import Config, load_config


def _run_research(
    config: Config,
    seed_prompt: str,
    mode: str,
    rounds: int | None = None,
    interactive: bool = False,
) -> None:
    """Run a research cycle synchronously (wraps async engine).

    Args:
        config: Application configuration.
        seed_prompt: Research prompt or topic.
        mode: Operating mode.
        rounds: Optional rounds-per-phase override.
        interactive: Whether to prompt for confirmation before phase transitions.
    """
    from paradigm.agents.factory import AgentFactory
    from paradigm.agents.skills import SkillRegistry
    from paradigm.literature.corpus import Corpus
    from paradigm.logging.events import EventLogger
    from paradigm.orchestrator.engine import InterventionHook, OrchestrationEngine
    from paradigm.storage.database import Database

    database = Database(config.storage.db_path)
    logger = EventLogger(config.storage.log_path)

    # Set up skill registry (optional, may not be available)
    skill_registry = None
    if config.skills.skills_dir.is_dir():
        try:
            skill_registry = SkillRegistry(config.skills.skills_dir)
        except Exception:
            pass

    factory = AgentFactory(config, skill_registry=skill_registry)
    corpus = Corpus(
        database=database,
        literature_config=config.literature,
        storage_config=config.storage,
        logger=logger,
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

    engine = OrchestrationEngine(
        config=config,
        database=database,
        corpus=corpus,
        logger=logger,
        agent_factory=factory,
        intervention_hook=hook,
    )

    try:
        thread_id = asyncio.run(engine.run_research_cycle(seed_prompt=seed_prompt, mode=mode))
        click.echo(f"Research cycle complete. Thread ID: {thread_id}")
    except KeyboardInterrupt:
        click.echo("\nResearch cycle interrupted.", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"Error during research cycle: {e}", err=True)
        sys.exit(1)
    finally:
        database.close()


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
    type=click.Choice(["directed", "explore", "hypothesis", "experimental", "replication"]),
    default="directed",
    help="Research operating mode",
)
@click.option(
    "--prompt",
    type=str,
    help="Research prompt or question (for directed mode)",
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
@click.pass_obj
def run(
    config: Config,
    mode: str,
    prompt: str | None,
    topic: str | None,
    rounds: int | None,
    interactive: bool,
) -> None:
    """Run a research cycle.

    Examples:
        paradigm run --mode directed --prompt "Explain the period-luminosity relation"
        paradigm run --mode explore --topic "massive star variability"
    """
    if mode == "directed" and not prompt:
        click.echo("Error: --prompt required for directed mode", err=True)
        sys.exit(1)

    if mode == "explore" and not topic:
        click.echo("Error: --topic required for exploratory mode", err=True)
        sys.exit(1)

    seed_prompt = prompt or topic or ""
    click.echo(f"Starting {mode} research cycle...")
    if rounds is not None:
        click.echo(f"Rounds per phase: {rounds} (override)")
    if interactive:
        click.echo("Interactive mode: will pause before major phase transitions")
    _run_research(config, seed_prompt, mode, rounds=rounds, interactive=interactive)


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
        mgr = CheckpointManager(database, api_key=config.api_key or "")
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


@cli.command()
@click.pass_obj
def agents(config: Config) -> None:
    """List agents and their statistics."""
    click.echo("Agents:")
    click.echo("(Implementation pending - Phase 2)")


if __name__ == "__main__":
    cli()
