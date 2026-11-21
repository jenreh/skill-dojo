"""Build the core ``Context`` from the working directory and ``gh``."""

import os
from datetime import UTC, datetime
from pathlib import Path

from skill_dojo_core import Context, GhCli, NotFoundError


def find_repo_root(start: Path) -> Path:
    """The nearest directory at or above ``start`` that holds ``.git``."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    raise NotFoundError(f"{start} is not inside a git repository")


def resolve_actor(github: GhCli) -> str:
    """``GITHUB_ACTOR`` in Actions, otherwise the ``gh auth`` login."""
    return os.environ.get("GITHUB_ACTOR") or github.current_user()


def build_context(start: Path | None = None, *, need_actor: bool = False) -> Context:
    repo = find_repo_root(start or Path.cwd())
    github = GhCli(cwd=repo)
    actor = resolve_actor(github) if need_actor else ""
    return Context(repo=repo, github=github, actor=actor, now=datetime.now(UTC))
