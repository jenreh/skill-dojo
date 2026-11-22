"""Shared fixtures: a curated repo on a bare remote, and two upstream sources."""

from collections.abc import Callable

import pytest

from skill_dojo_core import Context, SourceType, ToolPin, init, source_add
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import FixtureRepo, FixtureRepos, git


@pytest.fixture
def admin(
    fixture_repos: FixtureRepos,
    make_context: Callable[..., Context],
    fake_github: FakeGitHub,
) -> Context:
    remote, clone = fixture_repos.curated()
    fake_github.remote = remote.bare
    ctx = make_context(clone)
    init(ctx, name="acme", tool=ToolPin(git="0" * 40), repository="acme/market")
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "init marketplace")
    git(clone, "push", "-q", "origin", "HEAD:main")
    return ctx


@pytest.fixture
def upstreams(admin: Context, fixture_repos: FixtureRepos) -> tuple[FixtureRepo, ...]:
    ap = fixture_repos.agent_plugins_marketplace()
    cl = fixture_repos.claude_marketplace()
    source_add(admin, "ap", ap.url)
    source_add(admin, "cl", cl.url, kind=SourceType.CLAUDE_MARKETPLACE)
    return ap, cl
