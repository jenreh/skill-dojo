"""Shared UI state: theme, repo facts in the shell, toasts, sync.

States only orchestrate: every fact and every change comes from a
``skill_dojo_core`` function called with a fresh ``Context``.
"""

import asyncio
import functools
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any, Concatenate

import appkit_mantine as mn
import reflex as rx
from reflex.event import EventSpec

import skill_dojo_core as core
from skill_dojo_core import Context, Registry, SkillDojoError
from skill_dojo_web import backend

log = logging.getLogger(__name__)

TOAST_MS = 5000
FAILURE_TOAST_MS = 10000


def toast(text: str, ok: bool = True) -> EventSpec:
    """A notification that closes by itself and always has a close button."""
    return mn.notifications.show(
        text,
        color="teal" if ok else "red",
        auto_close=TOAST_MS if ok else FAILURE_TOAST_MS,
        with_auto_close_progress=True,
        with_close_button=True,
    )


def failure(exc: Exception) -> str:
    """The message a toast shows for a failed core call."""
    if isinstance(exc, SkillDojoError):
        return str(exc)
    log.error("Unexpected error in the web UI", exc_info=exc)
    return f"Unexpected error: {exc}"


def off_loop[S, **P, R](
    fn: Callable[Concatenate[S, P], R],
) -> Callable[Concatenate[S, P], Coroutine[Any, Any, R]]:
    """Run a handler in a worker thread: core runs git and gh, which block."""

    @functools.wraps(fn)
    async def run(self: S, *args: P.args, **kwargs: P.kwargs) -> R:
        return await asyncio.to_thread(fn, self, *args, **kwargs)

    return run


class AppState(rx.State):
    repository: str = ""
    branch: str = "skill-dojo/changes"
    actor: str = ""
    gh_ok: bool = False
    version: str = backend.tool_version()
    queue_count: int = 0
    synced: str = "Not synced in this session"
    notice: str = ""
    notice_ok: bool = True
    _toasts: list[tuple[str, bool]] = []
    busy: bool = False
    progress: str = ""
    working: str = ""

    @rx.var
    def initial(self) -> str:
        return self.actor[:1].upper()

    def _ctx(self, progress: Callable[[str], None] | None = None) -> Context:
        return backend.make_context(progress)

    def _say(self, text: str, ok: bool = True) -> None:
        """Queue a toast; the event handler returns it with ``_flush``."""
        self.notice, self.notice_ok = text, ok
        self._toasts = [*self._toasts, (text, ok)]

    def _flush(self) -> list[EventSpec]:
        """The queued toasts as events, emptying the queue."""
        found, self._toasts = self._toasts, []
        return [toast(text, ok) for text, ok in found]

    def _fail(self, exc: Exception) -> None:
        self._say(failure(exc), ok=False)

    @rx.event
    def start_work(self, key: str) -> None:
        """Mark the control ``key`` as busy; its spinner shows until ``end_work``."""
        self.working = key

    @rx.event
    def end_work(self) -> None:
        self.working = ""

    def load_shell(self) -> None:
        try:
            ctx = self._ctx()
            reg = Registry.load(ctx.repo)
            self.repository = reg.config.repository or reg.config.name
            self.branch = core.work_branch(reg)
            self.actor, self.gh_ok = ctx.actor, True
            self.queue_count = len(core.pending_versions(ctx))
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self.gh_ok = False
            self._fail(exc)

    @rx.event(background=True)
    async def run_sync(self) -> AsyncIterator[list[EventSpec]]:
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
            changed = result.changed
            async with self:
                self.synced = "Synced just now"
                self._say(
                    f"Sync: {len(changed)} update(s) on the work branch "
                    f"{', '.join(changed)}".strip()
                )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            async with self:
                self._fail(exc)
        finally:
            async with self:
                self.busy, self.progress = False, ""
                toasts = self._flush()
        yield toasts


def dump(models: list[Any]) -> list[dict[str, Any]]:
    """Pydantic results as plain dicts for state vars."""
    return [m.model_dump(mode="json") for m in models]
