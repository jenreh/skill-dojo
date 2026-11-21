"""Throwaway worktrees and tool-made branches on ``origin``.

Every branch the tool pushes is built in a detached worktree, so the admin's
checkout is never switched or touched.
"""

import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from skill_dojo_core import git
from skill_dojo_core.context import Context
from skill_dojo_core.errors import NotFoundError
from skill_dojo_core.github import PullRequest
from skill_dojo_core.models import Channel
from skill_dojo_core.registry import Registry

CANDIDATE = "candidate/"
QUARANTINE = "quarantine/"


def candidate_branch(item_id: str, digest: str) -> str:
    return f"{CANDIDATE}{item_id}/{digest[:12]}"


def candidate_item(head: str) -> str | None:
    """The item of a ``candidate/<item>/<sha>`` branch."""
    parts = head.split("/")
    if len(parts) == 3 and head.startswith(CANDIDATE):  # noqa: PLR2004
        return parts[1]
    return None


def base_branch(reg: Registry) -> str:
    rule = reg.policy.channels.get(Channel.BETA)
    return rule.branch if rule else "staging"


def main_branch(reg: Registry) -> str:
    rule = reg.policy.channels.get(Channel.STABLE)
    return rule.branch if rule else "main"


@contextmanager
def view(repo: Path, start: str) -> Generator[Path]:
    """A throwaway detached worktree of ``repo`` at ``start``."""
    with tempfile.TemporaryDirectory(prefix="skill-dojo-wt-") as tmp:
        path = Path(tmp) / "wt"
        git.run(repo, "worktree", "add", "-q", "--detach", str(path), start)
        try:
            yield path
        finally:
            git.worktree_remove(repo, path)


def remote_start(repo: Path, base: str) -> str:
    """Fetch ``origin/<base>`` and return it as a start point."""
    if git.remote_branch_exists(repo, base):
        git.run(repo, "fetch", "-q", "origin", base)
    start = f"origin/{base}"
    if not git.ref_exists(repo, start):
        raise NotFoundError(
            f"branch '{base}' not found on origin; create it with "
            f"'git push origin main:{base}'"
        )
    return start


def commit(wt: Path, message: str) -> str:
    """Commit everything in the (detached) worktree; returns the tree SHA."""
    git.run(wt, "add", "-A")
    if git.run(wt, "status", "--porcelain"):
        # --no-verify: local hooks never run on untrusted upstream content.
        git.run(wt, "commit", "-q", "--no-verify", "-m", message)
    return git.run(wt, "rev-parse", "HEAD^{tree}")


def push(wt: Path, branch: str) -> bool:
    """Force-push ``HEAD`` unless the branch already holds the same tree."""
    tree = git.run(wt, "rev-parse", "HEAD^{tree}")
    if git.remote_tree(wt, branch) == tree:
        return False
    git.run(wt, "push", "-q", "-f", "origin", f"HEAD:refs/heads/{branch}")
    return True


def commit_and_push(wt: Path, branch: str, message: str) -> bool:
    """Commit the worktree and push it; returns whether it pushed."""
    commit(wt, message)
    return push(wt, branch)


def open_or_update(
    ctx: Context, head: str, base: str, title: str, body: str
) -> tuple[PullRequest, str]:
    """The PR from ``head`` into ``base``, opened or updated."""
    found = ctx.github.find_open_pull_request(head, base)
    if found is None:
        return ctx.github.open_pull_request(head, base, title, body), "opened"
    return ctx.github.update_pull_request(found.number, title, body), "updated"
