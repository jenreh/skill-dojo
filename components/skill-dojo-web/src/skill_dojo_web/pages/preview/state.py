"""Marketplace preview: the exact catalogs and tree ``build`` would commit."""

from typing import Any

import reflex as rx
from reflex.event import EventSpec

import skill_dojo_core as core
from skill_dojo_web.state import AppState, off_loop


class PreviewState(AppState):
    preview: dict[str, Any] = {}
    catalog: int = 0
    full: bool = False

    @rx.var
    def current(self) -> dict[str, Any]:
        catalogs = self.preview.get("catalogs", [])
        return catalogs[self.catalog] if len(catalogs) > self.catalog else {}

    @rx.var
    def tree(self) -> list[dict[str, Any]]:
        return list(self.preview.get("tree", []))

    @rx.var
    def warnings(self) -> list[dict[str, Any]]:
        return list(self.preview.get("warnings", []))

    @rx.var
    def pending_count(self) -> int:
        return len(self.preview.get("pending", []))

    @rx.var
    def errors(self) -> int:
        return int(self.preview.get("errors", 0))

    @rx.var
    def view(self) -> str:
        return "full" if self.full else "changes"

    @rx.var
    def catalog_key(self) -> str:
        return str(self.catalog)

    @rx.var
    def lines(self) -> list[dict[str, Any]]:
        return self.current.get("full" if self.full else "changes", [])

    @rx.event
    @off_loop
    def load(self) -> list[EventSpec]:
        self.load_shell()
        try:
            self.preview = core.marketplace_preview(self._ctx()).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        return self._flush()

    @rx.event
    def show_catalog(self, index: int) -> None:
        self.catalog = index

    @rx.event
    def set_catalog(self, value: str) -> None:
        """From the catalog switch: ``"0"`` or ``"1"``."""
        self.catalog = 1 if value == "1" else 0

    @rx.event
    def set_view(self, value: str) -> None:
        """From the view switch: ``changes`` or ``full``."""
        self.full = value == "full"

    @rx.event
    def set_full(self, value: bool) -> None:
        self.full = value
