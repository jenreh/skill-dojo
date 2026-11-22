"""``release`` (tag main, GitHub Release) and ``revoke`` (a change on the work branch).

A release is an annotated tag ``marketplace-vYYYY.MM.DD[.N]`` on ``origin/<main>``
whose message lists the items added, updated and removed since the previous
release, plus a GitHub Release with the same notes. It is made by hand after the
work-branch PR was merged.
"""

import logging
import shutil
from pathlib import Path

from skill_dojo_core import builder, git
from skill_dojo_core.branches import (
    commit_work,
    editing,
    main_branch,
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
from skill_dojo_core.models import Client, ItemsFile, LockFile
from skill_dojo_core.registry import ITEMS, LOCK, Registry, model_at
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result
from skill_dojo_core.validation import validate_registry

log = logging.getLogger(__name__)

TAG_PREFIX = "marketplace-v"


class ReleaseResult(Result):
    status: str  # created | published (release of an existing tag) | up-to-date
    tag: str
    commit: str
    previous: str | None = None
    notes: str = ""
    url: str | None = None


class RevokeResult(Result):
    item: str
    action: str  # removed | rolled-back
    commit: str | None = None
    affected_clients: list[Client] = []
    unknown_clients: list[Client] = []


def fetch_tags(repo: Path) -> None:
    git.run(repo, "fetch", "-q", "--tags", "--force", "origin")


def check_valid(wt: Path, what: str) -> None:
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


def previous_tag(repo: Path, commit: str) -> str | None:
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


def release(ctx: Context, *, notes: str | None = None) -> ReleaseResult:
    """Tag ``origin/<main>`` after checking that it validates, and publish a
    GitHub Release. ``notes`` replaces the generated notes (the UI edits them)."""
    main = main_branch(Registry.load(ctx.repo))
    start = remote_start(ctx.repo, main)
    fetch_tags(ctx.repo)
    commit = git.run(ctx.repo, "rev-parse", f"{start}^{{commit}}")
    previous = previous_tag(ctx.repo, commit)
    if previous and git.run(ctx.repo, "rev-parse", f"{previous}^{{commit}}") == commit:
        return _finish_release(ctx, previous, commit)
    with view(ctx.repo, start) as wt:
        check_valid(wt, f"origin/{main}")
    with repo_lock(ctx.repo):
        tag = _next_tag(ctx.repo, f"{ctx.now:%Y.%m.%d}")
        notes = (
            notes.strip() + "\n"
            if notes and notes.strip()
            else release_notes(ctx.repo, previous, commit, tag)
        )
        git.run(ctx.repo, "tag", "-a", tag, "-m", notes, commit)
        # If another run pushed this tag first, the push fails and nothing moves.
        git.run(ctx.repo, "push", "-q", "origin", f"refs/tags/{tag}")
    url = ctx.github.create_release(tag, f"Marketplace {tag}", notes)
    ctx.report(f"Released {tag}")
    log.info("Released %s at %s", tag, commit)
    return ReleaseResult(
        status="created",
        tag=tag,
        commit=commit,
        previous=previous,
        notes=notes,
        url=url,
    )


def _finish_release(ctx: Context, tag: str, commit: str) -> ReleaseResult:
    """Main is already tagged: create its GitHub Release if an earlier run
    pushed the tag but failed to publish the release."""
    url = ctx.github.release_url(tag)
    if url is not None:
        return ReleaseResult(
            status="up-to-date", tag=tag, commit=commit, previous=tag, url=url
        )
    notes = git.run(
        ctx.repo, "for-each-ref", "--format=%(contents)", f"refs/tags/{tag}"
    )
    url = ctx.github.create_release(tag, f"Marketplace {tag}", notes + "\n")
    ctx.report(f"Published the missing GitHub Release of {tag}")
    log.info("Published the missing GitHub Release of %s", tag)
    return ReleaseResult(
        status="published", tag=tag, commit=commit, notes=notes + "\n", url=url
    )


# --- revoke ------------------------------------------------------------------


def resolve(repo: Path, ref: str) -> str | None:
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
        commit = resolve(repo, client.ref) if git.is_ref(client.ref) else None
        if commit is None:
            unknown.append(client)
            continue
        entry = model_at(repo, commit, LOCK, LockFile).items.get(item_id)
        if entry is not None and entry.tree_sha256 != kept:
            hit.append(client)
    return hit, unknown


def _roll_back(reg: Registry, item_id: str, commit: str) -> str:
    """Restore ``item_id`` as it is at ``commit``; returns its treeSha256."""
    repo = reg.repo
    item = model_at(repo, commit, ITEMS, ItemsFile).get(item_id)
    lock = model_at(repo, commit, LOCK, LockFile).items.get(item_id)
    if item is None or lock is None:
        raise NotFoundError(f"'{item_id}' is not in the registry at {commit[:12]}")
    current = reg.lock.items.get(item_id)
    if current is not None and current.tree_sha256 == lock.tree_sha256:
        raise ConflictError(f"'{item_id}' is already at that content")
    prefix = builder.plugin_dir(item_id)
    shutil.rmtree(repo / prefix, ignore_errors=True)
    git.run(repo, "checkout", commit, "--", prefix)
    item.quarantined = True
    reg.items.items = [i if i.id != item_id else item for i in reg.items.items]
    reg.lock.items[item_id] = lock
    return lock.tree_sha256


def _remove(reg: Registry, item_id: str) -> None:
    shutil.rmtree(reg.repo / builder.plugin_dir(item_id), ignore_errors=True)
    reg.items.items = [i for i in reg.items.items if i.id != item_id]
    reg.lock.items.pop(item_id, None)


def revoke(ctx: Context, item_id: str, *, to: str | None = None) -> RevokeResult:
    """Remove the item, or roll it back to its content at ``to`` (a tag or ref)
    and quarantine it, as a commit on the work branch."""
    with editing(ctx):
        fetch_tags(ctx.repo)
        target = None
        if to is not None:
            target = resolve(ctx.repo, to) if git.is_ref(to) else None
            if target is None:
                raise InvalidInputError(f"'{to}' is not a tag, branch or commit")
        reg = Registry.load(ctx.repo)
        if reg.items.get(item_id) is None:
            raise NotFoundError(f"no item '{item_id}' in registry/items.yaml")
        kept = _roll_back(reg, item_id, target) if target else None
        if target is None:
            _remove(reg, item_id)
        reg.save_items()
        reg.save_lock()
        builder.apply_build(Registry.load(ctx.repo))
        action = "rolled-back" if target else "removed"
        commit = commit_work(ctx, f"revoke {item_id} ({action})")
    hit, unknown = affected(ctx.repo, reg.clients.clients, item_id, kept)
    ctx.report(f"Revoked {item_id} ({action}); finish to open the PR")
    log.info("Revoke %s: %s", item_id, action)
    return RevokeResult(
        item=item_id,
        action=action,
        commit=commit,
        affected_clients=hit,
        unknown_clients=unknown,
    )
