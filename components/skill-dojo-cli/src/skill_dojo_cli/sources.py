"""``source`` commands and ``browse``."""

from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_core import SourceType

source_app = typer.Typer(help="Manage upstream sources (registry/sources.yaml).")


@source_app.command("add")
def source_add(
    source_id: Annotated[str, typer.Argument(help="Id of the new source.")],
    repository: Annotated[
        str,
        typer.Argument(
            help="owner/name or a git URL; the base URL for --type mcp_registry."
        ),
    ],
    kind: Annotated[
        SourceType, typer.Option("--type", help="What the repository holds.")
    ] = SourceType.AGENT_PLUGINS_MARKETPLACE,
    ref: Annotated[str, typer.Option(help="Branch or tag to track.")] = "main",
    marketplace_path: Annotated[
        str | None, typer.Option(help="Catalog path if not the default.")
    ] = None,
    allow: Annotated[
        list[str] | None, typer.Option(help="Only offer these plugins (repeatable).")
    ] = None,
) -> None:
    """Add an upstream source."""
    core.source_add(
        build_context(Path.cwd()),
        source_id,
        repository,
        kind=kind,
        ref=ref,
        marketplace_path=marketplace_path,
        allowlist=allow,
    )
    typer.echo(f"Added source '{source_id}'.")


@source_app.command("list")
def source_list() -> None:
    """List the upstream sources."""
    for source in core.source_list(build_context(Path.cwd())).sources:
        allow = f" allow={','.join(source.allowlist)}" if source.allowlist else ""
        typer.echo(
            f"{source.id}\t{source.type.value}\t{source.repository}@{source.ref}{allow}"
        )


@source_app.command("remove")
def source_remove(source_id: str) -> None:
    """Remove an upstream source no item uses."""
    core.source_remove(build_context(Path.cwd()), source_id)
    typer.echo(f"Removed source '{source_id}'.")


def browse(
    source_id: str,
    search: Annotated[
        str | None, typer.Option(help="MCP Registry: only servers matching this.")
    ] = None,
) -> None:
    """List what an upstream source offers."""
    result = core.browse(build_context(Path.cwd()), source_id, search=search)
    typer.echo(f"{result.source} @ {result.commit}")
    for plugin in result.plugins:
        version = f" {plugin.version}" if plugin.version else ""
        where = f" ({plugin.repository})" if plugin.repository != result.source else ""
        note = f"  [cannot mirror: {plugin.unsupported}]" if plugin.unsupported else ""
        if not plugin.allowed:
            note += "  [not on the allowlist]"
        if plugin.name in result.tracked:
            note += f"  [{result.tracked[plugin.name]}]"
        typer.echo(f"  {plugin.name}{version}  {plugin.path}{where}{note}")
