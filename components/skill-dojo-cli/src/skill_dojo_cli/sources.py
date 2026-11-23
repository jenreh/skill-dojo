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
        SourceType | None,
        typer.Option(
            "--type", help="What the repository holds (default: detected from it)."
        ),
    ] = None,
    ref: Annotated[str, typer.Option(help="Branch or tag to track.")] = "main",
    marketplace_path: Annotated[
        str | None, typer.Option(help="Catalog path if not the default.")
    ] = None,
    allow: Annotated[
        list[str] | None, typer.Option(help="Only offer these plugins (repeatable).")
    ] = None,
) -> None:
    """Add an upstream source on the work branch and cache it."""
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


@source_app.command("refresh")
def source_refresh(
    source_id: Annotated[
        str | None, typer.Argument(help="Only this source (default: all).")
    ] = None,
) -> None:
    """Fetch the cached catalogs again."""
    core.source_refresh(build_context(Path.cwd()), source_id)
    typer.echo(f"Refreshed {source_id or 'all sources'}.")


@source_app.command("set-type")
def source_set_type(
    source_id: str,
    kind: Annotated[
        SourceType | None,
        typer.Argument(help="The new type (default: detect it from the upstream)."),
    ] = None,
) -> None:
    """Change a source's type and cache its catalog again."""
    result = core.source_set_type(build_context(Path.cwd()), source_id, kind)
    found = next(s for s in result.sources if s.id == source_id)
    typer.echo(f"Source '{source_id}' is now {found.type.value}.")


@source_app.command("allow")
def source_allow(source_id: str, plugin: str) -> None:
    """Add a plugin to a source's allowlist."""
    core.source_allow(build_context(Path.cwd()), source_id, plugin)
    typer.echo(f"Allowed '{plugin}' from '{source_id}'.")


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
    refresh: Annotated[
        bool, typer.Option(help="Fetch the source again instead of the cache.")
    ] = False,
    parts: Annotated[bool, typer.Option(help="Also list each plugin's parts.")] = False,
) -> None:
    """List what an upstream source offers (from the local cache)."""
    result = core.browse(
        build_context(Path.cwd()), source_id, search=search, refresh=refresh
    )
    cached = " (cached)" if result.cached else ""
    marketplace = f" v{result.version}" if result.version else ""
    typer.echo(f"{result.source}{marketplace} @ {result.commit}{cached}")
    for plugin in result.plugins:
        version = f" {plugin.version}" if plugin.version else ""
        where = f" ({plugin.repository})" if plugin.repository != result.source else ""
        note = f"  [cannot mirror: {plugin.unsupported}]" if plugin.unsupported else ""
        if not plugin.allowed:
            note += "  [not on the allowlist]"
        if plugin.name in result.tracked:
            note += f"  [{result.tracked[plugin.name]}]"
        typer.echo(f"  {plugin.name}{version}  {plugin.path}{where}{note}")
        if parts:
            for part in result.parts.get(plugin.name, []):
                spec = f"{result.source}:{plugin.name}/{part.kind}/{part.name}"
                typer.echo(f"      {spec} {part.version or ''}".rstrip())
