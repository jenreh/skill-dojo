"""``review list|show|approve|reject|quarantine`` of the PRs the tool opened.

Approving submits a GitHub review and merges through the GitHub API, the same as
on github.com. Branch protection is never bypassed: a PR that still waits for a
reviewer or a check is reported as ``waiting``.
"""

import logging
import re

from pydantic import Field

from skill_dojo_core import builder, git
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
from skill_dojo_core.models import Channel, ItemsFile, RiskTier
from skill_dojo_core.registry import ITEMS, Registry, model_at
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result
from skill_dojo_core.risk import FLAG_ROW

log = logging.getLogger(__name__)

TOOL_PREFIXES = (CANDIDATE, "promote/", "revoke/", "quarantine/")


class ReviewEntry(Result):
    pull_request: PullRequest
    item: str | None = None
    kind: str | None = Field(default=None, description="Kind on staging; None if new")
    flags: int = Field(default=0, description="Risk flag rows in the PR body")
    pin: str = Field(default="", description="Upstream pin the candidate holds")


class ReviewListResult(Result):
    entries: list[ReviewEntry]
    quarantined: list[str] = Field(default_factory=list, description="On staging")


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


PIN_RE = re.compile(r"skill-dojo:candidate item=\S+ commit=(\S+)")


def _pin(body: str) -> str:
    """The upstream pin from the candidate marker the tool writes."""
    match = PIN_RE.search(body)
    return match[1] if match else ""


def review_list(ctx: Context) -> ReviewListResult:
    """Open candidate PRs into staging, and the items quarantined there."""
    base = base_branch(Registry.load(ctx.repo))
    staged = model_at(ctx.repo, remote_start(ctx.repo, base), ITEMS, ItemsFile)
    entries = []
    for pr in ctx.github.list_open_pull_requests(base):
        if not pr.head.startswith(CANDIDATE) or pr.cross_repository:
            continue
        item_id = candidate_item(pr.head)
        item = staged.get(item_id) if item_id else None
        entries.append(
            ReviewEntry(
                pull_request=pr,
                item=item_id,
                kind=item.kind.value if item else None,
                flags=len(FLAG_ROW.findall(pr.body)),
                pin=_pin(pr.body),
            )
        )
    quarantined = [i.id for i in staged.items if i.quarantined]
    return ReviewListResult(entries=entries, quarantined=quarantined)


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


def review_policy(
    ctx: Context,
    number: int,
    *,
    risk_tier: RiskTier,
    data_classification: str,
    channels: list[Channel],
) -> ReviewActionResult:
    """Set the risk tier, data classification and channels of a candidate's
    item on its own branch (the PR head moves, so earlier reviews go stale)."""
    pr = tool_pull_request(ctx, number)
    item_id = candidate_item(pr.head)
    if item_id is None:
        raise InvalidInputError(f"PR #{number} is not a candidate PR")
    with repo_lock(ctx.repo), view(ctx.repo, git.fetch_branch(ctx.repo, pr.head)) as wt:
        reg = Registry.load(wt)
        if data_classification not in reg.policy.data_classifications:
            raise InvalidInputError(
                f"'{data_classification}' is not one of "
                + ", ".join(reg.policy.data_classifications)
            )
        item = reg.items.get(item_id)
        if item is None:
            raise InvalidInputError(f"PR #{number} has no '{item_id}' item")
        item.risk_tier = risk_tier
        item.data_classification = data_classification
        item.supported_channels = channels
        reg.save_items()
        builder.apply_build(Registry.load(wt))
        pushed = commit_and_push(wt, pr.head, f"chore: policy of {item_id}")
    ctx.report(f"Policy of {item_id} on PR #{number}")
    return ReviewActionResult(
        pull_request=ctx.github.get_pull_request(number),
        item=item_id,
        status="updated" if pushed else "unchanged",
    )


def review_decide(  # noqa: PLR0913
    ctx: Context,
    number: int,
    *,
    risk_tier: RiskTier,
    data_classification: str,
    channels: list[Channel],
) -> ReviewActionResult:
    """Approve a candidate with this policy: a changed tier, classification or
    channel list is committed first, then the new head is approved and merged."""
    pr = tool_pull_request(ctx, number)
    item_id = candidate_item(pr.head)
    head = git.fetch_branch(ctx.repo, pr.head)
    item = model_at(ctx.repo, head, ITEMS, ItemsFile).get(item_id or "")
    current = (
        (item.risk_tier, item.data_classification, item.supported_channels)
        if item
        else None
    )
    if current != (risk_tier, data_classification, channels):
        review_policy(
            ctx,
            number,
            risk_tier=risk_tier,
            data_classification=data_classification,
            channels=channels,
        )
    fresh = ctx.github.get_pull_request(number)
    return review_approve(ctx, number, head=fresh.head_oid)
