"""Upstream catalogs: what a source offers, and where each plugin lives.

Readers for an Agent Plugins marketplace, a Claude Code marketplace and a plain
git repo. Remote plugin sources inside a catalog (another repo or git URL) are
returned as their own location, so they get pinned to their own commit.
"""

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from skill_dojo_core.errors import InvalidInputError, NotFoundError
from skill_dojo_core.models import Source, SourceType
from skill_dojo_core.results import Result

GITHUB = "https://github.com/"
OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
URL_RE = re.compile(r"^(?:https://|ssh://|file://|git@[A-Za-z0-9.-]+:)\S+$")
DEFAULT_PATHS = {
    SourceType.AGENT_PLUGINS_MARKETPLACE: ".agents/plugins/marketplace.json",
    SourceType.CLAUDE_MARKETPLACE: ".claude-plugin/marketplace.json",
}


class UpstreamPlugin(Result):
    """One plugin a source offers."""

    name: str
    path: str
    repository: str
    ref: str | None = None
    version: str | None = None
    description: str | None = None


def repo_url(repository: str) -> str:
    """``owner/name`` -> GitHub URL; a full git URL stays as it is."""
    if OWNER_REPO_RE.match(repository):
        return f"{GITHUB}{repository}.git"
    if URL_RE.match(repository):
        return repository
    raise InvalidInputError(f"'{repository}' is not owner/name or a git URL")


def safe_path(path: str) -> str:
    """A repo-relative POSIX path without ``..`` (``.`` for the root)."""
    parts = PurePosixPath(path.removeprefix("./")).parts
    if PurePosixPath(path).is_absolute() or ".." in parts:
        raise InvalidInputError(f"plugin path '{path}' leaves the repository")
    return "/".join(parts) or "."


def _read_catalog(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    if not path.is_file():
        raise NotFoundError(f"{rel} not found in the source")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidInputError(f"{rel}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise InvalidInputError(f"{rel}: 'plugins' must be an array")
    return data


def _remote(source: dict[str, Any]) -> tuple[str, str | None, str] | None:
    """(repository, ref, path) of a remote plugin source entry."""
    kind = source.get("source")
    repository = source.get("repo") if kind == "github" else source.get("url")
    if kind not in {"github", "url", "git"} or not isinstance(repository, str):
        return None
    ref = source.get("ref") or source.get("sha")
    path = source.get("path") or "."
    return repository, ref if isinstance(ref, str) else None, str(path)


def _entry(source: Source, entry: dict[str, Any]) -> UpstreamPlugin | None:
    name = entry.get("name")
    if not isinstance(name, str):
        return None
    where = entry.get("source")
    common = {
        "name": name,
        "version": entry.get("version")
        if isinstance(entry.get("version"), str)
        else None,
        "description": entry.get("description")
        if isinstance(entry.get("description"), str)
        else None,
    }
    if isinstance(where, str):
        return UpstreamPlugin(
            path=safe_path(where), repository=source.repository, **common
        )
    if isinstance(where, dict):
        if where.get("source") == "local" and isinstance(where.get("path"), str):
            return UpstreamPlugin(
                path=safe_path(where["path"]), repository=source.repository, **common
            )
        remote = _remote(where)
        if remote is not None:
            repository, ref, path = remote
            repo_url(repository)
            return UpstreamPlugin(
                path=safe_path(path), repository=repository, ref=ref, **common
            )
    return None


def _manifest(plugin: Path) -> dict[str, Any] | None:
    for rel in (".claude-plugin/plugin.json", "plugin.json"):
        try:
            data = json.loads((plugin / rel).read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _git_plugins(source: Source, root: Path) -> list[UpstreamPlugin]:
    """A plain repo: ``plugins/*`` with a manifest, or a root ``skills/`` folder."""
    found = []
    for plugin in sorted((root / "plugins").glob("*")):
        manifest = _manifest(plugin) if plugin.is_dir() else None
        if manifest is not None:
            found.append(
                UpstreamPlugin(
                    name=str(manifest.get("name") or plugin.name),
                    path=f"plugins/{plugin.name}",
                    repository=source.repository,
                    version=manifest.get("version"),
                    description=manifest.get("description"),
                )
            )
    if not found and (root / "skills").is_dir():
        found.append(
            UpstreamPlugin(name=source.id, path=".", repository=source.repository)
        )
    return found


def list_plugins(source: Source, root: Path) -> list[UpstreamPlugin]:
    """What ``source`` offers, read from its checkout at ``root``."""
    if source.type is SourceType.GIT:
        plugins = _git_plugins(source, root)
    elif source.type in DEFAULT_PATHS:
        rel = source.marketplace_path or DEFAULT_PATHS[source.type]
        catalog = _read_catalog(root, rel)
        plugins = [
            p
            for e in catalog["plugins"]
            if isinstance(e, dict) and (p := _entry(source, e)) is not None
        ]
    else:
        raise InvalidInputError(f"source type '{source.type.value}' has no catalog yet")
    if source.allowlist:
        plugins = [p for p in plugins if p.name in source.allowlist]
    return sorted(plugins, key=lambda p: p.name)
