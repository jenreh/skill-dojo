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


PR_JSON = (
    '{"number": 7, "url": "https://github.invalid/o/r/pull/7", "title": "t", '
    '"body": "b", "headRefName": "h", "baseRefName": "staging", "state": "OPEN"}'
)


def test_pull_request_commands(tmp_path: Path) -> None:
    script = f"""case "$1 $2" in
  "pr list") echo '[{PR_JSON}]' ;;
  "pr create") echo https://github.invalid/o/r/pull/7 ;;
  "pr view") echo '{PR_JSON}' ;;
  "pr edit") ;;
  "pr comment") echo "$@" > {tmp_path}/comment ;;
esac
"""
    gh = GhCli(cwd=tmp_path, executable=fake_gh(tmp_path, script))
    found = gh.find_open_pull_request("h", "staging")
    assert found is not None
    assert found.number == 7
    assert gh.open_pull_request("h", "staging", "t", "b").base == "staging"
    assert gh.update_pull_request(7, "t", "b").title == "t"
    gh.comment(7, "hello")
    assert "hello" in (tmp_path / "comment").read_text()


def test_no_open_pull_request(tmp_path: Path) -> None:
    gh = GhCli(cwd=tmp_path, executable=fake_gh(tmp_path, "echo '[]'\n"))
    assert gh.find_open_pull_request("h", "b") is None
