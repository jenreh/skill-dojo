"""``clients`` commands for registry/clients.yaml."""

import typer

from skill_dojo_core import not_implemented

clients_app = typer.Typer(help="Keep the hand-kept list of clients.")


@clients_app.command("add")
def clients_add(name: str, ref: str) -> None:
    """Record that a client uses a ref or tag."""
    not_implemented("clients add")


@clients_app.command("list")
def clients_list() -> None:
    """List the clients."""
    not_implemented("clients list")


@clients_app.command("remove")
def clients_remove(name: str) -> None:
    """Remove a client."""
    not_implemented("clients remove")
