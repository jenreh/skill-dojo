"""``promote``: the PR that moves all of staging to main.

Approval facts come from the GitHub API, never from the tool's own actions, so a
candidate merged on github.com counts the same as one merged with
``review approve``. For every candidate PR merged into staging that main's
``approvals.yaml`` does not know yet, the approving reviewers plus the person
who merged are recorded with the exact content (``treeSha256``) at the merge.
Build then stamps ``approved-by``/``approved-at``/``reviewEvidence`` into every
item whose content matches an approval.
"""

import logging
import re
from pathlib import Path

from skill_dojo_core import builder, git
from skill_dojo_core.branches import (
    base_branch,
    candidate_item,
    commit,
    main_branch,
    open_or_update,
    push,
    remote_start,
    view,
)
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, PolicyError, ValidationFailedError
from skill_dojo_core.github import PullRequest
from skill_dojo_core.models import (
    Approval,
    ApprovalsFile,
    Channel,
    ItemKind,
    ItemsFile,
    LockFile,
    RiskTier,
)
from skill_dojo_core.registry import (
    APPROVALS,
    ITEMS,
    LOCK,
    Registry,
    model_at,
    save_yaml_model,
)
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result
from skill_dojo_core.validation import validate_registry

log = logging.getLogger(__name__)

MARKER = "<!-- skill-dojo:promote -->"
# A row of the risk-flag table in a candidate PR body (risk.render).
FLAG_ROW = re.compile(r"^\| `[a-z0-9-]+` \|", re.MULTILINE)


class PolicyBlock(Result):
    item: str
    reason: str


class PromoteResult(Result):
    status: str  # opened | updated | up-to-date
    branch: str
    pull_request: PullRequest | None = None
    approvals: list[Approval] = []
    items: list[str] = []


def approval_of(ctx: Context, pr: PullRequest, staging: str) -> Approval | None:
    """The approval a merged candidate PR stands for, read from git and GitHub."""
    item_id = candidate_item(pr.head)
    if item_id is None or not pr.merge_commit or pr.cross_repository:
        return None
    if not git.is_ancestor(ctx.repo, pr.merge_commit, staging):
        log.info("PR %d is not on %s (reverted or squashed away)", pr.number, staging)
        return None
    lock = model_at(ctx.repo, pr.merge_commit, LOCK, LockFile).items.get(item_id)
    if lock is None:
        return None
    # Only approvals of the final head count; GitHub keeps older ones unless
    # stale approvals are dismissed.
    reviews = [
        r
        for r in ctx.github.reviews(pr.number)
        if r.state == "APPROVED" and (r.commit is None or r.commit == pr.head_oid)
    ]
    people = {r.user for r in reviews if r.user}
    if pr.merged_by:
        people.add(pr.merged_by)
    # The author only counts when nobody else approved or merged: merging one's
    # own candidate is the approval in a one-person repo, but never a second vote.
    independent = people - {pr.author}
    times = [t for t in (*(r.submitted_at for r in reviews), pr.merged_at) if t]
    return Approval(
        item=item_id,
        version=builder.manifest_version_at(ctx.repo, pr.merge_commit, item_id),
        commit=lock.upstream.commit,
        digest=lock.tree_sha256,
        pull_request=pr.url,
        reviewers=sorted(independent or people),
        approved_at=max(times) if times else ctx.now.isoformat(),
        channel=Channel.BETA,
        risk_flags=len(FLAG_ROW.findall(pr.body)),
    )


def collect_approvals(
    ctx: Context, base: str, staging: str, known: set[str]
) -> list[Approval]:
    found = []
    for pr in ctx.github.list_merged_pull_requests(base):
        if pr.url in known:
            continue
        approval = approval_of(ctx, pr, staging)
        if approval is not None:
            found.append(approval)
    return sorted(found, key=lambda a: a.approved_at)


def check_policy(
    reg: Registry, main_lock: LockFile, main_items: ItemsFile
) -> list[PolicyBlock]:
    """What keeps staging out of main (``channel-policy.yaml``)."""
    blocks = []
    policy = reg.policy
    for item in reg.items.items:
        on_main_item = main_items.get(item.id)
        if (
            on_main_item is not None
            and on_main_item.quarantined
            and not item.quarantined
        ):
            blocks.append(
                PolicyBlock(
                    item=item.id,
                    reason="quarantined on main; merge its back-merge PR into staging",
                )
            )
        tier = item.risk_tier or policy.default_risk_tier
        if tier is RiskTier.FORBIDDEN:
            blocks.append(PolicyBlock(item=item.id, reason="risk tier is forbidden"))
        if Channel.STABLE not in item.supported_channels:
            blocks.append(
                PolicyBlock(item=item.id, reason="stable is not a supported channel")
            )
        lock = reg.lock.items.get(item.id)
        if item.kind is ItemKind.LOCAL or lock is None:
            continue
        on_main = main_lock.items.get(item.id)
        if on_main is not None and on_main.tree_sha256 == lock.tree_sha256:
            continue
        approval = reg.approvals.for_digest(item.id, lock.tree_sha256)
        if approval is None:
            blocks.append(
                PolicyBlock(
                    item=item.id,
                    reason="no merged candidate PR approved this content",
                )
            )
            continue
        need = policy.reviewers.get(tier, 1)
        if len(approval.reviewers) < need:
            blocks.append(
                PolicyBlock(
                    item=item.id,
                    reason=f"{tier.value} needs {need} reviewers, "
                    f"{approval.pull_request} has {len(approval.reviewers)}",
                )
            )
    return blocks


def _merge_main(wt: Path, main: str) -> None:
    """Bring main's own commits (stamps, revocations) into the promote branch.

    Conflicting hunks keep staging's side; build regenerates the stamps and
    ``approvals.yaml`` is rewritten below.
    """
    if git.is_ancestor(wt, main, "HEAD"):
        return
    if not git.succeeds(wt, "merge", "-q", "--no-edit", "-X", "ours", main):
        git.run(wt, "merge", "--abort", check=False)
        raise ConflictError(
            f"staging does not merge with {main}; merge the open back-merge PR first"
        )


def _body(approvals: list[Approval], items: list[str]) -> str:
    lines = ["## Promote staging to main", "", "### Changed items", ""]
    lines += [f"- `{i}`" for i in items] or ["- none (approval stamps only)"]
    lines += ["", "### New approvals", ""]
    if approvals:
        lines += ["| Item | Version | Reviewers | PR |", "| --- | --- | --- | --- |"]
        lines += [
            f"| `{a.item}` | {a.version or ''} | {', '.join(a.reviewers)} "
            f"| {a.pull_request} |"
            for a in approvals
        ]
    else:
        lines.append("- none")
    lines += ["", MARKER]
    return "\n".join(lines)


def _changed_items(reg: Registry, main_lock: LockFile) -> list[str]:
    ids = set(reg.lock.items) | set(main_lock.items)
    return sorted(
        i
        for i in ids
        if (reg.lock.items.get(i) is None) != (main_lock.items.get(i) is None)
        or (
            i in reg.lock.items
            and i in main_lock.items
            and reg.lock.items[i].tree_sha256 != main_lock.items[i].tree_sha256
        )
    )


def promote(ctx: Context) -> PromoteResult:
    """Open or update the promote PR; raises ``PolicyError`` when blocked."""
    with repo_lock(ctx.repo):
        return _promote(ctx)


def _promote(ctx: Context) -> PromoteResult:
    admin = Registry.load(ctx.repo)
    base, main = base_branch(admin), main_branch(admin)
    staging = remote_start(ctx.repo, base)
    main_ref = remote_start(ctx.repo, main)
    branch = f"promote/{ctx.now:%Y-%m-%d}"
    main_approvals = model_at(ctx.repo, main_ref, APPROVALS, ApprovalsFile)
    main_lock = model_at(ctx.repo, main_ref, LOCK, LockFile)
    main_items = model_at(ctx.repo, main_ref, ITEMS, ItemsFile)
    known = {a.pull_request for a in main_approvals.approvals}
    new = collect_approvals(ctx, base, staging, known)
    with view(ctx.repo, staging) as wt:
        _merge_main(wt, main_ref)
        reg = Registry.load(wt)
        # Never trust approvals.yaml on staging: only main's and GitHub's.
        merged = {a.pull_request: a for a in [*main_approvals.approvals, *new]}
        reg.approvals.approvals = sorted(
            merged.values(), key=lambda a: (a.approved_at, a.item)
        )
        save_yaml_model(wt, APPROVALS, reg.approvals)
        blocks = check_policy(reg, main_lock, main_items)
        if blocks:
            raise PolicyError(
                "promotion blocked: "
                + "; ".join(f"{b.item}: {b.reason}" for b in blocks)
            )
        builder.apply_build(reg)
        report = validate_registry(Registry.load(wt))
        if report.errors:
            raise ValidationFailedError(
                "promote branch does not validate: "
                + "; ".join(str(e) for e in report.errors[:10])
            )
        items = _changed_items(reg, main_lock)
        tree = commit(wt, "promote: stamp approvals")
        if tree == git.run(wt, "rev-parse", f"{main_ref}^{{tree}}"):
            return PromoteResult(status="up-to-date", branch="")
        push(wt, branch)
    title = f"promote: staging to {main} ({ctx.now:%Y-%m-%d})"
    pr, status = open_or_update(ctx, branch, main, title, _body(new, items))
    ctx.report(f"{status} promote PR {pr.url}")
    log.info("Promote PR %s: %s", status, pr.url)
    return PromoteResult(
        status=status, branch=branch, pull_request=pr, approvals=new, items=items
    )
