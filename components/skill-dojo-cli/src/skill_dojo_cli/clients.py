"""``clients`` commands for registry/clients.yaml."""

from pathlib import Path
from typing import Annotated

import typer

import skill_dojo_core as core
from skill_dojo_cli.context import build_context

clients_app = typer.Typer(help="Keep the hand-kept list of clients.")


def echo_clients(result: core.ClientsResult) -> None:
    if not result.clients:
        typer.echo("No clients.")
    for client in result.clients:
        contact = f" <{client.contact}>" if client.contact else ""
        typer.echo(f"{client.name}: {client.ref}{contact}")


@clients_app.command("add")
def clients_add(
    name: str,
    ref: str,
    contact: Annotated[str | None, typer.Option(help="Who to tell.")] = None,
    notes: Annotated[str | None, typer.Option(help="Free text.")] = None,
    update: Annotated[bool, typer.Option(help="Replace an existing client.")] = False,
) -> None:
    """Record that a client uses a ref or tag."""
    result = core.clients_add(
        build_context(Path.cwd()),
        name,
        ref,
        contact=contact,
        notes=notes,
        update=update,
    )
    echo_clients(result)


@clients_app.command("list")
def clients_list() -> None:
    """List the clients."""
    echo_clients(core.clients_list(build_context(Path.cwd())))


@clients_app.command("remove")
def clients_remove(name: str) -> None:
    """Remove a client."""
    echo_clients(core.clients_remove(build_context(Path.cwd()), name))
