"""``review`` commands for candidate PRs."""

from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context
from skill_dojo_cli.output import echo_lines

review_app = typer.Typer(help="Review candidate PRs into staging.")

ReasonOption = Annotated[str, typer.Option(help="Comment on the closed PR.")]


def echo_action(result: core.ReviewActionResult) -> None:
    pr = result.pull_request
    typer.echo(f"#{pr.number} {result.item or pr.head}: {result.status} {pr.url}")
    if result.status == "waiting":
        typer.echo("  Branch protection still blocks the merge; nothing bypassed.")
    if result.quarantine is not None:
        typer.echo(f"  Quarantine PR: {result.quarantine.url}")


@review_app.command("list")
def review_list() -> None:
    """List open candidate PRs."""
    entries = core.review_list(build_context(Path.cwd())).entries
    if not entries:
        typer.echo("No open candidates.")
    for entry in entries:
        pr = entry.pull_request
        typer.echo(f"#{pr.number} {entry.item or pr.head}: {pr.title} {pr.url}")


@review_app.command("show")
def review_show(number: int) -> None:
    """Show a candidate's changed files, risk flags and notes."""
    result = core.review_show(build_context(Path.cwd()), number)
    pr = result.pull_request
    typer.echo(f"#{pr.number} {pr.title} ({pr.head} -> {pr.base})\n{pr.url}\n")
    typer.echo("Changed files:")
    echo_lines(result.files)
    typer.echo(f"\n{pr.body}")


@review_app.command("approve")
def review_approve(number: int) -> None:
    """Approve and merge a candidate PR (or report that it waits)."""
    echo_action(core.review_approve(build_context(Path.cwd(), need_actor=True), number))


@review_app.command("reject")
def review_reject(number: int, reason: ReasonOption = "") -> None:
    """Close a candidate PR."""
    echo_action(core.review_reject(build_context(Path.cwd()), number, reason=reason))


@review_app.command("quarantine")
def review_quarantine(number: int, reason: ReasonOption = "") -> None:
    """Close a candidate PR and stop future candidates of its item."""
    ctx = build_context(Path.cwd(), need_actor=True)
    echo_action(core.review_quarantine(ctx, number, reason=reason))
