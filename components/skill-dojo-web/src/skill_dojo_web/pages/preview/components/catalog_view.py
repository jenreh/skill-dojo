"""One generated catalog, as changes against staging or the full file."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import diff_line, empty, mono, panel
from skill_dojo_web.pages.preview.state import PreviewState as S


def _warning(w: rx.Var) -> rx.Component:
    return mn.group(
        rx.icon("triangle-alert", size=15, color="var(--mantine-color-yellow-6)"),
        mn.text(w["message"], size="sm", flex="1"),
        mono(w["path"], c="brand"),
        px="md",
        py="xs",
        wrap="nowrap",
    )


def catalog_view() -> rx.Component:
    p = S.preview
    return mn.stack(
        mn.group(
            mn.stack(
                mono(f"compared with {p['base']} HEAD {p['base_head']}", c="dimmed"),
                mn.title(S.current["path"], order=2, size="h5", ff="monospace"),
                gap=2,
            ),
            mn.group(
                mn.segmented_control(
                    data=[
                        {"label": "Agent Plugins", "value": "0"},
                        {"label": "Claude Code", "value": "1"},
                    ],
                    value=S.catalog_key,
                    on_change=S.set_catalog,
                    size="xs",
                ),
                mn.segmented_control(
                    data=[
                        {"label": "Changes", "value": "changes"},
                        {"label": "Full file", "value": "full"},
                    ],
                    value=S.view,
                    on_change=S.set_view,
                    size="xs",
                ),
                mn.button(
                    "Copy",
                    left_section=rx.icon("copy", size=14),
                    variant="default",
                    size="xs",
                    on_click=rx.set_clipboard(S.current["text"].to(str)),
                ),
                gap="xs",
            ),
            justify="space-between",
            wrap="wrap",
        ),
        panel(
            mn.scroll_area(
                rx.foreach(
                    S.lines,
                    lambda line: diff_line(
                        line["kind"].to(str), line["number"], line["text"]
                    ),
                ),
                rx.cond(S.lines.length() == 0, empty("No changes against staging.")),
                type="auto",
            ),
            py="xs",
        ),
        rx.cond(
            S.warnings.length() > 0,
            panel(rx.foreach(S.warnings, _warning)),
        ),
        gap="md",
    )
