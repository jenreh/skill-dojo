"""The ``Context`` the web UI hands to core, built per event.

``serve`` passes the curated repo in ``SKILL_DOJO_REPO``. Tests replace
``settings.github`` with a fake; nothing else differs from the CLI.
"""

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from skill_dojo_core import Context, GhCli, GitHub, NotFoundError

log = logging.getLogger(__name__)

REPO_ENV = "SKILL_DOJO_REPO"


def _gh(repo: Path) -> GitHub:
    return GhCli(cwd=repo)


@dataclass
class Settings:
    github: Callable[[Path], GitHub] = _gh
    actors: dict[Path, str] = field(default_factory=dict)


settings = Settings()


def repo_path() -> Path:
    value = os.environ.get(REPO_ENV)
    if not value:
        raise NotFoundError(
            f"{REPO_ENV} is not set; start the UI with 'skill-dojo serve'"
        )
    return Path(value)


def actor(repo: Path, github: GitHub) -> str:
    """The ``gh auth`` login, asked once per repo."""
    if repo not in settings.actors:
        settings.actors[repo] = github.current_user()
    return settings.actors[repo]


async def warm_actor() -> None:
    """Ask ``gh`` for the login in a worker thread at startup.

    ``gh api user`` is a network call; asked inside the first page load it
    blocks the event loop. A failure here is left for that load to report.
    """
    try:
        repo = repo_path()
        await asyncio.to_thread(actor, repo, settings.github(repo))
    except Exception as exc:  # noqa: BLE001 (the page load reports it)
        log.debug("Actor prefetch failed: %s", exc)


def make_context(progress: Callable[[str], None] | None = None) -> Context:
    repo = repo_path()
    github = settings.github(repo)
    return Context(
        repo=repo,
        github=github,
        actor=actor(repo, github),
        now=datetime.now(UTC),
        progress=progress,
    )


def tool_version() -> str:
    try:
        return version("skill-dojo-web")
    except PackageNotFoundError:  # pragma: no cover (always installed)
        return "dev"
