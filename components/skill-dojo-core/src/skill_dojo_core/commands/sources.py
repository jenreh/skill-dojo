"""``source add|list|remove`` and ``browse``."""

import logging
import tempfile
from pathlib import Path

from skill_dojo_core import git, mcp_registry, sources
from skill_dojo_core.branches import base_branch, remote_start
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError, NotFoundError
from skill_dojo_core.models import ItemsFile, LockFile, Source, SourceType
from skill_dojo_core.registry import (
    ITEMS,
    LOCK,
    SOURCES,
    Registry,
    model_at,
    save_yaml_model,
)
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result
from skill_dojo_core.sources import UpstreamPlugin

log = logging.getLogger(__name__)

# Bundle parts from this repo's own plugins use this source id.
LOCAL_SOURCE = "local"


class SourcesResult(Result):
    sources: list[Source]


class BrowseResult(Result):
    source: str
    commit: str
    plugins: list[UpstreamPlugin]
    tracked: dict[str, str] = {}


def tracked_plugins(ctx: Context, source_id: str) -> dict[str, str]:
    """Upstream plugin -> how staging uses it (mirror, bundle part)."""
    start = remote_start(ctx.repo, base_branch(Registry.load(ctx.repo)))
    items = model_at(ctx.repo, start, ITEMS, ItemsFile)
    locks = model_at(ctx.repo, start, LOCK, LockFile).items
    found: dict[str, str] = {}
    for item in items.items:
        if item.source == source_id and item.upstream_plugin:
            lock = locks.get(item.id)
            version = (
                lock.version if lock and lock.version else (item.commit or "")[:12]
            )
            state = "quarantined" if item.quarantined else f"pinned {version}"
            found[item.upstream_plugin] = f"mirror · {state}"
        parts = [p for p in item.parts if p.source == source_id and p.upstream_plugin]
        for part in parts:
            count = sum(1 for p in parts if p.upstream_plugin == part.upstream_plugin)
            found.setdefault(
                str(part.upstream_plugin),
                f"bundle part · {count} {part.kind.replace('_', ' ')}",
            )
    return found


def _save(reg: Registry) -> None:
    save_yaml_model(reg.repo, SOURCES, reg.sources)


def get_source(reg: Registry, source_id: str) -> Source:
    found = next((s for s in reg.sources.sources if s.id == source_id), None)
    if found is None:
        raise NotFoundError(f"no source '{source_id}' in registry/sources.yaml")
    return found


def source_add(
    ctx: Context,
    source_id: str,
    repository: str,
    *,
    kind: SourceType = SourceType.AGENT_PLUGINS_MARKETPLACE,
    ref: str = "main",
    marketplace_path: str | None = None,
    allowlist: list[str] | None = None,
) -> SourcesResult:
    """Add an upstream source to ``registry/sources.yaml``.

    An MCP Registry source takes the registry's base URL as ``repository``.
    """
    if kind is SourceType.MCP_REGISTRY:
        repository = mcp_registry.check_url(repository)
        if marketplace_path is not None:
            raise InvalidInputError("an MCP Registry source has no catalog path")
    else:
        sources.repo_url(repository)
    if marketplace_path is not None:
        sources.safe_path(marketplace_path)
    with repo_lock(ctx.repo):
        reg = Registry.load(ctx.repo)
        if any(s.id == source_id for s in reg.sources.sources):
            raise ConflictError(f"source '{source_id}' already exists")
        if source_id == LOCAL_SOURCE:
            raise InvalidInputError(
                f"'{LOCAL_SOURCE}' is reserved for this repo's own plugins"
            )
        try:
            source = Source(
                id=source_id,
                type=kind,
                repository=repository,
                marketplace_path=marketplace_path,
                ref=ref,
                allowlist=allowlist or [],
            )
        except ValueError as exc:
            raise InvalidInputError(str(exc)) from exc
        reg.sources.sources.append(source)
        _save(reg)
    ctx.report(f"Added source '{source_id}'")
    return SourcesResult(sources=reg.sources.sources)


def source_list(ctx: Context) -> SourcesResult:
    return SourcesResult(sources=Registry.load(ctx.repo).sources.sources)


def source_remove(ctx: Context, source_id: str) -> SourcesResult:
    """Remove a source that no item uses any more."""
    with repo_lock(ctx.repo):
        reg = Registry.load(ctx.repo)
        source = get_source(reg, source_id)
        users = sorted(
            i.id
            for i in reg.items.items
            if i.source == source_id or any(p.source == source_id for p in i.parts)
        )
        if users:
            raise ConflictError(f"source '{source_id}' is used by {', '.join(users)}")
        reg.sources.sources.remove(source)
        _save(reg)
    return SourcesResult(sources=reg.sources.sources)


def checkout_source(ctx: Context, source: Source, dest: Path) -> str:
    """Fetch ``source`` at its ref into ``dest``; returns the commit."""
    url = sources.repo_url(source.repository)
    commit = git.resolve(url, source.ref, ctx.repo)
    git.fetch_commit(url, commit, dest, credentials_from=ctx.repo)
    return commit


def browse_servers(ctx: Context, source: Source, search: str | None) -> BrowseResult:
    """The servers an MCP Registry offers, at their latest version."""
    offered = [
        mcp_registry.offered(entry, source.repository)
        for entry in mcp_registry.list_servers(source.repository, search)
        if not source.allowlist or entry.name in source.allowlist
    ]
    return BrowseResult(
        source=source.id,
        commit="latest",
        plugins=offered,
        tracked=tracked_plugins(ctx, source.id),
    )


def browse(ctx: Context, source_id: str, *, search: str | None = None) -> BrowseResult:
    """List the plugins a source offers at its current ref.

    ``search`` filters the servers of an MCP Registry by name.
    """
    reg = Registry.load(ctx.repo)
    source = get_source(reg, source_id)
    if source.type is SourceType.MCP_REGISTRY:
        return browse_servers(ctx, source, search)
    with tempfile.TemporaryDirectory(prefix="skill-dojo-") as tmp:
        root = Path(tmp) / "src"
        commit = checkout_source(ctx, source, root)
        plugins = [
            sources.describe(p, root) if p.repository == source.repository else p
            for p in sources.list_plugins(source, root, only_allowed=False)
        ]
    return BrowseResult(
        source=source_id,
        commit=commit,
        plugins=plugins,
        tracked=tracked_plugins(ctx, source_id),
    )


def source_allow(ctx: Context, source_id: str, plugin: str) -> SourcesResult:
    """Add ``plugin`` to the allowlist of a source that has one."""
    with repo_lock(ctx.repo):
        reg = Registry.load(ctx.repo)
        source = get_source(reg, source_id)
        if source.allowlist and plugin not in source.allowlist:
            source.allowlist.append(plugin)
            _save(reg)
    ctx.report(f"Allowed '{plugin}' from '{source_id}'")
    return SourcesResult(sources=reg.sources.sources)
