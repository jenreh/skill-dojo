"""``status``, ``finish``, ``release`` and ``revoke``."""

from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_cli.output import echo_lines


def echo_pending(pending: list[core.PendingVersion]) -> None:
    if not pending:
        typer.echo("No changed plugins.")
        return
    typer.echo("Changed plugins:")
    for p in pending:
        after = p.branch_version or "-"
        note = "" if p.editable else " (upstream version)"
        typer.echo(
            f"  {p.item} [{p.kind}, {p.status}]: {p.main_version or 'new'} -> "
            f"{after}{note}"
        )


def status() -> None:
    """Show the work branch: commits, dirty files, PR and pending versions."""
    result = core.status(build_context(Path.cwd()))
    where = "checked out" if result.on_branch else "not checked out"
    if not result.exists:
        typer.echo(f"No work branch '{result.branch}' yet; the next change creates it.")
    else:
        typer.echo(
            f"{result.branch} ({where}): {result.ahead} ahead, {result.behind} "
            f"behind origin/{result.main}" + (", merged" if result.merged else "")
        )
    if result.pull_request is not None:
        pr = result.pull_request
        typer.echo(f"PR #{pr.number} {pr.state.lower()}: {pr.url}")
    if result.dirty:
        typer.echo("Uncommitted:")
        echo_lines(result.dirty)
    echo_pending(result.pending)


def finish(
    level: Annotated[
        list[str] | None,
        typer.Option(help="item=patch|minor|major|X.Y.Z (repeatable)."),
    ] = None,
    pr: Annotated[
        bool, typer.Option("--pr/--no-pr", help="Open or update the PR into main.")
    ] = True,
) -> None:
    """Build, set versions, push the work branch and open or update its PR."""
    result = core.finish(build_context(Path.cwd()), levels=level, open_pr=pr)
    if result.status == "nothing":
        typer.echo("Nothing to finish: the work branch has no changes.")
        return
    echo_pending(result.pending)
    if result.pull_request is not None:
        typer.echo(f"PR {result.status}: {result.pull_request.url}")
    else:
        typer.echo(f"Pushed {result.branch}; open the PR into main by hand.")


def release(
    notes: Annotated[
        str | None, typer.Option(help="Release notes instead of the generated ones.")
    ] = None,
) -> None:
    """Tag main as marketplace-vYYYY.MM.DD[.N] and publish a GitHub Release."""
    result = core.release(build_context(Path.cwd()), notes=notes)
    if result.status == "up-to-date":
        typer.echo(f"Main has not changed since {result.tag}; nothing to release.")
        return
    typer.echo(f"Tagged {result.tag} at {result.commit[:12]}.")
    if result.url:
        typer.echo(f"GitHub Release: {result.url}")
    typer.echo(f"\n{result.notes}")


def revoke(
    item: str,
    to: Annotated[
        str | None,
        typer.Option(help="Roll back to the item as it is at this tag or ref."),
    ] = None,
) -> None:
    """Remove or roll back an item on the work branch."""
    result = core.revoke(build_context(Path.cwd()), item, to=to)
    typer.echo(
        f"{result.item}: {result.action}. Run 'skill-dojo finish' to open the PR."
    )
