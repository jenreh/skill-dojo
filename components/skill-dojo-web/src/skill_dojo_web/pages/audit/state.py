"""Audit: a timeline built from work-branch commits on main, merged PRs and tags."""

from datetime import UTC, datetime, timedelta
from typing import Any

import reflex as rx
from reflex.event import EventSpec

import skill_dojo_core as core
from skill_dojo_web.state import AppState, off_loop

KINDS = [
    ("all", "All"),
    ("change", "Change"),
    ("sync", "Sync"),
    ("merge", "Merge"),
    ("release", "Release"),
    ("revocation", "Revocation"),
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
    @off_loop
    def load(self) -> list[EventSpec]:
        self.load_shell()
        try:
            result = core.audit_log(self._ctx())
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return self._flush()
        self.csv = result.csv()
        self.events = [
            {**e.model_dump(), "time": e.at[11:16] if len(e.at) >= 16 else ""}  # noqa: PLR2004
            for e in result.events
        ]
        return self._flush()

    @rx.event
    def set_kind(self, value: str) -> None:
        self.kind = value

    @rx.event
    def export(self) -> rx.event.EventSpec:
        return rx.download(data=self.csv, filename="skill-dojo-audit.csv")
