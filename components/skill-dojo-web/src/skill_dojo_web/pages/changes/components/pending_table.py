"""The changed plugins with their version choice, and the risk flags."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import badge, empty, mono, panel, panel_head
from skill_dojo_web.pages.changes.state import CUSTOM, LEVEL_OPTIONS
from skill_dojo_web.pages.changes.state import ChangesState as S


def _version_choice(r: rx.Var) -> rx.Component:
    item = r["item"].to(str)
    return rx.cond(
        r["editable"].to(bool),
        mn.group(
            mn.select(
                data=LEVEL_OPTIONS,
                value=r["choice"].to(str),
                on_change=lambda v: S.choose(item, v),
                allow_deselect=False,
                size="xs",
                w=110,
                aria_label="Version level",
            ),
            rx.cond(
                r["choice"].to(str) == CUSTOM,
                mn.text_input(
                    placeholder="X.Y.Z",
                    default_value=r["custom_version"].to(str),
                    on_blur=lambda v: S.set_custom(item, v),
                    size="xs",
                    w=90,
                    aria_label="Custom version",
                ),
            ),
            gap=6,
            wrap="nowrap",
        ),
        mn.text("upstream version", size="xs", c="dimmed"),
    )


def _row(r: rx.Var) -> rx.Component:
    return mn.table.tr(
        mn.table.td(mn.text(r["item"], fw=600, size="sm")),
        mn.table.td(badge(r["kind"])),
        mn.table.td(
            badge(
                r["status"],
                rx.match(r["status"].to(str), ("added", "add"), ("removed", "bad"), ""),
            )
        ),
        mn.table.td(mono(r["shown_main"])),
        mn.table.td(mono(r["shown_branch"])),
        mn.table.td(_version_choice(r)),
    )


def pending_table() -> rx.Component:
    return panel(
        panel_head("Changed plugins", badge(S.rows.length())),
        mn.table.scroll_container(
            mn.table(
                mn.table.thead(
                    mn.table.tr(
                        *(
                            mn.table.th(h)
                            for h in (
                                "Plugin",
                                "Kind",
                                "Change",
                                "On main",
                                "On branch",
                                "Release as",
                            )
                        )
                    )
                ),
                mn.table.tbody(rx.foreach(S.rows, _row)),
                vertical_spacing="sm",
            ),
            min_width=640,
        ),
        rx.cond(S.rows.length() == 0, empty("No plugin differs from main.")),
    )


def _flag(f: rx.Var) -> rx.Component:
    return mn.group(
        badge(f["kind"], f["tone"]),
        mn.text(f["item"], fw=500, size="sm"),
        mono(f["where"], c="dimmed"),
        mn.text(f["detail"], size="xs", c="dimmed", flex="1 1 200px"),
        px="md",
        py="xs",
        wrap="wrap",
    )


def flag_list() -> rx.Component:
    return panel(
        panel_head("Risk flags against main", badge(S.flags.length())),
        mn.divider(),
        rx.foreach(S.flags, _flag),
        rx.cond(S.flags.length() == 0, empty("No risk flags.")),
    )
