"""Item commands: ``mirror``, ``bundle``, ``local``, ``lock`` and ``sync``."""

from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_cli.output import echo_lines

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
        typer.echo("No mirrors or bundles to sync.")
    for candidate in result.candidates:
        echo_candidate(candidate)


PARTS = typer.Argument(help="Parts as source:plugin/kind/name.")
PartsArgument = Annotated[list[str], PARTS]


@bundle_app.command("create")
def bundle_create(
    name: str,
    parts: Annotated[list[str] | None, PARTS] = None,
    description: Annotated[str | None, typer.Option(help="Plugin text.")] = None,
    category: Annotated[str | None, typer.Option(help="Catalog category.")] = None,
) -> None:
    """Create a new bundle plugin as a candidate PR."""
    ctx = build_context(Path.cwd(), need_actor=True)
    echo_candidate(
        core.bundle_create(ctx, name, parts, description=description, category=category)
    )


@bundle_app.command("add")
def bundle_add(name: str, parts: PartsArgument) -> None:
    """Add parts (source:plugin/kind/name; source 'local' = this repo)."""
    ctx = build_context(Path.cwd(), need_actor=True)
    echo_candidate(core.bundle_add(ctx, name, parts))


@bundle_app.command("remove")
def bundle_remove(
    name: str,
    parts: Annotated[list[str], typer.Argument(help="Parts as kind/name.")],
) -> None:
    """Remove parts from a bundle."""
    ctx = build_context(Path.cwd(), need_actor=True)
    echo_candidate(core.bundle_remove(ctx, name, parts))


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
