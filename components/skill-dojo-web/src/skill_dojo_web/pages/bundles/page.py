"""Bundles page: pick parts from any source and open the candidate PR."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.bundles.components.bundle_editor import bundle_editor
from skill_dojo_web.pages.bundles.components.part_picker import part_picker
from skill_dojo_web.pages.bundles.state import BundlesState

ROUTE = "/bundles"
TITLE = "Bundles"
ON_LOAD = BundlesState.load


def page() -> rx.Component:
    return shell(
        "bundles",
        mn.flex(
            mn.box(part_picker(), flex="1 1 300px", maw=360),
            mn.box(bundle_editor(), flex="999 1 520px", miw=0),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
