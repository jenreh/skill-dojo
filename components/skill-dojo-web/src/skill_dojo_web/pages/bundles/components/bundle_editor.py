"""The bundle being edited: name, fields, parts and what the PR will hold."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import (
    badge,
    check_line,
    mono,
    panel,
    panel_head,
)
from skill_dojo_web.pages.bundles.state import BundlesState as S


def _part_row(p: rx.Var) -> rx.Component:
    return mn.group(
        mn.stack(
            mn.group(
                mn.text(p["name"], fw=500, size="sm"), badge(p["kind_label"]), gap="xs"
            ),
            mono(f"{p['source']} · {p['path']}", c="dimmed"),
            gap=2,
            flex="1 1 220px",
        ),
        mono(f"@ {p['commit'].to(str)[:12]}", c="dimmed"),
        mono(p["license"], c="dimmed"),
        rx.cond(
            p["new"].to(bool),
            badge("new", "warn"),
            rx.cond(
                p["source"].to(str) == "local", badge("local"), badge("pinned", "add")
            ),
        ),
        mn.action_icon(
            rx.icon("x", size=14),
            variant="subtle",
            color="gray",
            aria_label=f"Remove {p['name']}",
            on_click=S.toggle(p["spec"].to(str)),
        ),
        px="md",
        py="xs",
        wrap="wrap",
    )


def _header() -> rx.Component:
    return mn.group(
        mn.stack(
            mn.select(
                data=S.bundle_options,
                value=S.bundle_value,
                on_change=S.choose,
                allow_deselect=False,
                aria_label="Bundle",
                size="xs",
                w=240,
            ),
            mn.group(
                rx.cond(
                    S.bundle == "",
                    mn.text_input(
                        placeholder="new-bundle-name",
                        aria_label="Bundle name",
                        value=S.new_name,
                        on_change=S.set_new_name,
                        w=260,
                    ),
                    mn.title(S.current["id"], order=2, size="h3"),
                ),
                badge("bundle"),
                badge(S.next_version),
                rx.cond(S.dirty, badge("unsaved", "warn")),
                gap="xs",
            ),
            gap="xs",
        ),
        mn.group(
            mn.button("Discard", variant="default", on_click=S.discard),
            mn.button(
                "Open candidate PR",
                left_section=rx.icon("git-pull-request-arrow", size=14),
                on_click=S.open_pr,
            ),
            gap="xs",
        ),
        justify="space-between",
        align="flex-start",
        wrap="wrap",
    )


def bundle_editor() -> rx.Component:
    return mn.stack(
        _header(),
        mn.group(
            mn.text_input(
                label="Category",
                value=S.category,
                on_change=S.set_category,
                flex="1 1 260px",
            ),
            mn.text_input(
                label="Description",
                value=S.description,
                on_change=S.set_description,
                flex="2 1 360px",
            ),
            wrap="wrap",
            grow=True,
        ),
        panel(
            panel_head(
                "Parts",
                badge(S.parts.length()),
                mn.text(
                    "Each part is pinned on its own", size="xs", c="dimmed", ml="auto"
                ),
            ),
            mn.divider(),
            rx.foreach(S.parts, _part_row),
        ),
        mn.simple_grid(
            panel(
                mn.stack(
                    mn.text("What the PR will contain", fw=600, size="sm"),
                    check_line("Exact pinned files for every part"),
                    check_line("plugin.json with a parts list per origin"),
                    check_line("lock.json hashes and vendored licenses"),
                    check_line(f"Patch bump to {S.next_version}"),
                    gap="xs",
                ),
                p="md",
            ),
            panel(
                mn.stack(
                    mn.text("Pre-check", fw=600, size="sm"),
                    check_line("validate runs on the candidate branch"),
                    check_line("Risk flags are listed in the PR", "info"),
                    check_line("Part names must not clash"),
                    gap="xs",
                ),
                p="md",
            ),
            cols={"base": 1, "md": 2},
        ),
        gap="md",
    )
