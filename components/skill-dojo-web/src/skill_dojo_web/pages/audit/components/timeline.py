"""The audit timeline: filter, days, events."""

from typing import Any

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import empty, mono, panel, segmented
from skill_dojo_web.pages.audit.state import KINDS
from skill_dojo_web.pages.audit.state import AuditState as S

# event kind -> (icon, Mantine color)
DOTS = {
    "change": ("pencil", "blue"),
    "sync": ("refresh-cw", "blue"),
    "merge": ("git-merge", "green"),
    "release": ("tag", "yellow"),
    "revocation": ("shield", "red"),
}


def _dot(kind: rx.Var) -> rx.Component:
    def dot(name: str, color: str) -> rx.Component:
        return mn.theme_icon(rx.icon(name, size=15), color=color, variant="light")

    return rx.match(
        kind,
        *((key, dot(name, color)) for key, (name, color) in DOTS.items()),
        dot("clock", "gray"),
    )


def _event(e: rx.Var) -> rx.Component:
    return mn.group(
        _dot(e["kind"].to(str)),
        mn.text(
            mn.text(e["actor"], fw=600, span=True),
            " ",
            e["action"],
            " ",
            mn.text(e["subject"], fw=600, span=True),
            " ",
            mn.text(e["detail"], c="dimmed", span=True),
            size="sm",
            flex="1 1 280px",
        ),
        rx.cond(
            e["url"].to(str) != "",
            mn.anchor(mono(e["ref"]), href=e["url"].to(str), target="_blank"),
            mono(e["ref"], c="brand"),
        ),
        mono(e["time"], c="dimmed"),
        px="md",
        py="xs",
        wrap="wrap",
    )


def _day(group: rx.Var) -> rx.Component:
    return mn.stack(
        mn.text(
            group["day"], size="xs", fw=500, tt="uppercase", c="dimmed", lts="0.04em"
        ),
        panel(rx.foreach(group["events"].to(list[dict[str, Any]]), _event)),
        gap="xs",
    )


def timeline() -> rx.Component:
    return mn.stack(
        segmented(S.kind, KINDS, S.set_kind),
        rx.foreach(S.days, _day),
        rx.cond(S.days.length() == 0, empty("No events yet.")),
        gap="md",
    )
