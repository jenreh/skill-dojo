import logging
from importlib.metadata import version

import pytest
from typer.testing import CliRunner

from skill_dojo_cli.main import app
from skill_dojo_core import NotImplementedYetError

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


STUBS = [
    ["source", "add", "x", "o/r"],
    ["source", "list"],
    ["source", "remove", "x"],
    ["browse", "x"],
    ["mirror", "x", "p"],
    ["bundle", "create", "b"],
    ["bundle", "add", "b", "x:p/skill/s"],
    ["bundle", "remove", "b", "x:p/skill/s"],
    ["sync"],
    ["review", "list"],
    ["review", "show", "1"],
    ["review", "approve", "1"],
    ["review", "reject", "1"],
    ["review", "quarantine", "1"],
    ["promote"],
    ["release"],
    ["revoke", "x"],
    ["flags"],
    ["clients", "add", "c", "main"],
    ["clients", "list"],
    ["clients", "remove", "c"],
    ["vendor"],
]


@pytest.mark.parametrize("argv", STUBS, ids=" ".join)
def test_stubs_raise_not_implemented(argv: list[str]) -> None:
    result = runner.invoke(app, argv)
    assert isinstance(result.exception, NotImplementedYetError)


def test_verbose_enables_debug_logging() -> None:
    runner.invoke(app, ["-v", "promote"])
    assert logging.getLogger().level == logging.DEBUG
