"""What the selected source offers: filters, the plugin table, the mirror note."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import badge, mono, panel, segmented
from skill_dojo_web.pages.sources.state import KINDS
from skill_dojo_web.pages.sources.state import SourcesState as S


def _status(p: rx.Var) -> rx.Component:
    tracked = p["tracked"].to(str)
    return rx.cond(
        tracked != "",
        badge(
            tracked,
            rx.cond(
                tracked.contains("quarantined"),
                "warn",
                rx.cond(tracked.contains("mirror"), "add", ""),
            ),
        ),
        mn.text(
            rx.cond(
                p["unsupported"].to(str) != "",
                "cannot mirror",
                rx.cond(p["allowed"].to(bool), "not added", "not on allow-list"),
            ),
            size="sm",
            c="dimmed",
        ),
    )


def _actions(p: rx.Var) -> rx.Component:
    name = p["name"].to(str)
    addable = (p["tracked"].to(str) == "") & (p["unsupported"].to(str) == "")
    return rx.cond(
        p["allowed"].to(bool),
        rx.cond(
            addable,
            mn.group(
                mn.button("Mirror", size="xs", on_click=S.mirror(name)),
                mn.button(
                    "Add to bundle",
                    size="xs",
                    variant="default",
                    on_click=rx.redirect(f"/bundles?source={S.selected}&plugin={name}"),
                ),
                gap=6,
                justify="flex-end",
            ),
            mn.button(
                "Details", size="xs", variant="subtle", on_click=S.set_focus(name)
            ),
        ),
        mn.button("Allow", size="xs", variant="subtle", on_click=S.allow(name)),
    )


def _row(p: rx.Var) -> rx.Component:
    return mn.table.tr(
        mn.table.td(
            mn.text(p["name"], fw=600, size="sm"),
            mn.text(p["description"], size="xs", c="dimmed"),
        ),
        mn.table.td(mono(p["version"])),
        mn.table.td(mn.text(p["contents"], size="sm", c="dimmed")),
        mn.table.td(
            rx.cond(
                p["license"].to(str) != "",
                mono(p["license"]),
                badge("no license", "bad"),
            )
        ),
        mn.table.td(_status(p)),
        mn.table.td(_actions(p), ta="right"),
        on_mouse_enter=S.set_focus(p["name"].to(str)),
    )


def _note() -> rx.Component:
    return mn.alert(
        mn.group(
            mn.text(
                "Mirror pins ",
                mono(S.focus),
                " at the source's current commit and opens a candidate PR into "
                "staging. Nothing ships until it is approved and promoted.",
                size="sm",
                flex="1 1 300px",
            ),
            mono(f"skill-dojo mirror {S.selected} {S.focus}", c="dimmed"),
            wrap="wrap",
        ),
        icon=rx.icon("info", size=16),
        color="blue",
        variant="light",
    )


def catalog() -> rx.Component:
    src = S.source
    return mn.stack(
        mn.group(
            mn.stack(
                mono(f"{src['repository']} {src['path']}", c="dimmed"),
                mn.group(
                    mn.title(S.selected, order=2, size="h3"),
                    badge(f"{S.plugins.length()} plugins"),
                    gap="xs",
                ),
                gap=4,
            ),
            mn.button(
                "Refresh catalog",
                left_section=rx.icon("refresh-cw", size=14),
                variant="default",
                on_click=S.refresh,
            ),
            justify="space-between",
            align="flex-start",
        ),
        mn.group(
            mn.text_input(
                placeholder="Filter by name, skill or keyword",
                aria_label="Filter plugins",
                left_section=rx.icon("search", size=14),
                value=S.query,
                on_change=S.set_query,
                flex="1 1 280px",
            ),
            segmented(S.kind, KINDS, S.set_kind),
            wrap="wrap",
        ),
        panel(
            mn.table.scroll_container(
                mn.table(
                    mn.table.thead(
                        mn.table.tr(
                            *(
                                mn.table.th(h)
                                for h in (
                                    "Plugin",
                                    "Version",
                                    "Contents",
                                    "License",
                                    "In this marketplace",
                                )
                            ),
                            mn.table.th(mn.visually_hidden("Actions")),
                        )
                    ),
                    mn.table.tbody(rx.foreach(S.shown, _row)),
                    highlight_on_hover=True,
                    vertical_spacing="sm",
                ),
                min_width=720,
            ),
        ),
        rx.cond(S.focus != "", _note()),
        gap="md",
    )
