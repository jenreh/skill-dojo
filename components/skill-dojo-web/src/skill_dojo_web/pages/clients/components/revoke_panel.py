"""Revoke an item: action, affected clients, a change on the work branch."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import panel
from skill_dojo_web.pages.clients.state import ClientsState as S

STEPS = (
    "A commit on the work branch removes or rolls back the item",
    "A rollback sets the quarantine flag, so sync skips it",
    "Finish and merge the PR to ship it",
)


def revoke_panel() -> rx.Component:
    target = S.target
    return panel(
        mn.stack(
            mn.group(
                mn.theme_icon(
                    rx.icon("shield-x", size=16), color="red", variant="transparent"
                ),
                mn.text("Revoke an item", fw=600),
                gap="xs",
            ),
            mn.select(
                label="Item",
                data=S.item_options,
                value=S.item,
                on_change=S.set_item,
                allow_deselect=False,
            ),
            mn.select(
                label="Action",
                data=[
                    {
                        "value": "rollback",
                        "label": rx.cond(
                            target["rollback_to"].to(str) != "",
                            f"Roll back to {target['rollback_to']}",
                            "Roll back (no earlier release)",
                        ),
                    },
                    {"value": "remove", "label": "Remove from marketplace"},
                ],
                value=S.action,
                on_change=S.set_action,
                allow_deselect=False,
            ),
            mn.paper(
                mn.text(
                    f"{S.affected_names.length()} clients affected", fw=500, size="sm"
                ),
                mn.text(
                    f"In {S.affected_refs}. Tell them after the merge.",
                    size="xs",
                    c="dimmed",
                ),
                p="sm",
                bg="var(--mantine-color-default-hover)",
            ),
            mn.list_(
                *(
                    mn.list_.item(mn.text(step, size="xs", c="dimmed"))
                    for step in STEPS
                ),
                type="ordered",
                size="xs",
            ),
            mn.button(
                "Revoke on the work branch",
                color="red",
                variant="light",
                disabled=(S.item == "")
                | ((S.action == "rollback") & (target["rollback_to"].to(str) == "")),
                on_click=S.revoke,
            ),
            gap="sm",
        ),
        p="md",
    )
