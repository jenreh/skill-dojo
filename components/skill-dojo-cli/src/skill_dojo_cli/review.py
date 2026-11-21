"""``review`` commands for candidate PRs."""

import typer

from skill_dojo_cli.stub import not_implemented

review_app = typer.Typer(help="Review candidate PRs into staging.")


@review_app.command("list")
def review_list() -> None:
    """List open candidate PRs."""
    not_implemented("review list")


@review_app.command("show")
def review_show(number: int) -> None:
    """Show a candidate's diff summary and risk flags."""
    not_implemented("review show")


@review_app.command("approve")
def review_approve(number: int) -> None:
    """Approve and merge a candidate PR."""
    not_implemented("review approve")


@review_app.command("reject")
def review_reject(number: int) -> None:
    """Close a candidate PR."""
    not_implemented("review reject")


@review_app.command("quarantine")
def review_quarantine(number: int) -> None:
    """Close a candidate PR and stop future candidates of its item."""
    not_implemented("review quarantine")
