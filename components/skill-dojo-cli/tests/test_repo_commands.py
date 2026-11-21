from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from skill_dojo_cli.main import app
from tests.support.fixture_repos import (
    FixtureRepos,
    agent_plugin_manifest,
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


def test_init_adopt_is_not_implemented_yet(repo: Path) -> None:
    result = runner.invoke(app, ["init", "--adopt"])
    assert result.exception is not None
