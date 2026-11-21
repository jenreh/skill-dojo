"""Planned file changes on top of a repo, applied at once or only reported.

``build`` writes through an ``Overlay`` so that ``build --check`` runs the exact
same code and just reports what would change.
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from skill_dojo_core.errors import InvalidInputError

log = logging.getLogger(__name__)


def check_contained(repo: Path, rel: str) -> Path:
    """``repo / rel``, refusing ``..`` and symlinked parent directories.

    Generated files must never be written or read through a link that leaves
    the plugin (e.g. a ``.claude-plugin`` folder linked to ``.github/workflows``).
    """
    parts = PurePosixPath(rel).parts
    if not parts or PurePosixPath(rel).is_absolute() or ".." in parts:
        raise InvalidInputError(f"{rel}: path leaves the repository")
    current = repo
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise InvalidInputError(f"{rel}: parent folder {part} is a symlink")
    return repo / rel


@dataclass(frozen=True)
class Link:
    target: str


type Entry = str | bytes | Link | None  # None = deleted


@dataclass
class Overlay:
    repo: Path
    pending: dict[str, Entry] = field(default_factory=dict)

    def _disk(self, rel: str) -> Entry:
        path = check_contained(self.repo, rel)
        if path.is_symlink():
            return Link(str(path.readlink()))
        if path.is_file():
            return path.read_bytes()
        return None

    def current(self, rel: str) -> Entry:
        if rel in self.pending:
            return self.pending[rel]
        return self._disk(rel)

    def exists(self, rel: str) -> bool:
        return self.current(rel) is not None

    def is_link(self, rel: str) -> bool:
        return isinstance(self.current(rel), Link)

    def read_text(self, rel: str) -> str | None:
        """Text of a file, following a link inside the repo; None if absent."""
        entry = self.current(rel)
        if isinstance(entry, Link):
            target = os.path.normpath(PurePosixPath(rel).parent / entry.target)
            if target.startswith(".."):
                return None
            return self.read_text(target)
        if isinstance(entry, bytes):
            return entry.decode("utf-8")
        return entry

    def _set(self, rel: str, entry: Entry) -> None:
        disk = self._disk(rel)
        same = disk == entry or (
            isinstance(entry, str)
            and isinstance(disk, bytes)
            and disk == entry.encode()
        )
        if same:
            self.pending.pop(rel, None)
        else:
            self.pending[rel] = entry

    def write(self, rel: str, content: str | bytes) -> None:
        self._set(rel, content)

    def link(self, rel: str, target: str) -> None:
        self._set(rel, Link(target))

    def remove(self, rel: str) -> None:
        self._set(rel, None)

    def changes(self) -> list[str]:
        return sorted(self.pending)

    def apply(self) -> None:
        for rel, entry in sorted(self.pending.items()):
            path = check_contained(self.repo, rel)
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir() and entry is not None:
                shutil.rmtree(path)
            if entry is None:
                log.debug("Removed %s", rel)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(entry, Link):
                path.symlink_to(entry.target)
            elif isinstance(entry, bytes):
                path.write_bytes(entry)
            else:
                path.write_text(entry, encoding="utf-8")
            log.debug("Wrote %s", rel)
        self.pending.clear()
