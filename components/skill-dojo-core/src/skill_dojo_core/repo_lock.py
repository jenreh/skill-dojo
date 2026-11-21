"""A per-repo file lock, so concurrent writers on one checkout cannot interleave."""

import logging
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from skill_dojo_core.errors import RepoLockedError

log = logging.getLogger(__name__)

LOCK_FILE = Path("registry") / ".lock"

if os.name == "nt":  # pragma: no cover
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def repo_lock(repo: Path, timeout: float = 30.0) -> Generator[None]:
    """Hold ``registry/.lock`` of ``repo`` for the duration of the block."""
    path = repo / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + timeout
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise RepoLockedError(f"{path} is held by another operation")
            time.sleep(0.05)
        log.debug("Acquired %s", path)
        try:
            yield
        finally:
            _unlock(fd)
            log.debug("Released %s", path)
    finally:
        os.close(fd)
