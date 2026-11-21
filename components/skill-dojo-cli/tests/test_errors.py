import pytest

from skill_dojo_cli.errors import exit_code_for
from skill_dojo_cli.main import main
from skill_dojo_core import (
    NotImplementedYetError,
    SkillDojoError,
    ValidationFailedError,
)


def test_validation_failure_exits_one() -> None:
    assert exit_code_for(ValidationFailedError("x")) == 1


def test_unknown_error_exits_one() -> None:
    assert exit_code_for(SkillDojoError("x")) == 1


def test_not_implemented_has_its_own_code() -> None:
    assert exit_code_for(NotImplementedYetError("x")) == 3


def test_main_maps_core_errors_to_exit_codes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["skill-dojo", "promote"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 3
    assert "not implemented" in capsys.readouterr().err
