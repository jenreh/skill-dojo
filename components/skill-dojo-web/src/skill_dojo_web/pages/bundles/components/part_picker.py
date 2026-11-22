"""Pick parts: the skills, agents and MCP servers of the loaded plugins."""

from typing import Any

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import badge, section_title
from skill_dojo_web.pages.bundles.state import BundlesState as S


def _pick(p: rx.Var) -> rx.Component:
    spec = p["spec"].to(str)
    return mn.group(
        mn.checkbox(
            label=p["name"].to(str),
            checked=S.picked.contains(spec),
            on_change=lambda _: S.toggle(spec),
        ),
        badge(p["kind_label"], ml="auto"),
        py=4,
        wrap="nowrap",
    )


def _group(g: rx.Var) -> rx.Component:
    return mn.stack(
        mn.text(
            g["title"], size="xs", fw=500, tt="uppercase", c="dimmed", lts="0.04em"
        ),
        rx.foreach(g["parts"].to(list[dict[str, Any]]), _pick),
        gap=2,
    )


def part_picker() -> rx.Component:
    return mn.stack(
        section_title("Pick parts", "Skills, agents and MCP servers from any source"),
        mn.text_input(
            placeholder="Search parts",
            aria_label="Search parts",
            left_section=rx.icon("search", size=14),
            value=S.query,
            on_change=S.set_query,
        ),
        rx.foreach(S.shown_groups, _group),
        mn.text(
            "Add plugins from Sources and browse (Add to bundle).",
            size="xs",
            c="dimmed",
        ),
        gap="sm",
    )
