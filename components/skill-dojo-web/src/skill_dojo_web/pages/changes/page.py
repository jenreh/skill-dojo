"""Changes page: what the work branch would bring to main."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import page_header
from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.changes.components.branch_panel import branch_panel
from skill_dojo_web.pages.changes.components.pending_table import (
    flag_list,
    pending_table,
)
from skill_dojo_web.pages.changes.state import ChangesState

ROUTE = "/"
TITLE = "Changes"
ON_LOAD = ChangesState.load


def page() -> rx.Component:
    return shell(
        "changes",
        page_header(
            "Changes",
            "Every change lands on one work branch; finish opens one PR into main",
        ),
        mn.flex(
            mn.stack(pending_table(), flag_list(), gap="md", flex="999 1 520px", miw=0),
            mn.box(branch_panel(), flex="1 1 280px"),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
