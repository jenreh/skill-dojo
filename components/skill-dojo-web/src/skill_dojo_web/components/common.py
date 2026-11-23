"""Small building blocks every page uses, made of appkit-mantine components."""

from typing import Any

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.state import AppState
from skill_dojo_web.theme import MONO

# Risk severity / status tone -> Mantine color
TONES = {"add": "green", "warn": "yellow", "bad": "red", "info": "blue"}

# A column that fills the window: below the shell header (52px) and main padding.
WINDOW_TOP = "calc(52px + var(--mantine-spacing-md))"
WINDOW_HEIGHT = "calc(100dvh - 52px - 2 * var(--mantine-spacing-md))"


def work(key: Any, *events: Any) -> list[Any]:
    """Events for a click: ``key`` shows as working until ``events`` are done.

    Each event's state update reaches the browser before the next one runs, so
    the spinner appears at once and stays for the whole backend call.
    """
    return [AppState.start_work(key), *events, AppState.end_work]


def working(key: Any) -> Any:
    """True while the control ``key`` waits for its events."""
    return AppState.working == key


def tone_color(tone: Any) -> Any:
    """Mantine color of a tone (works for Vars and plain strings)."""
    return rx.match(tone, *TONES.items(), "gray")


def badge(text: Any, tone: Any = "", **props: Any) -> rx.Component:
    """A small label; ``tone`` colors it (add, warn, bad, info)."""
    color = tone_color(tone) if isinstance(tone, rx.Var) or tone else "gray"
    return mn.badge(text, color=color, variant="light", radius="sm", tt="none", **props)


def mono(*text: Any, **props: Any) -> rx.Component:
    """Monospace text (pins, SHAs, paths)."""
    props.setdefault("size", "xs")
    return mn.text(*text, ff=MONO, span=True, **props)


def page_header(title: str, subtitle: Any, *actions: rx.Component) -> rx.Component:
    return mn.group(
        mn.stack(
            mn.title(title, order=2, size="h3"),
            mn.text(subtitle, size="xs", c="dimmed"),
            gap=2,
        ),
        mn.group(*actions, gap="xs"),
        justify="space-between",
        align="flex-start",
        wrap="wrap",
    )


def section_title(title: str, subtitle: Any) -> rx.Component:
    return mn.stack(
        mn.title(title, order=3, size="h5"),
        mn.text(subtitle, size="xs", c="dimmed"),
        gap=2,
    )


def panel(*children: Any, **props: Any) -> rx.Component:
    """A bordered surface for a list or a form."""
    return mn.paper(*children, with_border=True, radius="md", **props)


def panel_head(title: str, *rest: Any) -> rx.Component:
    return mn.group(
        mn.text(title, fw=600, size="sm"),
        *rest,
        gap="xs",
        px="md",
        py="xs",
    )


def check_line(text: Any, kind: str = "check") -> rx.Component:
    icons = {
        "check": ("check", "green"),
        "warn": ("triangle-alert", "yellow"),
        "info": ("info", "blue"),
        "x": ("x", "red"),
    }
    name, color = icons[kind]
    return mn.group(
        mn.theme_icon(
            rx.icon(name, size=13), size="sm", color=color, variant="transparent"
        ),
        mn.text(text, size="sm", c="dimmed"),
        gap=6,
        wrap="nowrap",
    )


def segmented(
    value: Any, options: list[tuple[str, str]], on_change: Any
) -> rx.Component:
    """A filter row: one option active at a time."""
    return mn.segmented_control(
        data=[{"label": label, "value": key} for key, label in options],
        value=value,
        on_change=on_change,
        size="xs",
    )


def labelled(label: str, value: Any) -> rx.Component:
    """One fact: a dimmed label over a monospace value."""
    return mn.stack(
        mn.text(label, size="xs", c="dimmed"),
        mono(value, size="sm"),
        gap=2,
        miw=0,
    )


def diff_line(kind: Any, number: Any, text: Any) -> rx.Component:
    """One diff line, colored by kind (+, -, …, space)."""
    return mn.text(
        mn.text(
            rx.cond(kind == "…", "…", number),
            span=True,
            c="dimmed",
            w=40,
            display="inline-block",
            ta="right",
            mr="md",
        ),
        rx.cond((kind == "+") | (kind == "-"), kind, " "),
        " ",
        text,
        ff=MONO,
        size="xs",
        px="md",
        bg=rx.match(
            kind,
            ("+", "var(--mantine-color-green-light)"),
            ("-", "var(--mantine-color-red-light)"),
            "transparent",
        ),
        c=rx.match(kind, ("+", "green"), ("-", "red"), ("…", "dimmed"), "dimmed"),
        style={"whiteSpace": "pre"},
    )


def empty(text: str) -> rx.Component:
    return mn.text(text, size="sm", c="dimmed", px="md", py="xs")
