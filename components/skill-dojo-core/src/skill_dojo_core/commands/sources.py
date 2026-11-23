"""``source add|list|remove|allow|refresh`` and ``browse`` (from the local cache)."""

import logging
from pathlib import PurePosixPath

from skill_dojo_core import cache, mcp_registry, sources
from skill_dojo_core.branches import commit_work, editing
from skill_dojo_core.cache import CachedPlugin, PartRef, SourceIndex
from skill_dojo_core.context import Context
from skill_dojo_core.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    SkillDojoError,
)
from skill_dojo_core.models import Source, SourceType
from skill_dojo_core.parts import LOCAL_SOURCE, index_parts
from skill_dojo_core.registry import SOURCES, Registry, save_yaml_model
from skill_dojo_core.results import Result
from skill_dojo_core.sources import UpstreamPlugin
from skill_dojo_core.vendoring import Fetched, checkout_source, upstream_files

log = logging.getLogger(__name__)


class SourcesResult(Result):
    sources: list[Source]
    commit: str | None = None


class BrowseResult(Result):
    source: str
    commit: str
    plugins: list[UpstreamPlugin]
    parts: dict[str, list[PartRef]] = {}
    tracked: dict[str, str] = {}
    cached: bool = False


def tracked_plugins(reg: Registry, source_id: str) -> dict[str, str]:
    """Upstream plugin -> how this checkout uses it (mirror, part)."""
    found: dict[str, str] = {}
    for item in reg.items.items:
        if item.source == source_id and item.upstream_plugin:
            lock = reg.lock.items.get(item.id)
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
                f"parts in {item.id} · {count}",
            )
    return found


def _save(reg: Registry) -> None:
    save_yaml_model(reg.repo, SOURCES, reg.sources)


def get_source(reg: Registry, source_id: str) -> Source:
    found = next((s for s in reg.sources.sources if s.id == source_id), None)
    if found is None:
        raise NotFoundError(f"no source '{source_id}' in registry/sources.yaml")
    return found


# --- the cached catalog ---------------------------------------------------------


def _server_index(source: Source) -> SourceIndex:
    plugins = [
        CachedPlugin(
            plugin=mcp_registry.offered(entry, source.repository),
            parts=[
                PartRef(kind="mcp_server", name=mcp_registry.server_key(entry.name))
            ],
        )
        for entry in mcp_registry.list_servers(source.repository)
    ]
    return SourceIndex(
        source=source.id,
        commit=cache.LATEST,
        settings=cache.settings_key(source),
        plugins=plugins,
    )


def index_source(ctx: Context, source: Source) -> SourceIndex:
    """Fetch the source at its ref and cache what it offers (all plugins,
    whatever the allowlist says, with their parts)."""
    if source.type is SourceType.MCP_REGISTRY:
        index = _server_index(source)
        cache.write_index(ctx.repo, index)
        return index
    root, commit = checkout_source(ctx, source)
    every = source.model_copy(update={"allowlist": []})
    found = []
    for plugin in sources.list_plugins(every, root, only_allowed=False):
        parts = None
        if plugin.repository == source.repository and not plugin.unsupported:
            plugin = sources.describe(plugin, root)
            try:
                fetched = Fetched(root, plugin, source.repository, source.ref, commit)
                parts = index_parts(upstream_files(fetched))
            except SkillDojoError as exc:
                log.debug("No part index for %s: %s", plugin.name, exc)
        found.append(CachedPlugin(plugin=plugin, parts=parts))
    index = SourceIndex(
        source=source.id,
        commit=commit,
        settings=cache.settings_key(source),
        plugins=found,
    )
    cache.write_index(ctx.repo, index)
    ctx.report(f"Cached {source.id} at {commit[:12]}")
    return index


def _browse_result(
    reg: Registry, source: Source, index: SourceIndex, cached: bool
) -> BrowseResult:
    allow = set(source.allowlist)
    plugins = [
        c.plugin.model_copy(update={"allowed": not allow or c.plugin.name in allow})
        for c in index.plugins
    ]
    return BrowseResult(
        source=source.id,
        commit=index.commit,
        plugins=sorted(plugins, key=lambda p: p.name),
        parts={c.plugin.name: c.parts for c in index.plugins if c.parts is not None},
        tracked=tracked_plugins(reg, source.id),
        cached=cached,
    )


def browse(
    ctx: Context,
    source_id: str,
    *,
    search: str | None = None,
    refresh: bool = False,
) -> BrowseResult:
    """What a source offers, read from the cache (``refresh`` fetches again).

    ``search`` filters the servers of an MCP Registry by name (always live).
    """
    reg = Registry.load(ctx.repo)
    source = get_source(reg, source_id)
    if source.type is SourceType.MCP_REGISTRY and search:
        offered = [
            mcp_registry.offered(entry, source.repository)
            for entry in mcp_registry.list_servers(source.repository, search)
            if not source.allowlist or entry.name in source.allowlist
        ]
        return BrowseResult(
            source=source.id,
            commit=cache.LATEST,
            plugins=offered,
            tracked=tracked_plugins(reg, source.id),
        )
    index = None if refresh else cache.read_index(ctx.repo, source)
    cached = index is not None
    if index is None:
        index = index_source(ctx, source)
    return _browse_result(reg, source, index, cached)


def refresh_sources(ctx: Context, ids: list[str] | None = None) -> list[str]:
    """Fetch the catalogs again (``source refresh``, ``sync``); returns the ids
    refreshed. A source that fails is logged and skipped."""
    reg = Registry.load(ctx.repo)
    done = []
    for source in reg.sources.sources:
        if ids is not None and source.id not in ids:
            continue
        try:
            index_source(ctx, source)
            done.append(source.id)
        except SkillDojoError as exc:
            log.warning("Could not refresh source %s: %s", source.id, exc)
            ctx.report(f"Could not refresh {source.id}: {exc}")
    return done


def source_refresh(ctx: Context, source_id: str | None = None) -> SourcesResult:
    """Fetch one source's catalog again, or every source's."""
    reg = Registry.load(ctx.repo)
    if source_id is not None:
        index_source(ctx, get_source(reg, source_id))
    else:
        refresh_sources(ctx)
    return SourcesResult(sources=reg.sources.sources)


# --- editing sources.yaml -------------------------------------------------------


def _detect(
    ctx: Context, source_id: str, repository: str, ref: str, path: str | None
) -> SourceType:
    """The source type: from the catalog path if given, else from the upstream."""
    if path is not None:
        parent = PurePosixPath(path).parent.name
        if parent == ".claude-plugin":
            return SourceType.CLAUDE_MARKETPLACE
        return SourceType.AGENT_PLUGINS_MARKETPLACE
    probe = Source(id=source_id, type=SourceType.GIT, repository=repository, ref=ref)
    root, _ = checkout_source(ctx, probe)
    found = sources.detect_type(root)
    ctx.report(f"Detected {found.value} in {repository}")
    return found


def source_add(  # noqa: PLR0913
    ctx: Context,
    source_id: str,
    repository: str,
    *,
    kind: SourceType | None = None,
    ref: str = "main",
    marketplace_path: str | None = None,
    allowlist: list[str] | None = None,
) -> SourcesResult:
    """Add an upstream source on the work branch and cache its catalog.

    ``owner/name`` is stored as its GitHub URL. Without ``kind`` the type is
    read from the upstream: an Agent Plugins catalog, a Claude Code catalog or
    a plain git repo. An MCP Registry source takes the registry's base URL.
    """
    if kind is SourceType.MCP_REGISTRY:
        repository = mcp_registry.check_url(repository)
        if marketplace_path is not None:
            raise InvalidInputError("an MCP Registry source has no catalog path")
    else:
        repository = sources.normalize_repository(repository)
    if marketplace_path is not None:
        sources.safe_path(marketplace_path)
    if source_id == LOCAL_SOURCE:
        raise InvalidInputError(
            f"'{LOCAL_SOURCE}' is reserved for this repo's own plugins"
        )
    with editing(ctx):
        reg = Registry.load(ctx.repo)
        if any(s.id == source_id for s in reg.sources.sources):
            raise ConflictError(f"source '{source_id}' already exists")
        try:
            Source(id=source_id, type=SourceType.GIT, repository=repository)
        except ValueError as exc:
            raise InvalidInputError(str(exc)) from exc
        if kind is None:
            kind = _detect(ctx, source_id, repository, ref, marketplace_path)
        source = Source(
            id=source_id,
            type=kind,
            repository=repository,
            marketplace_path=marketplace_path,
            ref=ref,
            allowlist=allowlist or [],
        )
        if kind is not SourceType.MCP_REGISTRY:
            index_source(ctx, source)
        reg.sources.sources.append(source)
        _save(reg)
        commit = commit_work(ctx, f"source add {source_id}")
    ctx.report(f"Added source '{source_id}'")
    return SourcesResult(sources=reg.sources.sources, commit=commit)


def source_list(ctx: Context) -> SourcesResult:
    return SourcesResult(sources=Registry.load(ctx.repo).sources.sources)


def source_remove(ctx: Context, source_id: str) -> SourcesResult:
    """Remove a source that no item uses any more."""
    with editing(ctx):
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
        commit = commit_work(ctx, f"source remove {source_id}")
    cache.drop_source(ctx.repo, source_id)
    return SourcesResult(sources=reg.sources.sources, commit=commit)


def source_allow(ctx: Context, source_id: str, plugin: str) -> SourcesResult:
    """Add ``plugin`` to the allowlist of a source that has one."""
    with editing(ctx):
        reg = Registry.load(ctx.repo)
        source = get_source(reg, source_id)
        if source.allowlist and plugin not in source.allowlist:
            source.allowlist.append(plugin)
            _save(reg)
        commit = commit_work(ctx, f"source allow {source_id} {plugin}")
    ctx.report(f"Allowed '{plugin}' from '{source_id}'")
    return SourcesResult(sources=reg.sources.sources, commit=commit)
