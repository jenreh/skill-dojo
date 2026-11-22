"""Every plugin of the marketplace with its parts."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import badge, empty, mono, panel, panel_head
from skill_dojo_web.pages.plugins.state import PluginsState as S


def _part(plugin: rx.Var, p: rx.Var) -> rx.Component:
    return mn.group(
        badge(p["kind_label"]),
        mono(p["name"]),
        mn.text(f"from {p['source']}:{p['plugin']}", size="xs", c="dimmed"),
        mono(p["commit"], c="dimmed"),
        mn.action_icon(
            rx.icon("x", size=12),
            variant="subtle",
            color="gray",
            size="sm",
            aria_label="Remove part",
            on_click=S.remove_part(plugin["id"].to(str), p["short"].to(str)),
        ),
        gap="xs",
        wrap="wrap",
    )


def _plugin(p: rx.Var) -> rx.Component:
    return mn.stack(
        mn.group(
            mn.text(p["id"], fw=600, size="sm"),
            badge(p["kind"], rx.cond(p["kind"].to(str) == "mirror", "info", "")),
            mono(p["version"]),
            rx.cond(p["quarantined"].to(bool), badge("quarantined", "warn")),
            rx.cond(
                p["pin"].to(str) != "",
                mono(f"{p['source']} @ {p['pin']}", c="dimmed"),
            ),
            mono(p["path"], c="dimmed", ml="auto"),
            gap="xs",
            wrap="wrap",
        ),
        rx.cond(
            p["description"].to(str) != "",
            mn.text(p["description"], size="xs", c="dimmed"),
        ),
        rx.foreach(p["parts"].to(list[dict[str, str]]), lambda part: _part(p, part)),
        gap=6,
        px="md",
        py="sm",
    )


def plugin_list() -> rx.Component:
    return panel(
        panel_head(
            "Plugins",
            badge(S.plugins.length()),
            mn.text_input(
                placeholder="Filter",
                aria_label="Filter plugins",
                left_section=rx.icon("search", size=14),
                value=S.query,
                on_change=S.set_query,
                size="xs",
                ml="auto",
            ),
        ),
        mn.divider(),
        rx.foreach(S.shown, _plugin),
        rx.cond(S.shown.length() == 0, empty("No plugins yet.")),
    )
