"""Bundles: pick parts from any source and open the bundle's candidate PR."""

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

GROUP = {"padding": "10px 8px 6px", "color": "var(--faint)", "font_size": "11.5px", "font_weight": "500", "text_transform": "uppercase", "letter_spacing": ".04em"}  # fmt: skip
KIND = {"skill": "skill", "agent": "agent", "mcp_server": "mcp"}


def spec(part: dict[str, Any]) -> str:
    """``source:plugin/kind/name`` of a part."""
    return f"{part['source']}:{part['plugin']}/{part['kind']}/{part['name']}"


class BundlesState(AppState):
    bundles: list[dict[str, Any]] = []
    bundle: str = ""
    new_name: str = ""
    category: str = ""
    description: str = ""
    groups: list[dict[str, Any]] = []
    picked: list[str] = []
    query: str = ""

    @rx.var
    def current(self) -> dict[str, Any]:
        return next((b for b in self.bundles if b["id"] == self.bundle), {})

    @rx.var
    def existing(self) -> list[str]:
        return [spec(p) for p in self.current.get("parts", [])]

    @rx.var
    def parts(self) -> list[dict[str, Any]]:
        """Parts the bundle will have: kept ones first, then new picks."""
        known = {spec(p): p for g in self.groups for p in g["parts"]}
        kept = [p for p in self.current.get("parts", []) if spec(p) in self.picked]
        new = [known[s] for s in self.picked if s not in self.existing and s in known]
        return [
            {**p, "kind_label": KIND.get(p["kind"], p["kind"]), "new": p in new}
            for p in kept + new
        ]

    @rx.var
    def dirty(self) -> bool:
        return sorted(self.picked) != sorted(self.existing) or self.bundle == ""

    @rx.var
    def shown_groups(self) -> list[dict[str, Any]]:
        q = self.query.lower()
        return [
            {
                **g,
                "parts": [
                    {**p, "spec": spec(p), "kind_label": KIND.get(p["kind"], p["kind"])}
                    for p in g["parts"]
                    if q in p["name"].lower()
                ],
            }
            for g in self.groups
        ]

    @rx.var
    def next_version(self) -> str:
        version = self.current.get("version") or ""
        bits = version.split(".")
        if len(bits) == 3 and bits[2].isdigit():  # noqa: PLR2004
            return f"{version} → {bits[0]}.{bits[1]}.{int(bits[2]) + 1}"
        return "0.1.0"

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            ctx = self._ctx()
            self.bundles = [b.model_dump() for b in core.bundles_overview(ctx)]
            local = [
                i.id
                for i in core.Registry.load(ctx.repo).items.items
                if i.kind.value == "local"
            ]
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        wanted = [("local", i) for i in local]
        for b in self.bundles:
            wanted += [(p["source"], p["plugin"]) for p in b["parts"] if p["source"]]
        params = self.router.page.params
        if params.get("source") and params.get("plugin"):
            wanted.append((str(params["source"]), str(params["plugin"])))
        self.groups = []
        for source, plugin in dict.fromkeys(wanted):
            self._load_plugin(source, plugin)
        ids = [b["id"] for b in self.bundles]
        self._choose(self.bundle if self.bundle in ids else (ids[0] if ids else ""))

    def _load_plugin(self, source: str, plugin: str) -> None:
        try:
            parts = [
                p.model_dump() for p in core.plugin_parts(self._ctx(), source, plugin)
            ]
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        title = (
            f"{source} · this repo · {plugin}"
            if source == "local"
            else f"{source} · {plugin}"
        )
        self.groups = [*self.groups, {"title": title, "parts": parts}]

    def _choose(self, bundle_id: str) -> None:
        self.bundle = bundle_id
        current = next((b for b in self.bundles if b["id"] == bundle_id), {})
        self.picked = [spec(p) for p in current.get("parts", [])]
        self.description = current.get("description", "")
        self.category = current.get("category") or ""

    @rx.event
    def choose(self, bundle_id: str) -> None:
        self._choose(bundle_id)

    @rx.event
    def toggle(self, part: str) -> None:
        self.picked = (
            [p for p in self.picked if p != part]
            if part in self.picked
            else [*self.picked, part]
        )

    @rx.event
    def set_query(self, value: str) -> None:
        self.query = value

    @rx.event
    def set_new_name(self, value: str) -> None:
        self.new_name = value

    @rx.event
    def set_category(self, value: str) -> None:
        self.category = value

    @rx.event
    def set_description(self, value: str) -> None:
        self.description = value

    @rx.event
    def discard(self) -> None:
        self._choose(self.bundle)

    @rx.event
    def open_pr(self) -> None:
        try:
            ctx = self._ctx()
            if self.bundle == "":
                result = core.bundle_create(
                    ctx,
                    self.new_name.strip(),
                    self.picked,
                    description=self.description or None,
                    category=self.category or None,
                )
            else:
                added = [p for p in self.picked if p not in self.existing]
                removed = [
                    p.split("/", 1)[1] for p in self.existing if p not in self.picked
                ]
                result = None
                if added:
                    result = core.bundle_add(ctx, self.bundle, added)
                if removed:
                    result = core.bundle_remove(ctx, self.bundle, removed)
                if result is None:
                    self._say("Nothing to change")
                    return
            self._say(f"{result.item}: {result.status} candidate PR")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()


S = BundlesState


def _pick(p: rx.Var) -> rx.Component:
    s = p["spec"].to(str)
    return rx.el.label(
        rx.el.input(
            type="checkbox",
            checked=S.picked.contains(s),
            on_change=lambda _: S.toggle(s),
        ),
        rx.el.span(p["name"], style={"flex": "1"}),
        rx.el.span(p["kind_label"], class_name="chip"),
        class_name="pick",
    )


def _group(g: rx.Var) -> rx.Component:
    return rx.fragment(
        rx.el.div(icon("chevron-bold", 15), g["title"], class_name="row", style=GROUP),
        rx.foreach(g["parts"].to(list[dict[str, Any]]), _pick),
    )


def _part_row(p: rx.Var) -> rx.Component:
    local = p["source"].to(str) == "local"
    return rx.el.div(
        rx.el.span(
            rx.el.span(p["name"], style={"font_weight": "500"}), " ", rx.el.span(p["kind_label"], class_name="chip"),
            rx.el.br(),
            rx.el.span(f"{p['source']} · {p['path']}", class_name="mono", style={"color": "var(--faint)", "font_size": "11.5px"}),
            style={"flex": "1 1 220px"},
        ),
        rx.el.span(f"@ {p['commit'].to(str)[:12]}", class_name="mono", style={"color": "var(--muted)"}),
        rx.el.span(p["license"], class_name="mono", style={"color": "var(--muted)"}),
        rx.cond(p["new"].to(bool), chip("new", "warn"), rx.cond(local, chip("local"), chip("pinned", "add"))),
        rx.el.button(icon("x", 14), class_name="btn btn-ghost", aria_label=f"Remove {p['name']}", on_click=S.toggle(f"{p['source']}:{p['plugin']}/{p['kind']}/{p['name']}")),
        style={"display": "flex", "flex_wrap": "wrap", "align_items": "center", "gap": "8px 14px", "padding": "10px 14px", "border_bottom": "1px solid var(--line)"},
    )  # fmt: skip


def _field(id_: str, label: str, value: Any, on_change: Any, flex: str) -> rx.Component:
    return rx.el.div(
        rx.el.label(
            label, html_for=id_, style={"color": "var(--muted)", "font_size": "12px"}
        ),
        rx.el.input(id=id_, class_name="field", value=value, on_change=on_change),
        style={
            "flex": flex,
            "display": "flex",
            "flex_direction": "column",
            "gap": "4px",
        },
    )


def _editor() -> rx.Component:
    c = S.current
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.select(
                        rx.el.option("New bundle", value=""),
                        rx.foreach(S.bundles, lambda b: rx.el.option(f"plugins/{b['id']}", value=b["id"].to(str))),
                        class_name="field mono", value=S.bundle, on_change=S.choose, aria_label="Bundle",
                        style={"width": "auto", "min_height": "24px", "font_size": "11.5px", "color": "var(--faint)", "border": "0", "padding": "0", "background": "transparent"},
                    ),
                    rx.el.span(" · registry/items.yaml", class_name="mono", style={"color": "var(--faint)", "font_size": "11.5px"}),
                    class_name="row", style={"gap": "0"},
                ),
                rx.el.div(
                    rx.cond(
                        S.bundle == "",
                        rx.el.input(class_name="field", placeholder="new-bundle-name", value=S.new_name, on_change=S.set_new_name, aria_label="Bundle name", style={"max_width": "260px"}),
                        rx.el.h2(c["id"], style={"margin": "0", "font_size": "20px", "font_weight": "600"}),
                    ),
                    chip("bundle"),
                    rx.el.span(S.next_version, class_name="chip mono"),
                    rx.cond(S.dirty, chip("unsaved", "warn")),
                    class_name="row", style={"gap": "10px"},
                ),
                style={"flex": "1 1 320px", "display": "flex", "flex_direction": "column", "gap": "6px"},
            ),
            rx.el.button("Discard", class_name="btn", on_click=S.discard),
            rx.el.button(icon("promote", 14), "Open candidate PR", class_name="btn btn-primary", on_click=S.open_pr),
            style={"display": "flex", "flex_wrap": "wrap", "align_items": "flex-start", "gap": "12px"},
        ),
        rx.el.div(
            _field("bcat", "Category", S.category, S.set_category, "1 1 260px"),
            _field("bdesc", "Description", S.description, S.set_description, "2 1 360px"),
            style={"display": "flex", "flex_wrap": "wrap", "gap": "12px"},
        ),
        panel(
            panel_head("Parts", chip(S.parts.length()), rx.el.span("Each part is pinned on its own", style={"margin_left": "auto", **FAINT_12})),
            rx.foreach(S.parts, _part_row),
        ),
        rx.el.div(
            panel(
                rx.el.span("What the PR will contain", style={"font_weight": "600"}),
                check_line("Exact pinned files for every part"),
                check_line("plugin.json with a parts list per origin"),
                check_line("lock.json hashes and vendored licenses"),
                check_line(f"Patch bump to {S.next_version}"),
                flex="1 1 260px", padding="12px 14px", display="flex", flex_direction="column", gap="6px",
            ),
            panel(
                rx.el.span("Pre-check", style={"font_weight": "600"}),
                check_line("validate runs on the candidate branch"),
                check_line("Risk flags are listed in the PR", "info"),
                check_line("Part names must not clash"),
                flex="1 1 260px", padding="12px 14px", display="flex", flex_direction="column", gap="6px",
            ),
            style={"display": "flex", "flex_wrap": "wrap", "gap": "12px"},
        ),
        aria_label="Bundle",
        style={"flex": "999 1 520px", "min_width": "0", "box_sizing": "border-box", "padding": "18px 28px 28px", "display": "flex", "flex_direction": "column", "gap": "16px"},
    )  # fmt: skip


def bundles_page() -> rx.Component:
    return shell(
        "bundles",
        main_area(
            rx.el.div(
                rx.el.section(
                    rx.el.div(heading("Pick parts", "Skills, agents and MCP servers from any source", "16px"), style={"padding": "0 6px"}),
                    rx.el.div(
                        rx.el.label("Search parts", html_for="pq", style={"position": "absolute", "width": "1px", "height": "1px", "overflow": "hidden", "clip": "rect(0 0 0 0)"}),
                        rx.el.input(id="pq", class_name="field", placeholder="Search parts", value=S.query, on_change=S.set_query),
                        style={"padding": "0 6px"},
                    ),
                    rx.el.div(rx.foreach(S.shown_groups, _group), style={"display": "flex", "flex_direction": "column", "gap": "2px"}),
                    rx.el.p("Add plugins from Sources and browse (Add to bundle).", style={"padding": "0 6px", **FAINT_12}),
                    aria_label="Pick parts",
                    style={"flex": "1 1 340px", "box_sizing": "border-box", "padding": "18px 12px", "border_right": "1px solid var(--line)", "display": "flex", "flex_direction": "column", "gap": "10px"},
                ),
                _editor(),
                style={"display": "flex", "flex_wrap": "wrap", "width": "100%"},
            ),
        ),
    )  # fmt: skip
