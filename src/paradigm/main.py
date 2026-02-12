"""CLI entry point for Paradigm."""

import sys
from pathlib import Path

import click

from paradigm.config import load_config


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
@click.pass_obj
def run(config: object, mode: str, prompt: str | None, topic: str | None) -> None:
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

    click.echo(f"Starting {mode} research cycle...")
    click.echo("(Implementation pending - Phase 2)")


@cli.command()
@click.pass_obj
def status(config: object) -> None:
    """Show status of active research threads and system statistics."""
    click.echo("System Status:")
    click.echo("(Implementation pending - Phase 2)")


@cli.command()
@click.option(
    "--thread",
    type=str,
    required=True,
    help="Thread ID to inspect",
)
@click.pass_obj
def inspect(config: object, thread: str) -> None:
    """Inspect a research thread checkpoint.

    Shows the current state, participants, findings, and next steps.
    """
    click.echo(f"Inspecting thread: {thread}")
    click.echo("(Implementation pending - Phase 2)")


@cli.command()
@click.option(
    "--status",
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
def papers(config: object, status: str | None, limit: int) -> None:
    """List papers in the system."""
    click.echo("Papers:")
    click.echo("(Implementation pending - Phase 5)")


@cli.command()
@click.argument("paper_id")
@click.pass_obj
def paper(config: object, paper_id: str) -> None:
    """View a specific paper.

    Shows the full paper content, metadata, and review history.
    """
    click.echo(f"Paper: {paper_id}")
    click.echo("(Implementation pending - Phase 5)")


@cli.command()
@click.pass_obj
def agents(config: object) -> None:
    """List agents and their statistics."""
    click.echo("Agents:")
    click.echo("(Implementation pending - Phase 2)")


if __name__ == "__main__":
    cli()
