"""Own plugins: ``plugin new``, ``add-parts``, ``remove-parts`` and the parts
half of ``sync``.

A local plugin holds hand-written files and, optionally, parts copied from
upstream plugins (or from this repo's other local plugins). Every command only
changes files on the work branch; ``build`` locks the files and bumps the version.
"""

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from skill_dojo_core import builder, git, jsontext, versions
from skill_dojo_core.branches import editing
from skill_dojo_core.commands.items import register_local
from skill_dojo_core.commands.mirror import ChangeResult, flags_against_main
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError, NotFoundError
from skill_dojo_core.models import Item, ItemKind, Part, PartLock
from skill_dojo_core.parts import (
    Fetcher,
    PartSpec,
    Picked,
    PluginTree,
    check_no_links,
    parse_part,
    spec_of,
)
from skill_dojo_core.registry import Registry
from skill_dojo_core.vendoring import check_item_id, tree_of

log = logging.getLogger(__name__)


@dataclass
class Change:
    """What one parts command asks for."""

    add: list[PartSpec] = field(default_factory=list)
    remove: list[PartSpec] = field(default_factory=list)
    refresh: bool = False


def manifest_text(item_id: str, description: str | None) -> str:
    return jsontext.dump(
        {
            "name": item_id,
            "version": versions.FIRST_VERSION,
            "description": description or f"The {item_id} plugin.",
        }
    )


def create_plugin(
    reg: Registry, item_id: str, description: str | None, category: str | None
) -> Item:
    """``plugins/<id>/.claude-plugin/plugin.json`` plus item and lock entry."""
    check_item_id(item_id)
    root = reg.repo / builder.plugin_dir(item_id)
    if reg.items.get(item_id) is not None or root.exists() or root.is_symlink():
        raise ConflictError(f"'{item_id}' already exists")
    manifest = root / builder.CLAUDE_MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(manifest_text(item_id, description), encoding="utf-8")
    item = Item(id=item_id, kind=ItemKind.LOCAL, category=category)
    head = git.run(reg.repo, "rev-parse", "--verify", "-q", "HEAD", check=False)
    register_local(reg, item, head or "0" * 40)
    reg.save_items()
    reg.save_lock()
    return item


def plugin_new(
    ctx: Context,
    item_id: str,
    *,
    description: str | None = None,
    category: str | None = None,
) -> ChangeResult:
    """A new, empty local plugin at version 0.1.0; add files to it by hand."""
    with editing(ctx):
        reg = Registry.load(ctx.repo)
        create_plugin(reg, item_id, description, category)
        builder.apply_build(Registry.load(ctx.repo))
    ctx.report(f"Created {builder.plugin_dir(item_id)}; add files, then 'build'")
    log.info("Created local plugin %s", item_id)
    return ChangeResult(item=item_id, status="created")


# --- parts -----------------------------------------------------------------------


def _apply(
    item: Item, tree: PluginTree, change: Change, fetcher: Fetcher
) -> dict[tuple[str, str], Picked]:
    """Remove and add parts in the tree; returns the parts fetched now."""
    parts: dict[tuple[str, str], Part] = {(p.kind, p.name): p for p in item.parts}
    for spec in change.remove:
        part = parts.pop(spec.key, None)
        if part is None:
            raise NotFoundError(f"'{item.id}' has no part {spec.kind} '{spec.name}'")
        same_origin = any(
            (p.source, p.upstream_plugin) == (part.source, part.upstream_plugin)
            for p in parts.values()
        )
        tree.remove(part, keep_licenses=same_origin)
    for spec in change.add:
        if spec.key in parts:
            raise ConflictError(f"'{item.id}' already has {spec.kind} '{spec.name}'")
    picked: dict[tuple[str, str], Picked] = {}
    for spec in change.add:
        got = fetcher.part(spec)
        tree.check_free(got)
        picked[spec.key] = got
    if change.refresh:
        for part in parts.values():
            picked[(part.kind, part.name)] = fetcher.part(spec_of(part))
    for key, got in picked.items():
        if key in parts:
            tree.remove(parts[key], keep_licenses=True)
        tree.write(got)
        parts[key] = Part(
            kind=got.spec.kind,
            name=got.spec.name,
            source=got.spec.source,
            upstream_plugin=got.spec.plugin,
            ref=got.upstream.ref,
            commit=got.upstream.commit,
        )
    item.parts = sorted(parts.values(), key=lambda p: (p.kind, p.name))
    return picked


def _part_locks(
    reg: Registry, item: Item, picked: dict[tuple[str, str], Picked]
) -> list[PartLock]:
    old = reg.lock.items.get(item.id)
    old_parts = {(p.kind, p.name): p for p in old.parts} if old else {}
    return [
        picked[key].lock() if key in picked else old_parts[key]
        for key in ((p.kind, p.name) for p in item.parts)
        if key in picked or key in old_parts
    ]


def change_parts(ctx: Context, item: Item, change: Change) -> ChangeResult:
    """Apply ``change`` to a local plugin in the checkout (no lock, no commit)."""
    reg = Registry.load(ctx.repo)
    item = reg.items.get(item.id) or item
    root = ctx.repo / builder.plugin_dir(item.id)
    check_no_links(root)
    lock = reg.lock.items.get(item.id)
    generated = set(lock.generated) if lock else set()
    before = tree_of(root, reg.config.namespace, generated)
    for rel in generated:
        # Build made them from files the parts may change; it makes them again.
        (root / rel).unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="skill-dojo-up-") as tmp:
        fetcher = Fetcher(ctx, {s.id: s for s in reg.sources.sources}, Path(tmp))
        picked = _apply(item, PluginTree(root, generated), change, fetcher)
    if tree_of(root, reg.config.namespace, generated) == before and not (
        change.add or change.remove
    ):
        builder.apply_build(reg)  # puts generated files back
        return ChangeResult(item=item.id, status="up-to-date")
    if lock is not None:
        lock.parts = _part_locks(reg, item, picked)
    reg.items.items = [item if i.id == item.id else i for i in reg.items.items]
    reg.save_items()
    reg.save_lock()
    builder.apply_build(Registry.load(ctx.repo))
    return ChangeResult(
        item=item.id,
        status="updated",
        flags=flags_against_main(Registry.load(ctx.repo), item.id),
    )


def _local_item(reg: Registry, item_id: str) -> Item:
    item = reg.items.get(item_id)
    if item is None:
        raise NotFoundError(
            f"no plugin '{item_id}'; create it with 'plugin new' or '--create'"
        )
    if item.kind is not ItemKind.LOCAL:
        raise InvalidInputError(
            f"'{item_id}' is a {item.kind.value}; parts go into a local plugin"
        )
    return item


def add_parts(  # noqa: PLR0913
    ctx: Context,
    item_id: str,
    parts: list[str],
    *,
    create: bool = False,
    description: str | None = None,
    category: str | None = None,
) -> ChangeResult:
    """Copy parts (``source:plugin/kind/name``) into a local plugin."""
    specs = [parse_part(p) for p in parts]
    if not specs and not create:
        raise InvalidInputError("give at least one part")
    with editing(ctx):
        reg = Registry.load(ctx.repo)
        if create:
            item = create_plugin(reg, item_id, description, category)
        else:
            item = _local_item(reg, item_id)
        result = change_parts(ctx, item, Change(add=specs))
        if create:
            result = result.model_copy(update={"status": "created"})
    ctx.report(f"Added {len(specs)} part(s) to {item_id}")
    return result


def remove_parts(ctx: Context, item_id: str, parts: list[str]) -> ChangeResult:
    """Remove parts (``kind/name``) from a local plugin."""
    specs = [parse_part(p, need_source=False) for p in parts]
    if not specs:
        raise InvalidInputError("give at least one part")
    with editing(ctx):
        item = _local_item(Registry.load(ctx.repo), item_id)
        return change_parts(ctx, item, Change(remove=specs))


def refresh_parts(ctx: Context, item_id: str) -> ChangeResult:
    """Fetch every part again at its source's ref (``sync``; no lock taken)."""
    item = _local_item(Registry.load(ctx.repo), item_id)
    if item.quarantined:
        return ChangeResult(item=item_id, status="quarantined")
    return change_parts(ctx, item, Change(refresh=True))
