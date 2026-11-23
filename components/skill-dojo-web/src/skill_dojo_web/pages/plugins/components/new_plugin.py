"""Create a local plugin, then drop files into its folder and scan."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import mono, panel, work, working
from skill_dojo_web.pages.plugins.state import PluginsState as S


def new_plugin() -> rx.Component:
    return panel(
        mn.stack(
            mn.text("New plugin", fw=600),
            mn.text_input(
                label="Name",
                placeholder="team-tools",
                value=S.new_name,
                on_change=S.set_new_name,
            ),
            mn.text_input(
                label="Description",
                value=S.new_description,
                on_change=S.set_new_description,
            ),
            mn.text_input(
                label="Category",
                value=S.new_category,
                on_change=S.set_new_category,
            ),
            mn.text(
                "Put its files (skills/, agents/, hooks/, .mcp.json) into:",
                size="xs",
                c="dimmed",
            ),
            mono(S.new_path, size="sm"),
            mn.button(
                "Create plugin",
                left_section=rx.icon("plus", size=14),
                disabled=S.cannot_create,
                loading=working("new_plugin"),
                on_click=work("new_plugin", S.create),
            ),
            mn.divider(),
            mn.text(
                "Added or edited files by hand? Scan locks them, bumps the version "
                "and regenerates manifests and catalogs.",
                size="xs",
                c="dimmed",
            ),
            mn.button(
                "Scan for new files",
                left_section=rx.icon("scan-search", size=14),
                variant="default",
                loading=working("scan"),
                on_click=work("scan", S.scan),
            ),
            gap="sm",
        ),
        p="md",
    )
