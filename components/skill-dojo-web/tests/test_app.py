import pytest

import skill_dojo_web
from skill_dojo_core import NotImplementedYetError
from skill_dojo_web import app


def test_serve_is_a_stub() -> None:
    with pytest.raises(NotImplementedYetError):
        skill_dojo_web.serve()


def test_app_module_builds_an_app() -> None:
    assert app.app is not None
