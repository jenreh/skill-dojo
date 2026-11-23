"""Main since the last release, the notes, the release button and past tags."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import (
    badge,
    empty,
    mono,
    panel,
    panel_head,
    work,
    working,
)
from skill_dojo_web.pages.releases.state import ReleasesState as S


def _commit_row(c: rx.Var) -> rx.Component:
    return mn.group(
        mono(c["sha"], c="dimmed"),
        mn.text(c["subject"], size="sm", flex="1 1 260px"),
        mn.text(c["author"], size="xs", c="dimmed"),
        px="md",
        py="xs",
        wrap="wrap",
    )


def since_last() -> rx.Component:
    return mn.stack(
        panel(
            panel_head(
                "On main since the last release",
                badge(S.commits.length()),
                mono(f"main {S.main_head} · {S.latest}", c="dimmed"),
            ),
            mn.divider(),
            rx.foreach(S.commits, _commit_row),
            rx.cond(S.commits.length() == 0, empty("Nothing new since the last tag.")),
        ),
        mn.textarea(
            label="Release notes",
            description="Drafted from the changed items. Used as tag message and "
            "GitHub Release text.",
            default_value=S.notes,
            on_blur=S.set_notes,
            autosize=True,
            min_rows=6,
            ff="'JetBrains Mono', monospace",
        ),
        mn.group(
            mn.button(
                "Create release",
                left_section=rx.icon("tag", size=14),
                disabled=S.nothing_new,
                loading=working("release"),
                on_click=work("release", S.create),
            ),
            mn.text(
                "Checks that main validates, then tags it and creates a GitHub "
                "Release.",
                size="xs",
                c="dimmed",
            ),
            gap="sm",
        ),
        gap="md",
    )


def _tag_row(t: rx.Var) -> rx.Component:
    return mn.group(
        rx.icon("tag", size=13),
        mono(t["tag"].to(str).replace("marketplace-", ""), flex="1"),
        mn.text(f"{t['items']} items", size="xs", c="dimmed"),
        px="md",
        py="xs",
    )


def past_releases() -> rx.Component:
    return panel(
        panel_head("Past releases"),
        mn.divider(),
        rx.foreach(S.tags, _tag_row),
        rx.cond(S.tags.length() == 0, empty("No release yet.")),
    )
