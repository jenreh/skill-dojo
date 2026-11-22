"""Clients and revocation: who uses which ref, and the revoke PR."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.state import AppState


class ClientsState(AppState):
    clients: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    item: str = ""
    action: str = "rollback"
    reason: str = ""
    adding: bool = False
    name: str = ""
    ref: str = ""
    contact: str = ""
    notes: str = ""

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

    @rx.var
    def affected_names(self) -> list[str]:
        return [c["name"] for c in self.target.get("affected", [])]

    @rx.var
    def affected_refs(self) -> str:
        refs = sorted({c["ref"] for c in self.target.get("affected", [])})
        return ", ".join(refs) or "no client ref"

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            ctx = self._ctx()
            self.clients = [c.model_dump() for c in core.clients_list(ctx).clients]
            self.targets = [
                t.model_dump(mode="json") for t in core.revoke_preview(ctx).targets
            ]
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        items = [t["item"] for t in self.targets]
        if items and self.item not in items:
            self.item = items[0]

    @rx.event
    def set_item(self, value: str) -> None:
        self.item = value

    @rx.event
    def set_action(self, value: str) -> None:
        self.action = value

    @rx.event
    def set_reason(self, value: str) -> None:
        self.reason = value

    @rx.event
    def toggle_add(self) -> None:
        self.adding = not self.adding

    @rx.event
    def set_field(self, key: str, value: str) -> None:
        setattr(self, key, value)

    @rx.event
    def add_client(self) -> None:
        try:
            core.clients_add(
                self._ctx(),
                self.name.strip(),
                self.ref.strip(),
                contact=self.contact or None,
                notes=self.notes or None,
                update=any(c["name"] == self.name.strip() for c in self.clients),
            )
            self._say(f"Client {self.name} uses {self.ref}")
            self.adding, self.name, self.ref, self.contact, self.notes = (
                False,
                "",
                "",
                "",
                "",
            )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def edit_client(self, name: str) -> None:
        found = next((c for c in self.clients if c["name"] == name), None)
        if found:
            self.adding = True
            self.name, self.ref = found["name"], found["ref"]
            self.contact, self.notes = found["contact"] or "", found["notes"] or ""

    @rx.event
    def remove_client(self, name: str) -> None:
        try:
            core.clients_remove(self._ctx(), name)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def revoke(self) -> None:
        try:
            result = core.revoke(
                self._ctx(),
                self.item,
                rollback=self.action == "rollback",
                reason=self.reason,
            )
            self._say(
                f"Revoke {result.item} ({result.action}): {result.pull_request.url}"
            )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()
