"""What the selected source offers: filters, plugins, their parts, add to plugin."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import (
    WINDOW_HEIGHT,
    badge,
    mono,
    panel,
    segmented,
    work,
    working,
)
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
                mn.button(
                    "Mirror whole plugin",
                    size="xs",
                    loading=working(f"mirror:{name}"),
                    on_click=work(f"mirror:{name}", S.mirror(name)),
                ),
            ),
            rx.cond(
                addable,
                mn.button(
                    rx.cond(S.expanded == name, "Hide parts", "Pick parts"),
                    size="xs",
                    variant="default",
                    loading=working(f"parts:{name}"),
                    on_click=work(f"parts:{name}", S.expand(name)),
                ),
            ),
            gap=6,
            justify="flex-end",
        ),
        mn.button(
            "Allow",
            size="xs",
            variant="subtle",
            loading=working(f"allow:{name}"),
            on_click=work(f"allow:{name}", S.allow(name)),
        ),
    )


# Plugin rows and each part highlight on their own (not the whole parts block,
# which Mantine's highlight_on_hover would do).
_HOVER = {"backgroundColor": "var(--table-hover-color)"}


def _part(part: rx.Var) -> rx.Component:
    """Name, kind and description; the plugin select and switch on the right."""
    spec = part["spec"].to(str)
    on = part["on"].to(bool)
    description = part["description"].to(str)
    return mn.group(
        mn.stack(
            mn.group(
                mono(part["name"]),
                badge(part["kind"]),
                rx.cond(
                    part["version"].to(str) != "",
                    mono(part["version"], c="dimmed"),
                ),
                gap="xs",
            ),
            rx.cond(
                description != "",
                mn.text(description, size="xs", c="dimmed", line_clamp=2),
            ),
            gap=2,
            flex="1",
            miw=0,
        ),
        mn.group(
            mn.select(
                data=S.target_options,
                value=part["target"].to(str),
                on_change=lambda v: S.set_part_target(spec, v),
                allow_deselect=False,
                disabled=on,
                aria_label="Plugin for this part",
                size="xs",
                w=180,
            ),
            rx.cond(working(f"part:{spec}"), mn.loader(size="xs")),
            mn.switch(
                checked=on,
                disabled=working(f"part:{spec}"),
                on_change=lambda v: work(f"part:{spec}", S.toggle_part(spec, v)),
                aria_label="In the selected plugin",
            ),
            gap="sm",
            wrap="nowrap",
            ml="auto",
        ),
        justify="space-between",
        wrap="nowrap",
        py=6,
        px="sm",
        style={"borderRadius": "var(--mantine-radius-sm)"},
        _hover=_HOVER,
    )


def _parts(p: rx.Var) -> rx.Component:
    return mn.table.tr(
        mn.table.td(
            mn.stack(
                rx.foreach(S.part_list, _part),
                rx.cond(
                    S.part_list.length() == 0,
                    mn.text("This plugin has no parts to pick.", size="xs", c="dimmed"),
                ),
                gap=0,
                pl="md",
            ),
            custom_attrs={"colSpan": 6},
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
        _hover=_HOVER,
    )


def _rows(p: rx.Var) -> rx.Component:
    return rx.fragment(_row(p), rx.cond(S.expanded == p["name"].to(str), _parts(p)))


def catalog() -> rx.Component:
    """Header, filter and bars stay put; the plugin rows scroll within the window."""
    src = S.source
    return mn.stack(
        mn.group(
            mn.stack(
                mn.group(
                    rx.cond(
                        src["url"].to(str) != "",
                        mn.anchor(
                            mono(src["repository"]),
                            href=src["url"].to(str),
                            target="_blank",
                            rel="noopener noreferrer",
                        ),
                        mono(src["repository"], c="dimmed"),
                    ),
                    mono(src["path"], c="dimmed"),
                    gap=6,
                ),
                mn.group(
                    mn.title(S.selected, order=2, size="h3"),
                    rx.cond(S.version != "", badge(f"v{S.version}")),
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
                loading=working("refresh"),
                on_click=work("refresh", S.refresh),
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
                    highlight_on_hover=False,
                    vertical_spacing="sm",
                    sticky_header=True,
                ),
                min_width=720,
                flex="1",
                mih=0,
            ),
            flex="1",
            mih=0,
            display="flex",
            style={"flexDirection": "column"},
        ),
        _dialog(),
        gap="md",
        h=WINDOW_HEIGHT,
    )


def _dialog() -> rx.Component:
    return mn.modal(
        mn.stack(
            mn.text(
                f"Creates a local plugin with the pinned part {S.pending_name} on "
                "the work branch. You decide when to commit it.",
                size="sm",
                c="dimmed",
            ),
            mn.text_input(
                label="Plugin name",
                placeholder="team-kit",
                value=S.target_name,
                on_change=S.set_target_name,
            ),
            mn.group(
                mn.button("Cancel", variant="default", on_click=S.close_dialog),
                mn.button(
                    "Create plugin",
                    disabled=S.cannot_create,
                    loading=working("create_plugin"),
                    on_click=work("create_plugin", S.create_plugin),
                ),
                justify="flex-end",
            ),
            gap="sm",
        ),
        title="New plugin",
        opened=S.dialog,
        on_close=S.close_dialog,
        centered=True,
    )
