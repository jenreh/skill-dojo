"""Sources and browse page: upstream sources and what each one offers."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.sources.components.catalog import catalog
from skill_dojo_web.pages.sources.components.source_list import source_list
from skill_dojo_web.pages.sources.state import SourcesState

ROUTE = "/sources"
TITLE = "Sources and browse"
ON_LOAD = SourcesState.load


def page() -> rx.Component:
    return shell(
        "sources",
        mn.flex(
            mn.box(source_list(), flex="1 1 280px", maw=340),
            mn.box(
                rx.cond(SourcesState.selected != "", catalog()),
                flex="999 1 520px",
                miw=0,
            ),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
