"""The explicit context every core operation receives."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from skill_dojo_core.github import GitHub


@dataclass(frozen=True, slots=True)
class Context:
    """Who runs an operation, on which repo, at what time.

    Core never reads the working directory, the environment or ``gh auth`` itself.
    The caller builds this once per command (CLI) or per request (server).
    """

    repo: Path
    github: GitHub
    actor: str
    now: datetime
    progress: Callable[[str], None] | None = None

    def __post_init__(self) -> None:
        if self.now.tzinfo is None:
            raise ValueError("Context.now needs a timezone")

    def report(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)
