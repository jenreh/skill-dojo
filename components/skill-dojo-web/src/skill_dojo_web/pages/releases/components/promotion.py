"""What the promotion brings, the release notes, checks and tags."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import (
    badge,
    check_line,
    empty,
    mono,
    panel,
    panel_head,
)
from skill_dojo_web.pages.releases.state import ReleasesState as S


def _item_row(i: rx.Var) -> rx.Component:
    return mn.group(
        mn.text(i["item"], fw=500, size="sm", flex="1 1 200px"),
        badge(i["kind"]),
        mono(i["change"], c="dimmed"),
        mono(i["who"], c="dimmed"),
        px="md",
        py="xs",
        wrap="wrap",
    )


def promotion_items() -> rx.Component:
    return mn.stack(
        panel(
            panel_head("In this promotion", badge(S.items.length())),
            mn.divider(),
            rx.foreach(S.items, _item_row),
            rx.cond(S.items.length() == 0, empty("Staging and main are the same.")),
        ),
        mn.textarea(
            label="Release notes",
            description="Drafted from the merged candidate PRs. Used as the tag message.",
            default_value=S.notes,
            on_blur=S.set_notes,
            autosize=True,
            min_rows=6,
            ff="'JetBrains Mono', monospace",
        ),
        gap="md",
    )


def _tag_row(t: rx.Var) -> rx.Component:
    clients = t["clients"].to(int)
    return mn.group(
        rx.icon("tag", size=13),
        mono(t["tag"].to(str).replace("marketplace-", ""), flex="1"),
        mn.text(
            f"{t['items']} items · {clients} ",
            rx.cond(clients == 1, "client", "clients"),
            size="xs",
            c="dimmed",
        ),
        px="md",
        py="xs",
    )


def checks_and_tags() -> rx.Component:
    return mn.stack(
        panel(
            mn.stack(
                mn.text("Promotion checks", fw=600, size="sm"),
                rx.cond(
                    S.blocks.length() == 0,
                    mn.stack(
                        check_line("All items approved on staging"),
                        check_line("No forbidden risk tier"),
                        check_line("stable is in every item's channels"),
                        gap="xs",
                    ),
                    rx.foreach(S.blocks, lambda b: check_line(b, "x")),
                ),
                check_line("Open candidates stay on staging", "info"),
                gap="xs",
            ),
            p="md",
        ),
        panel(
            panel_head("Tags"),
            mn.divider(),
            rx.foreach(S.tags, _tag_row),
            rx.cond(S.tags.length() == 0, empty("No release yet.")),
        ),
        gap="md",
    )
