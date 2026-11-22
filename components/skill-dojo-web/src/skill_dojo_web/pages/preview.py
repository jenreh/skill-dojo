"""Marketplace preview: the exact catalogs and tree ``build`` would commit."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.icons import icon
from skill_dojo_web.shell import check_line, chip, main_area, panel, shell
from skill_dojo_web.state import AppState


class PreviewState(AppState):
    preview: dict[str, Any] = {}
    catalog: int = 0
    full: bool = False

    @rx.var
    def current(self) -> dict[str, Any]:
        catalogs = self.preview.get("catalogs", [])
        return catalogs[self.catalog] if len(catalogs) > self.catalog else {}

    @rx.var
    def tree(self) -> list[dict[str, Any]]:
        return list(self.preview.get("tree", []))

    @rx.var
    def warnings(self) -> list[dict[str, Any]]:
        return list(self.preview.get("warnings", []))

    @rx.var
    def pending_count(self) -> int:
        return len(self.preview.get("pending", []))

    @rx.var
    def errors(self) -> int:
        return int(self.preview.get("errors", 0))

    @rx.var
    def changes_view(self) -> bool:
        return not self.full

    @rx.var
    def lines(self) -> list[dict[str, Any]]:
        return self.current.get("full" if self.full else "changes", [])

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            self.preview = core.marketplace_preview(self._ctx()).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)

    @rx.event
    def show_catalog(self, index: int) -> None:
        self.catalog = index

    @rx.event
    def set_full(self, value: bool) -> None:
        self.full = value


S = PreviewState


def _tree_entry(e: rx.Var) -> rx.Component:
    status = e["status"].to(str)
    nested = e["depth"].to(int) > 0
    name = e["path"].to(str).split("/")
    return rx.el.div(
        rx.cond(nested, rx.fragment(), icon("folder", 14)),
        rx.cond(
            nested,
            rx.cond(e["path"].to(str).endswith("/"), name[-2] + "/", name[-1]),
            e["path"],
        ),
        rx.cond(
            status != "",
            chip(
                status,
                rx.cond(status == "A", "add", "warn"),
                margin_left="auto",
                height="18px",
            ),
        ),
        class_name="tree",
        style=rx.cond(nested, {"padding_left": "26px"}, {}),
    )


def _line(line: rx.Var) -> rx.Component:
    kind = line["kind"].to(str)
    return rx.el.div(
        rx.el.span(rx.cond(kind == "…", "…", line["number"]), class_name="ln"),
        rx.cond((kind == "+") | (kind == "-"), kind, " "),
        line["text"],
        style=rx.match(
            kind,
            (
                "+",
                {
                    "padding": "0 14px",
                    "background": "var(--add-bg)",
                    "color": "var(--add)",
                },
            ),
            (
                "-",
                {
                    "padding": "0 14px",
                    "background": "var(--del-bg)",
                    "color": "var(--del)",
                },
            ),
            ("…", {"padding": "0 14px", "color": "var(--faint)"}),
            {"padding": "0 14px", "color": "var(--muted)"},
        ),
    )


def _seg(label: str, on: Any, click: Any) -> rx.Component:
    return rx.el.button(
        label,
        class_name=rx.cond(on, "btn", "btn btn-ghost"),
        style={"min_height": "28px"},
        on_click=click,
        aria_pressed=on,
    )


def _warning(w: rx.Var) -> rx.Component:
    return rx.el.div(
        icon("warn", 15, color="var(--warn)", flex="none"),
        rx.el.span(w["message"], style={"flex": "1"}),
        rx.el.span(w["path"], class_name="mono", style={"color": "var(--accent)"}),
        class_name="row",
        style={
            "padding": "9px 14px",
            "border_bottom": "1px solid var(--line)",
            "gap": "10px",
        },
    )


def preview_page() -> rx.Component:
    p = S.preview
    group = {
        "gap": "2px",
        "padding": "3px",
        "border": "1px solid var(--line)",
        "border_radius": "8px",
    }
    return shell(
        "preview",
        main_area(
            rx.el.div(
                rx.el.section(
                    rx.el.div(
                        rx.el.h1("Marketplace preview", style={"margin": "0", "font_size": "16px", "font_weight": "600"}),
                        rx.el.p("What ", rx.el.span("skill-dojo build", class_name="mono"), " would commit", style={"margin": "2px 0 0", "color": "var(--faint)", "font_size": "12px"}),
                        style={"padding": "0 8px 10px"},
                    ),
                    rx.foreach(S.tree, _tree_entry),
                    rx.el.div(
                        rx.cond(S.errors == 0, check_line("validate: 0 errors"), check_line(f"validate: {S.errors} errors", "x")),
                        check_line(f"{S.warnings.length()} warnings", "warn"),
                        rx.cond(S.pending_count == 0, check_line("build is up to date"), check_line(f"build would change {S.pending_count} files", "warn")),
                        style={"margin_top": "14px", "padding": "10px", "border_top": "1px solid var(--line)", "display": "flex", "flex_direction": "column", "gap": "6px", "font_size": "12px"},
                    ),
                    aria_label="Generated tree",
                    style={"flex": "1 1 300px", "box_sizing": "border-box", "padding": "18px 10px", "border_right": "1px solid var(--line)", "display": "flex", "flex_direction": "column", "gap": "2px"},
                ),
                rx.el.section(
                    rx.el.div(
                        rx.el.div(
                            rx.el.div(f"compared with {p['base']} HEAD {p['base_head']}", class_name="mono", style={"color": "var(--faint)", "font_size": "11.5px"}),
                            rx.el.h2(S.current["path"], class_name="mono", style={"margin": "2px 0 0", "font_size": "15px", "font_weight": "500"}),
                            style={"flex": "1 1 300px"},
                        ),
                        rx.el.div(_seg("Agent Plugins", S.catalog == 0, S.show_catalog(0)), _seg("Claude Code", S.catalog == 1, S.show_catalog(1)), class_name="row", role="group", aria_label="Catalog format", style=group),
                        rx.el.div(_seg("Changes", S.changes_view, S.set_full(False)), _seg("Full file", S.full, S.set_full(True)), class_name="row", role="group", aria_label="View", style=group),
                        rx.el.button(icon("file", 14), "Copy", class_name="btn", on_click=rx.set_clipboard(S.current["text"].to(str))),
                        style={"display": "flex", "flex_wrap": "wrap", "align_items": "center", "gap": "10px"},
                    ),
                    rx.el.div(
                        rx.foreach(S.lines, _line),
                        rx.cond(S.lines.length() == 0, rx.el.div("No changes against staging.", style={"padding": "0 14px", "color": "var(--faint)"})),
                        class_name="mono",
                        style={"border": "1px solid var(--line)", "border_radius": "9px", "background": "var(--panel)", "padding": "10px 0", "line_height": "1.75", "white_space": "pre", "overflow_x": "auto"},
                    ),
                    rx.cond(S.warnings.length() > 0, panel(rx.foreach(S.warnings, _warning), display="flex", flex_direction="column")),
                    aria_label="File",
                    style={"flex": "999 1 520px", "min_width": "0", "box_sizing": "border-box", "padding": "18px 28px 28px", "display": "flex", "flex_direction": "column", "gap": "14px"},
                ),
                style={"display": "flex", "flex_wrap": "wrap", "width": "100%"},
            ),
        ),
    )  # fmt: skip
