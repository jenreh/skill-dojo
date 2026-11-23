"""Plugins page: mirrors and own plugins, their parts, and new plugins."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import page_header
from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.plugins.components.new_plugin import new_plugin
from skill_dojo_web.pages.plugins.components.plugin_list import plugin_list
from skill_dojo_web.pages.plugins.state import PluginsState

ROUTE = "/plugins"
TITLE = "Plugins"
ON_LOAD = PluginsState.load


def page() -> rx.Component:
    return shell(
        "plugins",
        page_header("Plugins", "Mirrors and the team's own plugins with their parts"),
        mn.flex(
            mn.box(plugin_list(), flex="999 1 520px", miw=0),
            mn.box(new_plugin(), flex="1 1 280px"),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
