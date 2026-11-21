import pytest

import skill_dojo_web
from skill_dojo_core import NotImplementedYetError


def test_serve_is_a_stub() -> None:
    with pytest.raises(NotImplementedYetError):
        skill_dojo_web.serve()


def test_app_module_builds_an_app() -> None:
    from skill_dojo_web import app  # noqa: PLC0415  # imports reflex lazily

    assert app.app is not None
