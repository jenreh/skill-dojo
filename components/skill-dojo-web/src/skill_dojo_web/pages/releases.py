"""Releases: promote staging to main, then tag an immutable release."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.icons import icon
from skill_dojo_web.shell import (
    FAINT_12,
    check_line,
    chip,
    heading,
    main_area,
    panel,
    panel_head,
    shell,
)
from skill_dojo_web.state import AppState

BIG = {"font_size": "22px", "font_weight": "600"}
SHA = {"color": "var(--faint)", "font_size": "11.5px"}


class ReleasesState(AppState):
    overview: dict[str, Any] = {}

    @rx.var
    def items(self) -> list[dict[str, Any]]:
        return [
            {
                **i,
                "change": f"{i['old_version']} → {i['new_version']}"
                if i.get("old_version")
                else f"new · {i.get('new_version') or ''}",
                "who": " · ".join(
                    x
                    for x in (
                        ("PR #" + i["pull_request"].rsplit("/", 1)[-1])
                        if i.get("pull_request")
                        else "",
                        ", ".join(i.get("reviewers", [])),
                    )
                    if x
                ),
            }
            for i in self.overview.get("items", [])
        ]

    @rx.var
    def blocks(self) -> list[str]:
        return list(self.overview.get("blocks", []))

    @rx.var
    def tags(self) -> list[dict[str, Any]]:
        return list(self.overview.get("tags", []))

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            self.overview = core.release_overview(self._ctx()).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)

    @rx.event
    def promote(self) -> None:
        try:
            result = core.promote(self._ctx())
            url = result.pull_request.url if result.pull_request else ""
            self._say(f"Promote PR {result.status} {url}".strip())
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def tag(self) -> None:
        try:
            result = core.release(self._ctx())
            self._say(f"Release {result.tag}: {result.status}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()


S = ReleasesState


def _item_row(i: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.el.span(i["item"], style={"flex": "1 1 200px", "font_weight": "500"}),
        chip(i["kind"]),
        rx.el.span(i["change"], class_name="mono", style={"color": "var(--muted)"}),
        rx.el.span(i["who"], class_name="mono", style=SHA),
        style={"display": "flex", "flex_wrap": "wrap", "align_items": "center", "gap": "6px 14px", "padding": "10px 14px", "border_bottom": "1px solid var(--line)"},
    )  # fmt: skip


def _tag_row(t: rx.Var) -> rx.Component:
    return rx.el.div(
        icon("tag", 13, color="var(--faint)"),
        rx.el.span(
            t["tag"].to(str).replace("marketplace-", ""),
            class_name="mono",
            style={"flex": "1"},
        ),
        rx.el.span(f"{t['items']} items · {t['clients']} clients", style=FAINT_12),
        class_name="row",
        style={"padding": "9px 14px", "border_bottom": "1px solid var(--line)"},
    )


def _flow() -> rx.Component:
    o = S.overview
    return rx.el.div(
        rx.el.div(
            rx.el.span(rx.el.span(o["staging"], class_name="chip mono"), rx.el.span("beta", style=FAINT_12), class_name="row"),
            rx.el.span(f"{S.items.length()} items ahead", style=BIG),
            rx.el.span(f"HEAD {o['staging_head']} · {o['commits_ahead']} commits", class_name="mono", style=SHA),
            style={"flex": "1 1 260px", "padding": "16px 18px", "display": "flex", "flex_direction": "column", "gap": "6px"},
        ),
        rx.el.div(
            rx.el.svg(rx.el.path(d="M4 12h108M104 5l8 7-8 7", stroke_linecap="round", stroke_linejoin="round"), width="120", height="24", view_box="0 0 120 24", fill="none", stroke="currentColor", stroke_width="1.5", aria_hidden="true"),
            style={"flex": "0 1 140px", "display": "flex", "align_items": "center", "justify_content": "center", "padding": "12px", "color": "var(--faint)"},
        ),
        rx.el.div(
            rx.el.span(rx.el.span(o["main"], class_name="chip mono"), rx.el.span("stable", style=FAINT_12), class_name="row"),
            rx.el.span(rx.cond(o["latest_tag"].to(str) != "", o["latest_tag"], "no release yet"), style=BIG),
            rx.el.span(f"HEAD {o['main_head']}", rx.cond(o["untagged"].to(bool), " · untagged commits", ""), class_name="mono", style=SHA),
            style={"flex": "1 1 260px", "padding": "16px 18px", "display": "flex", "flex_direction": "column", "gap": "6px", "border_left": "1px solid var(--line)"},
        ),
        rx.el.div(
            rx.el.button(icon("promote", 14), "Open promote PR", class_name="btn btn-primary", on_click=S.promote),
            rx.el.span("Stamps approvals, rebuilds catalogs, runs validate", style={**FAINT_12, "text_align": "center"}),
            rx.cond(o["untagged"].to(bool), rx.el.button(icon("tag", 14), "Tag release of main", class_name="btn", on_click=S.tag)),
            style={"flex": "1 1 220px", "padding": "16px 18px", "display": "flex", "flex_direction": "column", "justify_content": "center", "gap": "8px", "border_left": "1px solid var(--line)", "background": "var(--raised)"},
        ),
        style={"display": "flex", "flex_wrap": "wrap", "align_items": "stretch", "border": "1px solid var(--line)", "border_radius": "10px", "background": "var(--panel)", "overflow": "hidden"},
    )  # fmt: skip


def _checks() -> rx.Component:
    return panel(
        rx.el.span("Promotion checks", style={"font_weight": "600"}),
        rx.cond(
            S.blocks.length() == 0,
            rx.fragment(
                check_line("All items approved on staging"),
                check_line("No forbidden risk tier"),
                check_line("stable is in every item's channels"),
            ),
            rx.foreach(S.blocks, lambda b: check_line(b, "x")),
        ),
        check_line("Open candidates stay on staging", "info"),
        padding="14px", display="flex", flex_direction="column", gap="8px",
    )  # fmt: skip


def releases_page() -> rx.Component:
    o = S.overview
    return shell(
        "releases",
        main_area(
            rx.el.div(rx.el.div(heading("Releases", "Promote all of staging to main, then tag an immutable release"), style={"flex": "1 1 320px"}), style={"display": "flex", "flex_wrap": "wrap", "gap": "12px"}),
            rx.cond(o.contains("staging"), _flow()),
            rx.el.div(
                rx.el.div(
                    panel(panel_head("In this promotion", chip(S.items.length())), rx.foreach(S.items, _item_row)),
                    rx.el.div(
                        rx.el.label("Release notes", html_for="notes", style={"font_weight": "600"}),
                        rx.el.textarea(o["notes"].to(str), id="notes", class_name="field field-area mono", rows="6", read_only=True),
                        rx.el.span("Drafted from the merged candidate PRs. Used as the tag message.", style=FAINT_12),
                        style={"display": "flex", "flex_direction": "column", "gap": "6px"},
                    ),
                    style={"flex": "999 1 460px", "min_width": "0", "display": "flex", "flex_direction": "column", "gap": "18px"},
                ),
                rx.el.aside(
                    _checks(),
                    panel(panel_head("Tags"), rx.foreach(S.tags, _tag_row)),
                    style={"flex": "1 1 280px", "display": "flex", "flex_direction": "column", "gap": "18px"},
                ),
                style={"display": "flex", "flex_wrap": "wrap", "gap": "18px", "align_items": "flex-start"},
            ),
            box_sizing="border-box", padding="18px 28px 28px", display="flex", flex_direction="column", gap="18px",
        ),
    )  # fmt: skip
