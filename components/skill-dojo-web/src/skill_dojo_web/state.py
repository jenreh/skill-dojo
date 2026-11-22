"""Shared UI state: theme, repo facts in the shell, notices, sync.

States only orchestrate: every fact and every change comes from a
``skill_dojo_core`` function called with a fresh ``Context``.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_core import Context, Registry, SkillDojoError
from skill_dojo_web import backend

log = logging.getLogger(__name__)


def failure(exc: Exception) -> str:
    """The message a notice shows for a failed core call."""
    if isinstance(exc, SkillDojoError):
        return str(exc)
    log.error("Unexpected error in the web UI", exc_info=exc)
    return f"Unexpected error: {exc}"


class AppState(rx.State):
    repository: str = ""
    branch: str = "staging"
    actor: str = ""
    gh_ok: bool = False
    version: str = backend.tool_version()
    queue_count: int = 0
    synced: str = "Not synced in this session"
    notice: str = ""
    notice_ok: bool = True
    busy: bool = False
    progress: str = ""

    @rx.var
    def initial(self) -> str:
        return self.actor[:1].upper()

    def _ctx(self, progress: Callable[[str], None] | None = None) -> Context:
        return backend.make_context(progress)

    def _say(self, text: str, ok: bool = True) -> None:
        self.notice, self.notice_ok = text, ok

    def _fail(self, exc: Exception) -> None:
        self._say(failure(exc), ok=False)

    @rx.event
    def dismiss(self) -> None:
        self.notice = ""

    @rx.event
    def load_shell(self) -> None:
        try:
            ctx = self._ctx()
            reg = Registry.load(ctx.repo)
            self.repository = reg.config.repository or reg.config.name
            self.branch = core.base_branch(reg)
            self.actor, self.gh_ok = ctx.actor, True
            self.queue_count = len(core.review_list(ctx).entries)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self.gh_ok = False
            self._fail(exc)

    @rx.event(background=True)
    async def run_sync(self) -> None:
        """``sync`` in a worker thread; progress lines reach the header."""
        async with self:
            if self.busy:
                return
            self.busy, self.progress = True, "Sync started"
        lines: list[str] = []
        try:
            ctx = self._ctx(lines.append)
            task = asyncio.create_task(asyncio.to_thread(core.sync, ctx))
            while not task.done():
                await asyncio.sleep(0.3)
                async with self:
                    self.progress = lines[-1] if lines else self.progress
            result = task.result()
            opened = [
                c.item for c in result.candidates if c.status in {"opened", "updated"}
            ]
            async with self:
                self.synced = "Synced just now"
                self._say(
                    f"Sync: {len(opened)} candidate PR(s) {', '.join(opened)}".strip()
                )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            async with self:
                self._fail(exc)
        finally:
            async with self:
                self.busy, self.progress = False, ""


def dump(models: list[Any]) -> list[dict[str, Any]]:
    """Pydantic results as plain dicts for state vars."""
    return [m.model_dump(mode="json") for m in models]
