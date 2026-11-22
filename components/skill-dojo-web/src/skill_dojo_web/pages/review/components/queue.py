"""The candidate list on the left of the review queue."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import (
    badge,
    empty,
    mono,
    section_title,
    segmented,
)
from skill_dojo_web.pages.review.state import ReviewState as S


def _queue_row(entry: rx.Var) -> rx.Component:
    flags = entry["flags"].to(int)
    selected = S.selected == entry["number"]
    return mn.unstyled_button(
        mn.stack(
            mn.group(
                mn.text(entry["item"], fw=600, size="sm"),
                badge(entry["kind"]),
                mn.text(entry["age"], size="xs", c="dimmed", ml="auto"),
                gap="xs",
            ),
            mono(entry["pin"], c="dimmed"),
            mn.group(
                rx.cond(
                    flags > 0,
                    badge(
                        rx.cond(flags == 1, "1 flag", f"{flags} flags"),
                        rx.cond(flags > 2, "bad", "warn"),
                    ),
                    badge("no flags", "add"),
                ),
                mono(f"PR #{entry['number']}", c="dimmed"),
                gap=6,
            ),
            gap=4,
        ),
        on_click=S.select(entry["number"].to(int)),
        p="sm",
        w="100%",
        bg=rx.cond(selected, "var(--mantine-color-default-hover)", "transparent"),
        style={"borderRadius": "var(--mantine-radius-md)"},
    )


def _held_row(item: rx.Var) -> rx.Component:
    return mn.stack(
        mn.text(item, fw=600, size="sm"),
        badge(mn.group(rx.icon("pause", size=10), "quarantined", gap=4)),
        gap=4,
        p="sm",
        opacity="0.75",
    )


def queue() -> rx.Component:
    return mn.stack(
        section_title("Review queue", "Candidate PRs into staging"),
        segmented(
            S.filter,
            [
                ("all", f"All {S.entries.length() + S.quarantined.length()}"),
                ("flagged", f"Flagged {S.flagged_count}"),
                ("quarantined", f"Quarantined {S.quarantined.length()}"),
            ],
            S.set_filter,
        ),
        rx.foreach(S.rows, _queue_row),
        rx.cond(S.filter != "flagged", rx.foreach(S.quarantined, _held_row)),
        rx.cond(S.entries.length() == 0, empty("No open candidate PRs.")),
        gap="xs",
    )
