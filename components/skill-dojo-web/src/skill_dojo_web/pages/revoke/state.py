"""Revoking an item on the work branch."""

from typing import Any

import reflex as rx
from reflex.event import EventSpec

import skill_dojo_core as core
from skill_dojo_web.state import AppState, off_loop


class RevokeState(AppState):
    targets: list[dict[str, Any]] = []
    item: str = ""
    action: str = "remove"

    @rx.var
    def target(self) -> dict[str, Any]:
        return next((t for t in self.targets if t["item"] == self.item), {})

    @rx.var
    def item_options(self) -> list[dict[str, str]]:
        return [
            {
                "value": t["item"],
                "label": f"{t['item']} {t.get('version') or ''}".strip(),
            }
            for t in self.targets
        ]

    @rx.event
    @off_loop
    def load(self) -> list[EventSpec]:
        return self._load()

    def _load(self) -> list[EventSpec]:
        self.load_shell()
        try:
            self.targets = [
                t.model_dump(mode="json")
                for t in core.revoke_preview(self._ctx()).targets
            ]
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return self._flush()
        items = [t["item"] for t in self.targets]
        if items and self.item not in items:
            self.item = items[0]
        return self._flush()

    @rx.event
    def set_item(self, value: str) -> None:
        self.item = value

    @rx.event
    def set_action(self, value: str) -> None:
        self.action = value

    @rx.event
    @off_loop
    def revoke(self) -> list[EventSpec]:
        rollback = self.target.get("rollback_to") if self.action == "rollback" else None
        try:
            result = core.revoke(self._ctx(), self.item, to=rollback or None)
            self._say(
                f"Revoked {result.item} ({result.action}) on the work branch; "
                "finish it on the Changes page"
            )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        return self._load()
