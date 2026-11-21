import appkit_mantine as mn
import reflex as rx


def app_navbar() -> rx.Component:
    return mn.box(
        mn.stack(
            mn.text("skill-dojo", fw=700, size="md"),
            rx.link("Home", href="/"),
        ),
        padding="2rem",
        height="100vh",
    )
