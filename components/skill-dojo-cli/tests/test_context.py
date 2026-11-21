from pathlib import Path

import pytest

from skill_dojo_cli.context import build_context, find_repo_root
from skill_dojo_core import NotFoundError
from tests.support.fixture_repos import git


def test_find_repo_root_walks_up(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == tmp_path.resolve()


def test_find_repo_root_outside_git(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        find_repo_root(tmp_path)


def test_build_context_prefers_github_actor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git(tmp_path, "init", "-q")
    monkeypatch.setenv("GITHUB_ACTOR", "ci-bot")
    ctx = build_context(tmp_path, need_actor=True)
    assert ctx.actor == "ci-bot"
    assert ctx.repo == tmp_path.resolve()
    assert ctx.now.tzinfo is not None


def test_build_context_without_actor(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    ctx = build_context(tmp_path)
    assert ctx.actor == ""
