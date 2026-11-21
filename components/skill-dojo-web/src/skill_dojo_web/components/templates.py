"""Page layouts of the app."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.navbar import app_navbar


def navbar_template(content: rx.Component) -> rx.Component:
    """Layout with the app navbar on the left."""
    return mn.theme_wrapper(
        mn.app_shell(
            mn.app_shell.navbar(app_navbar()),
            mn.app_shell.main(content),
            navbar={"width": 250, "breakpoint": "sm"},
        )
    )
