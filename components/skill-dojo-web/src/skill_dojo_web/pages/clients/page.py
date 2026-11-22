"""Clients and revocation page."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.clients.components.client_table import client_table
from skill_dojo_web.pages.clients.components.revoke_panel import revoke_panel
from skill_dojo_web.pages.clients.state import ClientsState

ROUTE = "/clients"
TITLE = "Clients"
ON_LOAD = ClientsState.load


def page() -> rx.Component:
    return shell(
        "clients",
        mn.flex(
            mn.box(client_table(), flex="999 1 520px", miw=0),
            mn.box(revoke_panel(), flex="1 1 300px"),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
