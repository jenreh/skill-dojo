"""``review list|show|approve|reject|quarantine`` of the PRs the tool opened.

Approving submits a GitHub review and merges through the GitHub API, the same as
on github.com. Branch protection is never bypassed: a PR that still waits for a
reviewer or a check is reported as ``waiting``.
"""

import logging

from skill_dojo_core import git
from skill_dojo_core.branches import base_branch, commit_and_push, remote_start, view
from skill_dojo_core.commands.vendor import REF_RE
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError
from skill_dojo_core.github import PullRequest
from skill_dojo_core.registry import Registry
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)

CANDIDATE = "candidate/"
TOOL_PREFIXES = (CANDIDATE, "promote/", "revoke/", "quarantine/")


class ReviewEntry(Result):
    pull_request: PullRequest
    item: str | None = None


class ReviewListResult(Result):
    entries: list[ReviewEntry]


class ReviewShowResult(Result):
    pull_request: PullRequest
    item: str | None = None
    files: list[str]


class ReviewActionResult(Result):
    pull_request: PullRequest
    item: str | None = None
    status: str  # merged | waiting | closed | quarantined
    quarantine: PullRequest | None = None


def candidate_item(head: str) -> str | None:
    """The item of a ``candidate/<item>/<sha>`` branch."""
    parts = head.split("/")
    if len(parts) == 3 and head.startswith(CANDIDATE):  # noqa: PLR2004
        return parts[1]
    return None


def tool_pull_request(ctx: Context, number: int) -> PullRequest:
    """An open PR on a branch the tool made, or a typed error."""
    pr = ctx.github.get_pull_request(number)
    if not pr.head.startswith(TOOL_PREFIXES) or not REF_RE.match(pr.head):
        raise InvalidInputError(f"PR #{number} is not a skill-dojo PR ({pr.head})")
    if pr.state != "OPEN":
        raise ConflictError(f"PR #{number} is {pr.state.lower()}")
    return pr


def review_list(ctx: Context) -> ReviewListResult:
    """Open candidate PRs into staging."""
    base = base_branch(Registry.load(ctx.repo))
    entries = [
        ReviewEntry(pull_request=pr, item=candidate_item(pr.head))
        for pr in ctx.github.list_open_pull_requests(base)
        if pr.head.startswith(CANDIDATE)
    ]
    return ReviewListResult(entries=entries)


def review_show(ctx: Context, number: int) -> ReviewShowResult:
    """The PR with its changed files (``git diff --name-status``)."""
    pr = tool_pull_request(ctx, number)
    for branch in (pr.base, pr.head):
        git.run(
            ctx.repo,
            "fetch",
            "-q",
            "origin",
            f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
        )
    out = git.run(
        ctx.repo,
        "diff",
        "--name-status",
        f"origin/{pr.base}...origin/{pr.head}",
    )
    files = [line for line in out.splitlines() if line]
    return ReviewShowResult(pull_request=pr, item=candidate_item(pr.head), files=files)


def review_approve(ctx: Context, number: int) -> ReviewActionResult:
    """Submit an approving review, then merge (or report ``waiting``)."""
    pr = tool_pull_request(ctx, number)
    # GitHub refuses a review of one's own PR; merging it is the approval then.
    if pr.author != ctx.actor:
        ctx.github.approve(number, "Approved with skill-dojo.")
    merged = ctx.github.merge(number)
    status = "merged" if merged else "waiting"
    ctx.report(f"PR #{number}: {status}")
    log.info("PR %d %s", number, status)
    return ReviewActionResult(
        pull_request=ctx.github.get_pull_request(number),
        item=candidate_item(pr.head),
        status=status,
    )


def review_reject(ctx: Context, number: int, *, reason: str = "") -> ReviewActionResult:
    pr = tool_pull_request(ctx, number)
    ctx.github.close_pull_request(number, reason or "Rejected with skill-dojo.")
    ctx.report(f"Closed PR #{number}")
    return ReviewActionResult(
        pull_request=ctx.github.get_pull_request(number),
        item=candidate_item(pr.head),
        status="closed",
    )


def review_quarantine(
    ctx: Context, number: int, *, reason: str = ""
) -> ReviewActionResult:
    """Close a candidate PR and stop future candidates of its item.

    The flag goes to ``staging`` through its own small PR. An item that is not
    on staging yet has no future candidates, so closing is enough.
    """
    pr = tool_pull_request(ctx, number)
    item_id = candidate_item(pr.head)
    if item_id is None:
        raise InvalidInputError(f"PR #{number} is not a candidate PR")
    ctx.github.close_pull_request(
        number, reason or f"Quarantined '{item_id}' with skill-dojo."
    )
    base = base_branch(Registry.load(ctx.repo))
    branch = f"quarantine/{item_id}"
    with view(ctx.repo, remote_start(ctx.repo, base)) as wt:
        reg = Registry.load(wt)
        item = reg.items.get(item_id)
        if item is None or item.quarantined:
            return ReviewActionResult(
                pull_request=ctx.github.get_pull_request(number),
                item=item_id,
                status="closed",
            )
        item.quarantined = True
        reg.save_items()
        commit_and_push(wt, branch, f"chore: quarantine {item_id}")
    quarantine = ctx.github.find_open_pull_request(branch, base)
    if quarantine is None:
        quarantine = ctx.github.open_pull_request(
            branch,
            base,
            f"quarantine: {item_id}",
            f"Stops candidates of `{item_id}` (closed #{number}).\n\n{reason}".strip(),
        )
    ctx.report(f"Quarantined {item_id}: {quarantine.url}")
    log.info("Quarantined %s", item_id)
    return ReviewActionResult(
        pull_request=ctx.github.get_pull_request(number),
        item=item_id,
        status="quarantined",
        quarantine=quarantine,
    )
