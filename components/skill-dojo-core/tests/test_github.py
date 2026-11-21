import stat
from pathlib import Path

import pytest

from skill_dojo_core import ExternalToolError, GhCli


def fake_gh(tmp_path: Path, script: str) -> str:
    exe = tmp_path / "gh"
    exe.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)


def test_current_user(tmp_path: Path) -> None:
    gh = GhCli(cwd=tmp_path, executable=fake_gh(tmp_path, "echo alice\n"))
    assert gh.current_user() == "alice"


def test_api_parses_json(tmp_path: Path) -> None:
    gh = GhCli(cwd=tmp_path, executable=fake_gh(tmp_path, "echo '{\"a\": 1}'\n"))
    assert gh.api("repos/x/y") == {"a": 1}


def test_failure_raises_external_tool_error(tmp_path: Path) -> None:
    gh = GhCli(cwd=tmp_path, executable=fake_gh(tmp_path, "echo boom >&2\nexit 1\n"))
    with pytest.raises(ExternalToolError, match="boom"):
        gh.current_user()


def test_missing_executable(tmp_path: Path) -> None:
    gh = GhCli(cwd=tmp_path, executable=str(tmp_path / "nope"))
    with pytest.raises(ExternalToolError, match="not installed"):
        gh.current_user()
