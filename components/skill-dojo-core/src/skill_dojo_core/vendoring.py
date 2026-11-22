"""Fetching upstream plugins at a pinned commit and copying them into the repo.

Shared by ``mirror``, parts of local plugins and ``sync``. Checkouts come from
the local cache (``cache.py``); the ref is always resolved against the remote.
"""

import json
import logging
import posixpath
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from skill_dojo_core import (
    cache,
    frontmatter,
    git,
    hashing,
    jsontext,
    mcp_registry,
    sources,
)
from skill_dojo_core.context import Context
from skill_dojo_core.errors import InvalidInputError, NotFoundError
from skill_dojo_core.models import ITEM_ID_RE, Namespace, Source, SourceType
from skill_dojo_core.risk import Tree

log = logging.getLogger(__name__)

LICENSE_NAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "NOTICE",
    "NOTICE.md",
    "COPYING",
)
# Repo plumbing that is not part of a plugin at the repo root (its manifest in
# .claude-plugin/ is still vendored).
SKIPPED_TOP = frozenset({".git", ".github", ".agents", ".claude-plugin", "registry"})


@dataclass(frozen=True)
class Fetched:
    """An upstream plugin checked out at a pinned commit."""

    root: Path
    plugin: sources.UpstreamPlugin
    repository: str
    ref: str
    commit: str


def check_item_id(item_id: str) -> None:
    if not (1 <= len(item_id) <= 64) or not ITEM_ID_RE.match(item_id):
        raise InvalidInputError(f"'{item_id}' is not a valid plugin name")


# --- trees ------------------------------------------------------------------


def unstamp(rel: str, data: bytes, namespace: Namespace) -> bytes:
    """``data`` without the tool's provenance keys (for risk comparison)."""
    name = PurePosixPath(rel).name
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    try:
        if name == "SKILL.md" and frontmatter.split(text) is not None:
            return frontmatter.set_metadata(text, namespace.skill, {}).encode()
        if rel in hashing.MANIFESTS:
            return jsontext.set_extension(text, namespace.plugin, None).encode()
    except ValueError:
        return data
    return data


def tree_of(root: Path, namespace: Namespace, skip: set[str] | None = None) -> Tree:
    files = {}
    for rel in hashing.list_files(root):
        if rel in (skip or set()):
            continue
        path = root / rel
        data = hashing.raw_bytes(path)
        files[rel] = (hashing.file_mode(path), unstamp(rel, data, namespace))
    return files


def tree_at(
    repo: Path, ref: str, prefix: str, namespace: Namespace, skip: set[str]
) -> Tree:
    files = {}
    for path, (mode, data) in git.files_at(repo, ref, prefix).items():
        rel = path.removeprefix(prefix + "/")
        if rel not in skip:
            files[rel] = (mode, unstamp(rel, data, namespace))
    return files


def file_changes(old: Tree, new: Tree) -> dict[str, list[str]]:
    return {
        "added": sorted(set(new) - set(old)),
        "changed": sorted(r for r in new if r in old and old[r] != new[r]),
        "removed": sorted(set(old) - set(new)),
    }


# --- sources ------------------------------------------------------------------


def checkout_source(ctx: Context, source: Source) -> tuple[Path, str]:
    """The source at its current ref (cached checkout); returns (root, commit)."""
    url = sources.repo_url(source.repository)
    commit = git.resolve(url, source.ref, ctx.repo)
    return cache.source_checkout(ctx.repo, source, url, commit), commit


def fetch_server(source: Source, name: str, item_id: str, tmp: Path) -> Fetched:
    """Pin the latest version of MCP server ``name`` and write its wrapper."""
    entry = mcp_registry.get_server(source.repository, name)
    package = mcp_registry.choose_package(entry)
    pinned = mcp_registry.pin(package)
    root = tmp / "mcp"
    for rel, text in mcp_registry.wrapper_files(
        item_id, entry, pinned, package
    ).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    plugin = mcp_registry.offered(entry, source.repository)
    return Fetched(root, plugin, source.repository, entry.version, pinned.pin)


def fetch_plugin(
    ctx: Context, source: Source, name: str, tmp: Path, item_id: str | None = None
) -> Fetched:
    """Check out the source, find ``name`` and follow a remote plugin source.

    From the MCP Registry, the wrapper plugin of server ``name`` (named
    ``item_id``) is generated into ``tmp`` instead.
    """
    if source.allowlist and name not in source.allowlist:
        raise InvalidInputError(f"'{name}' is not in the allowlist of '{source.id}'")
    if source.type is SourceType.MCP_REGISTRY:
        return fetch_server(
            source, name, item_id or mcp_registry.default_item_id(name), tmp
        )
    root, commit = checkout_source(ctx, source)
    offered = {p.name: p for p in sources.list_plugins(source, root)}
    plugin = offered.get(name)
    if plugin is None:
        raise NotFoundError(f"source '{source.id}' offers no plugin '{name}'")
    if plugin.unsupported:
        raise InvalidInputError(f"'{name}' cannot be mirrored: {plugin.unsupported}")
    if plugin.repository == source.repository:
        return Fetched(root, plugin, source.repository, source.ref, commit)
    url = sources.repo_url(plugin.repository)
    local_source = sources.repo_url(source.repository).startswith("file://")
    if url.startswith("file://") and not local_source:
        raise InvalidInputError(
            f"'{name}' points at a local repository; only a local source may"
        )
    ref = plugin.ref or "HEAD"
    remote_commit = git.resolve(url, ref, ctx.repo)
    folder = cache.repo_checkout(ctx.repo, url, remote_commit)
    return Fetched(folder, plugin, plugin.repository, ref, remote_commit)


def upstream_files(fetched: Fetched) -> dict[str, Path]:
    """Plugin-relative path -> source file of everything to vendor."""
    base = (
        fetched.root
        if fetched.plugin.path == "."
        else fetched.root / fetched.plugin.path
    )
    root = fetched.root.resolve()
    current = fetched.root
    for part in PurePosixPath(fetched.plugin.path).parts:
        current = current / part
        if current.is_symlink():
            raise InvalidInputError(f"upstream path {fetched.plugin.path} is a symlink")
    if base.resolve() != root and root not in base.resolve().parents:
        raise InvalidInputError(f"upstream path {fetched.plugin.path} leaves the repo")
    if not base.is_dir():
        raise NotFoundError(f"{fetched.plugin.path} not found upstream")
    files = {}
    for rel in hashing.list_files(base):
        top = PurePosixPath(rel).parts[0]
        if (
            fetched.plugin.path == "."
            and top in SKIPPED_TOP
            and rel not in hashing.MANIFESTS
        ):
            continue
        files[rel] = base / rel
    if fetched.plugin.path != "." and not any(
        PurePosixPath(r).name in LICENSE_NAMES for r in files
    ):
        for name in LICENSE_NAMES:
            if (fetched.root / name).is_file():
                files[f"licenses/{name}"] = fetched.root / name
    return files


def check_representable(item_id: str, base: dict[str, Path]) -> None:
    """Reject plugins that could only be vendored by rewriting their files."""
    manifests = [rel for rel in hashing.MANIFESTS if rel in base]
    if not manifests and not any(r.startswith("skills/") for r in base):
        raise InvalidInputError(f"'{item_id}' has no manifest and no skills")
    for rel in manifests:
        try:
            name = json.loads(base[rel].read_text(encoding="utf-8")).get("name")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise InvalidInputError(f"'{item_id}': unreadable {rel}: {exc}") from exc
        if name not in (None, item_id):
            raise InvalidInputError(
                f"upstream plugin is named '{name}'; mirroring it as '{item_id}' "
                "would rewrite its manifest"
            )
    for rel, path in base.items():
        if not path.is_symlink():
            continue
        target = str(path.readlink())
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
        if target.startswith("/") or resolved == ".." or resolved.startswith("../"):
            raise InvalidInputError(f"'{item_id}': {rel} links outside the plugin")


def vendor_into(dest: Path, files: dict[str, Path]) -> None:
    if dest.is_symlink():
        raise InvalidInputError(f"{dest.name} is a symlink")
    if dest.exists():
        shutil.rmtree(dest)
    for rel, src in sorted(files.items()):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            target.symlink_to(src.readlink())
        else:
            shutil.copy2(src, target)
