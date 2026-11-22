"""Audit page: a timeline built from git commits, PRs and tags."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import page_header
from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.audit.components.timeline import timeline
from skill_dojo_web.pages.audit.state import AuditState

ROUTE = "/audit"
TITLE = "Audit"
ON_LOAD = AuditState.load


def page() -> rx.Component:
    return shell(
        "audit",
        mn.stack(
            page_header(
                "Audit",
                "Built from git commits, PRs and tags. Nothing is stored apart.",
                mn.button("Export CSV", variant="default", on_click=AuditState.export),
            ),
            timeline(),
            gap="md",
            maw=1040,
        ),
    )
