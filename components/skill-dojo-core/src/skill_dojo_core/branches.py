"""The one work branch in the admin's checkout, and read-only worktrees.

Every writing command first puts the checkout on the work branch
(``ensure_work_branch``) and ends with one commit on it (``commit_work``).
``finish`` pushes it and opens or updates the one PR into main. The tool never
force-pushes and never rewrites history the admin pushed.
"""

import logging
import re
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from skill_dojo_core import git, merging
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, NotFoundError, SkillDojoError
from skill_dojo_core.github import PullRequest
from skill_dojo_core.registry import REGISTRY_DIR, Registry
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)

HEX_RE = re.compile(r"^[0-9a-f]*$")
COMMIT_PREFIX = "skill-dojo: "
MAX_DIRTY = 10


class WorkBranch(Result):
    name: str
    status: str  # current | checked-out | created


def short_pin(pin: str) -> str:
    """A git commit cut to 12 characters; other pins (package versions) whole."""
    return pin[:12] if HEX_RE.match(pin) else pin


def work_branch(reg: Registry) -> str:
    return reg.config.work_branch


def main_branch(reg: Registry) -> str:
    return reg.config.main_branch


def current_branch(repo: Path) -> str | None:
    """The checked-out branch, or None on a detached HEAD."""
    name = git.run(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False)
    return name or None


def dirty_files(repo: Path) -> list[str]:
    """Changed and untracked paths (``git status``; ignored files never count)."""
    out = git.run(repo, "status", "--porcelain", "--untracked-files=all")
    return [line[3:] for line in out.splitlines() if line.strip()]


def has_origin(repo: Path) -> bool:
    return git.succeeds(repo, "remote", "get-url", "origin")


def fetch(repo: Path) -> None:
    """Fetch ``origin`` (branches and tags) when there is one."""
    if has_origin(repo):
        git.run(repo, "fetch", "-q", "--prune", "origin")


def _local(repo: Path, branch: str) -> str | None:
    ref = f"refs/heads/{branch}"
    return ref if git.ref_exists(repo, ref) else None


def _remote(repo: Path, branch: str) -> str | None:
    ref = f"refs/remotes/origin/{branch}"
    return ref if git.ref_exists(repo, ref) else None


def main_start(repo: Path, main: str) -> str:
    """``origin/<main>``, which must hold an initialised registry."""
    start = _remote(repo, main)
    if start is None:
        raise NotFoundError(
            f"branch '{main}' not found on origin; push the initialised registry "
            f"first: 'git push origin HEAD:{main}'"
        )
    if git.show_file(repo, start, f"{REGISTRY_DIR}/config.yaml") is None:
        raise NotFoundError(
            f"origin/{main} has no {REGISTRY_DIR}/config.yaml; push the initialised "
            f"registry first: 'git push origin HEAD:{main}'"
        )
    return start


def _local_start(repo: Path, main: str) -> str:
    """Without an ``origin`` (a local trial repo): local main, else HEAD."""
    return _local(repo, main) or git.head(repo)


def remote_start(repo: Path, branch: str) -> str:
    """Fetch ``origin/<branch>`` and return it as a start point."""
    fetch(repo)
    return main_start(repo, branch)


def _check_clean(repo: Path, branch: str) -> None:
    dirty = dirty_files(repo)
    if dirty:
        shown = ", ".join(dirty[:MAX_DIRTY])
        more = f" and {len(dirty) - MAX_DIRTY} more" if len(dirty) > MAX_DIRTY else ""
        raise ConflictError(
            f"the working tree has changes ({shown}{more}); commit or stash them, "
            f"or switch to '{branch}' first"
        )


def _fast_forward(repo: Path, local: str, remote: str | None) -> None:
    """Move the checked-out work branch up to ``origin`` when that is a pure
    fast-forward; a diverged branch is left alone (``finish`` merges it)."""
    if remote and git.is_ancestor(repo, local, remote):
        git.run(repo, "merge", "-q", "--ff-only", remote)


def _restart_if_merged(ctx: Context, work: str, main: str) -> WorkBranch:
    """On the work branch: once main holds all of it (the PR was merged), move
    it up to main, which is the same as a fresh branch. Edits in the working
    tree are carried along; a conflict stops with an error."""
    try:
        fetch(ctx.repo)
    except SkillDojoError as exc:
        log.warning("Could not fetch origin: %s", exc)
        return WorkBranch(name=work, status="current")
    start = _remote(ctx.repo, main)
    if start is None or not git.is_ancestor(ctx.repo, "HEAD", start):
        return WorkBranch(name=work, status="current")
    if git.run(ctx.repo, "rev-parse", "HEAD") == git.run(ctx.repo, "rev-parse", start):
        return WorkBranch(name=work, status="current")
    if not git.succeeds(ctx.repo, "merge", "-q", "--ff-only", start):
        raise ConflictError(
            f"{work} was merged into {main}, but your edits conflict with {main}; "
            "commit or stash them first"
        )
    ctx.report(f"{work} was merged; started again from origin/{main}")
    return WorkBranch(name=work, status="created")


def ensure_work_branch(ctx: Context) -> WorkBranch:
    """Check out the work branch, creating it from ``origin/<main>`` when needed.

    - Already on it: use it as it is.
    - Otherwise the tree must be clean. A local branch with commits that main does
      not have is kept (unpushed work); else an unmerged ``origin/<work>`` is
      checked out; else the branch starts fresh from ``origin/<main>``.
    """
    reg = Registry.load(ctx.repo)
    work, main = work_branch(reg), main_branch(reg)
    git.check_ref(work)
    if current_branch(ctx.repo) == work:
        return _restart_if_merged(ctx, work, main)
    _check_clean(ctx.repo, work)
    fetch(ctx.repo)
    start = (
        main_start(ctx.repo, main)
        if has_origin(ctx.repo)
        else _local_start(ctx.repo, main)
    )
    local, remote = _local(ctx.repo, work), _remote(ctx.repo, work)
    if local and not git.is_ancestor(ctx.repo, local, start):
        git.run(ctx.repo, "checkout", "-q", work)
        _fast_forward(ctx.repo, local, remote)
        status = "checked-out"
    elif remote and not git.is_ancestor(ctx.repo, remote, start):
        git.run(ctx.repo, "checkout", "-q", "-B", work, "--track", remote)
        status = "checked-out"
    else:
        # The old branch (if any) is fully merged: start again from main.
        git.run(ctx.repo, "checkout", "-q", "--no-track", "-B", work, start)
        status = "created"
    ctx.report(f"On work branch {work} ({status})")
    log.info("Work branch %s: %s", work, status)
    return WorkBranch(name=work, status=status)


def commit_work(ctx: Context, message: str) -> str | None:
    """Commit everything on the work branch; returns the commit or None.

    ``--no-verify``: local hooks never run on untrusted upstream content.
    """
    git.run(ctx.repo, "add", "-A")
    if not git.run(ctx.repo, "status", "--porcelain"):
        return None
    git.run(ctx.repo, "commit", "-q", "--no-verify", "-m", f"{COMMIT_PREFIX}{message}")
    commit = git.head(ctx.repo)
    log.info("Committed %s: %s", commit[:12], message)
    return commit


def push_work(ctx: Context, work: str) -> bool:
    """Push the work branch, merging ``origin/<work>`` first when it diverged.

    Never a force-push: commits that sync pushed meanwhile are merged, not lost.
    Returns whether commits from ``origin`` came in.
    """
    remote = _remote(ctx.repo, work)
    merged = bool(remote and not git.is_ancestor(ctx.repo, remote, "HEAD"))
    if remote and merged:
        if git.is_ancestor(ctx.repo, "HEAD", remote):
            git.run(ctx.repo, "merge", "-q", "--ff-only", remote)
        else:
            merging.merge_branch(ctx.repo, remote)
    git.run(ctx.repo, "push", "-q", "-u", "origin", f"HEAD:refs/heads/{work}")
    return merged


@contextmanager
def view(repo: Path, start: str) -> Generator[Path]:
    """A throwaway detached worktree of ``repo`` at ``start`` (read only)."""
    with tempfile.TemporaryDirectory(prefix="skill-dojo-wt-") as tmp:
        path = Path(tmp) / "wt"
        git.run(repo, "worktree", "add", "-q", "--detach", str(path), start)
        try:
            yield path
        finally:
            git.worktree_remove(repo, path)


def open_or_update(
    ctx: Context, head: str, base: str, title: str, body: str
) -> tuple[PullRequest, str]:
    """The PR from ``head`` into ``base``, opened or updated."""
    found = ctx.github.find_open_pull_request(head, base)
    if found is None:
        return ctx.github.open_pull_request(head, base, title, body), "opened"
    return ctx.github.update_pull_request(found.number, title, body), "updated"


@contextmanager
def editing(ctx: Context) -> Generator[WorkBranch]:
    """The repo lock plus the work branch: the frame of every writing command.

    Code inside must not take ``repo_lock`` again (it is not re-entrant).
    """
    with repo_lock(ctx.repo):
        yield ensure_work_branch(ctx)
