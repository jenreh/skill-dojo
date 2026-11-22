"""Header, side navigation and notices: the frame of every page."""

from typing import Any

import reflex as rx

from skill_dojo_web.icons import icon, logo
from skill_dojo_web.state import AppState

PAGES = [
    ("review", "/", "queue", "Review queue"),
    ("sources", "/sources", "sources", "Sources and browse"),
    ("bundles", "/bundles", "bundles", "Bundles"),
    ("preview", "/preview", "preview", "Marketplace preview"),
    ("releases", "/releases", "releases", "Releases"),
    ("clients", "/clients", "clients", "Clients"),
    ("audit", "/audit", "audit", "Audit"),
]
FAINT_12 = {"color": "var(--faint)", "font_size": "12px"}


def chip(text: Any, tone: Any = "", **style: Any) -> rx.Component:
    """A chip; ``tone`` is add, warn, bad or info (colored background)."""
    if isinstance(tone, rx.Var) or tone:
        style = {"background": f"var(--{tone}-bg)", "color": f"var(--{tone})", **style}
    return rx.el.span(text, class_name="chip", style=style or None)


def heading(title: str, subtitle: Any, size: str = "20px") -> rx.Component:
    return rx.el.div(
        rx.el.h1(title, style={"margin": "0", "font_size": size, "font_weight": "600"}),
        rx.el.p(subtitle, style={"margin": "2px 0 0", **FAINT_12}),
    )


def panel(*children: Any, **style: Any) -> rx.Component:
    return rx.el.div(
        *children,
        style={
            "border": "1px solid var(--line)",
            "border_radius": "9px",
            "background": "var(--panel)",
            **style,
        },
    )


def panel_head(title: str, *rest: Any) -> rx.Component:
    return rx.el.div(
        rx.el.span(title, style={"font_weight": "600"}),
        *rest,
        class_name="row",
        style={"padding": "10px 14px", "border_bottom": "1px solid var(--line)"},
    )


def check_line(text: Any, kind: str = "check") -> rx.Component:
    colors = {
        "check": "var(--add)",
        "warn": "var(--warn)",
        "info": "var(--info)",
        "x": "var(--bad)",
    }
    name = {"check": "check", "warn": "warn", "info": "info", "x": "x"}[kind]
    return rx.el.span(
        icon(name, 13, color=colors[kind]),
        text,
        class_name="row",
        style={"color": "var(--muted)"},
    )


def _header() -> rx.Component:
    return rx.el.header(
        rx.el.div(
            logo(),
            rx.el.span(
                "SKILL DOJO",
                style={"font_family": "Jost, Inter, sans-serif", "font_weight": "500", "font_size": "12.5px", "letter_spacing": "0.26em"},
            ),
            class_name="row",
            style={"font_weight": "600", "font_size": "13.5px", "margin_right": "6px"},
        ),
        rx.el.button(
            icon("folder", 14),
            rx.el.span(AppState.repository, class_name="mono", style={"color": "var(--text)"}),
            icon("chevron", 12),
            class_name="btn btn-ghost",
            aria_label="Curated repository",
        ),
        rx.el.span(icon("branch", 12), AppState.branch, class_name="chip mono"),
        rx.el.div(style={"flex": "1"}),
        rx.el.div(
            rx.el.button(
                rx.el.span(icon("search", 14), "Search or run a command", class_name="row"),
                rx.el.span("⌘K", class_name="kbd"),
                class_name="btn",
                style={"min_width": "280px", "justify_content": "space-between", "color": "var(--muted)"},
                on_click=AppState.toggle_palette,
                aria_expanded=AppState.palette_open,
            ),
            rx.cond(AppState.palette_open, _palette()),
            style={"position": "relative"},
        ),
        rx.el.span(
            rx.cond(AppState.busy, AppState.progress, AppState.synced), style=FAINT_12
        ),
        rx.el.button(
            icon("sync"),
            class_name="btn btn-ghost",
            aria_label="Sync upstream now",
            on_click=AppState.run_sync,
            disabled=AppState.busy,
        ),
        rx.el.div(
            rx.el.button(
                icon("sun", 14),
                class_name=rx.cond(AppState.theme == "t-light", "seg-btn on", "seg-btn"),
                aria_label="Light mode",
                aria_pressed=AppState.theme == "t-light",
                on_click=AppState.set_light,
            ),
            rx.el.button(
                icon("moon", 14),
                class_name=rx.cond(AppState.theme == "t-dark", "seg-btn on", "seg-btn"),
                aria_label="Dark mode",
                aria_pressed=AppState.theme == "t-dark",
                on_click=AppState.set_dark,
            ),
            class_name="seg",
            role="group",
            aria_label="Color mode",
        ),
        style={
            "display": "flex", "flex_wrap": "wrap", "align_items": "center", "gap": "10px",
            "min_height": "46px", "padding": "6px 14px", "border_bottom": "1px solid var(--line)",
            "background": "var(--side)", "box_sizing": "border-box",
        },
    )  # fmt: skip


def _palette() -> rx.Component:
    links = [
        rx.el.a(
            icon(ic),
            label,
            href=route,
            class_name="nav",
            on_click=AppState.toggle_palette,
        )
        for _, route, ic, label in PAGES
    ]
    return rx.el.div(
        *links,
        rx.el.button(
            icon("sync"), "Sync upstream now", class_name="nav",
            style={"border": "0", "background": "transparent", "font": "inherit", "width": "100%", "cursor": "pointer"},
            on_click=[AppState.toggle_palette, AppState.run_sync],
        ),
        style={
            "position": "absolute", "top": "38px", "left": "0", "right": "0", "z_index": "10",
            "padding": "6px", "border": "1px solid var(--line)", "border_radius": "9px",
            "background": "var(--panel)", "box_shadow": "0 8px 24px rgba(0,0,0,.25)",
        },
    )  # fmt: skip


def _nav(active: str) -> rx.Component:
    links = []
    for key, route, ic, label in PAGES:
        badge = (
            rx.cond(
                AppState.queue_count > 0,
                chip(
                    AppState.queue_count,
                    background="var(--accent-fill)",
                    color="var(--on-accent)",
                ),
            )
            if key == "review"
            else rx.fragment()
        )
        links.append(
            rx.el.a(
                icon(ic),
                rx.el.span(label, style={"flex": "1"}),
                badge,
                class_name="nav on" if key == active else "nav",
                href=route,
                aria_current="page" if key == active else None,
            )
        )
    footer = rx.el.div(
        rx.el.div(
            rx.el.span(
                AppState.initial,
                style={
                    "width": "22px", "height": "22px", "border_radius": "50%", "background": "var(--raised)",
                    "color": "var(--text)", "display": "inline-flex", "align_items": "center",
                    "justify_content": "center", "font_size": "11px", "font_weight": "600",
                },
            ),
            rx.el.span(AppState.actor, style={"color": "var(--text)"}),
            rx.el.span(rx.cond(AppState.gh_ok, "gh auth ok", "gh auth missing"), style={"margin_left": "auto"}),
            class_name="row",
        ),
        rx.el.div(f"skill-dojo {AppState.version} · 127.0.0.1", class_name="mono", style={"font_size": "11px"}),
        style={
            "margin_top": "auto", "padding": "10px", "border_top": "1px solid var(--line)", "display": "flex",
            "flex_direction": "column", "gap": "6px", "font_size": "12px", "color": "var(--faint)",
        },
    )  # fmt: skip
    return rx.el.nav(
        *links,
        footer,
        aria_label="Main",
        style={
            "flex": "1 1 228px", "box_sizing": "border-box", "padding": "12px 10px", "background": "var(--side)",
            "border_right": "1px solid var(--line)", "display": "flex", "flex_direction": "column", "gap": "2px",
        },
    )  # fmt: skip


def notice() -> rx.Component:
    return rx.cond(
        AppState.notice != "",
        rx.el.div(
            rx.el.span(AppState.notice, style={"flex": "1"}),
            rx.el.button(icon("x", 13), class_name="btn btn-ghost", aria_label="Dismiss", on_click=AppState.dismiss, style={"min_height": "24px", "padding": "0 6px"}),
            class_name=rx.cond(AppState.notice_ok, "notice notice-ok row", "notice notice-bad row"),
            role="status",
        ),
    )  # fmt: skip


def shell(active: str, main: rx.Component) -> rx.Component:
    """The page frame around ``main`` (a ``<main>`` element)."""
    return rx.el.div(
        _header(),
        rx.el.div(
            _nav(active),
            main,
            style={"flex": "1", "display": "flex", "flex_wrap": "wrap"},
        ),
        class_name=f"app {AppState.theme}",
        style={"min_height": "100vh", "display": "flex", "flex_direction": "column"},
    )


def main_area(*children: Any, **style: Any) -> rx.Component:
    """``<main>`` with the notice on top."""
    return rx.el.main(
        notice(),
        *children,
        style={"flex": "999 1 560px", "min_width": "0", **style},
    )
