import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skill_dojo_cli.main import app
from skill_dojo_core import NotFoundError

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


def _fake_web(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, int]]:
    calls: list[tuple[Path, int]] = []
    fake = types.SimpleNamespace(
        serve=lambda repo, port: calls.append((repo, port)) or 0
    )
    monkeypatch.setitem(sys.modules, "skill_dojo_web", fake)
    return calls


def test_serve_uses_the_repo_option_instead_of_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "my-repo"
    (target / ".git").mkdir(parents=True)
    (target / "sub").mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    calls = _fake_web(monkeypatch)
    monkeypatch.chdir(elsewhere)
    result = runner.invoke(app, ["serve", "--repo", str(target / "sub")])
    assert result.exit_code == 0, result.output
    assert calls == [(target.resolve(), 8080)]


def test_serve_expands_a_tilde_in_the_repo_option(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "my-repo" / ".git").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    calls = _fake_web(monkeypatch)
    result = runner.invoke(app, ["serve", "--repo", "~/my-repo"])
    assert result.exit_code == 0, result.output
    assert calls == [((tmp_path / "my-repo").resolve(), 8080)]


def test_serve_rejects_a_missing_repo_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".git").mkdir()
    calls = _fake_web(monkeypatch)
    result = runner.invoke(app, ["serve", "--repo", str(tmp_path / "missing")])
    assert isinstance(result.exception, NotFoundError)
    assert calls == []
