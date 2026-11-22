"""``marketplace add|update``: copy a curated marketplace into a consumer repo
(git subtree).

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
# Only plain transports: no ext::, fd:: or other remote helpers that run commands.
URL_RE = re.compile(r"^(?:https://|ssh://|file://|git@[A-Za-z0-9.-]+:)[^\s]+$")


class MarketplaceResult(Result):
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


def marketplace_add(
    ctx: Context, url: str, *, ref: str = "main", name: str | None = None
) -> MarketplaceResult:
    """Add the marketplace subtree and its skill links to this consumer repo."""
    return _subtree(ctx, url, ref=ref, name=name, update=False)


def marketplace_update(
    ctx: Context, url: str, *, ref: str = "main", name: str | None = None
) -> MarketplaceResult:
    """Pull the marketplace subtree again, at ``ref`` (e.g. a newer release tag)."""
    return _subtree(ctx, url, ref=ref, name=name, update=True)


def _subtree(
    ctx: Context,
    url: str,
    *,
    ref: str,
    name: str | None,
    update: bool,
) -> MarketplaceResult:
    """Add (or with ``update`` pull) the marketplace subtree and its links."""
    if not URL_RE.match(url):
        raise InvalidInputError(
            f"'{url}' is not an https://, ssh://, git@host: or file:// URL"
        )
    name = name or default_name(url)
    if not NAME_RE.match(name):
        raise InvalidInputError(f"'{name}' is not a valid folder name")
    git.check_ref(ref)
    repo = ctx.repo
    prefix = f".agents/{name}"
    # A consumer repo has no registry/; git's own index lock guards it.
    if git.run(repo, "status", "--porcelain"):
        raise ConflictError("working tree is dirty; commit or stash first")
    exists = (repo / prefix).exists()
    if exists and not update:
        raise ConflictError(f"{prefix} exists; use 'marketplace update'")
    if update and not exists:
        raise ConflictError(f"{prefix} does not exist; use 'marketplace add'")
    links = _links(name)
    for link, target in links.items():
        path = repo / link
        same = path.is_symlink() and str(path.readlink()) == target
        if not same and (path.exists() or path.is_symlink()):
            raise ConflictError(f"{link} exists and is not a link to {target}")
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
        f"chore: marketplace {name} at {ref}",
    )
    created = []
    for link, target in links.items():
        path = repo / link
        if path.is_symlink():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        created.append(link)
    if created:
        git.run(repo, "add", "--", *created)
        git.run(repo, "commit", "-q", "-m", f"chore: link {name} skills for agents")
    ctx.report(f"Marketplace {name} at {ref}")
    log.info("Marketplace %s at %s", name, ref)
    return MarketplaceResult(prefix=prefix, ref=ref, updated=update, links=created)
