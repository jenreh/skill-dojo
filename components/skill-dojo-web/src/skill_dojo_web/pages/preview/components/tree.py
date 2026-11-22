"""The generated tree and the check summary."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import badge, check_line, mono, section_title
from skill_dojo_web.pages.preview.state import PreviewState as S


def _entry(e: rx.Var) -> rx.Component:
    status = e["status"].to(str)
    nested = e["depth"].to(int) > 0
    parts = e["path"].to(str).split("/")
    return mn.group(
        rx.cond(nested, None, rx.icon("folder", size=14)),
        mono(
            rx.cond(
                nested,
                rx.cond(e["path"].to(str).endswith("/"), parts[-2] + "/", parts[-1]),
                e["path"],
            ),
            size="sm",
        ),
        rx.cond(
            status != "",
            badge(status, rx.cond(status == "A", "add", "warn"), ml="auto"),
        ),
        gap="xs",
        pl=rx.cond(nested, "lg", "xs"),
        py=2,
        wrap="nowrap",
    )


def tree() -> rx.Component:
    return mn.stack(
        section_title("Marketplace preview", "What skill-dojo build would commit"),
        mn.stack(rx.foreach(S.tree, _entry), gap=0),
        mn.divider(),
        rx.cond(
            S.errors == 0,
            check_line("validate: 0 errors"),
            check_line(f"validate: {S.errors} errors", "x"),
        ),
        check_line(f"{S.warnings.length()} warnings", "warn"),
        rx.cond(
            S.pending_count == 0,
            check_line("build is up to date"),
            check_line(f"build would change {S.pending_count} files", "warn"),
        ),
        gap="xs",
    )
