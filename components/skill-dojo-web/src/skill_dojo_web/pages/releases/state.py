"""Releases: what main has since the last tag, and the manual release."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.state import AppState


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
    def load(self) -> None:
        self.load_shell()
        try:
            self.overview = core.release_overview(self._ctx()).model_dump(mode="json")
            self.notes = self.overview.get("notes", "")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)

    @rx.event
    def set_notes(self, value: str) -> None:
        self.notes = value

    @rx.event
    def create(self) -> None:
        try:
            result = core.release(self._ctx(), notes=self.notes)
            if result.status == "created":
                self._say(f"Released {result.tag}: {result.url or ''}".strip())
            else:
                self._say(f"Main has not changed since {result.tag}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()
