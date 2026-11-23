"""Item commands: ``mirror``, ``add-parts``, ``remove-parts``, ``plugin``,
``version``, ``local``, ``lock`` and ``sync``."""

from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_cli.output import echo_lines

plugin_app = typer.Typer(help="Create the team's own plugins.")
local_app = typer.Typer(help="Register a plugin folder that is already there.")
lock_app = typer.Typer(help="Maintain registry/lock.json.")

ItemOption = Annotated[str | None, typer.Option(help="Only this item.")]


def echo_change(result: core.ChangeResult) -> None:
    pin = f" @ {result.pin[:12]}" if result.pin else ""
    typer.echo(f"{result.item}: {result.status}{pin}")
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
    """Mirror one whole upstream plugin onto the work branch."""
    echo_change(core.mirror(build_context(Path.cwd()), source_id, plugin, item_id=item))


PARTS = typer.Argument(
    help="Parts as source:plugin/kind/name (kind: skill, agent, mcp_server, hook; "
    "source 'local' = this repo)."
)


def add_parts(
    plugin: Annotated[str, typer.Argument(help="The local plugin to add to.")],
    parts: Annotated[list[str] | None, PARTS] = None,
    create: Annotated[
        bool, typer.Option("--create", help="Create the plugin first.")
    ] = False,
    description: Annotated[
        str | None, typer.Option(help="Text of a new plugin.")
    ] = None,
    category: Annotated[str | None, typer.Option(help="Catalog category.")] = None,
) -> None:
    """Copy parts of upstream plugins into a local plugin."""
    echo_change(
        core.add_parts(
            build_context(Path.cwd()),
            plugin,
            parts or [],
            create=create,
            description=description,
            category=category,
        )
    )


def remove_parts(
    plugin: str,
    parts: Annotated[list[str], typer.Argument(help="Parts as kind/name.")],
) -> None:
    """Remove parts from a local plugin."""
    echo_change(core.remove_parts(build_context(Path.cwd()), plugin, parts))


@plugin_app.command("new")
def plugin_new(
    name: str,
    description: Annotated[str | None, typer.Option(help="Plugin text.")] = None,
    category: Annotated[str | None, typer.Option(help="Catalog category.")] = None,
) -> None:
    """Create an empty local plugin (0.1.0); add files, then run 'build'."""
    result = core.plugin_new(
        build_context(Path.cwd()), name, description=description, category=category
    )
    echo_change(result)
    typer.echo(f"Put its files into plugins/{name}/, then run 'skill-dojo build'.")


def version(
    item: str,
    patch: Annotated[bool, typer.Option("--patch", help="Next patch.")] = False,
    minor: Annotated[bool, typer.Option("--minor", help="Next minor.")] = False,
    major: Annotated[bool, typer.Option("--major", help="Next major.")] = False,
    exact: Annotated[
        str | None, typer.Option("--set", help="An exact X.Y.Z above main's.")
    ] = None,
) -> None:
    """Set a local plugin's version relative to its version on main."""
    levels = [
        n for n, on in (("patch", patch), ("minor", minor), ("major", major)) if on
    ]
    if len(levels) + (exact is not None) != 1:
        raise typer.BadParameter("give exactly one of --patch, --minor, --major, --set")
    result = core.set_version(
        build_context(Path.cwd()),
        item,
        level=levels[0] if levels else None,
        exact=exact,
    )
    typer.echo(
        f"{result.item}: {result.main_version or 'new'} -> {result.branch_version}"
    )


def sync(item: ItemOption = None) -> None:
    """Write upstream changes into the work branch (finish commits them)."""
    result = core.sync(build_context(Path.cwd()), item=item)
    if result.refreshed:
        typer.echo(f"Refreshed sources: {', '.join(result.refreshed)}")
    if not result.changes:
        typer.echo("No mirrors or plugins with parts to sync.")
    for change in result.changes:
        echo_change(change)


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
def lock_refresh(item: ItemOption = None) -> None:
    """Recompute lock entries of local items after an edit."""
    result = core.lock_refresh(build_context(Path.cwd()), item=item)
    if not result.refreshed:
        typer.echo("All lock entries are current.")
        return
    typer.echo("Refreshed:")
    echo_lines(result.refreshed)
