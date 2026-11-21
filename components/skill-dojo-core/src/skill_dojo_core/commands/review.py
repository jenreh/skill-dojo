"""``review list|show|approve|reject|quarantine`` of the PRs the tool opened.

Approving submits a GitHub review and merges through the GitHub API, the same as
on github.com. Branch protection is never bypassed: a PR that still waits for a
reviewer or a check is reported as ``waiting``.
"""

import logging

from skill_dojo_core import git
from skill_dojo_core.branches import (
    CANDIDATE,
    QUARANTINE,
    base_branch,
    candidate_item,
    commit_and_push,
    open_or_update,
    remote_start,
    view,
)
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError
from skill_dojo_core.github import PullRequest
from skill_dojo_core.registry import Registry
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)

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


def tool_pull_request(ctx: Context, number: int) -> PullRequest:
    """An open PR on a branch the tool made, or a typed error."""
    pr = ctx.github.get_pull_request(number)
    if not pr.head.startswith(TOOL_PREFIXES) or not git.is_ref(pr.head):
        raise InvalidInputError(f"PR #{number} is not a skill-dojo PR ({pr.head})")
    if pr.cross_repository:
        raise InvalidInputError(f"PR #{number} comes from a fork, not from the tool")
    if pr.state != "OPEN":
        raise ConflictError(f"PR #{number} is {pr.state.lower()}")
    return pr


def review_list(ctx: Context) -> ReviewListResult:
    """Open candidate PRs into staging."""
    base = base_branch(Registry.load(ctx.repo))
    entries = [
        ReviewEntry(pull_request=pr, item=candidate_item(pr.head))
        for pr in ctx.github.list_open_pull_requests(base)
        if pr.head.startswith(CANDIDATE) and not pr.cross_repository
    ]
    return ReviewListResult(entries=entries)


def review_show(ctx: Context, number: int) -> ReviewShowResult:
    """The PR with its changed files (``git diff --name-status``)."""
    pr = tool_pull_request(ctx, number)
    base, head = (
        git.fetch_branch(ctx.repo, pr.base),
        git.fetch_branch(ctx.repo, pr.head),
    )
    if pr.head_oid and git.run(ctx.repo, "rev-parse", head) != pr.head_oid:
        raise ConflictError(f"PR #{number} head moved while fetching; try again")
    out = git.run(ctx.repo, "diff", "--name-status", f"{base}...{head}")
    files = [line for line in out.splitlines() if line]
    return ReviewShowResult(pull_request=pr, item=candidate_item(pr.head), files=files)


def review_approve(
    ctx: Context, number: int, *, head: str | None = None
) -> ReviewActionResult:
    """Submit an approving review, then merge (or report ``waiting``).

    ``head`` is the commit the reviewer looked at (``review show``); the merge
    happens only while the PR still points there.
    """
    pr = tool_pull_request(ctx, number)
    if head is not None and pr.head_oid is not None and head != pr.head_oid:
        raise ConflictError(f"PR #{number} moved to {pr.head_oid[:12]}; review again")
    # GitHub refuses a review of one's own PR; merging it is the approval then.
    if pr.author != ctx.actor:
        ctx.github.approve(number, "Approved with skill-dojo.")
    merged = ctx.github.merge(number, head_oid=pr.head_oid)
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
    branch = f"{QUARANTINE}{item_id}"
    with repo_lock(ctx.repo), view(ctx.repo, remote_start(ctx.repo, base)) as wt:
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
    quarantine, _ = open_or_update(
        ctx,
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
