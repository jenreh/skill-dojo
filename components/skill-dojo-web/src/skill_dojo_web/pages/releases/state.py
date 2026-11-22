"""Releases: promote staging to main, then tag an immutable release."""

import asyncio
from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.state import AppState


class ReleasesState(AppState):
    overview: dict[str, Any] = {}
    notes: str = ""

    @rx.var
    def items(self) -> list[dict[str, Any]]:
        return [
            {
                **i,
                "change": f"{i['old_version']} → {i['new_version']}"
                if i.get("old_version")
                else f"new · {i.get('new_version') or ''}",
                "who": " · ".join(
                    x
                    for x in (
                        ("PR #" + i["pull_request"].rsplit("/", 1)[-1])
                        if i.get("pull_request")
                        else "",
                        ", ".join(i.get("reviewers", [])),
                    )
                    if x
                ),
            }
            for i in self.overview.get("items", [])
        ]

    @rx.var
    def blocks(self) -> list[str]:
        return list(self.overview.get("blocks", []))

    @rx.var
    def tags(self) -> list[dict[str, Any]]:
        return list(self.overview.get("tags", []))

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

    @rx.event(background=True)
    async def promote(self) -> None:
        """``promote`` in a worker thread; progress lines reach the header."""
        async with self:
            if self.busy:
                return
            self.busy, self.progress = True, "Promote started"
        lines: list[str] = []
        try:
            ctx = self._ctx(lines.append)
            task = asyncio.create_task(asyncio.to_thread(core.promote, ctx))
            while not task.done():
                await asyncio.sleep(0.3)
                async with self:
                    self.progress = lines[-1] if lines else self.progress
            result = task.result()
            url = result.pull_request.url if result.pull_request else ""
            async with self:
                self._say(f"Promote PR {result.status} {url}".strip())
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            async with self:
                self._fail(exc)
        finally:
            async with self:
                self.busy, self.progress = False, ""
                self.load()

    @rx.event
    def tag(self) -> None:
        try:
            result = core.release(self._ctx(), notes=self.notes)
            self._say(f"Release {result.tag}: {result.status}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()
