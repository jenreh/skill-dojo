import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.branding import LOGO_DARK, LOGO_LIGHT


def _logo(src: str) -> rx.Component:
    return rx.image(src=src, alt="skill-dojo", height="28px", width="auto")


def app_logo() -> rx.Component:
    return rx.color_mode_cond(light=_logo(LOGO_LIGHT), dark=_logo(LOGO_DARK))


def app_navbar() -> rx.Component:
    return mn.box(
        mn.stack(
            app_logo(),
            rx.link("Home", href="/"),
        ),
        padding="2rem",
        height="100vh",
    )
