"""Releases page: tag merged main as an immutable release, by hand."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import page_header
from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.releases.components.release_panel import (
    past_releases,
    since_last,
)
from skill_dojo_web.pages.releases.state import ReleasesState

ROUTE = "/releases"
TITLE = "Releases"
ON_LOAD = ReleasesState.load


def page() -> rx.Component:
    return shell(
        "releases",
        page_header(
            "Releases",
            "After the work-branch PR is merged, tag main and publish a release",
        ),
        mn.flex(
            mn.box(since_last(), flex="999 1 460px", miw=0),
            mn.box(past_releases(), flex="1 1 280px"),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
