"""Revoke page: remove or roll back an item on the work branch."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import page_header
from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.revoke.components.revoke_panel import revoke_panel
from skill_dojo_web.pages.revoke.state import RevokeState

ROUTE = "/revoke"
TITLE = "Revoke"
ON_LOAD = RevokeState.load


def page() -> rx.Component:
    return shell(
        "revoke",
        page_header(
            "Revoke",
            "Remove an item, or roll it back to an earlier release, on the work branch",
        ),
        mn.box(revoke_panel(), maw=520),
    )
