"""Item commands: ``mirror``, ``bundle``, ``local``, ``lock`` and ``sync``."""

from typing import Annotated

import typer

from skill_dojo_cli.stub import not_implemented

bundle_app = typer.Typer(help="Build plugins out of parts from several sources.")
local_app = typer.Typer(help="Register the team's own plugins.")
lock_app = typer.Typer(help="Maintain registry/lock.json.")


def mirror(source_id: str, plugin: str) -> None:
    """Mirror one upstream plugin as a candidate PR."""
    not_implemented("mirror")


def sync(
    item: Annotated[str | None, typer.Option(help="Only this item.")] = None,
) -> None:
    """Open candidate PRs for upstream changes."""
    not_implemented("sync")


@bundle_app.command("create")
def bundle_create(name: str) -> None:
    """Create a new bundle plugin."""
    not_implemented("bundle create")


@bundle_app.command("add")
def bundle_add(name: str, part: str) -> None:
    """Add a part (source:plugin/kind/name) to a bundle."""
    not_implemented("bundle add")


@bundle_app.command("remove")
def bundle_remove(name: str, part: str) -> None:
    """Remove a part from a bundle."""
    not_implemented("bundle remove")


@local_app.command("add")
def local_add(plugin_dir: str) -> None:
    """Register a local plugin directory."""
    not_implemented("local add")


@lock_app.command("refresh")
def lock_refresh(
    item: Annotated[str | None, typer.Option(help="Only this item.")] = None,
) -> None:
    """Recompute lock entries of local items after an edit."""
    not_implemented("lock refresh")
