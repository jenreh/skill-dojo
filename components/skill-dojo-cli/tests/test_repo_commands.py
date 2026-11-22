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


def test_vendor_command(repo: Path, fixture_repos: FixtureRepos) -> None:
    market = fixture_repos.create("market", {"skills/a/SKILL.md": "x\n"})
    result = invoke("vendor", market.url)
    assert result.exit_code == 0, result.output
    assert "Vendored .agents/market at main" in result.output
    assert "Updated" in invoke("vendor", market.url, "--update").output


def test_source_mirror_sync_flags_commands(
    repo: Path, fixture_repos: FixtureRepos, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeGitHub()
    monkeypatch.setattr("skill_dojo_cli.context.GhCli", lambda cwd: fake)
    monkeypatch.setenv("GITHUB_ACTOR", "ci")
    invoke("init", "--name", "acme", "--tool-git", "1" * 40)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "push", "-q", "origin", "HEAD:staging")
    ap = fixture_repos.agent_plugins_marketplace()
    assert invoke("source", "add", "ap", ap.url, "--allow", "hello").exit_code == 0
    assert "agent_plugins_marketplace" in invoke("source", "list").output
    assert "hello" in invoke("browse", "ap").output
    mirrored = invoke("mirror", "ap", "hello")
    assert "hello: opened" in mirrored.output
    assert "No mirrors or bundles to sync" in invoke("sync").output
    assert "## Risk flags" in invoke("flags").output
    invoke("source", "add", "spare", ap.url)
    assert "Removed" in invoke("source", "remove", "spare").output


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
    git(repo, "push", "-q", "origin", "HEAD:staging")
    added = invoke("source", "add", "mcp", registry.url, "--type", "mcp_registry")
    assert added.exit_code == 0, added.output
    listed = invoke("browse", "mcp", "--search", "acme").output
    assert "io.github.acme/weather 1.0.0" in listed
    assert "cannot mirror" in listed
    assert "weather: opened" in invoke("mirror", "mcp", "io.github.acme/weather").output
