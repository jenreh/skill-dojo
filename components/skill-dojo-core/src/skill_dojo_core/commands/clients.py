"""``clients add|list|remove``: the hand-kept ``registry/clients.yaml``."""

import logging

from skill_dojo_core.commands.vendor import REF_RE
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError, NotFoundError
from skill_dojo_core.models import Client
from skill_dojo_core.registry import CLIENTS, Registry, save_yaml_model
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)


class ClientsResult(Result):
    clients: list[Client]


def _check_ref(ref: str) -> None:
    if not REF_RE.match(ref) or ".." in ref:
        raise InvalidInputError(f"'{ref}' is not a valid git ref")


def clients_list(ctx: Context) -> ClientsResult:
    return ClientsResult(clients=Registry.load(ctx.repo).clients.clients)


def clients_add(
    ctx: Context,
    name: str,
    ref: str,
    *,
    contact: str | None = None,
    notes: str | None = None,
    update: bool = False,
) -> ClientsResult:
    """Record that ``name`` uses ``ref`` (a tag or branch)."""
    if not name.strip():
        raise InvalidInputError("client name must not be empty")
    _check_ref(ref)
    with repo_lock(ctx.repo):
        reg = Registry.load(ctx.repo)
        clients = reg.clients.clients
        existing = next((c for c in clients if c.name == name), None)
        if existing is not None and not update:
            raise ConflictError(f"client '{name}' exists; use --update")
        client = Client(name=name, ref=ref, contact=contact, notes=notes)
        if existing is None:
            clients.append(client)
        else:
            clients[clients.index(existing)] = client
        save_yaml_model(ctx.repo, CLIENTS, reg.clients)
    ctx.report(f"Client {name} uses {ref}")
    log.info("Client %s uses %s", name, ref)
    return ClientsResult(clients=clients)


def clients_remove(ctx: Context, name: str) -> ClientsResult:
    with repo_lock(ctx.repo):
        reg = Registry.load(ctx.repo)
        kept = [c for c in reg.clients.clients if c.name != name]
        if len(kept) == len(reg.clients.clients):
            raise NotFoundError(f"no client '{name}' in registry/clients.yaml")
        reg.clients.clients = kept
        save_yaml_model(ctx.repo, CLIENTS, reg.clients)
    ctx.report(f"Removed client {name}")
    return ClientsResult(clients=kept)
