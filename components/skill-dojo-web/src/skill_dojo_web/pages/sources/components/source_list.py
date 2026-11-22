"""The source list and the add-source form."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import badge, mono, section_title
from skill_dojo_web.pages.sources.state import TYPE_LABEL
from skill_dojo_web.pages.sources.state import SourcesState as S


def _source_row(source: rx.Var) -> rx.Component:
    return mn.unstyled_button(
        mn.stack(
            mn.text(source["id"], fw=600, size="sm"),
            mn.group(badge(source["type"]), mono(source["where"], c="dimmed"), gap=6),
            gap=4,
        ),
        on_click=S.select(source["id"].to(str)),
        p="sm",
        w="100%",
        bg=rx.cond(
            S.selected == source["id"],
            "var(--mantine-color-default-hover)",
            "transparent",
        ),
        style={"borderRadius": "var(--mantine-radius-md)"},
    )


def add_form() -> rx.Component:
    return mn.paper(
        mn.stack(
            mn.text_input(
                label="Id", value=S.new_id, on_change=S.set_new_id, required=True
            ),
            mn.text_input(
                label="Repository or URL",
                value=S.new_repo,
                on_change=S.set_new_repo,
                required=True,
            ),
            mn.select(
                label="Type",
                data=[{"value": k, "label": v} for k, v in TYPE_LABEL.items()],
                value=S.new_type,
                on_change=S.set_new_type,
                allow_deselect=False,
            ),
            mn.button("Add source", on_click=S.add_source),
            gap="xs",
        ),
        with_border=True,
        p="sm",
    )


def source_list() -> rx.Component:
    return mn.stack(
        mn.group(
            section_title("Sources", "registry/sources.yaml"),
            mn.button(
                "Add",
                left_section=rx.icon("plus", size=13),
                variant="default",
                size="xs",
                on_click=S.toggle_add,
            ),
            justify="space-between",
        ),
        rx.cond(S.adding, add_form()),
        rx.foreach(S.sources, _source_row),
        mn.paper(
            mn.text(
                "Sync runs on a schedule in GitHub Actions.", size="xs", c="dimmed"
            ),
            mono(".github/workflows/sync.yml", c="dimmed"),
            p="sm",
            with_border=True,
            style={"borderStyle": "dashed"},
        ),
        gap="xs",
    )
