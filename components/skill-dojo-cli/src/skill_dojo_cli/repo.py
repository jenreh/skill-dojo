"""Repo-wide commands: ``init``, ``build``, ``validate``, ``flags``, ``vendor``."""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_cli.output import echo_lines, echo_report
from skill_dojo_core import not_implemented, tool_pin


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
    if adopt:
        not_implemented("init --adopt")
    result = core.init(
        build_context(Path.cwd()),
        name=name,
        tool=tool_pin(
            tool_git,
            tool_version if tool_git or tool_version else version("skill-dojo"),
        ),
        repository=repository,
    )
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
    base: Annotated[str, typer.Option(help="Compare against this ref.")] = "staging",
) -> None:
    """Print the risk flags of the current branch against a base."""
    not_implemented("flags")


def vendor(
    marketplace: Annotated[str, typer.Argument(help="Marketplace git URL.")] = "",
    update: Annotated[bool, typer.Option(help="Pull the subtree again.")] = False,
) -> None:
    """Vendor a marketplace's skills into this (consumer) repo."""
    not_implemented("vendor")
