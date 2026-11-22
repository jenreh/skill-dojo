"""Marketplace preview page: the exact catalogs and tree build would commit."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.preview.components.catalog_view import catalog_view
from skill_dojo_web.pages.preview.components.tree import tree
from skill_dojo_web.pages.preview.state import PreviewState

ROUTE = "/preview"
TITLE = "Marketplace preview"
ON_LOAD = PreviewState.load


def page() -> rx.Component:
    return shell(
        "preview",
        mn.flex(
            mn.box(tree(), flex="1 1 280px", maw=340),
            mn.box(catalog_view(), flex="999 1 520px", miw=0),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
