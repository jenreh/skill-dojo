"""Clients and revocation: who uses which ref, and the revoke PR."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.icons import icon
from skill_dojo_web.shell import FAINT_12, heading, main_area, panel, shell
from skill_dojo_web.state import AppState

FIELD = {"display": "flex", "flex_direction": "column", "gap": "4px"}
LABEL = {"color": "var(--muted)", "font_size": "12px"}


class ClientsState(AppState):
    clients: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    item: str = ""
    action: str = "rollback"
    reason: str = ""
    adding: bool = False
    name: str = ""
    ref: str = ""
    contact: str = ""
    notes: str = ""

    @rx.var
    def target(self) -> dict[str, Any]:
        return next((t for t in self.targets if t["item"] == self.item), {})

    @rx.var
    def affected_names(self) -> list[str]:
        return [c["name"] for c in self.target.get("affected", [])]

    @rx.var
    def affected_refs(self) -> str:
        refs = sorted({c["ref"] for c in self.target.get("affected", [])})
        return ", ".join(refs) or "no client ref"

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            ctx = self._ctx()
            self.clients = [c.model_dump() for c in core.clients_list(ctx).clients]
            self.targets = [
                t.model_dump(mode="json") for t in core.revoke_preview(ctx).targets
            ]
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        items = [t["item"] for t in self.targets]
        if items and self.item not in items:
            self.item = items[0]

    @rx.event
    def set_item(self, value: str) -> None:
        self.item = value

    @rx.event
    def set_action(self, value: str) -> None:
        self.action = value

    @rx.event
    def set_reason(self, value: str) -> None:
        self.reason = value

    @rx.event
    def toggle_add(self) -> None:
        self.adding = not self.adding

    @rx.event
    def set_field(self, key: str, value: str) -> None:
        setattr(self, key, value)

    @rx.event
    def add_client(self) -> None:
        try:
            core.clients_add(
                self._ctx(),
                self.name.strip(),
                self.ref.strip(),
                contact=self.contact or None,
                notes=self.notes or None,
                update=any(c["name"] == self.name.strip() for c in self.clients),
            )
            self._say(f"Client {self.name} uses {self.ref}")
            self.adding, self.name, self.ref, self.contact, self.notes = (
                False,
                "",
                "",
                "",
                "",
            )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def edit_client(self, name: str) -> None:
        found = next((c for c in self.clients if c["name"] == name), None)
        if found:
            self.adding = True
            self.name, self.ref = found["name"], found["ref"]
            self.contact, self.notes = found["contact"] or "", found["notes"] or ""

    @rx.event
    def remove_client(self, name: str) -> None:
        try:
            core.clients_remove(self._ctx(), name)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def revoke(self) -> None:
        try:
            result = core.revoke(
                self._ctx(),
                self.item,
                rollback=self.action == "rollback",
                reason=self.reason,
            )
            self._say(
                f"Revoke {result.item} ({result.action}): {result.pull_request.url}"
            )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()


S = ClientsState


def _client_row(c: rx.Var) -> rx.Component:
    hit = S.affected_names.contains(c["name"])
    return rx.el.tr(
        rx.el.td(
            rx.el.button(
                c["name"],
                on_click=S.edit_client(c["name"].to(str)),
                aria_label=f"Edit {c['name']}",
                style={"font": "inherit", "font_weight": "500", "color": "inherit", "background": "none", "border": "0", "padding": "0", "cursor": "pointer"},
            ),
            class_name="td",
        ),
        rx.el.td(c["notes"], class_name="td"),
        rx.el.td(c["ref"], class_name="td mono"),
        rx.el.td(c["contact"], class_name="td", style={"color": "var(--muted)"}),
        rx.el.td(
            rx.cond(
                hit,
                rx.el.span(icon("warn-bold", 11), "yes", class_name="chip", style={"background": "transparent", "color": "var(--bad)"}),
                rx.el.span("no", style={"color": "var(--faint)"}),
            ),
            class_name="td",
        ),
        rx.el.td(
            rx.el.button(icon("x", 13), class_name="btn btn-ghost", aria_label=f"Remove {c['name']}", on_click=S.remove_client(c["name"].to(str))),
            class_name="td",
            style={"text_align": "right"},
        ),
        style=rx.cond(hit, {"background": "var(--bad-bg)"}, {}),
    )  # fmt: skip


def _input(label: str, key: str, value: Any, required: bool = False) -> rx.Component:
    return rx.el.label(
        label,
        rx.el.input(
            class_name="field",
            value=value,
            on_change=lambda v: S.set_field(key, v),
            required=required,
        ),
        style={**FIELD, **LABEL, "flex": "1 1 160px"},
    )


def _add_form() -> rx.Component:
    return rx.el.form(
        _input("Workspace", "name", S.name, True),
        _input("Ref in use", "ref", S.ref, True),
        _input("Contact", "contact", S.contact),
        _input("Client", "notes", S.notes),
        rx.el.button("Save client", type="submit", class_name="btn btn-primary", style={"align_self": "flex-end"}),
        on_submit=lambda _: S.add_client(),
        style={"display": "flex", "flex_wrap": "wrap", "gap": "10px", "padding": "12px", "border": "1px solid var(--line)", "border_radius": "9px"},
    )  # fmt: skip


def _revoke() -> rx.Component:
    t = S.target
    return rx.el.aside(
        rx.el.div(icon("shield-x", 16, color="var(--bad)"), rx.el.span("Revoke an item", style={"font_weight": "600"}), class_name="row"),
        rx.el.div(
            rx.el.label("Item", html_for="ritem", style=LABEL),
            rx.el.select(
                rx.foreach(S.targets, lambda x: rx.el.option(f"{x['item']} {x['version']}", value=x["item"].to(str))),
                id="ritem", class_name="field", value=S.item, on_change=S.set_item,
            ),
            style=FIELD,
        ),
        rx.el.div(
            rx.el.label("Action", html_for="ract", style=LABEL),
            rx.el.select(
                rx.el.option(rx.cond(t["rollback_to"].to(str) != "", f"Roll back to {t['rollback_to']}", "Roll back (no earlier approved release)"), value="rollback"),
                rx.el.option("Remove from marketplace", value="remove"),
                id="ract", class_name="field", value=S.action, on_change=S.set_action,
            ),
            style=FIELD,
        ),
        rx.el.div(
            rx.el.label("Reason", html_for="rwhy", style=LABEL),
            rx.el.textarea(id="rwhy", class_name="field field-area", rows="3", value=S.reason, on_change=S.set_reason),
            style=FIELD,
        ),
        rx.el.div(
            rx.el.span(f"{S.affected_names.length()} clients affected", style={"font_weight": "500"}),
            rx.el.span(f"In {S.affected_refs}. Contacts are copied to the PR body.", style={"color": "var(--muted)", "font_size": "12px"}),
            style={"padding": "10px 12px", "border_radius": "8px", "background": "var(--raised)", "display": "flex", "flex_direction": "column", "gap": "4px"},
        ),
        rx.el.div(
            *(
                rx.el.span(rx.el.span(str(n), class_name="mono", style={"color": "var(--faint)"}), text, class_name="row")
                for n, text in enumerate(("Hotfix PR straight to main", "Back-merge PR into staging", "Quarantine flag stops new candidates"), 1)
            ),
            style={"display": "flex", "flex_direction": "column", "gap": "6px", "color": "var(--muted)", "font_size": "12px"},
        ),
        rx.el.button("Open revocation PR", class_name="btn btn-danger", on_click=S.revoke, disabled=S.item == ""),
        aria_label="Revoke",
        style={
            "flex": "1 1 300px", "border": "1px solid var(--line)", "border_radius": "9px", "background": "var(--panel)",
            "padding": "16px", "display": "flex", "flex_direction": "column", "gap": "12px",
        },
    )  # fmt: skip


def clients_page() -> rx.Component:
    return shell(
        "clients",
        main_area(
            rx.el.section(
                rx.el.div(
                    rx.el.div(heading("Clients", "Hand-kept in registry/clients.yaml. Who to warn when something is revoked."), style={"flex": "1 1 280px"}),
                    rx.el.button(icon("plus", 13), "Add client", class_name="btn", on_click=S.toggle_add, aria_expanded=S.adding),
                    style={"display": "flex", "flex_wrap": "wrap", "align_items": "flex-start", "gap": "12px"},
                ),
                rx.cond(S.adding, _add_form()),
                panel(
                    rx.el.table(
                        rx.el.thead(rx.el.tr(*(rx.el.th(h, class_name="th", scope="col") for h in ("Workspace", "Client", "Ref in use", "Contact", "Affected", "")))),
                        rx.el.tbody(rx.foreach(S.clients, _client_row)),
                        style={"width": "100%", "border_collapse": "collapse", "min_width": "620px"},
                    ),
                    rx.cond(S.clients.length() == 0, rx.el.p("No clients yet.", style={"padding": "10px 12px", "margin": "0", **FAINT_12})),
                    overflow_x="auto",
                ),
                aria_label="Clients",
                style={"flex": "999 1 520px", "min_width": "0", "display": "flex", "flex_direction": "column", "gap": "14px"},
            ),
            _revoke(),
            box_sizing="border-box", padding="18px 28px 28px", display="flex", flex_wrap="wrap", gap="18px", align_content="flex-start",
        ),
    )  # fmt: skip
