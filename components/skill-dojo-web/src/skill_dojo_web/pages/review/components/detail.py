"""One candidate: facts, risk flags, diff and metadata."""

from typing import Any

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.common import (
    badge,
    diff_line,
    empty,
    labelled,
    mono,
    panel,
    panel_head,
    tone_color,
)
from skill_dojo_web.pages.review.components.decision import decision
from skill_dojo_web.pages.review.state import ReviewState as S


def _flag_row(flag: rx.Var) -> rx.Component:
    tone = flag["tone"].to(str)
    return mn.group(
        mn.theme_icon(
            rx.match(
                tone,
                ("info", rx.icon("info", size=15)),
                rx.icon("triangle-alert", size=15),
            ),
            color=tone_color(tone),
            variant="transparent",
            size="sm",
        ),
        mn.text(flag["detail"], size="sm", flex="1"),
        mono(flag["where"], c="brand"),
        gap="sm",
        px="md",
        py=6,
        wrap="nowrap",
    )


def _diff_file(file: rx.Var) -> rx.Component:
    return mn.stack(
        mn.group(
            rx.icon("file", size=13),
            mono(file["path"]),
            mn.group(
                mono(f"+{file['added']}", c="green"),
                mono(f"−{file['removed']}", c="red"),
                gap=6,
                ml="auto",
            ),
            gap="xs",
            px="md",
            py=6,
            bg="var(--mantine-color-default-hover)",
        ),
        mn.scroll_area(
            rx.foreach(
                file["lines"].to(list[dict[str, Any]]),
                lambda line: diff_line(
                    line["kind"].to(str), line["number"], line["text"]
                ),
            ),
            type="auto",
        ),
        gap=0,
    )


def _metadata() -> rx.Component:
    d = S.detail
    rows = [
        ("Source", d["source"]),
        ("Upstream", d["upstream"]),
        ("Branch", d["head"]),
        ("Tree SHA-256", d["tree_sha256"]),
        ("Risk tier", d["risk_tier"]),
        ("Data classification", d["data_classification"]),
        ("Contents", d["contents"]),
    ]
    return mn.data_list(
        *(
            mn.data_list.item(
                mn.data_list.item_label(label), mn.data_list.item_value(mono(value))
            )
            for label, value in rows
        ),
        orientation="horizontal",
        label_width=160,
        p="md",
    )


def _facts() -> rx.Component:
    d = S.detail
    return panel(
        mn.simple_grid(
            labelled("Version", f"{d['old_version']} → {d['new_version']}"),
            labelled("Upstream commit", f"{d['old_commit']} → {d['new_commit']}"),
            labelled("Tracked ref", d["ref"]),
            labelled("Tree SHA-256", d["tree_sha256"].to(str)[:12]),
            cols={"base": 2, "md": 4},
            spacing="md",
        ),
        p="sm",
    )


def detail() -> rx.Component:
    d = S.detail
    return mn.stack(
        mn.group(
            mn.stack(
                mono(
                    f"{d['source']} / {d['item']} · PR #{d['number']} into staging",
                    c="dimmed",
                ),
                mn.group(
                    mn.title(d["item"], order=2, size="h3"),
                    badge(d["kind"]),
                    badge(d["contents"]),
                    gap="xs",
                ),
                gap=4,
            ),
            mn.button(
                "Open on GitHub",
                left_section=rx.icon("external-link", size=14),
                variant="default",
                on_click=rx.redirect(d["url"].to(str), is_external=True),
            ),
            justify="space-between",
            align="flex-start",
        ),
        _facts(),
        mn.flex(
            mn.stack(
                panel(
                    panel_head(
                        "Risk flags",
                        badge(S.flags.length()),
                        mn.text(
                            "Flags inform. Policy decides.",
                            size="xs",
                            c="dimmed",
                            ml="auto",
                        ),
                    ),
                    mn.divider(),
                    rx.foreach(S.flags, _flag_row),
                    rx.cond(S.flags.length() == 0, empty("No risk flags.")),
                ),
                panel(
                    mn.tabs(
                        mn.tabs.list(
                            mn.tabs.tab(
                                "Diff",
                                value="diff",
                                right_section=badge(f"{S.files.length()} files"),
                            ),
                            mn.tabs.tab("Metadata", value="meta"),
                            mn.group(
                                mono(f"+{S.added}", c="green"),
                                mono(f"−{S.removed}", c="red"),
                                gap=6,
                                ml="auto",
                                px="sm",
                            ),
                        ),
                        mn.tabs.panel(rx.foreach(S.files, _diff_file), value="diff"),
                        mn.tabs.panel(_metadata(), value="meta"),
                        value=S.tab,
                        on_change=S.set_tab,
                    ),
                ),
                flex="999 1 420px",
                miw=0,
                gap="md",
            ),
            decision(),
            gap="md",
            wrap="wrap",
            align="flex-start",
        ),
        gap="md",
    )
