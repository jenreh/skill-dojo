import sys

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
