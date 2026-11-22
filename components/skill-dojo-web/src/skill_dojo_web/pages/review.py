"""Review queue: candidate PRs into staging, their flags and diff, the decision."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_core import Channel, RiskTier
from skill_dojo_web.icons import icon
from skill_dojo_web.shell import (
    FAINT_12,
    chip,
    heading,
    main_area,
    panel,
    panel_head,
    shell,
)
from skill_dojo_web.state import AppState


def flag_tone(kind: str) -> str:
    """bad / warn / info color of a risk flag kind."""
    if kind.startswith(("mcp-", "hook-", "binary", "symlink")):
        return "bad" if kind.startswith("mcp-") else "warn"
    if set(kind.split("-")) & {"network", "script", "executable", "tool", "tools"}:
        return "warn"
    return "info"


class ReviewState(AppState):
    entries: list[dict[str, Any]] = []
    quarantined: list[str] = []
    filter: str = "all"
    selected: int = 0
    detail: dict[str, Any] = {}
    tab: str = "diff"
    tier: str = "standard"
    classification: str = "internal"
    beta: bool = True
    stable: bool = True

    @rx.var
    def rows(self) -> list[dict[str, Any]]:
        if self.filter == "flagged":
            return [e for e in self.entries if e["flags"] > 0]
        if self.filter == "quarantined":
            return []
        return self.entries

    @rx.var
    def flagged_count(self) -> int:
        return sum(1 for e in self.entries if e["flags"] > 0)

    @rx.var
    def flags(self) -> list[dict[str, Any]]:
        return [
            {
                **f,
                "tone": flag_tone(f["kind"]),
                "where": f["path"] + (f":{f['line']}" if f.get("line") else ""),
            }
            for f in self.detail.get("flags", [])
        ]

    @rx.var
    def files(self) -> list[dict[str, Any]]:
        return self.detail.get("files", [])

    @rx.var
    def added(self) -> int:
        return sum(f["added"] for f in self.files)

    @rx.var
    def removed(self) -> int:
        return sum(f["removed"] for f in self.files)

    @rx.var
    def approvals(self) -> list[str]:
        return list(self.detail.get("approvals", []))

    @rx.var
    def approved_count(self) -> int:
        return len(self.approvals)

    @rx.var
    def review_width(self) -> str:
        needed = max(int(self.detail.get("reviewers_needed", 1)), 1)
        return f"{min(100, round(100 * self.approved_count / needed))}%"

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            listed = core.review_list(self._ctx())
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.entries = [
            {
                "number": e.pull_request.number,
                "item": e.item or e.pull_request.head,
                "kind": e.kind or "new",
                "title": e.pull_request.title,
                "pin": e.pull_request.title.partition(" @ ")[2],
                "flags": e.flags,
                "age": (e.pull_request.created_at or "")[:10],
            }
            for e in listed.entries
        ]
        self.quarantined = listed.quarantined
        numbers = [e["number"] for e in self.entries]
        if numbers:
            self._open(self.selected if self.selected in numbers else numbers[0])
        else:
            self.selected, self.detail = 0, {}

    def _open(self, number: int) -> None:
        try:
            detail = core.review_detail(self._ctx(), number)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.selected, self.tab = number, "diff"
        self.detail = detail.model_dump(mode="json")
        self.tier, self.classification = detail.risk_tier, detail.data_classification
        self.beta, self.stable = "beta" in detail.channels, "stable" in detail.channels

    @rx.event
    def select(self, number: int) -> None:
        self._open(number)

    @rx.event
    def set_filter(self, value: str) -> None:
        self.filter = value

    @rx.event
    def set_tab(self, value: str) -> None:
        self.tab = value

    @rx.event
    def set_tier(self, value: str) -> None:
        self.tier = value

    @rx.event
    def set_classification(self, value: str) -> None:
        self.classification = value

    @rx.event
    def set_beta(self, value: bool) -> None:
        self.beta = value

    @rx.event
    def set_stable(self, value: bool) -> None:
        self.stable = value

    def _policy_changed(self) -> bool:
        d = self.detail
        return (
            self.tier != d.get("risk_tier")
            or self.classification != d.get("data_classification")
            or {"beta": self.beta, "stable": self.stable}
            != {c: c in d.get("channels", []) for c in ("beta", "stable")}
        )

    @rx.event
    def approve(self) -> None:
        number = self.selected
        try:
            ctx = self._ctx()
            if self._policy_changed():
                channels = [
                    c
                    for c, on in (
                        (Channel.BETA, self.beta),
                        (Channel.STABLE, self.stable),
                    )
                    if on
                ]
                core.review_policy(
                    ctx,
                    number,
                    risk_tier=RiskTier(self.tier),
                    data_classification=self.classification,
                    channels=channels,
                )
            head = core.review_show(ctx, number).pull_request.head_oid
            result = core.review_approve(ctx, number, head=head)
            self._say(f"PR #{number}: {result.status}", ok=result.status == "merged")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def reject(self) -> None:
        self._act(core.review_reject, "rejected")

    @rx.event
    def quarantine(self) -> None:
        self._act(core.review_quarantine, "quarantined")

    def _act(self, action: Any, word: str) -> None:
        try:
            action(self._ctx(), self.selected)
            self._say(f"PR #{self.selected} {word}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()


S = ReviewState


def _filter_button(key: str, label: Any) -> rx.Component:
    return rx.el.button(
        label,
        class_name=rx.cond(S.filter == key, "btn", "btn btn-ghost"),
        style={"min_height": "28px", "padding": "0 10px"},
        on_click=S.set_filter(key),
        aria_pressed=S.filter == key,
    )


def _queue_row(entry: rx.Var) -> rx.Component:
    flags = entry["flags"].to(int)
    on = S.selected == entry["number"]
    return rx.el.button(
        rx.el.span(
            rx.el.span(entry["item"], style={"font_weight": "600"}),
            rx.el.span(entry["kind"], class_name="chip", style=rx.cond(on, {"background": "var(--bg)"}, {})),
            rx.el.span(entry["age"], style={"margin_left": "auto", "color": "var(--faint)", "font_size": "11.5px"}),
            class_name="row",
        ),
        rx.el.span(entry["pin"], class_name="mono", style={"color": "var(--muted)"}),
        rx.el.span(
            rx.cond(
                flags > 0,
                chip(f"{flags} flag(s)", rx.cond(flags > 2, "bad", "warn")),
                chip("no flags", "add"),
            ),
            rx.el.span(f"PR #{entry['number']}", class_name="mono", style={"color": "var(--faint)", "font_size": "11.5px"}),
            class_name="row",
            style={"gap": "6px"},
        ),
        on_click=S.select(entry["number"].to(int)),
        aria_current=rx.cond(on, "true", "false"),
        style={
            "font": "inherit", "text_align": "left", "color": "inherit", "border": "0", "cursor": "pointer",
            "width": "100%", "padding": "10px 10px", "border_radius": "8px",
            "background": rx.cond(on, "var(--raised)", "transparent"),
            "display": "flex", "flex_direction": "column", "gap": "4px",
        },
    )  # fmt: skip


def _held_row(item: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.el.span(rx.el.span(item, style={"font_weight": "600"}), class_name="row"),
        rx.el.span(chip(icon("pause", 10), "quarantined"), class_name="row"),
        style={"padding": "10px", "border_radius": "8px", "display": "flex", "flex_direction": "column", "gap": "4px", "opacity": ".75"},
    )  # fmt: skip


def _queue() -> rx.Component:
    return rx.el.section(
        rx.el.div(heading("Review queue", "Candidate PRs into staging", "16px"), style={"padding": "0 6px"}),
        rx.el.div(
            _filter_button("all", f"All {S.entries.length()}"),
            _filter_button("flagged", f"Flagged {S.flagged_count}"),
            _filter_button("quarantined", f"Quarantined {S.quarantined.length()}"),
            class_name="row",
            role="group",
            aria_label="Filter",
            style={"padding": "0 6px", "gap": "4px"},
        ),
        rx.foreach(S.rows, _queue_row),
        rx.cond(S.filter != "flagged", rx.foreach(S.quarantined, _held_row)),
        rx.cond(S.entries.length() == 0, rx.el.p("No open candidate PRs.", style={"padding": "0 6px", **FAINT_12})),
        aria_label="Candidates",
        style={
            "flex": "1 1 300px", "box_sizing": "border-box", "padding": "18px 12px", "border_right": "1px solid var(--line)",
            "display": "flex", "flex_direction": "column", "gap": "10px",
        },
    )  # fmt: skip


def _fact(label: str, value: Any) -> rx.Component:
    return rx.el.div(
        rx.el.div(label, style={"color": "var(--faint)", "font_size": "11.5px"}),
        rx.el.div(value, class_name="mono"),
        style={
            "background": "var(--panel)",
            "padding": "10px 12px",
            "min_width": "0",
            "overflow_wrap": "anywhere",
        },
    )


def _flag_row(flag: rx.Var) -> rx.Component:
    tone = flag["tone"].to(str)
    return rx.el.div(
        rx.match(
            tone,
            ("info", icon("info", 15, color="var(--info)", flex="none")),
            ("bad", icon("warn", 15, color="var(--bad)", flex="none")),
            icon("warn", 15, color="var(--warn)", flex="none"),
        ),
        rx.el.span(flag["detail"], style={"flex": "1"}),
        rx.el.span(flag["where"], class_name="mono", style={"color": "var(--accent)"}),
        class_name="row",
        style={
            "padding": "9px 14px",
            "border_bottom": "1px solid var(--line)",
            "gap": "10px",
        },
    )


def _diff_line(line: rx.Var) -> rx.Component:
    kind = line["kind"].to(str)
    return rx.el.div(
        f"{line['kind']} {line['number']}  {line['text']}",
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
            {"padding": "0 14px", "color": "var(--faint)"},
        ),
    )


def _diff_file(file: rx.Var) -> rx.Component:
    return rx.fragment(
        rx.el.div(
            icon("file", 13),
            file["path"],
            rx.el.span(
                rx.el.span(f"+{file['added']}", style={"color": "var(--add)"}),
                " ",
                rx.el.span(f"−{file['removed']}", style={"color": "var(--del)"}),
                style={"margin_left": "auto"},
            ),
            class_name="row mono",
            style={"padding": "8px 14px", "background": "var(--raised)", "color": "var(--muted)", "border_top": "1px solid var(--line)"},
        ),
        rx.el.div(
            rx.foreach(file["lines"].to(list[dict[str, Any]]), _diff_line),
            class_name="mono",
            style={"padding": "6px 0", "line_height": "1.7", "white_space": "pre", "overflow_x": "auto"},
        ),
    )  # fmt: skip


def _tab(key: str, *label: Any) -> rx.Component:
    return rx.el.button(
        *label,
        class_name=rx.cond(S.tab == key, "btn", "btn btn-ghost"),
        role="tab",
        aria_selected=S.tab == key,
        style={"min_height": "28px"},
        on_click=S.set_tab(key),
    )


def _metadata() -> rx.Component:
    d = S.detail
    rows = [
        ("Source", d["source"]), ("Upstream", d["upstream"]), ("Branch", d["head"]),
        ("Tree SHA-256", d["tree_sha256"]), ("Risk tier", d["risk_tier"]),
        ("Data classification", d["data_classification"]), ("Contents", d["contents"]),
    ]  # fmt: skip
    return rx.el.div(
        *(
            rx.el.div(
                rx.el.span(k, style={"width": "160px", **FAINT_12}),
                rx.el.span(v, class_name="mono", style={"overflow_wrap": "anywhere"}),
                class_name="row",
                style={"padding": "6px 14px"},
            )
            for k, v in rows
        ),
        style={"padding": "6px 0"},
    )


def _detail() -> rx.Component:
    d = S.detail
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    f"{d['source']} / {d['item']} · ",
                    rx.el.a(f"PR #{d['number']}", href=d["url"].to(str), target="_blank", rel="noreferrer"),
                    " into staging",
                    class_name="mono",
                    style={"color": "var(--faint)", "font_size": "11.5px"},
                ),
                rx.el.div(
                    rx.el.h2(d["item"], style={"margin": "0", "font_size": "20px", "font_weight": "600"}),
                    chip(d["kind"]),
                    chip(d["contents"]),
                    class_name="row",
                    style={"gap": "10px"},
                ),
                style={"flex": "1 1 320px", "display": "flex", "flex_direction": "column", "gap": "6px"},
            ),
            rx.el.a(icon("external", 14), "Open on GitHub", href=d["url"].to(str), target="_blank", rel="noreferrer", class_name="btn", style={"text_decoration": "none"}),
            style={"display": "flex", "flex_wrap": "wrap", "align_items": "flex-start", "gap": "12px"},
        ),
        rx.el.div(
            _fact("Version", rx.fragment(f"{d['old_version']} → ", rx.el.span(d["new_version"], style={"color": "var(--accent)"}))),
            _fact("Upstream commit", f"{d['old_commit']} → {d['new_commit']}"),
            _fact("Tracked ref", d["ref"]),
            _fact("Tree SHA-256", d["tree_sha256"].to(str)[:12]),
            style={
                "display": "grid", "grid_template_columns": "repeat(4, minmax(0, 1fr))", "gap": "1px",
                "background": "var(--line)", "border": "1px solid var(--line)", "border_radius": "9px", "overflow": "hidden",
            },
        ),
        rx.el.div(
            rx.el.div(
                panel(
                    panel_head("Risk flags", chip(S.flags.length()), rx.el.span("Flags inform. Policy decides.", style={"margin_left": "auto", **FAINT_12})),
                    rx.foreach(S.flags, _flag_row),
                    rx.cond(S.flags.length() == 0, rx.el.div("No risk flags.", style={"padding": "9px 14px", **FAINT_12})),
                ),
                panel(
                    rx.el.div(
                        _tab("diff", "Diff ", chip(f"{S.files.length()} files", height="18px")),
                        _tab("meta", "Metadata"),
                        rx.el.span(
                            rx.el.span(f"+{S.added}", style={"color": "var(--add)"}), " ",
                            rx.el.span(f"−{S.removed}", style={"color": "var(--del)"}),
                            class_name="mono", style={"margin_left": "auto", "padding_right": "6px"},
                        ),
                        class_name="row", role="tablist",
                        style={"padding": "6px 8px", "border_bottom": "1px solid var(--line)", "gap": "2px"},
                    ),
                    rx.cond(S.tab == "diff", rx.foreach(S.files, _diff_file), _metadata()),
                    overflow="hidden",
                ),
                style={"flex": "999 1 420px", "min_width": "0", "display": "flex", "flex_direction": "column", "gap": "18px"},
            ),
            _decision(),
            style={"display": "flex", "flex_wrap": "wrap", "gap": "18px", "align_items": "flex-start"},
        ),
        aria_label="Candidate detail",
        style={
            "flex": "999 1 520px", "min_width": "0", "box_sizing": "border-box", "padding": "18px 28px 28px",
            "display": "flex", "flex_direction": "column", "gap": "18px",
        },
    )  # fmt: skip


def _select(
    id_: str, label: str, value: Any, options: list[str], on_change: Any
) -> rx.Component:
    return rx.el.div(
        rx.el.label(label, html_for=id_, style={"color": "var(--muted)", "font_size": "12px"}),
        rx.el.select(*(rx.el.option(o, value=o) for o in options), id=id_, class_name="field", value=value, on_change=on_change),
        style={"display": "flex", "flex_direction": "column", "gap": "4px"},
    )  # fmt: skip


def _decision() -> rx.Component:
    d = S.detail
    return rx.el.aside(
        rx.el.div("Decision", style={"font_weight": "600"}),
        _select("tier", "Risk tier", S.tier, [t.value for t in RiskTier], S.set_tier),
        _select("cls", "Data classification", S.classification, ["public", "internal", "confidential"], S.set_classification),
        rx.el.fieldset(
            rx.el.legend("Channels", style={"color": "var(--muted)", "font_size": "12px", "padding": "0", "margin_bottom": "4px"}),
            rx.el.label(rx.el.input(type="checkbox", checked=S.beta, on_change=S.set_beta), " beta (staging)", class_name="row"),
            rx.el.label(rx.el.input(type="checkbox", checked=S.stable, on_change=S.set_stable), " stable (main)", class_name="row"),
            style={"border": "0", "margin": "0", "padding": "0", "display": "flex", "flex_direction": "column", "gap": "6px"},
        ),
        rx.el.div(
            rx.el.div(
                rx.el.span("Reviews", style={"color": "var(--muted)", "font_size": "12px"}),
                rx.el.span(f"{S.approved_count} / {d['reviewers_needed']}", class_name="mono", style={"margin_left": "auto"}),
                class_name="row",
            ),
            rx.el.div(
                rx.el.div(style={"width": S.review_width, "height": "4px", "border_radius": "2px", "background": "var(--accent)"}),
                style={"height": "4px", "border_radius": "2px", "background": "var(--raised)"},
            ),
            rx.foreach(
                S.approvals,
                lambda user: rx.el.div(icon("check", 13, color="var(--add)"), f"{user} approved", class_name="row", style={"font_size": "12px"}),
            ),
            rx.el.p(
                f"{d['risk_tier']} needs {d['reviewers_needed']} reviewer(s). Your approval merges only when branch protection allows it.",
                style={"margin": "0", **FAINT_12},
            ),
            style={"border_top": "1px solid var(--line)", "padding_top": "12px", "display": "flex", "flex_direction": "column", "gap": "8px"},
        ),
        rx.el.button(icon("check", 14), "Approve and merge", class_name="btn btn-primary", style={"width": "100%"}, on_click=S.approve),
        rx.el.div(
            rx.el.button("Reject", class_name="btn", style={"flex": "1"}, on_click=S.reject),
            rx.el.button("Quarantine", class_name="btn", style={"flex": "1"}, on_click=S.quarantine),
            class_name="row",
        ),
        aria_label="Decision",
        style={
            "flex": "1 1 260px", "border": "1px solid var(--line)", "border_radius": "9px", "background": "var(--panel)",
            "padding": "14px", "display": "flex", "flex_direction": "column", "gap": "12px",
        },
    )  # fmt: skip


def review_page() -> rx.Component:
    return shell(
        "review",
        main_area(
            rx.el.div(
                _queue(),
                rx.cond(S.selected > 0, _detail()),
                style={"display": "flex", "flex_wrap": "wrap", "width": "100%"},
            ),
            display="flex",
            flex_direction="column",
        ),
    )
