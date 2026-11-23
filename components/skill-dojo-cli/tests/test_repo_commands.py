from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer
from typer.testing import CliRunner, Result

from skill_dojo_cli.main import app
from tests.support.fake_github import FakeGitHub
from tests.support.fake_mcp_registry import FakeMcpRegistry, npm
from tests.support.fixture_repos import (
    FixtureRepos,
    agent_plugin_manifest,
    git,
    skill_md,
    write_tree,
)

runner = CliRunner()


@pytest.fixture
def repo(fixture_repos: FixtureRepos, monkeypatch: pytest.MonkeyPatch) -> Path:
    _, clone = fixture_repos.curated()
    monkeypatch.chdir(clone)
    return clone


def invoke(*args: str) -> Result:
    return runner.invoke(app, list(args), catch_exceptions=False)


def test_init_build_validate_local_flow(repo: Path) -> None:
    result = invoke("init", "--name", "acme", "--tool-git", "1" * 40)
    assert result.exit_code == 0, result.output
    assert "registry/config.yaml" in result.output
    assert invoke("validate").exit_code == 0
    write_tree(
        repo,
        {
            "plugins/hello/plugin.json": agent_plugin_manifest("hello"),
            "plugins/hello/skills/greet/SKILL.md": skill_md(
                "greet", "Greets the user. Use when saying hello."
            ),
        },
    )
    failed = invoke("validate")
    assert failed.exit_code == 1
    assert "not tracked" in failed.output
    added = invoke("local", "add", "plugins/hello", "--category", "Coding")
    assert added.exit_code == 0, added.output
    assert "Added 'hello'" in added.output
    assert invoke("validate").exit_code == 0
    assert "Nothing to change" in invoke("build", "--check").output
    assert "Nothing to change" in invoke("build").output
    assert "current" in invoke("lock", "refresh").output
    (repo / "plugins/hello/notes.md").write_text("x\n")
    refreshed = invoke("lock", "refresh", "--item", "hello")
    assert "Refreshed" in refreshed.output


def test_build_check_fails_on_changes(repo: Path) -> None:
    invoke("init", "--tool-version", "1.2.3")
    (repo / ".claude-plugin/marketplace.json").write_text("{}")
    result = invoke("build", "--check")
    assert result.exit_code == 1
    assert ".claude-plugin/marketplace.json" in result.output
    changed = invoke("build")
    assert "Changed:" in changed.output


def test_build_keeps_workflows_of_the_pinned_tool(repo: Path) -> None:
    invoke("init", "--tool-version", "1.2.3")
    validate = repo / ".github/workflows/validate-marketplace.yml"
    sync = repo / ".github/workflows/sync-upstream.yml"
    older = "jobs:\n  v:\n    steps:\n      - run: uvx skill-dojo==1.2.3 validate\n"
    validate.write_text(older)
    sync.unlink()
    result = invoke("build", "--check")
    assert result.exit_code == 1
    assert ".github/workflows/sync-upstream.yml" in result.output
    assert "validate-marketplace" not in result.output
    invoke("build")
    assert validate.read_text() == older
    config = repo / "registry/config.yaml"
    config.write_text(config.read_text().replace("1.2.3", "1.2.4"))
    invoke("build")
    assert "uvx skill-dojo==1.2.4 build --check" in validate.read_text()


def test_init_pin_defaults_and_conflicts(repo: Path) -> None:
    result = runner.invoke(
        app, ["init", "--tool-git", "1" * 40, "--tool-version", "1.0.0"]
    )
    assert result.exception is not None
    assert "exactly one" in str(result.exception)
    assert invoke("init").exit_code == 0
    assert (
        "skill-dojo=="
        in (repo / ".github/workflows/validate-marketplace.yml").read_text()
    )


def test_init_adopt_reports(repo: Path) -> None:
    mcp = '{"mcpServers": {"d": {"type": "stdio", "command": "uvx", "args": ["d"]}}}'
    write_tree(
        repo,
        {
            "plugins/hello/plugin.json": agent_plugin_manifest("hello"),
            "plugins/hello/.mcp.json": mcp,
            "plugins/hello/skills/up/SKILL.md": skill_md("up", "Upstream skill here."),
            "plugins/hello/skills/up/LICENSE": "MIT\n",
        },
    )
    result = invoke("init", "--adopt", "--tool-git", "2" * 40)
    assert result.exit_code == 0, result.output
    assert "Adopted 1 plugin(s)" in result.output
    assert "Floating MCP references" in result.output
    assert "likely from upstream" in result.output


def test_marketplace_command(repo: Path, fixture_repos: FixtureRepos) -> None:
    market = fixture_repos.create("market", {"skills/a/SKILL.md": "x\n"})
    result = invoke("marketplace", "add", market.url)
    assert result.exit_code == 0, result.output
    assert "Added .agents/market at main" in result.output
    assert "Updated" in invoke("marketplace", "update", market.url).output


def test_source_mirror_parts_sync_flags_commands(
    repo: Path, fixture_repos: FixtureRepos, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeGitHub()
    monkeypatch.setattr("skill_dojo_cli.context.GhCli", lambda cwd: fake)
    monkeypatch.setenv("GITHUB_ACTOR", "ci")
    invoke("init", "--name", "acme", "--tool-git", "1" * 40)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "push", "-q", "origin", "HEAD:main")
    ap = fixture_repos.agent_plugins_marketplace()
    assert invoke("source", "add", "ap", ap.url, "--allow", "hello").exit_code == 0
    assert "agent_plugins_marketplace" in invoke("source", "list").output
    browsed = invoke("browse", "ap", "--parts").output
    assert "(cached)" in browsed
    assert "ap:hello/skill/greet" in browsed
    cl = fixture_repos.claude_marketplace()
    assert invoke("source", "add", "cl", cl.url).exit_code == 0
    browsed = invoke("browse", "cl", "--parts").output
    assert "cl v3.1.0 @ " in browsed
    assert "cl:tools/skill/lint 1.4.0" in browsed
    assert "Refreshed ap" in invoke("source", "refresh", "ap").output
    assert "Allowed" in invoke("source", "allow", "ap", "hello").output
    assert "hello: added" in invoke("mirror", "ap", "hello").output
    made = invoke("add-parts", "kit", "ap:hello/skill/greet", "--create")
    assert "kit: created" in made.output, made.output
    assert "kit: updated" in invoke("remove-parts", "kit", "skill/greet").output
    assert "own: created" in invoke("plugin", "new", "own").output
    assert "own: new -> 1.0.0" in invoke("version", "own", "--major").output
    bad = runner.invoke(app, ["version", "own"])
    assert bad.exit_code != 0
    synced = invoke("sync").output
    assert "hello: up-to-date" in synced
    assert "## Risk flags" in invoke("flags").output
    status = invoke("status").output
    assert "skill-dojo/changes (checked out)" in status
    assert "own [local, added]" in status
    assert "PR opened" in invoke("finish").output
    assert "PR #1 open" in invoke("status").output
    invoke("source", "add", "spare", ap.url)
    retyped = invoke("source", "set-type", "spare", "git")
    assert "'spare' is now git" in retyped.output, retyped.output
    assert "'spare' is now agent_plugins_marketplace" in (
        invoke("source", "set-type", "spare").output
    )
    assert "Removed" in invoke("source", "remove", "spare").output


def test_release_and_revoke_commands(
    repo: Path, fixture_repos: FixtureRepos, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeGitHub()
    monkeypatch.setattr("skill_dojo_cli.context.GhCli", lambda cwd: fake)
    remote = fixture_repos.root / "remotes" / "curated.git"
    fake.remote = remote
    invoke("init", "--name", "acme", "--tool-git", "1" * 40)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "push", "-q", "origin", "HEAD:main")
    assert "No work branch" in invoke("status").output
    assert "Nothing to finish" in invoke("finish").output
    invoke("plugin", "new", "own")
    assert "Pushed skill-dojo/changes" in invoke("finish", "--no-pr").output
    assert "PR opened" in invoke("finish", "--level", "own=minor").output
    assert fake.merge(1)
    released = invoke("release")
    assert "Tagged marketplace-v" in released.output
    assert "GitHub Release:" in released.output
    assert "nothing to release" in invoke("release").output
    revoked = invoke("revoke", "own")
    assert "own: removed" in revoked.output


def test_mcp_registry_browse_and_mirror(
    repo: Path, httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeGitHub()
    monkeypatch.setattr("skill_dojo_cli.context.GhCli", lambda cwd: fake)
    registry = FakeMcpRegistry(httpserver)
    registry.publish("io.github.acme/weather", "1.0.0", [npm("weather", "1.0.0")])
    registry.publish("io.github.acme/remote", "1.0.0")
    invoke("init", "--name", "acme", "--tool-git", "1" * 40)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "push", "-q", "origin", "HEAD:main")
    added = invoke("source", "add", "mcp", registry.url, "--type", "mcp_registry")
    assert added.exit_code == 0, added.output
    listed = invoke("browse", "mcp", "--search", "acme").output
    assert "io.github.acme/weather 1.0.0" in listed
    assert "cannot mirror" in listed
    assert "weather: added" in invoke("mirror", "mcp", "io.github.acme/weather").output
