"""Releases page: promote staging to main, then tag an immutable release."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import page_header
from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.releases.components.flow import flow
from skill_dojo_web.pages.releases.components.promotion import (
    checks_and_tags,
    promotion_items,
)
from skill_dojo_web.pages.releases.state import ReleasesState

ROUTE = "/releases"
TITLE = "Releases"
ON_LOAD = ReleasesState.load


def page() -> rx.Component:
    return shell(
        "releases",
        page_header(
            "Releases", "Promote all of staging to main, then tag an immutable release"
        ),
        rx.cond(ReleasesState.overview.contains("staging"), flow()),
        mn.flex(
            mn.box(promotion_items(), flex="999 1 460px", miw=0),
            mn.box(checks_and_tags(), flex="1 1 280px"),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
