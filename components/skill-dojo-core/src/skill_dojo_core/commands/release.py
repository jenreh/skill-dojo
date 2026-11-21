"""``release`` (tag main) and ``revoke`` (hotfix PR into main, back-merge PR).

A release is an annotated tag ``marketplace-vYYYY.MM.DD[.N]`` on main whose
message lists the items added, updated and removed since the previous release.
"""

import logging
import shutil
from pathlib import Path

from skill_dojo_core import builder, git
from skill_dojo_core.branches import (
    base_branch,
    commit_and_push,
    main_branch,
    open_or_update,
    remote_start,
    view,
)
from skill_dojo_core.context import Context
from skill_dojo_core.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ValidationFailedError,
)
from skill_dojo_core.github import PullRequest
from skill_dojo_core.models import ApprovalsFile, Client, ItemsFile, LockFile
from skill_dojo_core.registry import APPROVALS, ITEMS, LOCK, Registry, model_at
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result
from skill_dojo_core.validation import validate_registry

log = logging.getLogger(__name__)

TAG_PREFIX = "marketplace-v"


class ReleaseResult(Result):
    status: str  # created | up-to-date
    tag: str
    commit: str
    previous: str | None = None
    notes: str = ""


class RevokeResult(Result):
    item: str
    action: str  # removed | rolled-back
    branch: str
    pull_request: PullRequest
    back_merge: PullRequest
    affected_clients: list[Client] = []
    unknown_clients: list[Client] = []


def _fetch_tags(repo: Path) -> None:
    git.run(repo, "fetch", "-q", "--tags", "--force", "origin")


def _check_valid(wt: Path, what: str) -> None:
    reg = Registry.load(wt)
    errors = [str(e) for e in validate_registry(reg).errors]
    pending = builder.plan(Registry.load(wt)).changes()
    if pending:
        errors.append(f"build would change {', '.join(pending[:10])}")
    if errors:
        raise ValidationFailedError(f"{what} does not validate: " + "; ".join(errors))


def _versions(repo: Path, ref: str | None) -> dict[str, tuple[str, str]]:
    """item -> (version or short digest, treeSha256) at ``ref``."""
    if ref is None:
        return {}
    lock = model_at(repo, ref, LOCK, LockFile)
    return {
        item_id: (
            builder.manifest_version_at(repo, ref, item_id) or entry.tree_sha256[:12],
            entry.tree_sha256,
        )
        for item_id, entry in lock.items.items()
    }


def _update(old: tuple[str, str], new: tuple[str, str]) -> str:
    if old[0] != new[0]:
        return f"{old[0]} -> {new[0]}"
    return f"{new[0]} (content {old[1][:12]} -> {new[1][:12]})"


def release_notes(repo: Path, previous: str | None, commit: str, tag: str) -> str:
    old, new = _versions(repo, previous), _versions(repo, commit)
    lines = [f"Marketplace release {tag}", ""]
    lines.append(f"Changes since {previous}:" if previous else "First release.")
    sections = {
        "Added": [f"- {i} {new[i][0]}" for i in sorted(set(new) - set(old))],
        "Updated": [
            f"- {i} {_update(old[i], new[i])}"
            for i in sorted(set(new) & set(old))
            if old[i][1] != new[i][1]
        ],
        "Removed": [f"- {i}" for i in sorted(set(old) - set(new))],
    }
    for title, entries in sections.items():
        if entries:
            lines += ["", f"{title}:", *entries]
    return "\n".join(lines) + "\n"


def _previous_tag(repo: Path, commit: str) -> str | None:
    tag = git.run(
        repo,
        "describe",
        "--tags",
        "--abbrev=0",
        f"--match={TAG_PREFIX}*",
        commit,
        check=False,
    )
    return tag or None


def _next_tag(repo: Path, day: str) -> str:
    name, n = f"{TAG_PREFIX}{day}", 1
    while git.ref_exists(repo, f"refs/tags/{name}"):
        n += 1
        name = f"{TAG_PREFIX}{day}.{n}"
    return name


def release(ctx: Context) -> ReleaseResult:
    """Tag ``origin/main`` after checking that it validates."""
    main = main_branch(Registry.load(ctx.repo))
    start = remote_start(ctx.repo, main)
    _fetch_tags(ctx.repo)
    commit = git.run(ctx.repo, "rev-parse", f"{start}^{{commit}}")
    previous = _previous_tag(ctx.repo, commit)
    if previous and git.run(ctx.repo, "rev-parse", f"{previous}^{{commit}}") == commit:
        return ReleaseResult(
            status="up-to-date", tag=previous, commit=commit, previous=previous
        )
    with view(ctx.repo, start) as wt:
        _check_valid(wt, main)
    with repo_lock(ctx.repo):
        tag = _next_tag(ctx.repo, f"{ctx.now:%Y.%m.%d}")
        notes = release_notes(ctx.repo, previous, commit, tag)
        git.run(ctx.repo, "tag", "-a", tag, "-m", notes, commit)
        # If another run pushed this tag first, the push fails and nothing moves.
        git.run(ctx.repo, "push", "-q", "origin", f"refs/tags/{tag}")
    ctx.report(f"Released {tag}")
    log.info("Released %s at %s", tag, commit)
    return ReleaseResult(
        status="created", tag=tag, commit=commit, previous=previous, notes=notes
    )


# --- revoke ------------------------------------------------------------------


def _resolve(repo: Path, ref: str) -> str | None:
    for candidate in (f"refs/tags/{ref}", f"origin/{ref}", ref):
        sha = git.run(
            repo, "rev-parse", "--verify", "-q", f"{candidate}^{{commit}}", check=False
        )
        if sha:
            return sha
    return None


def affected(
    repo: Path, clients: list[Client], item_id: str, kept: str | None
) -> tuple[list[Client], list[Client]]:
    """Clients whose ref holds the item in a content other than ``kept``."""
    hit, unknown = [], []
    for client in clients:
        commit = _resolve(repo, client.ref) if git.is_ref(client.ref) else None
        if commit is None:
            unknown.append(client)
            continue
        entry = model_at(repo, commit, LOCK, LockFile).items.get(item_id)
        if entry is not None and entry.tree_sha256 != kept:
            hit.append(client)
    return hit, unknown


def _roll_back(reg: Registry, wt: Path, item_id: str, commit: str) -> str:
    """Restore ``item_id`` as it is at ``commit``; returns its treeSha256."""
    item = model_at(wt, commit, ITEMS, ItemsFile).get(item_id)
    lock = model_at(wt, commit, LOCK, LockFile).items.get(item_id)
    if item is None or lock is None:
        raise NotFoundError(f"'{item_id}' is not in the registry at {commit[:12]}")
    current = reg.lock.items.get(item_id)
    if current is not None and current.tree_sha256 == lock.tree_sha256:
        raise ConflictError(f"'{item_id}' is already at that content")
    prefix = builder.plugin_dir(item_id)
    shutil.rmtree(wt / prefix, ignore_errors=True)
    git.run(wt, "checkout", commit, "--", prefix)
    item.quarantined = True
    reg.items.items = [i if i.id != item_id else item for i in reg.items.items]
    reg.lock.items[item_id] = lock
    return lock.tree_sha256


def _remove(reg: Registry, wt: Path, item_id: str) -> None:
    shutil.rmtree(wt / builder.plugin_dir(item_id), ignore_errors=True)
    reg.items.items = [i for i in reg.items.items if i.id != item_id]
    reg.lock.items.pop(item_id, None)


def _revoke_body(
    item_id: str, action: str, reason: str, hit: list[Client], unknown: list[Client]
) -> str:
    lines = [f"## Revoke `{item_id}` ({action})", ""]
    if reason:
        lines += [reason, ""]
    lines += ["### Affected clients", ""]
    lines += [f"- {c.name} (`{c.ref}`)" for c in hit] or ["- none"]
    if unknown:
        lines += ["", "Refs not found:", *(f"- {c.name} (`{c.ref}`)" for c in unknown)]
    return "\n".join(lines)


def last_approved(repo: Path, main: str, item_id: str) -> str:
    """The newest release older than main's content of ``item_id`` whose
    content of it has an approval in main's ``approvals.yaml``."""
    current = model_at(repo, main, LOCK, LockFile).items.get(item_id)
    approvals = model_at(repo, main, APPROVALS, ApprovalsFile)
    tags = git.run(
        repo,
        "tag",
        "--list",
        f"{TAG_PREFIX}*",
        "--sort=-creatordate",
        f"--merged={main}",
    ).splitlines()
    trees = []
    for tag in tags:
        entry = model_at(repo, tag, LOCK, LockFile).items.get(item_id)
        trees.append(entry.tree_sha256 if entry else None)
    now = current.tree_sha256 if current else None
    # Only releases from before the current content was first released.
    older = max((i for i, t in enumerate(trees) if t == now), default=-1) + 1
    for tag, tree in list(zip(tags, trees, strict=True))[older:]:
        if tree and tree != now and approvals.for_digest(item_id, tree):
            return git.run(repo, "rev-parse", f"{tag}^{{commit}}")
    raise NotFoundError(f"no earlier approved release of '{item_id}' to roll back to")


def _target(
    ctx: Context, main: str, item_id: str, to: str | None, rollback: bool
) -> str | None:
    if to is not None:
        target = _resolve(ctx.repo, to) if git.is_ref(to) else None
        if target is None:
            raise InvalidInputError(f"'{to}' is not a tag, branch or commit")
        return target
    return last_approved(ctx.repo, main, item_id) if rollback else None


def revoke(
    ctx: Context,
    item_id: str,
    *,
    to: str | None = None,
    rollback: bool = False,
    reason: str = "",
) -> RevokeResult:
    """Hotfix PR into main that removes the item, or rolls it back (to ``to``, or
    with ``rollback`` to its last approved release), plus a back-merge PR of the
    same branch into staging."""
    admin = Registry.load(ctx.repo)
    main, base = main_branch(admin), base_branch(admin)
    start = remote_start(ctx.repo, main)
    _fetch_tags(ctx.repo)
    target = _target(ctx, start, item_id, to, rollback)
    branch = f"revoke/{item_id}"
    with repo_lock(ctx.repo), view(ctx.repo, start) as wt:
        reg = Registry.load(wt)
        if reg.items.get(item_id) is None:
            raise NotFoundError(f"no item '{item_id}' on {main}")
        kept = _roll_back(reg, wt, item_id, target) if target else None
        if target is None:
            _remove(reg, wt, item_id)
        reg.save_items()
        reg.save_lock()
        builder.apply_build(reg)
        _check_valid(wt, branch)
        action = "rolled-back" if target else "removed"
        commit_and_push(wt, branch, f"fix: revoke {item_id} ({action})")
    hit, unknown = affected(ctx.repo, admin.clients.clients, item_id, kept)
    body = _revoke_body(item_id, action, reason, hit, unknown)
    pr, _ = open_or_update(ctx, branch, main, f"revoke: {item_id}", body)
    back, _ = open_or_update(
        ctx,
        branch,
        base,
        f"back-merge: revoke {item_id} into {base}",
        f"Back-merge of {pr.url}, so {base} does not bring `{item_id}` back.",
    )
    ctx.report(f"Revoke PR {pr.url}; back-merge {back.url}")
    log.info("Revoke %s: %s", item_id, pr.url)
    return RevokeResult(
        item=item_id,
        action=action,
        branch=branch,
        pull_request=pr,
        back_merge=back,
        affected_clients=hit,
        unknown_clients=unknown,
    )
