"""The local cache of upstream sources: ``.skill-dojo/cache/`` in the curated repo.

The folder ignores itself (``.skill-dojo/.gitignore`` holds ``*``), so git never
sees it and the repo's own ``.gitignore`` stays untouched. It holds:

- ``sources/<id>/<commit>/checkout``: a checkout of the source at that commit,
- ``sources/<id>/<commit>/index.json``: what the source offers there (plugins
  and their parts), what ``browse`` shows,
- ``sources/<id>/current.json``: the commit ``browse`` reads, and the source
  settings it was made for,
- ``repos/<url hash>/<commit>``: checkouts of remote plugin sources.

The cache only saves time. Refs are always resolved against the remote before
anything is vendored, and a checkout is reused only when its ``HEAD`` is exactly
the pinned commit and its tree is unchanged.
"""

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from pydantic import ValidationError

from skill_dojo_core import git
from skill_dojo_core.errors import ExternalToolError
from skill_dojo_core.models import COMMIT_RE, ITEM_ID_RE, Source
from skill_dojo_core.repo_lock import file_lock
from skill_dojo_core.results import Result
from skill_dojo_core.sources import UpstreamPlugin

log = logging.getLogger(__name__)

ROOT = ".skill-dojo"
CACHE = f"{ROOT}/cache"
INDEX = "index.json"
CURRENT = "current.json"
IGNORE_ALL = "*\n"
LATEST = "latest"  # the MCP Registry has no commits
LOCK = ".lock"
# A checkout not used for this long may be pruned; a younger one may be in use.
PRUNE_AFTER = 3600.0


class PartRef(Result):
    """One part a cached plugin offers (``kind/name``)."""

    kind: str
    name: str


class CachedPlugin(Result):
    plugin: UpstreamPlugin
    parts: list[PartRef] | None = None  # None: lives in another repo, not indexed


class SourceIndex(Result):
    source: str
    commit: str
    settings: str
    plugins: list[CachedPlugin] = []


def root(repo: Path) -> Path:
    """``.skill-dojo/cache`` of ``repo``, created with its ignore file."""
    base = repo / ROOT
    if base.is_symlink():
        raise ExternalToolError(f"{ROOT} is a symlink; remove it")
    base.mkdir(exist_ok=True)
    ignore = base / ".gitignore"
    if not ignore.is_file() or ignore.read_text(encoding="utf-8") != IGNORE_ALL:
        ignore.write_text(IGNORE_ALL, encoding="utf-8")
    cache = repo / CACHE
    cache.mkdir(exist_ok=True)
    return cache


def settings_key(source: Source) -> str:
    """What the cached catalog depends on (a change means: fetch again)."""
    data = [source.type.value, source.repository, source.ref, source.marketplace_path]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()[:16]


def _usable(path: Path, commit: str) -> bool:
    """A cached checkout is reused only at exactly ``commit`` and unchanged."""
    if not (path / ".git").is_dir():
        return False
    head = git.run(path, "rev-parse", "--verify", "-q", "HEAD", check=False)
    return head == commit and not git.run(path, "status", "--porcelain", check=False)


def _check_commit(commit: str) -> str:
    if not COMMIT_RE.match(commit):
        raise ExternalToolError(f"'{commit}' is not a full commit SHA")
    return commit


def checkout(
    repo: Path, folder: Path, url: str, commit: str, *, credentials_from: Path
) -> Path:
    """A checkout of ``url`` at ``commit`` in ``folder``, fetched once."""
    _check_commit(commit)
    with file_lock(root(repo) / LOCK, timeout=600.0):
        if _usable(folder, commit):
            log.debug("Cache hit %s", folder.relative_to(repo))
            os.utime(folder)
            return folder
        folder.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder.parent, prefix=".fetch-") as tmp:
            fresh = Path(tmp) / "co"
            git.fetch_commit(url, commit, fresh, credentials_from=credentials_from)
            if folder.exists():
                shutil.rmtree(folder)
            fresh.rename(folder)
    log.debug("Cached %s", folder.relative_to(repo))
    return folder


def source_dir(repo: Path, source_id: str) -> Path:
    if not ITEM_ID_RE.match(source_id):
        raise ExternalToolError(f"'{source_id}' is not a valid source id")
    return root(repo) / "sources" / source_id


def source_checkout(repo: Path, source: Source, url: str, commit: str) -> Path:
    folder = source_dir(repo, source.id) / _check_commit(commit) / "checkout"
    return checkout(repo, folder, url, commit, credentials_from=repo)


def repo_checkout(repo: Path, url: str, commit: str) -> Path:
    """A remote plugin source (another repo) at ``commit``."""
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    folder = root(repo) / "repos" / key / _check_commit(commit)
    return checkout(repo, folder, url, commit, credentials_from=repo)


def write_index(repo: Path, index: SourceIndex) -> None:
    base = source_dir(repo, index.source)
    with file_lock(root(repo) / LOCK, timeout=600.0):
        folder = base / index.commit
        folder.mkdir(parents=True, exist_ok=True)
        (folder / INDEX).write_text(index.model_dump_json(indent=2), "utf-8")
        current = {"commit": index.commit, "settings": index.settings}
        (base / CURRENT).write_text(json.dumps(current), encoding="utf-8")
        _prune(base, keep=index.commit)


def _prune(base: Path, keep: str) -> None:
    """Drop older commits of a source that nothing used for a while (a command
    may still be reading a younger one); they are fetched again when needed."""
    limit = time.time() - PRUNE_AFTER
    for old in base.iterdir():
        if old.name == keep or not old.is_dir() or old.is_symlink():
            continue
        used = max(
            (p.stat().st_mtime for p in (old, old / "checkout") if p.exists()),
            default=0.0,
        )
        if used < limit:
            shutil.rmtree(old)


def read_index(repo: Path, source: Source) -> SourceIndex | None:
    """The cached catalog of ``source``, when it matches its current settings."""
    base = repo / CACHE / "sources" / source.id
    try:
        current = json.loads((base / CURRENT).read_text(encoding="utf-8"))
        commit = str(current["commit"])
        if not (COMMIT_RE.match(commit) or commit == LATEST):
            return None
        if current.get("settings") != settings_key(source):
            return None
        index = SourceIndex.model_validate_json(
            (base / commit / INDEX).read_text(encoding="utf-8")
        )
    except OSError, ValueError, KeyError, TypeError, ValidationError:
        return None
    if index.commit != commit or index.source != source.id:
        return None
    return index


def drop_source(repo: Path, source_id: str) -> None:
    """Forget everything cached for a removed source."""
    base = repo / CACHE / "sources" / source_id
    if ITEM_ID_RE.match(source_id) and base.is_dir() and not base.is_symlink():
        shutil.rmtree(base)
