"""Repo-wide commands: ``init``, ``build``, ``validate``, ``flags``, ``vendor``."""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_cli.output import echo_lines, echo_report
from skill_dojo_core import tool_pin


def init(
    name: Annotated[
        str | None, typer.Option(help="Marketplace name (default: folder name).")
    ] = None,
    repository: Annotated[
        str | None, typer.Option(help="owner/name of this repo on GitHub.")
    ] = None,
    tool_git: Annotated[
        str | None, typer.Option(help="Pin skill-dojo to this git commit SHA.")
    ] = None,
    tool_version: Annotated[
        str | None, typer.Option(help="Pin skill-dojo to this PyPI version.")
    ] = None,
    adopt: Annotated[
        bool, typer.Option(help="Register the existing plugins/ of this repo.")
    ] = False,
) -> None:
    """Scaffold a curated marketplace in this repo."""
    pin = tool_pin(
        tool_git,
        tool_version if tool_git or tool_version else version("skill-dojo"),
    )
    ctx = build_context(Path.cwd())
    if adopt:
        adopted = core.adopt(ctx, tool=pin, repository=repository)
        typer.echo(
            f"Adopted {len(adopted.items)} plugin(s) into '{adopted.marketplace}'."
        )
        echo_lines(adopted.changed)
        if adopted.floating_mcp:
            typer.echo("\nFloating MCP references (pin them, then 'lock refresh'):")
            echo_lines([str(f) for f in adopted.floating_mcp])
        if adopted.possibly_vendored:
            typer.echo("\nSkills with their own license (likely from upstream):")
            echo_lines([f.path for f in adopted.possibly_vendored])
        return
    result = core.init(ctx, name=name, tool=pin, repository=repository)
    typer.echo("Created:")
    echo_lines(result.created)


def build(
    check: Annotated[
        bool, typer.Option(help="Fail if build would change any file.")
    ] = False,
) -> None:
    """Regenerate both catalogs, manifests and the layout."""
    result = core.build(build_context(Path.cwd()), check=check)
    if not result.changed:
        typer.echo("Nothing to change.")
        return
    typer.echo("Would change:" if check else "Changed:")
    echo_lines(result.changed)
    if check:
        typer.echo("Run 'skill-dojo build' and commit the result.", err=True)
        raise typer.Exit(1)


def validate() -> None:
    """Validate plugins, skills, catalogs and registry/."""
    report = core.validate(build_context(Path.cwd()))
    echo_report(report)
    if not report.ok:
        raise typer.Exit(1)


def flags(
    base: Annotated[
        str, typer.Option(help="Compare against this ref.")
    ] = "origin/staging",
) -> None:
    """Print the risk flags (markdown) of the working tree against a base ref."""
    typer.echo(core.flags(build_context(Path.cwd()), base=base).markdown)


def vendor(
    marketplace: Annotated[str, typer.Argument(help="Marketplace git URL.")],
    ref: Annotated[
        str, typer.Option(help="Branch or release tag, e.g. marketplace-v2026.11.21.")
    ] = "main",
    name: Annotated[
        str | None, typer.Option(help="Folder under .agents/ (default: repo name).")
    ] = None,
    update: Annotated[bool, typer.Option(help="Pull the subtree again.")] = False,
) -> None:
    """Vendor a marketplace's skills into this (consumer) repo."""
    result = core.vendor(
        build_context(Path.cwd()), marketplace, ref=ref, name=name, update=update
    )
    verb = "Updated" if result.updated else "Vendored"
    typer.echo(f"{verb} {result.prefix} at {result.ref}.")
    echo_lines(result.links)
