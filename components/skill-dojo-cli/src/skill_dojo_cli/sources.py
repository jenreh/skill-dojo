"""``source`` commands and ``browse``."""

from typing import Annotated

import typer

from skill_dojo_cli.stub import not_implemented

source_app = typer.Typer(help="Manage upstream sources (registry/sources.yaml).")


@source_app.command("add")
def source_add(
    source_id: Annotated[str, typer.Argument(help="Id of the new source.")],
    repository: Annotated[str, typer.Argument(help="owner/name, git URL or registry")],
    kind: Annotated[
        str, typer.Option("--type", help="Source type, e.g. claude_marketplace.")
    ] = "agent_plugins_marketplace",
    ref: Annotated[str, typer.Option(help="Branch or tag to track.")] = "main",
) -> None:
    """Add an upstream source."""
    not_implemented("source add")


@source_app.command("list")
def source_list() -> None:
    """List the upstream sources."""
    not_implemented("source list")


@source_app.command("remove")
def source_remove(source_id: str) -> None:
    """Remove an upstream source."""
    not_implemented("source remove")


def browse(source_id: str) -> None:
    """List what an upstream source offers."""
    not_implemented("browse")
