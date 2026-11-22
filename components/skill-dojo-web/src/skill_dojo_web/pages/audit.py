"""Audit: a timeline built from merged PRs, candidate PRs and release tags."""

from datetime import UTC, datetime, timedelta
from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.icons import icon
from skill_dojo_web.shell import FAINT_12, heading, main_area, panel, shell
from skill_dojo_web.state import AppState

KINDS = [
    ("all", "All"),
    ("sync", "Sync"),
    ("approval", "Approval"),
    ("promotion", "Promotion"),
    ("release", "Release"),
    ("revocation", "Revocation"),
    ("quarantine", "Quarantine"),
]


def day_label(at: str, today: datetime) -> str:
    """``Today``, ``Yesterday`` or ``Nov 14`` for an ISO timestamp."""
    try:
        when = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(UTC).date()
    except ValueError:
        return "Undated"
    if when == today.date():
        return "Today"
    if when == (today - timedelta(days=1)).date():
        return "Yesterday"
    return f"{when:%b} {when.day}"


class AuditState(AppState):
    events: list[dict[str, Any]] = []
    kind: str = "all"
    csv: str = ""

    @rx.var
    def days(self) -> list[dict[str, Any]]:
        today = datetime.now(UTC)
        groups: dict[str, list[dict[str, Any]]] = {}
        for e in self.events:
            if self.kind in {"all", e["kind"]}:
                groups.setdefault(day_label(e["at"], today), []).append(e)
        return [{"day": day, "events": events} for day, events in groups.items()]

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            result = core.audit_log(self._ctx())
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.csv = result.csv()
        self.events = [
            {**e.model_dump(), "time": e.at[11:16] if len(e.at) >= 16 else ""}  # noqa: PLR2004
            for e in result.events
        ]

    @rx.event
    def set_kind(self, value: str) -> None:
        self.kind = value

    @rx.event
    def export(self) -> rx.event.EventSpec:
        return rx.download(data=self.csv, filename="skill-dojo-audit.csv")


S = AuditState


def _dot(kind: rx.Var) -> rx.Component:
    def dot(tone: str, name: str) -> rx.Component:
        bg = "var(--raised)" if tone == "muted" else f"var(--{tone}-bg)"
        return rx.el.span(
            icon(name, 15),
            class_name="dot",
            style={"background": bg, "color": f"var(--{tone})"},
        )

    return rx.match(
        kind,
        ("approval", dot("add", "check")),
        ("sync", dot("info", "sync")),
        ("quarantine", dot("muted", "pause")),
        ("release", dot("warn", "tag")),
        ("promotion", dot("muted", "promote")),
        ("revocation", dot("bad", "shield")),
        dot("muted", "audit"),
    )


def _event(e: rx.Var) -> rx.Component:
    bold = {"font_weight": "600"}
    return rx.el.div(
        _dot(e["kind"].to(str)),
        rx.el.span(
            rx.el.b(e["actor"], style=bold), " ", e["action"], " ",
            rx.cond(e["kind"].to(str) == "release", rx.el.span(e["subject"], class_name="mono", style={"color": "var(--text)"}), rx.el.b(e["subject"], style=bold)),
            " ", rx.el.span(e["detail"], style={"color": "var(--faint)"}),
            style={"flex": "1 1 280px"},
        ),
        rx.cond(e["url"].to(str) != "", rx.el.a(e["ref"], href=e["url"].to(str), class_name="mono", target="_blank", rel="noreferrer"), rx.el.span(e["ref"], class_name="mono", style={"color": "var(--accent)"})),
        rx.el.span(e["time"], class_name="mono", style={"color": "var(--faint)"}),
        class_name="ev",
    )  # fmt: skip


def _day(group: rx.Var) -> rx.Component:
    return rx.fragment(
        rx.el.div(group["day"], class_name="day"),
        panel(rx.foreach(group["events"].to(list[dict[str, Any]]), _event)),
    )


def audit_page() -> rx.Component:
    return shell(
        "audit",
        main_area(
            rx.el.div(
                rx.el.div(heading("Audit", "Built from git commits, PRs and tags. Nothing is stored apart."), style={"flex": "1 1 300px"}),
                rx.el.button("Export CSV", class_name="btn", on_click=S.export),
                style={"display": "flex", "flex_wrap": "wrap", "align_items": "flex-start", "gap": "12px"},
            ),
            rx.el.div(
                *(
                    rx.el.button(label, class_name=rx.cond(S.kind == key, "btn", "btn btn-ghost"), style={"min_height": "28px"}, on_click=S.set_kind(key), aria_pressed=S.kind == key)
                    for key, label in KINDS
                ),
                class_name="row", role="group", aria_label="Event type", style={"flex_wrap": "wrap", "gap": "4px"},
            ),
            rx.foreach(S.days, _day),
            rx.cond(S.days.length() == 0, rx.el.p("No events yet.", style=FAINT_12)),
            box_sizing="border-box", padding="18px 28px 28px", display="flex", flex_direction="column", gap="10px", max_width="1040px",
        ),
    )  # fmt: skip
