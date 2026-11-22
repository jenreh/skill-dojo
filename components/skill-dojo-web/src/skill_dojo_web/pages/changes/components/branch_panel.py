"""The work branch: where it stands, its PR and the finish button."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import mono, panel
from skill_dojo_web.pages.changes.state import ChangesState as S


def branch_panel() -> rx.Component:
    return panel(
        mn.stack(
            mn.group(
                rx.icon("git-branch", size=16),
                mn.text("Work branch", fw=600),
                gap="xs",
            ),
            mono(S.branch_line, size="sm"),
            mn.group(
                rx.icon("git-pull-request", size=14),
                rx.cond(
                    S.pr_url != "",
                    mn.anchor(S.pr_label, href=S.pr_url, target="_blank", size="sm"),
                    mn.text(S.pr_label, size="sm", c="dimmed"),
                ),
                gap="xs",
            ),
            rx.cond(
                S.dirty.length() > 0,
                mn.text(
                    f"{S.dirty.length()} uncommitted file(s); finish commits them.",
                    size="xs",
                    c="dimmed",
                ),
            ),
            mn.button(
                "Finish & open PR",
                left_section=rx.icon("send", size=14),
                loading=S.busy,
                disabled=S.nothing,
                on_click=S.finish,
            ),
            mn.text(
                "Runs build, sets the versions, pushes the branch and opens or "
                "updates one PR into main. Merging it is the approval.",
                size="xs",
                c="dimmed",
            ),
            gap="sm",
        ),
        p="md",
    )
