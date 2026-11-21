import threading
from pathlib import Path

import pytest

from skill_dojo_core import RepoLockedError
from skill_dojo_core.repo_lock import repo_lock


def test_lock_creates_registry_lock_file(tmp_path: Path) -> None:
    with repo_lock(tmp_path):
        assert (tmp_path / "registry" / ".lock").exists()


def test_second_lock_times_out(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with repo_lock(tmp_path):
            entered.set()
            release.wait(5)

    worker = threading.Thread(target=hold)
    worker.start()
    entered.wait(5)
    try:
        with pytest.raises(RepoLockedError), repo_lock(tmp_path, timeout=0.2):
            pass
    finally:
        release.set()
        worker.join()


def test_lock_is_reusable_after_release(tmp_path: Path) -> None:
    with repo_lock(tmp_path):
        pass
    with repo_lock(tmp_path, timeout=0.1):
        pass
