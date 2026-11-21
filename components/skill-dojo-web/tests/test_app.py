import pytest

import skill_dojo_web
from skill_dojo_core import NotImplementedYetError
from skill_dojo_web import app
from skill_dojo_web.components.navbar import app_navbar


def test_serve_is_a_stub() -> None:
    with pytest.raises(NotImplementedYetError):
        skill_dojo_web.serve()


def test_app_module_builds_an_app() -> None:
    assert app.app is not None


def test_app_links_the_shoji_svg_favicon() -> None:
    head = "".join(str(component) for component in app.app.head_components)
    assert "/img/logo/shoji_favicon.svg" in head
    assert "image/svg+xml" in head


def test_navbar_shows_the_shoji_logo_in_both_color_modes() -> None:
    rendered = str(app_navbar())
    assert "/img/logo/shoji_lockup.svg" in rendered
    assert "/img/logo/shoji_lockup_dark.svg" in rendered
