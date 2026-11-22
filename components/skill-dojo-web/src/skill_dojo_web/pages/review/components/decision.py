"""The decision panel: policy, reviews, approve, reject, quarantine."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_core import RiskTier
from skill_dojo_web.components.common import (
    mono,
    panel,
)
from skill_dojo_web.pages.review.state import ReviewState as S


def decision() -> rx.Component:
    d = S.detail
    return panel(
        mn.stack(
            mn.text("Decision", fw=600),
            mn.select(
                label="Risk tier",
                data=[t.value for t in RiskTier],
                value=S.tier,
                on_change=S.set_tier,
                allow_deselect=False,
            ),
            mn.select(
                label="Data classification",
                data=["public", "internal", "confidential"],
                value=S.classification,
                on_change=S.set_classification,
                allow_deselect=False,
            ),
            mn.fieldset(
                mn.stack(
                    mn.checkbox(
                        label="beta (staging)", checked=S.beta, on_change=S.set_beta
                    ),
                    mn.checkbox(
                        label="stable (main)", checked=S.stable, on_change=S.set_stable
                    ),
                    gap="xs",
                ),
                legend="Channels",
                variant="unstyled",
            ),
            mn.divider(),
            mn.group(
                mn.text("Reviews", size="xs", c="dimmed"),
                mono(f"{S.approved_count} / {d['reviewers_needed']}", ml="auto"),
            ),
            mn.progress(value=S.review_percent, size="sm"),
            rx.foreach(
                S.approvals,
                lambda user: mn.group(
                    rx.icon("check", size=13, color="var(--mantine-color-green-6)"),
                    mn.text(f"{user} approved", size="xs"),
                    gap=6,
                ),
            ),
            mn.text(
                f"{d['risk_tier']} needs {d['reviewers_needed']} reviewer(s). "
                "Your approval merges only when branch protection allows it.",
                size="xs",
                c="dimmed",
            ),
            mn.button(
                "Approve and merge",
                left_section=rx.icon("check", size=14),
                full_width=True,
                loading=S.busy,
                on_click=S.approve,
            ),
            mn.group(
                mn.button("Reject", variant="default", flex="1", on_click=S.reject),
                mn.button(
                    "Quarantine", variant="default", flex="1", on_click=S.quarantine
                ),
                grow=True,
            ),
            gap="sm",
        ),
        p="md",
        flex="1 1 260px",
    )
