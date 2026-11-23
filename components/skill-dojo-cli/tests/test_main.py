import logging
from importlib.metadata import version

import pytest
from typer.testing import CliRunner

from skill_dojo_cli.main import app

runner = CliRunner()

GROUPS = ["source", "plugin", "local", "lock", "marketplace"]
COMMANDS = [
    "init",
    "browse",
    "mirror",
    "add-parts",
    "remove-parts",
    "version",
    "sync",
    "status",
    "finish",
    "release",
    "revoke",
    "build",
    "validate",
    "flags",
    "serve",
]
REMOVED = ["review", "promote", "bundle", "vendor", "clients"]


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert version("skill-dojo") in result.output


def test_root_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in GROUPS + COMMANDS:
        assert name in result.output


@pytest.mark.parametrize("name", GROUPS + COMMANDS)
def test_every_command_has_help(name: str) -> None:
    result = runner.invoke(app, [name, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


def test_verbose_enables_debug_logging() -> None:
    runner.invoke(app, ["-v", "validate"])
    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.parametrize("name", REMOVED)
def test_removed_commands_are_gone(name: str) -> None:
    assert runner.invoke(app, [name, "--help"]).exit_code != 0
