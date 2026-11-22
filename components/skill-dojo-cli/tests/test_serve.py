import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skill_dojo_cli.main import app

runner = CliRunner()


def test_serve_without_web_extra_prints_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "skill_dojo_web", None)
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 2
    assert 'uv tool install "skill-dojo[web]"' in result.output


def test_serve_starts_the_web_ui_for_the_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "sub").mkdir()
    calls: list[tuple[Path, int]] = []
    fake = types.SimpleNamespace(
        serve=lambda repo, port: calls.append((repo, port)) or 0
    )
    monkeypatch.setitem(sys.modules, "skill_dojo_web", fake)
    monkeypatch.chdir(tmp_path / "sub")
    result = runner.invoke(app, ["serve", "--port", "8123"])
    assert result.exit_code == 0, result.output
    assert calls == [(tmp_path.resolve(), 8123)]
    assert "http://127.0.0.1:8123" in result.output
