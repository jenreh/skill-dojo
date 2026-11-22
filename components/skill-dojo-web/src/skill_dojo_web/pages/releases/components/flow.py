"""staging → main: where each branch is, and the promote and tag actions."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import badge, mono, panel
from skill_dojo_web.pages.releases.state import ReleasesState as S


def _branch(
    name: rx.Var, channel: str, headline: rx.Component, sha: rx.Component
) -> rx.Component:
    return mn.stack(
        mn.group(badge(name), mn.text(channel, size="xs", c="dimmed"), gap="xs"),
        headline,
        sha,
        gap=4,
        p="md",
        flex="1 1 240px",
    )


def flow() -> rx.Component:
    o = S.overview
    return panel(
        mn.flex(
            _branch(
                o["staging"],
                "beta",
                mn.text(f"{S.items.length()} items ahead", size="xl", fw=600),
                mono(
                    f"HEAD {o['staging_head']} · {o['commits_ahead']} commits",
                    c="dimmed",
                ),
            ),
            mn.center(rx.icon("arrow-right", size=24), c="dimmed", px="md"),
            _branch(
                o["main"],
                "stable",
                mn.text(
                    rx.cond(
                        o["latest_tag"].to(str) != "", o["latest_tag"], "no release yet"
                    ),
                    size="xl",
                    fw=600,
                ),
                mono(
                    f"HEAD {o['main_head']}",
                    rx.cond(o["untagged"].to(bool), " · untagged commits", ""),
                    c="dimmed",
                ),
            ),
            mn.stack(
                mn.button(
                    "Open promote PR",
                    left_section=rx.icon("git-pull-request-arrow", size=14),
                    loading=S.busy,
                    on_click=S.promote,
                ),
                mn.text(
                    "Stamps approvals, rebuilds catalogs, runs validate",
                    size="xs",
                    c="dimmed",
                    ta="center",
                ),
                rx.cond(
                    o["untagged"].to(bool),
                    mn.button(
                        "Tag release of main",
                        left_section=rx.icon("tag", size=14),
                        variant="default",
                        on_click=S.tag,
                    ),
                ),
                justify="center",
                gap="xs",
                p="md",
                flex="1 1 220px",
                bg="var(--mantine-color-default-hover)",
            ),
            wrap="wrap",
            align="stretch",
        ),
    )
