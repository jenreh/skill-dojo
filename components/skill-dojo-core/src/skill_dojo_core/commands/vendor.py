"""``vendor``: copy a curated marketplace into a consumer repo (git subtree).

Port of ``add-skills.sh`` from jenreh/agent-skills. Produces::

    .agents/<name>/        git subtree of the marketplace at a ref or tag
    .agents/skills         -> <name>/skills             (Codex / Copilot)
    .claude/skills         -> ../.agents/<name>/skills  (Claude Code)
"""

import logging
import re

from skill_dojo_core import git
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
# Only plain transports: no ext::, fd:: or other remote helpers that run commands.
URL_RE = re.compile(r"^(?:https://|ssh://|file://|git@[A-Za-z0-9.-]+:)[^\s]+$")


class VendorResult(Result):
    prefix: str
    ref: str
    updated: bool
    links: list[str]


def default_name(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


def _links(name: str) -> dict[str, str]:
    return {
        ".agents/skills": f"{name}/skills",
        ".claude/skills": f"../.agents/{name}/skills",
    }


def vendor(
    ctx: Context,
    url: str,
    *,
    ref: str = "main",
    name: str | None = None,
    update: bool = False,
) -> VendorResult:
    """Add (or with ``update`` pull) the marketplace subtree and its links."""
    if not URL_RE.match(url):
        raise InvalidInputError(
            f"'{url}' is not an https://, ssh://, git@host: or file:// URL"
        )
    name = name or default_name(url)
    if not NAME_RE.match(name):
        raise InvalidInputError(f"'{name}' is not a valid folder name")
    if not REF_RE.match(ref) or ".." in ref:
        raise InvalidInputError(f"'{ref}' is not a valid git ref")
    repo = ctx.repo
    prefix = f".agents/{name}"
    # A consumer repo has no registry/; git's own index lock guards it.
    if git.run(repo, "status", "--porcelain", "--untracked-files=no"):
        raise ConflictError("working tree is dirty; commit or stash first")
    exists = (repo / prefix).exists()
    if exists and not update:
        raise ConflictError(f"{prefix} exists; use --update to pull a new ref")
    if update and not exists:
        raise ConflictError(f"{prefix} does not exist; vendor it first")
    action = "pull" if update else "add"
    git.run(
        repo,
        "subtree",
        action,
        "--prefix",
        prefix,
        url,
        ref,
        "--squash",
        "-m",
        f"chore: vendor {name} at {ref}",
    )
    links = []
    for link, target in _links(name).items():
        path = repo / link
        if path.is_symlink() and str(path.readlink()) == target:
            continue
        if path.exists() or path.is_symlink():
            raise ConflictError(f"{link} exists and is not a link to {target}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        links.append(link)
    if links:
        git.run(repo, "add", "--", *links)
        git.run(repo, "commit", "-q", "-m", f"chore: link {name} skills for agents")
    ctx.report(f"Vendored {name} at {ref}")
    log.info("Vendored %s at %s", name, ref)
    return VendorResult(prefix=prefix, ref=ref, updated=update, links=links)
