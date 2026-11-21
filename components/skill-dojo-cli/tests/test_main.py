import logging
from importlib.metadata import version

import pytest
from typer.testing import CliRunner

from skill_dojo_cli.main import app

runner = CliRunner()

GROUPS = ["source", "bundle", "local", "lock", "review", "clients"]
COMMANDS = [
    "init",
    "browse",
    "mirror",
    "sync",
    "promote",
    "release",
    "revoke",
    "build",
    "validate",
    "flags",
    "vendor",
    "serve",
]


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
    runner.invoke(app, ["-v", "clients", "list"])
    assert logging.getLogger().level == logging.DEBUG
