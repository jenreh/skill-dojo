"""Shared pytest fixtures for all packages and the end-to-end tests."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_dojo_core import Context
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import FixtureRepos

NOW = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated_git(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep the user's git config (signing, hooks, aliases) out of every test."""
    home = tmp_path_factory.mktemp("git-home")
    config = home / ".gitconfig"
    config.write_text(
        "[user]\n\tname = Test\n\temail = test@example.invalid\n"
        "[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n"
        "[init]\n\tdefaultBranch = main\n"
        '[protocol "file"]\n\tallow = always\n',
        encoding="utf-8",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GIT_CONFIG_GLOBAL", str(config))
        mp.setenv("GIT_CONFIG_NOSYSTEM", "1")
        mp.delenv("GIT_DIR", raising=False)
        mp.delenv("GIT_WORK_TREE", raising=False)
        yield


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Commands default to the cwd; never let a test run them in this checkout."""
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def fixture_repos(tmp_path: Path) -> FixtureRepos:
    return FixtureRepos(tmp_path / "fixtures")


@pytest.fixture
def make_context(fake_github: FakeGitHub) -> Callable[..., Context]:
    def make(repo: Path, actor: str = "alice") -> Context:
        return Context(repo=repo, github=fake_github, actor=actor, now=NOW)

    return make
