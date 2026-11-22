"""The clients table and the add/edit form."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import empty, mono, page_header, panel
from skill_dojo_web.pages.clients.state import ClientsState as S

FIELDS = [
    ("Workspace", "name"),
    ("Ref in use", "ref"),
    ("Contact", "contact"),
    ("Client", "notes"),
]


def client_form() -> rx.Component:
    return panel(
        mn.group(
            *(
                mn.text_input(
                    label=label,
                    value=getattr(S, key),
                    on_change=lambda value, key=key: S.set_field(key, value),
                    required=key in {"name", "ref"},
                    flex="1 1 160px",
                )
                for label, key in FIELDS
            ),
            mn.button("Save client", on_click=S.add_client),
            align="flex-end",
            wrap="wrap",
        ),
        p="sm",
    )


def _row(c: rx.Var) -> rx.Component:
    hit = S.affected_names.contains(c["name"])
    return mn.table.tr(
        mn.table.td(
            mn.anchor(
                c["name"],
                fw=500,
                underline="hover",
                on_click=S.edit_client(c["name"].to(str)),
            )
        ),
        mn.table.td(c["notes"]),
        mn.table.td(mono(c["ref"])),
        mn.table.td(mn.text(c["contact"], size="sm", c="dimmed")),
        mn.table.td(
            rx.cond(
                hit,
                mn.badge(
                    "yes",
                    color="red",
                    variant="transparent",
                    left_section=rx.icon("triangle-alert", size=11),
                ),
                mn.text("no", size="sm", c="dimmed"),
            )
        ),
        mn.table.td(
            mn.action_icon(
                rx.icon("x", size=14),
                variant="subtle",
                color="gray",
                aria_label=f"Remove {c['name']}",
                on_click=S.remove_client(c["name"].to(str)),
            ),
            ta="right",
        ),
        bg=rx.cond(hit, "var(--mantine-color-red-light)", "transparent"),
    )


def client_table() -> rx.Component:
    return mn.stack(
        page_header(
            "Clients",
            "Hand-kept in registry/clients.yaml. Who to warn when something is "
            "revoked.",
            mn.button(
                "Add client",
                left_section=rx.icon("plus", size=13),
                variant="default",
                on_click=S.toggle_add,
            ),
        ),
        rx.cond(S.adding, client_form()),
        panel(
            mn.table.scroll_container(
                mn.table(
                    mn.table.thead(
                        mn.table.tr(
                            *(
                                mn.table.th(h)
                                for h in (
                                    "Workspace",
                                    "Client",
                                    "Ref in use",
                                    "Contact",
                                    "Affected",
                                )
                            ),
                            mn.table.th(mn.visually_hidden("Actions")),
                        )
                    ),
                    mn.table.tbody(rx.foreach(S.clients, _row)),
                    vertical_spacing="sm",
                ),
                min_width=620,
            ),
            rx.cond(S.clients.length() == 0, empty("No clients yet.")),
        ),
        gap="md",
    )
