"""``promote``, ``release`` and ``revoke``."""

from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_cli.output import echo_lines


def promote() -> None:
    """Open the promote PR from staging to main."""
    result = core.promote(build_context(Path.cwd(), need_actor=True))
    if result.pull_request is None:
        typer.echo("Main already has everything on staging.")
        return
    typer.echo(f"Promote PR {result.status}: {result.pull_request.url}")
    if result.items:
        typer.echo("Changed items:")
        echo_lines(result.items)
    for approval in result.approvals:
        typer.echo(
            f"  approved {approval.item} {approval.version or ''} by "
            f"{', '.join(approval.reviewers)} ({approval.pull_request})"
        )


def release() -> None:
    """Tag main as marketplace-vYYYY.MM.DD[.N]."""
    result = core.release(build_context(Path.cwd()))
    if result.status == "up-to-date":
        typer.echo(f"Main is already released as {result.tag}.")
        return
    typer.echo(f"Tagged {result.tag} at {result.commit[:12]}.\n")
    typer.echo(result.notes)


def revoke(
    item: str,
    to: Annotated[
        str | None,
        typer.Option(help="Roll back to the item as it is at this tag or ref."),
    ] = None,
    rollback: Annotated[
        bool, typer.Option(help="Roll back to the last approved release.")
    ] = False,
    reason: Annotated[str, typer.Option(help="Why, for the PR body.")] = "",
) -> None:
    """Remove or roll back an item on main through a hotfix PR."""
    result = core.revoke(
        build_context(Path.cwd(), need_actor=True),
        item,
        to=to,
        rollback=rollback,
        reason=reason,
    )
    typer.echo(f"{result.item}: {result.action}")
    typer.echo(f"  Hotfix PR: {result.pull_request.url}")
    typer.echo(f"  Back-merge PR: {result.back_merge.url}")
    if result.affected_clients:
        typer.echo("Affected clients:")
        echo_lines([f"{c.name} ({c.ref})" for c in result.affected_clients])
    if result.unknown_clients:
        typer.echo("Clients with a ref that was not found:")
        echo_lines([f"{c.name} ({c.ref})" for c in result.unknown_clients])
