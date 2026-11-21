"""Thin wrappers around the ``git`` command line (argument lists, no shell)."""

import logging
import re
import shutil
import subprocess
from pathlib import Path

from skill_dojo_core.errors import ExternalToolError

log = logging.getLogger(__name__)


def run(cwd: Path, *args: str, check: bool = True) -> str:
    exe = shutil.which("git")
    if exe is None:
        raise ExternalToolError("git is not installed")
    log.debug("Running git %s", args[0] if args else "")
    proc = subprocess.run(  # noqa: S603
        [exe, *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if check and proc.returncode != 0:
        raise ExternalToolError(
            f"git {args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def head(cwd: Path) -> str:
    """The commit ``HEAD`` points at."""
    return run(cwd, "rev-parse", "--verify", "HEAD^{commit}")


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def resolve(url: str, ref: str, cwd: Path) -> str:
    """The commit ``ref`` (branch, tag or full SHA) points at in ``url``."""
    if COMMIT_RE.match(ref):
        return ref
    out = run(cwd, "ls-remote", "--", url, ref, f"refs/tags/{ref}^{{}}")
    found: dict[str, str] = {}
    for line in out.splitlines():
        sha, _, name = line.partition("\t")
        found[name] = sha
    for name in (f"refs/tags/{ref}^{{}}", f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
        if name in found:
            return found[name]
    raise ExternalToolError(f"ref '{ref}' not found in {url}")


def auth_config(repo: Path) -> list[str]:
    """``-c`` options carrying the HTTP auth header ``actions/checkout`` set.

    A fresh fetch repo has no credentials; private upstreams then use the same
    token as the curated repo (design: "Private upstreams use the same token").
    """
    out = run(repo, "config", "--get-regexp", r"^http\..*\.extraheader$", check=False)
    options = []
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        if key and value:
            options += ["-c", f"{key}={value}"]
    return options


def fetch_commit(
    url: str, commit: str, dest: Path, *, credentials_from: Path | None = None
) -> Path:
    """A checkout of exactly ``commit`` of ``url`` in ``dest`` (shallow, partial)."""
    dest.mkdir(parents=True, exist_ok=True)
    auth = auth_config(credentials_from) if credentials_from else []
    run(dest, "init", "-q")
    run(
        dest,
        *auth,
        "fetch",
        "-q",
        "--depth",
        "1",
        "--filter=blob:none",
        "--",
        url,
        commit,
    )
    run(dest, *auth, "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD")
    head_commit = head(dest)
    if head_commit != commit:
        raise ExternalToolError(f"fetched {head_commit}, expected {commit}")
    return dest


def worktree_add(repo: Path, path: Path, branch: str, start: str) -> None:
    run(repo, "worktree", "add", "-q", "-B", branch, str(path), start)


def worktree_remove(repo: Path, path: Path) -> None:
    run(repo, "worktree", "remove", "--force", str(path), check=False)
    run(repo, "worktree", "prune", check=False)


def files_at(repo: Path, ref: str, prefix: str) -> dict[str, tuple[str, bytes]]:
    """``{path: (mode, bytes)}`` of every file under ``prefix`` at ``ref``."""
    out = run(repo, "ls-tree", "-r", "-z", ref, "--", prefix)
    files: dict[str, tuple[str, bytes]] = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        mode, kind, sha = meta.split()
        if kind != "blob":
            continue
        files[path] = (mode, show_blob(repo, sha))
    return files


def show_blob(repo: Path, sha: str) -> bytes:
    exe = shutil.which("git")
    if exe is None:
        raise ExternalToolError("git is not installed")
    proc = subprocess.run(  # noqa: S603
        [exe, "cat-file", "blob", sha], cwd=repo, capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise ExternalToolError(f"git cat-file failed for {sha}")
    return proc.stdout


def remote_branch_exists(repo: Path, branch: str) -> bool:
    """Whether ``origin`` has ``branch`` (network errors raise)."""
    return bool(run(repo, "ls-remote", "--heads", "origin", branch))


def remote_tree(repo: Path, branch: str) -> str | None:
    """Tree SHA of ``origin/<branch>`` after fetching it, or None if absent."""
    if not remote_branch_exists(repo, branch):
        return None
    run(
        repo,
        "fetch",
        "-q",
        "origin",
        f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
    )
    return run(repo, "rev-parse", f"origin/{branch}^{{tree}}")


def ref_exists(repo: Path, ref: str) -> bool:
    return bool(run(repo, "rev-parse", "--verify", "-q", ref, check=False))
