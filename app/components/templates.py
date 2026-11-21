"""Page layouts of the app."""

from collections.abc import Callable

import appkit_mantine as mn
import reflex as rx
from appkit_user.authentication.templates import default_meta

from app.components.navbar import app_navbar


def default_layout(
    *,
    route: str | None = None,
    title: str | None = None,
    on_load: rx.EventHandler | list[rx.EventHandler] | None = None,
) -> Callable[[Callable[[], rx.Component]], rx.Component]:
    """Public page decorator for login and password reset (``PageLayout``)."""

    def decorator(page_content: Callable[[], rx.Component]) -> rx.Component:
        @rx.page(route=route, title=title, meta=default_meta, on_load=on_load)
        def page() -> rx.Component:
            return mn.theme_wrapper(page_content())

        return page

    return decorator


def navbar_template(content: rx.Component) -> rx.Component:
    """Authenticated layout with the app navbar on the left."""
    return mn.app_shell(
        mn.app_shell.navbar(app_navbar()),
        mn.app_shell.main(content),
        navbar={"width": 250, "breakpoint": "sm"},
    )
