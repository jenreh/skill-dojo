"""The skill-dojo web UI app."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.templates import navbar_template
from skill_dojo_web.styles import base_style, base_stylesheets


@rx.page(route="/", title="skill-dojo")
def index() -> rx.Component:
    return navbar_template(
        mn.stack(
            mn.title("skill-dojo", order=1),
            mn.text("Curated agent plugin marketplace."),
            p="2rem",
        )
    )


app = rx.App(
    stylesheets=base_stylesheets,
    style=base_style,  # ty: ignore[invalid-argument-type]  # reflex dynamic styling
)
