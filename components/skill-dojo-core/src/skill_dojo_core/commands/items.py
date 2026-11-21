"""Local items: ``local add`` and ``lock refresh``."""

import logging

from skill_dojo_core import builder, git, hashing
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError, NotFoundError
from skill_dojo_core.models import Item, ItemKind, ItemLock, Upstream
from skill_dojo_core.overlay import Overlay
from skill_dojo_core.registry import Registry
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)


class LocalAddResult(Result):
    item: str
    tree_sha256: str
    changed: list[str]


class LockRefreshResult(Result):
    refreshed: list[str]
    unchanged: list[str]


def _local_lock(reg: Registry, item: Item, exclude: set[str], commit: str) -> ItemLock:
    """A lock entry for a local item: its files as they are now."""
    root = reg.repo / builder.plugin_dir(item.id)
    files = hashing.hash_tree(root, reg.config.namespace, exclude=exclude)
    return ItemLock(
        kind=ItemKind.LOCAL,
        upstream=Upstream(
            repository=reg.config.repository or reg.config.name,
            commit=commit,
            path=builder.plugin_dir(item.id),
        ),
        tree_sha256=hashing.tree_sha256(files),
        files=files,
    )


def _item_id(ctx: Context, plugin_dir: str) -> str:
    path = (ctx.repo / plugin_dir).resolve()
    plugins = (ctx.repo / builder.PLUGINS_DIR).resolve()
    if path.parent != plugins:
        raise InvalidInputError(f"{plugin_dir} must be a folder directly in plugins/")
    if not path.is_dir():
        raise NotFoundError(f"{plugin_dir} does not exist")
    return path.name


def _prepare(reg: Registry, item: Item) -> set[str]:
    """Generate missing manifests and branding before the first lock.

    Returns the paths (inside the plugin) that build generated, so they stay
    out of the lock entry.
    """
    overlay = Overlay(reg.repo)
    builder.PluginBuild(reg, overlay, item).run()
    base = builder.plugin_dir(item.id) + "/"
    created = {
        rel.removeprefix(base)
        for rel in overlay.changes()
        if rel.startswith(base) and not (reg.repo / rel).exists()
    }
    overlay.apply()
    return created


def local_add(
    ctx: Context,
    plugin_dir: str,
    *,
    category: str | None = None,
) -> LocalAddResult:
    """Register a local plugin: item, lock entry, metadata, catalogs."""
    item_id = _item_id(ctx, plugin_dir)
    with repo_lock(ctx.repo):
        reg = Registry.load(ctx.repo)
        if reg.items.get(item_id) is not None:
            raise ConflictError(f"'{item_id}' is already in registry/items.yaml")
        commit = git.head(ctx.repo)
        item = Item(id=item_id, kind=ItemKind.LOCAL, category=category)
        reg.items.items.append(item)
        generated = _prepare(reg, item)
        lock = _local_lock(reg, item, generated, commit)
        reg.lock.items[item_id] = lock
        reg.save_items()
        reg.save_lock()
        changed = sorted({*builder.apply_build(reg), *generated})
    ctx.report(f"Added local item '{item_id}'")
    log.info("Added local item %s", item_id)
    return LocalAddResult(item=item_id, tree_sha256=lock.tree_sha256, changed=changed)


def lock_refresh(ctx: Context, *, item: str | None = None) -> LockRefreshResult:
    """Recompute lock entries of local items after an edit."""
    with repo_lock(ctx.repo):
        reg = Registry.load(ctx.repo)
        if item is not None:
            target = reg.items.get(item)
            if target is None:
                raise NotFoundError(f"no item '{item}' in registry/items.yaml")
            if target.kind is not ItemKind.LOCAL:
                raise InvalidInputError(
                    f"'{item}' is a {target.kind.value}; it changes only through sync"
                )
            targets = [target]
        else:
            targets = [i for i in reg.items.items if i.kind is ItemKind.LOCAL]
        commit = git.head(ctx.repo)
        refreshed, unchanged = [], []
        for target in targets:
            old = reg.lock.items.get(target.id)
            root = ctx.repo / builder.plugin_dir(target.id)
            listed = hashing.list_files(root)
            exclude = {
                rel
                for rel in listed
                if builder.is_generated(rel, old.files if old else None, reg.config)
            }
            new = _local_lock(reg, target, exclude, commit)
            if old is not None and old.tree_sha256 == new.tree_sha256:
                unchanged.append(target.id)
                continue
            reg.lock.items[target.id] = new
            refreshed.append(target.id)
        if refreshed:
            reg.save_lock()
            builder.apply_build(reg)
    ctx.report(f"Refreshed lock entries: {len(refreshed)}")
    return LockRefreshResult(refreshed=refreshed, unchanged=unchanged)
