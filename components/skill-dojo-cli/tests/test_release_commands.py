"""CLI wiring of bundle, review, promote, release, revoke and clients."""

from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from skill_dojo_cli.main import app
from skill_dojo_core import ConflictError
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import FixtureRepos, git

runner = CliRunner()


def invoke(*args: str) -> Result:
    return runner.invoke(app, list(args), catch_exceptions=False)


@pytest.fixture
def fake(
    fixture_repos: FixtureRepos, monkeypatch: pytest.MonkeyPatch
) -> tuple[FakeGitHub, Path]:
    remote, clone = fixture_repos.curated()
    monkeypatch.chdir(clone)
    github = FakeGitHub(remote=remote.bare)
    monkeypatch.setattr("skill_dojo_cli.context.GhCli", lambda cwd: github)
    monkeypatch.setenv("GITHUB_ACTOR", "alice")
    invoke("init", "--name", "acme", "--tool-git", "1" * 40)
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "init")
    git(clone, "push", "-q", "origin", "HEAD:main")
    git(clone, "push", "-q", "origin", "HEAD:staging")
    ap = fixture_repos.agent_plugins_marketplace()
    assert invoke("source", "add", "ap", ap.url).exit_code == 0
    return github, clone


def test_bundle_review_promote_release_revoke(
    fake: tuple[FakeGitHub, Path],
) -> None:
    github, _ = fake
    created = invoke("bundle", "create", "kit", "ap:hello/skill/greet")
    assert "kit: opened" in created.output
    assert "#1 kit" in invoke("review", "list").output
    shown = invoke("review", "show", "1")
    assert "plugins/kit/plugin.json" in shown.output
    assert "### Parts" in shown.output
    assert "kit: merged" in invoke("review", "approve", "1").output
    assert "No open candidates." in invoke("review", "list").output
    with pytest.raises(ConflictError):
        invoke("bundle", "add", "kit", "ap:hello/skill/greet")
    assert "No mirrors or bundles" not in invoke("sync").output
    mirrored = invoke("mirror", "ap", "hello")
    assert "hello: opened" in mirrored.output
    number = github.pulls[-1].number
    assert "merged" in invoke("review", "approve", str(number)).output
    promoted = invoke("promote")
    assert "Promote PR opened" in promoted.output
    assert "approved hello" in promoted.output
    github.merge(github.pulls[-1].number)
    released = invoke("release")
    assert "Tagged marketplace-v" in released.output
    assert "already released" in invoke("release").output
    tag = released.output.split()[1]
    assert "team: " + tag in invoke("clients", "add", "team", tag).output
    assert "team" in invoke("clients", "list").output
    revoked = invoke("revoke", "hello", "--reason", "Bad.")
    assert "hello: removed" in revoked.output
    assert "team (" in revoked.output
    assert "No clients." in invoke("clients", "remove", "team").output


def test_reject_and_quarantine(fake: tuple[FakeGitHub, Path]) -> None:
    github, _ = fake
    invoke("mirror", "ap", "hello")
    rejected = invoke("review", "reject", "1", "--reason", "No.")
    assert "hello: closed" in rejected.output
    assert github.comments[1] == ["No."]
    invoke("bundle", "create", "kit", "ap:hello/skill/greet")
    invoke("review", "approve", "2")
    invoke("bundle", "remove", "kit", "skill/greet")
    quarantined = invoke("review", "quarantine", "3")
    assert "kit: quarantined" in quarantined.output
    assert "Quarantine PR" in quarantined.output
    github.blocked.add(4)
    assert "Branch protection" in invoke("review", "approve", "4").output
