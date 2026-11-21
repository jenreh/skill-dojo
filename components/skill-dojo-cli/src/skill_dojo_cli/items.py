"""Item commands: ``mirror``, ``bundle``, ``local``, ``lock`` and ``sync``."""

from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_cli.output import echo_lines
from skill_dojo_core import not_implemented

bundle_app = typer.Typer(help="Build plugins out of parts from several sources.")
local_app = typer.Typer(help="Register the team's own plugins.")
lock_app = typer.Typer(help="Maintain registry/lock.json.")

ItemOption = Annotated[str | None, typer.Option(help="Only this item.")]


def echo_candidate(result: core.CandidateResult) -> None:
    where = f" {result.pull_request.url}" if result.pull_request else ""
    typer.echo(f"{result.item}: {result.status}{where}")
    for flag in result.flags:
        line = f":{flag.line}" if flag.line else ""
        typer.echo(f"  {flag.kind} {flag.path}{line} {flag.detail}")


def mirror(
    source_id: str,
    plugin: str,
    item: Annotated[
        str | None, typer.Option("--as", help="Item id (default: plugin name).")
    ] = None,
) -> None:
    """Mirror one upstream plugin as a candidate PR into staging."""
    ctx = build_context(Path.cwd(), need_actor=True)
    echo_candidate(core.mirror(ctx, source_id, plugin, item_id=item))


def sync(item: ItemOption = None) -> None:
    """Open candidate PRs for upstream changes."""
    result = core.sync(build_context(Path.cwd(), need_actor=True), item=item)
    if not result.candidates:
        typer.echo("No mirrors to sync.")
    for candidate in result.candidates:
        echo_candidate(candidate)


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
def local_add(
    plugin_dir: Annotated[str, typer.Argument(help="A folder in plugins/.")],
    category: Annotated[str | None, typer.Option(help="Catalog category.")] = None,
) -> None:
    """Register a local plugin directory."""
    result = core.local_add(build_context(Path.cwd()), plugin_dir, category=category)
    typer.echo(f"Added '{result.item}' (treeSha256 {result.tree_sha256[:12]}).")
    echo_lines(result.changed)


@lock_app.command("refresh")
def lock_refresh(
    item: ItemOption = None,
) -> None:
    """Recompute lock entries of local items after an edit."""
    result = core.lock_refresh(build_context(Path.cwd()), item=item)
    if not result.refreshed:
        typer.echo("All lock entries are current.")
        return
    typer.echo("Refreshed:")
    echo_lines(result.refreshed)
