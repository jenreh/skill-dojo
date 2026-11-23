"""The app shell: header, navigation, toasts. Wraps every page."""

from typing import Any

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import badge, mono
from skill_dojo_web.state import AppState
from skill_dojo_web.theme import WORDMARK

PAGES = [
    ("changes", "/", "git-branch", "Changes"),
    ("sources", "/sources", "database", "Sources"),
    ("plugins", "/plugins", "layers", "Plugins"),
    ("preview", "/preview", "eye", "Marketplace preview"),
    ("releases", "/releases", "tag", "Releases"),
    ("revoke", "/revoke", "shield-x", "Revoke"),
    ("audit", "/audit", "clock", "Audit"),
]


def _brand() -> rx.Component:
    return mn.group(
        mn.image(src="/img/logo/shoji_favicon.svg", w=20, h=20, alt=""),
        mn.text("SKILL DOJO", ff=WORDMARK, fw=500, size="sm", lts="0.26em"),
        gap="xs",
        wrap="nowrap",
    )


def _command_menu() -> rx.Component:
    return mn.menu(
        mn.menu.target(
            mn.button(
                mn.group(mn.text("Search or run a command", size="sm"), gap="xs"),
                left_section=rx.icon("search", size=14),
                right_section=mn.kbd("⌘K", size="xs"),
                variant="default",
                justify="space-between",
                w=280,
                c="dimmed",
            )
        ),
        mn.menu.dropdown(
            mn.menu.label("Go to"),
            *(
                mn.menu.item(
                    label,
                    left_section=rx.icon(icon, size=14),
                    on_click=rx.redirect(route),
                )
                for _, route, icon, label in PAGES
            ),
            mn.menu.divider(),
            mn.menu.item(
                "Sync upstream now",
                left_section=rx.icon("refresh-cw", size=14),
                on_click=AppState.run_sync,
            ),
        ),
        width="target",
        position="bottom-start",
    )


def header() -> rx.Component:
    return mn.group(
        mn.group(
            _brand(),
            mn.button(
                mono(AppState.repository),
                left_section=rx.icon("folder", size=14),
                variant="subtle",
                color="gray",
                size="compact-sm",
            ),
            badge(mn.group(rx.icon("git-branch", size=12), AppState.branch, gap=4)),
            gap="sm",
        ),
        mn.group(
            _command_menu(),
            mn.text(
                rx.cond(AppState.busy, AppState.progress, AppState.synced),
                size="xs",
                c="dimmed",
            ),
            mn.action_icon(
                rx.icon("refresh-cw", size=15),
                variant="subtle",
                color="gray",
                aria_label="Sync upstream now",
                loading=AppState.busy,
                on_click=AppState.run_sync,
            ),
            mn.action_icon(
                rx.color_mode_cond(rx.icon("moon", size=15), rx.icon("sun", size=15)),
                variant="default",
                aria_label="Toggle light and dark mode",
                on_click=rx.toggle_color_mode,
            ),
            gap="sm",
        ),
        h="100%",
        px="md",
        justify="space-between",
        wrap="nowrap",
    )


def navbar(active: str) -> rx.Component:
    links = [
        mn.nav_link(
            label=label,
            left_section=rx.icon(icon, size=15),
            right_section=rx.cond(
                AppState.queue_count > 0,
                mn.badge(AppState.queue_count, size="sm", circle=True),
            )
            if key == "changes"
            else None,
            active=key == active,
            on_click=rx.redirect(route),
        )
        for key, route, icon, label in PAGES
    ]
    return mn.stack(
        mn.stack(*links, gap=2),
        mn.stack(
            mn.divider(),
            mn.group(
                mn.avatar(name=AppState.actor, size="sm", radius="xl"),
                mn.text(AppState.actor, size="sm"),
                mn.text(
                    rx.cond(AppState.gh_ok, "gh auth ok", "gh auth missing"),
                    size="xs",
                    c="dimmed",
                    ml="auto",
                ),
                gap="xs",
            ),
            mono(f"skill-dojo {AppState.version} · 127.0.0.1", c="dimmed"),
            gap="xs",
        ),
        h="100%",
        p="sm",
        justify="space-between",
    )


def shell(active: str, *content: Any) -> rx.Component:
    """The page frame: header, navigation and ``content`` in the main area."""
    return mn.theme_wrapper(
        rx.fragment(
            mn.notifications_provider(position="top-right", limit=5),
            mn.app_shell(
                mn.app_shell.header(header()),
                mn.app_shell.navbar(navbar(active)),
                mn.app_shell.main(mn.stack(*content, gap="md")),
                header={"height": 52},
                navbar={"width": 240, "breakpoint": "sm"},
                padding="md",
            ),
        )
    )
