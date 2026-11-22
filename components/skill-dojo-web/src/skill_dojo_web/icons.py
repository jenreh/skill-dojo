"""The prototype's stroke icons (16x16 viewBox), as inline SVG."""

from typing import Any

import reflex as rx

# name -> (stroke width, extra svg attrs, children as (tag, attrs))
ICONS: dict[str, tuple[str, dict[str, str], list[tuple[str, dict[str, str]]]]] = {
    "queue": ("1.5", {"stroke_linejoin": "round"}, [("path", {"d": "M2 9h3l1.5 2h3L11 9h3M3.5 3.5h9L14 9v3.5H2V9z"})]),
    "sources": ("1.5", {}, [("ellipse", {"cx": "8", "cy": "4", "rx": "6", "ry": "2"}), ("path", {"d": "M2 4v8c0 1.1 2.7 2 6 2s6-.9 6-2V4M2 8c0 1.1 2.7 2 6 2s6-.9 6-2"})]),
    "bundles": ("1.5", {"stroke_linejoin": "round"}, [("path", {"d": "M8 2l6 3-6 3-6-3zM2 8l6 3 6-3M2 11l6 3 6-3"})]),
    "preview": ("1.5", {}, [("path", {"d": "M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"}), ("circle", {"cx": "8", "cy": "8", "r": "2"})]),
    "releases": ("1.5", {"stroke_linejoin": "round"}, [("path", {"d": "M2 2h5.5L14 8.5 8.5 14 2 7.5z"}), ("circle", {"cx": "5", "cy": "5", "r": ".8"})]),
    "tag": ("1.5", {"stroke_linejoin": "round"}, [("path", {"d": "M2 2h5.5L14 8.5 8.5 14 2 7.5z"})]),
    "clients": ("1.5", {}, [("circle", {"cx": "6", "cy": "4.5", "r": "2.5"}), ("path", {"d": "M1.5 14c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4M11 2.2a2.5 2.5 0 010 4.6M12.5 10c1.3.5 2 1.8 2 4"})]),
    "audit": ("1.5", {}, [("circle", {"cx": "8", "cy": "8", "r": "6"}), ("path", {"d": "M8 5v3l2 1.5"})]),
    "folder": ("1.5", {}, [("path", {"d": "M1.5 4h4.5l1.5 1.5h7v8h-13z"})]),
    "chevron": ("1.5", {}, [("path", {"d": "M4 6l4 4 4-4"})]),
    "chevron-bold": ("1.8", {}, [("path", {"d": "M4 6l4 4 4-4"})]),
    "branch": ("1.5", {}, [("circle", {"cx": "5", "cy": "3.5", "r": "1.5"}), ("circle", {"cx": "5", "cy": "12.5", "r": "1.5"}), ("circle", {"cx": "11", "cy": "5", "r": "1.5"}), ("path", {"d": "M5 5v6M11 6.5c0 3-6 2-6 4.5"})]),
    "search": ("1.5", {}, [("circle", {"cx": "7", "cy": "7", "r": "5"}), ("path", {"d": "M14 14l-3.5-3.5"})]),
    "sync": ("1.5", {"stroke_linecap": "round"}, [("path", {"d": "M13.5 8A5.5 5.5 0 113 5.5M3 2v3.5h3.5"})]),
    "sun": ("1.5", {"stroke_linecap": "round"}, [("circle", {"cx": "8", "cy": "8", "r": "3"}), ("path", {"d": "M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1"})]),
    "moon": ("1.5", {"stroke_linejoin": "round"}, [("path", {"d": "M13.5 9.5A5.5 5.5 0 016.5 2.5a5.5 5.5 0 107 7z"})]),
    "external": ("1.5", {}, [("path", {"d": "M9 2h5v5M14 2L7.5 8.5M12 9.5V14H2V4h4.5"})]),
    "warn": ("1.5", {"stroke_linejoin": "round"}, [("path", {"d": "M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5h.01"})]),
    "warn-bold": ("1.8", {"stroke_linejoin": "round"}, [("path", {"d": "M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5h.01"})]),
    "info": ("1.5", {}, [("circle", {"cx": "8", "cy": "8", "r": "6"}), ("path", {"d": "M8 7.5v3.5M8 5h.01"})]),
    "file": ("1.5", {}, [("path", {"d": "M4 1.5h5l3 3v10H4zM9 1.5v3h3"})]),
    "check": ("1.8", {}, [("path", {"d": "M3 8.5l3 3 7-7"})]),
    "pause": ("2", {}, [("path", {"d": "M5.5 3v10M10.5 3v10"})]),
    "plus": ("1.6", {}, [("path", {"d": "M8 3v10M3 8h10"})]),
    "x": ("1.6", {}, [("path", {"d": "M4 4l8 8M12 4l-8 8"})]),
    "promote": ("1.5", {}, [("circle", {"cx": "4", "cy": "3.5", "r": "1.5"}), ("circle", {"cx": "4", "cy": "12.5", "r": "1.5"}), ("circle", {"cx": "12", "cy": "12.5", "r": "1.5"}), ("path", {"d": "M4 5v6M12 11V7c0-1.5-1-2.5-2.5-2.5H7"})]),
    "shield": ("1.5", {"stroke_linejoin": "round"}, [("path", {"d": "M8 1.5l5.5 2v4c0 3.5-2.5 6-5.5 7-3-1-5.5-3.5-5.5-7v-4z"})]),
    "shield-x": ("1.5", {"stroke_linejoin": "round"}, [("path", {"d": "M8 1.5l5.5 2v4c0 3.5-2.5 6-5.5 7-3-1-5.5-3.5-5.5-7v-4z"}), ("path", {"d": "M6 6l4 4M10 6l-4 4"})]),
}  # fmt: skip

TAGS = {"path": rx.el.path, "circle": rx.el.circle, "ellipse": rx.el.ellipse}


def icon(name: str, size: int = 15, **style: Any) -> rx.Component:
    """An icon in ``currentColor``; ``style`` sets e.g. its color."""
    width, attrs, children = ICONS[name]
    return rx.el.svg(
        *(TAGS[tag](**child) for tag, child in children),
        width=str(size),
        height=str(size),
        view_box="0 0 16 16",
        fill="none",
        stroke="currentColor",
        stroke_width=width,
        aria_hidden="true",
        style=style or None,
        **attrs,
    )


def logo() -> rx.Component:
    """The shoji mark in the accent color."""
    return rx.el.svg(
        rx.el.rect(x="7", y="7", width="50", height="50", rx="3", style={"fill": "none", "stroke": "var(--accent)"}, stroke_width="6"),
        rx.el.path(d="M36 7v50M7 25h50", style={"stroke": "var(--accent)"}, stroke_width="6"),
        rx.el.rect(x="36", y="7", width="21", height="18", style={"fill": "var(--accent)"}),
        width="20",
        height="20",
        view_box="0 0 64 64",
        aria_hidden="true",
    )  # fmt: skip
