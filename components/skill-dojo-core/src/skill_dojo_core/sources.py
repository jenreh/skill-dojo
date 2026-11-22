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
    unsupported: str | None = None
    contents: str | None = None
    license: str | None = None
    allowed: bool = True


GITHUB_HOST = "github.com/"


def normalize_repository(repository: str) -> str:
    """What ``source add`` stores: ``owner/name`` and ``github.com/owner/name``
    become ``https://github.com/owner/name``; URLs and ``git@`` stay as given."""
    text = repository.strip()
    if URL_RE.match(text):
        return text
    name = text.removeprefix(GITHUB_HOST)
    if OWNER_REPO_RE.match(name) and not name.startswith(("-", ".")):
        return f"{GITHUB}{name}"
    raise InvalidInputError(f"'{repository}' is not owner/name or a git URL")


def detect_type(root: Path) -> SourceType:
    """The kind of source a checkout holds: a catalog, else a plain git repo."""
    for kind, rel in DEFAULT_PATHS.items():
        if (root / rel).is_file():
            return kind
    return SourceType.GIT


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


REMOTE_KINDS = frozenset({"github", "url", "git", "git-subdir"})
# Catalog entries that define components inline describe a plugin that exists
# only in the catalog; vendoring it would mean writing files upstream never had.
INLINE_KEYS = frozenset(
    {"commands", "agents", "hooks", "mcpServers", "skills", "lspServers"}
)


def _remote(source: dict[str, Any]) -> tuple[str, str | None, str] | None:
    """(repository, ref, path) of a remote plugin source entry; a sha wins."""
    kind = source.get("source")
    repository = source.get("repo") if kind == "github" else source.get("url")
    if kind not in REMOTE_KINDS or not isinstance(repository, str):
        return None
    ref = source.get("sha") or source.get("ref")
    path = source.get("path") or "."
    return repository, ref if isinstance(ref, str) else None, str(path)


def _entry(
    source: Source, entry: dict[str, Any], plugin_root: str | None
) -> UpstreamPlugin | None:
    name = entry.get("name")
    if not isinstance(name, str):
        return None
    version = entry.get("version")
    description = entry.get("description")
    common: dict[str, Any] = {
        "name": name,
        "version": version if isinstance(version, str) else None,
        "description": description if isinstance(description, str) else None,
    }
    where = entry.get("source")
    inline = sorted(INLINE_KEYS & set(entry))
    if entry.get("strict") is False or inline:
        reason = "defines components in the catalog ({})".format(
            ", ".join(inline) or "strict: false"
        )
        return UpstreamPlugin(
            path=".", repository=source.repository, unsupported=reason, **common
        )
    if isinstance(where, str):
        if plugin_root and not where.startswith(("./", "/")):
            where = f"{plugin_root.rstrip('/')}/{where}"
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
        kind = where.get("source")
        return UpstreamPlugin(
            path=".",
            repository=source.repository,
            unsupported=f"source type '{kind}' cannot be vendored",
            **common,
        )
    return UpstreamPlugin(
        path=".", repository=source.repository, unsupported="no source", **common
    )


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


def describe(plugin: UpstreamPlugin, root: Path) -> UpstreamPlugin:
    """Add contents and license of a plugin that lives in this checkout."""
    base = root if plugin.path == "." else root / plugin.path
    if plugin.unsupported or not base.is_dir() or base.is_symlink():
        return plugin
    paths = [
        p.relative_to(base).as_posix()
        for p in base.rglob("*")
        if p.is_file() and not p.is_symlink() and ".git" not in p.parts
    ]
    servers = 0
    for rel in (".mcp.json", "mcp.json"):
        if (base / rel).is_symlink():
            continue
        try:
            data = json.loads((base / rel).read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, json.JSONDecodeError:
            continue
        found = data.get("mcpServers") if isinstance(data, dict) else None
        servers = len(found) if isinstance(found, dict) else 0
        break
    manifest = _manifest(base) or {}
    license_ = manifest.get("license")
    return plugin.model_copy(
        update={
            "contents": contents_summary(paths, servers),
            "license": license_ if isinstance(license_, str) else None,
        }
    )


def contents_summary(paths: list[str], mcp_servers: int = 0) -> str:
    """``3 skills · 1 MCP · 1 hook`` of a plugin's file list."""
    skills = {
        p.split("/")[1]
        for p in paths
        if p.startswith("skills/") and p.endswith("/SKILL.md")
    }
    agents = [p for p in paths if p.startswith("agents/") and p.endswith(".md")]
    hooks = 1 if any(PurePosixPath(p).name == "hooks.json" for p in paths) else 0
    parts = [
        (len(skills), "skill"),
        (len(agents), "agent"),
        (mcp_servers, "MCP"),
        (hooks, "hook"),
    ]
    text = [
        f"{n} {word}{'s' if n > 1 and word != 'MCP' else ''}" for n, word in parts if n
    ]
    return " · ".join(text) or "no components"


def list_plugins(
    source: Source, root: Path, *, only_allowed: bool = True
) -> list[UpstreamPlugin]:
    """What ``source`` offers, read from its checkout at ``root``.

    With ``only_allowed=False`` plugins outside the allowlist are listed too,
    marked ``allowed=False``.
    """
    if source.type is SourceType.GIT:
        plugins = _git_plugins(source, root)
    elif source.type in DEFAULT_PATHS:
        rel = source.marketplace_path or DEFAULT_PATHS[source.type]
        catalog = _read_catalog(root, rel)
        metadata = catalog.get("metadata")
        plugin_root = metadata.get("pluginRoot") if isinstance(metadata, dict) else None
        plugins = [
            p
            for e in catalog["plugins"]
            if isinstance(e, dict)
            and (
                p := _entry(
                    source, e, plugin_root if isinstance(plugin_root, str) else None
                )
            )
            is not None
        ]
    else:
        raise InvalidInputError(f"source type '{source.type.value}' has no catalog yet")
    if source.allowlist:
        plugins = [
            p.model_copy(update={"allowed": p.name in source.allowlist})
            for p in plugins
            if not only_allowed or p.name in source.allowlist
        ]
    return sorted(plugins, key=lambda p: p.name)
