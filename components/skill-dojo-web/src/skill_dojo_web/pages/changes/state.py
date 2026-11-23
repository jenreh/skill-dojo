"""Changes: the work branch, its changed plugins with versions, finish & PR."""

import asyncio
from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.state import AppState

CUSTOM = "custom"
LEVEL_OPTIONS = [
    {"value": "patch", "label": "patch"},
    {"value": "minor", "label": "minor"},
    {"value": "major", "label": "major"},
    {"value": CUSTOM, "label": "custom"},
]


def flag_rows(flags: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {
            **f,
            "item": item,
            "where": f"{f['path']}:{f['line']}" if f.get("line") else f["path"],
            "tone": core.flag_severity(f["kind"]),
        }
        for item, found in flags.items()
        for f in found
    ]


class ChangesState(AppState):
    status: dict[str, Any] = {}
    pending: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    chosen: dict[str, str] = {}
    custom: dict[str, str] = {}

    @rx.var
    def rows(self) -> list[dict[str, Any]]:
        return [
            {
                **p,
                "choice": self.chosen.get(p["item"], p.get("level") or "patch"),
                "custom_version": self.custom.get(p["item"], ""),
                "shown_main": p.get("main_version") or "new",
                "shown_branch": p.get("branch_version") or "-",
            }
            for p in self.pending
        ]

    @rx.var
    def pr_url(self) -> str:
        pr = self.status.get("pull_request") or {}
        return str(pr.get("url") or "")

    @rx.var
    def pr_label(self) -> str:
        pr = self.status.get("pull_request") or {}
        return f"PR #{pr['number']} open" if pr else "No open PR"

    @rx.var
    def branch_line(self) -> str:
        s = self.status
        if not s:
            return ""
        if not s.get("exists"):
            return f"No {s['branch']} yet; the next change creates it."
        where = "checked out" if s.get("on_branch") else "not checked out"
        merged = " · merged" if s.get("merged") else ""
        return (
            f"{s['branch']} ({where}) · {s['ahead']} ahead, {s['behind']} behind "
            f"origin/{s['main']}{merged}"
        )

    @rx.var
    def dirty(self) -> list[str]:
        return list(self.status.get("dirty", []))

    @rx.var
    def nothing(self) -> bool:
        return not self.pending and not self.status.get("ahead")

    def levels(self) -> dict[str, str]:
        """Only what the admin chose by hand; build does the patch bumps."""
        found = {}
        for item, level in self.chosen.items():
            if level == CUSTOM:
                if self.custom.get(item):
                    found[item] = self.custom[item].strip()
            else:
                found[item] = level
        return found

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            result = core.changes_overview(self._ctx()).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.status = result["status"]
        self.pending = list(result["status"]["pending"])
        self.flags = flag_rows(result["flags"])
        known = {p["item"] for p in self.pending if p["editable"]}
        self.chosen = {k: v for k, v in self.chosen.items() if k in known}

    @rx.event
    def choose(self, item: str, level: str) -> None:
        self.chosen = {**self.chosen, item: level or "patch"}

    @rx.event
    def set_custom(self, item: str, value: str) -> None:
        self.custom = {**self.custom, item: value}

    @rx.event(background=True)
    async def finish(self) -> None:
        """``finish`` in a worker thread; progress lines reach the header."""
        async with self:
            if self.busy:
                return
            self.busy, self.progress = True, "Finish started"
            levels = self.levels()
        lines: list[str] = []
        try:
            ctx = self._ctx(lines.append)
            task = asyncio.create_task(
                asyncio.to_thread(core.finish, ctx, levels=levels)
            )
            while not task.done():
                await asyncio.sleep(0.3)
                async with self:
                    self.progress = lines[-1] if lines else self.progress
            result = task.result()
            url = result.pull_request.url if result.pull_request else ""
            async with self:
                self.chosen, self.custom = {}, {}
                self._say(
                    "Nothing to finish"
                    if result.status == "nothing"
                    else f"PR {result.status} {url}".strip()
                )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            async with self:
                self._fail(exc)
        finally:
            async with self:
                self.busy, self.progress = False, ""
                self.load()
