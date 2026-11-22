"""Sources and browse: upstream sources, what each offers, mirror or bundle."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_core import SourceType
from skill_dojo_web.icons import icon
from skill_dojo_web.shell import FAINT_12, chip, heading, main_area, panel, shell
from skill_dojo_web.state import AppState

TYPE_LABEL = {
    "agent_plugins_marketplace": "agent plugins",
    "claude_marketplace": "claude",
    "git": "git",
    "mcp_registry": "mcp registry",
}
KINDS = [
    ("all", "All"),
    ("skill", "Skills"),
    ("agent", "Agents"),
    ("MCP", "MCP"),
    ("hook", "Hooks"),
]
HIDDEN = {
    "position": "absolute",
    "width": "1px",
    "height": "1px",
    "overflow": "hidden",
    "clip": "rect(0 0 0 0)",
}


class SourcesState(AppState):
    sources: list[dict[str, Any]] = []
    selected: str = ""
    commit: str = ""
    plugins: list[dict[str, Any]] = []
    query: str = ""
    kind: str = "all"
    focus: str = ""
    adding: bool = False
    new_id: str = ""
    new_repo: str = ""
    new_type: str = SourceType.AGENT_PLUGINS_MARKETPLACE.value

    @rx.var
    def source(self) -> dict[str, Any]:
        return next((s for s in self.sources if s["id"] == self.selected), {})

    @rx.var
    def shown(self) -> list[dict[str, Any]]:
        q = self.query.lower()
        return [
            p
            for p in self.plugins
            if (not q or q in f"{p['name']} {p['description']}".lower())
            and (self.kind == "all" or self.kind in p["contents"])
        ]

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            listed = core.source_list(self._ctx()).sources
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.sources = [
            {
                "id": s.id,
                "type": TYPE_LABEL[s.type.value],
                "repository": s.repository,
                "where": s.repository.removeprefix("https://")
                if s.type is SourceType.MCP_REGISTRY
                else f"@{s.ref}"
                + (f" · {len(s.allowlist)} allowed" if s.allowlist else ""),
                "path": s.marketplace_path or "",
            }
            for s in listed
        ]
        ids = [s["id"] for s in self.sources]
        if ids:
            self._browse(self.selected if self.selected in ids else ids[0])

    def _browse(self, source_id: str) -> None:
        self.selected, self.focus = source_id, ""
        try:
            result = core.browse(self._ctx(), source_id)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self.plugins = []
            self._fail(exc)
            return
        self.commit = result.commit[:7]
        self.plugins = [
            {
                "name": p.name,
                "description": p.description or "",
                "version": p.version or "",
                "contents": p.contents or "",
                "license": p.license or "",
                "allowed": p.allowed,
                "unsupported": p.unsupported or "",
                "tracked": result.tracked.get(p.name, ""),
            }
            for p in result.plugins
        ]

    @rx.event
    def select(self, source_id: str) -> None:
        self._browse(source_id)

    @rx.event
    def refresh(self) -> None:
        self._browse(self.selected)

    @rx.event
    def set_query(self, value: str) -> None:
        self.query = value

    @rx.event
    def set_kind(self, value: str) -> None:
        self.kind = value

    @rx.event
    def set_focus(self, value: str) -> None:
        self.focus = value

    @rx.event
    def toggle_add(self) -> None:
        self.adding = not self.adding

    @rx.event
    def set_new_id(self, value: str) -> None:
        self.new_id = value

    @rx.event
    def set_new_repo(self, value: str) -> None:
        self.new_repo = value

    @rx.event
    def set_new_type(self, value: str) -> None:
        self.new_type = value

    @rx.event
    def add_source(self) -> None:
        try:
            core.source_add(
                self._ctx(),
                self.new_id.strip(),
                self.new_repo.strip(),
                kind=SourceType(self.new_type),
            )
            self._say(f"Added source '{self.new_id}'")
            self.selected, self.adding, self.new_id, self.new_repo = (
                self.new_id.strip(),
                False,
                "",
                "",
            )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def mirror(self, plugin: str) -> None:
        try:
            result = core.mirror(self._ctx(), self.selected, plugin)
            self._say(f"{result.item}: {result.status} candidate PR")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self._browse(self.selected)

    @rx.event
    def allow(self, plugin: str) -> None:
        try:
            core.source_allow(self._ctx(), self.selected, plugin)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()


S = SourcesState


def _source_row(source: rx.Var) -> rx.Component:
    on = S.selected == source["id"]
    return rx.el.button(
        rx.el.span(rx.el.span(source["id"], style={"font_weight": "600"}), class_name="row"),
        rx.el.span(
            rx.el.span(source["type"], class_name="chip", style=rx.cond(on, {"background": "var(--bg)"}, {})),
            rx.el.span(source["where"], class_name="mono", style={"color": "var(--faint)", "font_size": "11.5px"}),
            class_name="row",
            style={"gap": "6px"},
        ),
        on_click=S.select(source["id"].to(str)),
        style={
            "font": "inherit", "text_align": "left", "color": "inherit", "border": "0", "cursor": "pointer", "width": "100%",
            "padding": "10px", "border_radius": "8px", "background": rx.cond(on, "var(--raised)", "transparent"),
            "display": "flex", "flex_direction": "column", "gap": "4px",
        },
    )  # fmt: skip


def _add_form() -> rx.Component:
    return rx.el.form(
        rx.el.label("Id", rx.el.input(class_name="field", value=S.new_id, on_change=S.set_new_id, required=True), style={"display": "flex", "flex_direction": "column", "gap": "4px", **FAINT_12}),
        rx.el.label("Repository or URL", rx.el.input(class_name="field", value=S.new_repo, on_change=S.set_new_repo, required=True), style={"display": "flex", "flex_direction": "column", "gap": "4px", **FAINT_12}),
        rx.el.label(
            "Type",
            rx.el.select(*(rx.el.option(label, value=value) for value, label in TYPE_LABEL.items()), class_name="field", value=S.new_type, on_change=S.set_new_type),
            style={"display": "flex", "flex_direction": "column", "gap": "4px", **FAINT_12},
        ),
        rx.el.button("Add source", type="submit", class_name="btn btn-primary"),
        on_submit=lambda _: S.add_source(),
        style={"padding": "10px", "border": "1px solid var(--line)", "border_radius": "8px", "display": "flex", "flex_direction": "column", "gap": "8px"},
    )  # fmt: skip


def _sources() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(heading("Sources", "registry/sources.yaml", "16px"), style={"flex": "1"}),
            rx.el.button(icon("plus", 13), "Add", class_name="btn", on_click=S.toggle_add, aria_expanded=S.adding),
            class_name="row",
            style={"padding": "0 6px 4px"},
        ),
        rx.cond(S.adding, _add_form()),
        rx.foreach(S.sources, _source_row),
        rx.el.div(
            rx.el.span("Sync runs on a schedule in GitHub Actions."),
            rx.el.span(".github/workflows/sync.yml", class_name="mono", style={"font_size": "11.5px"}),
            style={
                "margin_top": "10px", "padding": "12px", "border": "1px dashed var(--line)", "border_radius": "8px",
                "display": "flex", "flex_direction": "column", "gap": "6px", **FAINT_12,
            },
        ),
        aria_label="Sources",
        style={
            "flex": "1 1 300px", "box_sizing": "border-box", "padding": "18px 12px", "border_right": "1px solid var(--line)",
            "display": "flex", "flex_direction": "column", "gap": "8px",
        },
    )  # fmt: skip


def _status(p: rx.Var) -> rx.Component:
    tracked = p["tracked"].to(str)
    return rx.cond(
        tracked != "",
        rx.cond(
            tracked.contains("quarantined"),
            chip(tracked, "warn"),
            rx.cond(tracked.contains("mirror"), chip(tracked, "add"), chip(tracked)),
        ),
        rx.el.span(
            rx.cond(
                p["unsupported"].to(str) != "",
                "cannot mirror",
                rx.cond(p["allowed"].to(bool), "not added", "not on allow-list"),
            ),
            style={"color": "var(--faint)"},
        ),
    )


def _actions(p: rx.Var) -> rx.Component:
    name = p["name"].to(str)
    addable = (p["tracked"].to(str) == "") & (p["unsupported"].to(str) == "")
    allow = rx.el.button("Allow", class_name="btn btn-ghost", on_click=S.allow(name))
    return rx.cond(
        p["allowed"].to(bool),
        rx.cond(
            addable,
            rx.el.span(
                rx.el.button(
                    "Mirror", class_name="btn btn-primary", on_click=S.mirror(name)
                ),
                rx.el.a(
                    "Add to bundle",
                    class_name="btn",
                    href=f"/bundles?source={S.selected}&plugin={name}",
                    style={"text_decoration": "none"},
                ),
                class_name="row",
                style={"justify_content": "flex-end", "gap": "6px"},
            ),
            rx.el.button(
                "Details", class_name="btn btn-ghost", on_click=S.set_focus(name)
            ),
        ),
        allow,
    )


def _plugin_row(p: rx.Var) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            rx.el.div(p["name"], style={"font_weight": "600"}),
            rx.el.div(p["description"], style=FAINT_12),
            class_name="td",
        ),
        rx.el.td(p["version"], class_name="td mono"),
        rx.el.td(p["contents"], class_name="td", style={"color": "var(--muted)"}),
        rx.el.td(
            rx.cond(
                p["license"].to(str) != "", p["license"], chip("no license", "bad")
            ),
            class_name="td mono",
        ),
        rx.el.td(_status(p), class_name="td"),
        rx.el.td(_actions(p), class_name="td", style={"text_align": "right"}),
        on_mouse_enter=S.set_focus(p["name"].to(str)),
        style=rx.cond(S.focus == p["name"], {"background": "var(--raised)"}, {}),
    )


def _browse() -> rx.Component:
    src = S.source
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.div(f"{src['repository']} {src['path']}", class_name="mono", style={"color": "var(--faint)", "font_size": "11.5px"}),
                rx.el.div(
                    rx.el.h2(S.selected, style={"margin": "0", "font_size": "20px", "font_weight": "600"}),
                    chip(f"{S.plugins.length()} plugins"),
                    class_name="row",
                    style={"gap": "10px"},
                ),
                style={"flex": "1 1 320px", "display": "flex", "flex_direction": "column", "gap": "6px"},
            ),
            rx.el.button(icon("sync", 14), "Refresh catalog", class_name="btn", on_click=S.refresh),
            style={"display": "flex", "flex_wrap": "wrap", "align_items": "flex-start", "gap": "12px"},
        ),
        rx.el.div(
            rx.el.div(
                rx.el.label("Filter plugins", html_for="q", style=HIDDEN),
                rx.el.input(id="q", class_name="field", placeholder="Filter by name, skill or keyword", style={"padding_left": "32px"}, value=S.query, on_change=S.set_query),
                icon("search", 14, position="absolute", left="10px", top="9px", color="var(--faint)"),
                style={"flex": "1 1 280px", "position": "relative"},
            ),
            rx.el.div(
                *(
                    rx.el.button(label, class_name=rx.cond(S.kind == key, "btn", "btn btn-ghost"), style={"min_height": "30px"}, on_click=S.set_kind(key), aria_pressed=S.kind == key)
                    for key, label in KINDS
                ),
                class_name="row", role="group", aria_label="Content type", style={"gap": "4px"},
            ),
            style={"display": "flex", "flex_wrap": "wrap", "gap": "8px", "align_items": "center"},
        ),
        panel(
            rx.el.table(
                rx.el.thead(
                    rx.el.tr(
                        *(rx.el.th(h, class_name="th", scope="col") for h in ("Plugin", "Version", "Contents", "License", "In this marketplace")),
                        rx.el.th(rx.el.span("Actions", style=HIDDEN), class_name="th", scope="col"),
                    )
                ),
                rx.el.tbody(rx.foreach(S.shown, _plugin_row)),
                style={"width": "100%", "border_collapse": "collapse", "min_width": "720px"},
            ),
            overflow_x="auto",
        ),
        rx.cond(
            S.focus != "",
            rx.el.div(
                icon("info", 16, color="var(--info)", flex="none"),
                rx.el.span(
                    "Mirror pins ", rx.el.span(S.focus, class_name="mono", style={"color": "var(--text)"}),
                    " at the source's current commit and opens a candidate PR into staging. Nothing ships until it is approved and promoted.",
                    style={"flex": "1 1 300px", "color": "var(--muted)"},
                ),
                rx.el.span(f"skill-dojo mirror {S.selected} {S.focus}", class_name="mono", style={"color": "var(--faint)", "font_size": "11.5px"}),
                style={
                    "display": "flex", "flex_wrap": "wrap", "gap": "12px", "align_items": "center", "padding": "12px 14px",
                    "border": "1px solid var(--line)", "border_radius": "9px", "background": "var(--panel)",
                },
            ),
        ),
        aria_label="Browse source",
        style={
            "flex": "999 1 520px", "min_width": "0", "box_sizing": "border-box", "padding": "18px 28px 28px",
            "display": "flex", "flex_direction": "column", "gap": "16px",
        },
    )  # fmt: skip


def sources_page() -> rx.Component:
    return shell(
        "sources",
        main_area(
            rx.el.div(
                _sources(),
                rx.cond(S.selected != "", _browse()),
                style={"display": "flex", "flex_wrap": "wrap", "width": "100%"},
            ),
        ),
    )
