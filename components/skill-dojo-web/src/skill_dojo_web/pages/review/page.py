"""Review queue page: candidate PRs into staging and the decision on each."""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web.components.shell import shell
from skill_dojo_web.pages.review.components.detail import detail
from skill_dojo_web.pages.review.components.queue import queue
from skill_dojo_web.pages.review.state import ReviewState

ROUTE = "/"
TITLE = "Review queue"
ON_LOAD = ReviewState.load


def page() -> rx.Component:
    return shell(
        "review",
        mn.flex(
            mn.box(queue(), flex="1 1 300px", maw=360),
            mn.box(
                rx.cond(ReviewState.selected > 0, detail()),
                flex="999 1 520px",
                miw=0,
            ),
            gap="lg",
            wrap="wrap",
            align="flex-start",
        ),
    )
