"""What the selected source offers: filters, plugins, their parts, add to plugin."""

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
    addable = p["unsupported"].to(str) == ""
    return rx.cond(
        p["allowed"].to(bool),
        mn.group(
            rx.cond(
                addable & (p["tracked"].to(str) == ""),
                mn.button("Mirror whole plugin", size="xs", on_click=S.mirror(name)),
            ),
            rx.cond(
                addable,
                mn.button(
                    rx.cond(S.expanded == name, "Hide parts", "Pick parts"),
                    size="xs",
                    variant="default",
                    on_click=S.expand(name),
                ),
            ),
            gap=6,
            justify="flex-end",
        ),
        mn.button("Allow", size="xs", variant="subtle", on_click=S.allow(name)),
    )


def _part(part: rx.Var) -> rx.Component:
    spec = part["spec"].to(str)
    return mn.group(
        mn.checkbox(
            label=part["name"].to(str),
            checked=S.picked.contains(spec),
            on_change=lambda _: S.toggle_pick(spec),
        ),
        badge(part["kind"]),
        gap="xs",
    )


def _parts(p: rx.Var) -> rx.Component:
    return mn.table.tr(
        mn.table.td(
            mn.stack(
                mn.group(
                    rx.foreach(S.part_rows, _part),
                    gap="lg",
                    wrap="wrap",
                ),
                rx.cond(
                    S.part_rows.length() == 0,
                    mn.text("This plugin has no parts to pick.", size="xs", c="dimmed"),
                ),
                gap="xs",
                py="xs",
            ),
            col_span=6,
        ),
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


def _rows(p: rx.Var) -> rx.Component:
    return rx.fragment(_row(p), rx.cond(S.expanded == p["name"].to(str), _parts(p)))


def _note() -> rx.Component:
    return mn.alert(
        mn.group(
            mn.text(
                "Mirror pins ",
                mono(S.focus),
                " at the source's current commit as a commit on the work branch. "
                "Nothing ships until the work-branch PR is merged and released.",
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
                    rx.cond(S.cached, badge(f"cached @ {S.commit}", "info")),
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
                    mn.table.tbody(rx.foreach(S.shown, _rows)),
                    highlight_on_hover=True,
                    vertical_spacing="sm",
                ),
                min_width=720,
            ),
        ),
        rx.cond(S.picked_count > 0, _picked_bar()),
        rx.cond(S.focus != "", _note()),
        _dialog(),
        gap="md",
    )


def _picked_bar() -> rx.Component:
    return mn.alert(
        mn.group(
            mn.text(f"{S.picked_count} part(s) picked", size="sm", flex="1"),
            mn.button("Add to plugin", size="xs", on_click=S.open_dialog),
            wrap="nowrap",
        ),
        color="blue",
        variant="light",
    )


def _dialog() -> rx.Component:
    return mn.modal(
        mn.stack(
            mn.text(
                f"Copies {S.picked_count} pinned part(s) into a local plugin, as a "
                "commit on the work branch.",
                size="sm",
                c="dimmed",
            ),
            mn.select(
                label="Plugin",
                data=S.target_options,
                value=S.target,
                on_change=S.set_target,
                allow_deselect=False,
            ),
            rx.cond(
                S.creating,
                mn.text_input(
                    label="New plugin name",
                    placeholder="team-kit",
                    value=S.target_name,
                    on_change=S.set_target_name,
                ),
            ),
            mn.group(
                mn.button("Cancel", variant="default", on_click=S.close_dialog),
                mn.button("Add parts", disabled=S.cannot_add, on_click=S.add_to_plugin),
                justify="flex-end",
            ),
            gap="sm",
        ),
        title="Add to plugin",
        opened=S.dialog,
        on_close=S.close_dialog,
        centered=True,
    )
