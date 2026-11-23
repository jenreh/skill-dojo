"""Releases: what main has since the last tag, and the manual release."""

from typing import Any

import reflex as rx
from reflex.event import EventSpec

import skill_dojo_core as core
from skill_dojo_web.state import AppState, off_loop


class ReleasesState(AppState):
    overview: dict[str, Any] = {}
    notes: str = ""

    @rx.var
    def commits(self) -> list[dict[str, Any]]:
        return list(self.overview.get("commits", []))

    @rx.var
    def tags(self) -> list[dict[str, Any]]:
        return list(self.overview.get("tags", []))

    @rx.var
    def untagged(self) -> bool:
        return bool(self.overview.get("untagged", False))

    @rx.var
    def nothing_new(self) -> bool:
        return not self.overview.get("untagged", False)

    @rx.var
    def latest(self) -> str:
        return str(self.overview.get("latest_tag") or "no release yet")

    @rx.var
    def main_head(self) -> str:
        return str(self.overview.get("main_head") or "")

    @rx.event
    @off_loop
    def load(self) -> list[EventSpec]:
        return self._load()

    def _load(self) -> list[EventSpec]:
        self.load_shell()
        try:
            self.overview = core.release_overview(self._ctx()).model_dump(mode="json")
            self.notes = self.overview.get("notes", "")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        return self._flush()

    @rx.event
    def set_notes(self, value: str) -> None:
        self.notes = value

    @rx.event
    @off_loop
    def create(self) -> list[EventSpec]:
        try:
            result = core.release(self._ctx(), notes=self.notes)
            if result.status == "created":
                self._say(f"Released {result.tag}: {result.url or ''}".strip())
            else:
                self._say(f"Main has not changed since {result.tag}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        return self._load()
