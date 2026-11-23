"""``mirror``, the mirror half of ``sync``, and ``flags``.

A mirror is vendored at its pinned commit straight into the work branch: the
plugin files, the item and lock entry and the upstream metadata, as one commit.
"""

import logging
import tempfile
from pathlib import Path

from skill_dojo_core import builder, hashing, mcp_registry, risk
from skill_dojo_core.branches import (
    check_clean_folder,
    commit_work,
    editing,
    short_pin,
)
from skill_dojo_core.commands.sources import get_source
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, NotFoundError
from skill_dojo_core.models import (
    Item,
    ItemKind,
    ItemLock,
    LockFile,
    Source,
    SourceType,
    Upstream,
)
from skill_dojo_core.registry import LOCK, SOURCES, Registry, model_at, save_yaml_model
from skill_dojo_core.results import Result
from skill_dojo_core.risk import RiskFlag
from skill_dojo_core.vendoring import (
    Fetched,
    check_item_id,
    check_representable,
    fetch_plugin,
    tree_at,
    tree_of,
    upstream_files,
    vendor_into,
)

log = logging.getLogger(__name__)


class ChangeResult(Result):
    """What one change on the work branch did."""

    item: str
    status: str  # added | updated | created | removed | rolled-back | up-to-date
    #              | unchanged | quarantined
    pin: str = ""
    commit: str | None = None
    flags: list[RiskFlag] = []


class FlagsResult(Result):
    base: str
    flags: dict[str, list[RiskFlag]]
    markdown: str


def main_tree(reg: Registry, item_id: str) -> risk.Tree:
    """The item's files on ``origin/<main>`` (empty when main lacks it)."""
    base = builder.main_ref(reg)
    if base is None:
        return {}

    lock = model_at(reg.repo, base, LOCK, LockFile).items.get(item_id)
    skip = set(lock.generated) if lock else set()
    return tree_at(
        reg.repo, base, builder.plugin_dir(item_id), reg.config.namespace, skip
    )


def flags_against_main(reg: Registry, item_id: str) -> list[RiskFlag]:
    lock = reg.lock.items.get(item_id)
    root = reg.repo / builder.plugin_dir(item_id)
    skip = set(lock.generated) if lock else set()
    current = tree_of(root, reg.config.namespace, skip) if root.is_dir() else {}
    return risk.compare(main_tree(reg, item_id), current)


def _record(reg: Registry, item_id: str, source: Source, fetched: Fetched) -> None:
    """Write source, item and lock entry, then build."""
    if source not in reg.sources.sources:
        reg.sources.sources = [
            *(s for s in reg.sources.sources if s.id != source.id),
            source,
        ]
        save_yaml_model(reg.repo, SOURCES, reg.sources)
    item = reg.items.get(item_id)
    if item is None:
        item = Item(id=item_id, kind=ItemKind.MIRROR, source=source.id)
        reg.items.items.append(item)
    item.upstream_plugin = fetched.plugin.name
    item.ref = fetched.ref
    item.commit = fetched.commit
    root = reg.repo / builder.plugin_dir(item_id)
    files = hashing.hash_tree(root, reg.config.namespace)
    reg.lock.items[item_id] = ItemLock(
        kind=ItemKind.MIRROR,
        version=fetched.plugin.version or builder.manifest_version(root),
        upstream=Upstream(
            repository=fetched.repository,
            commit=fetched.commit,
            path=fetched.plugin.path,
            ref=fetched.ref,
            plugin=fetched.plugin.name,
        ),
        tree_sha256=hashing.tree_sha256(files),
        files=files,
    )
    reg.save_items()
    reg.save_lock()
    builder.apply_build(reg)


def vendor_mirror(
    ctx: Context, source: Source, name: str, item_id: str
) -> ChangeResult:
    """Fetch ``name`` and write it into the checkout (no lock, no commit)."""
    reg = Registry.load(ctx.repo)
    item = reg.items.get(item_id)
    if item is not None and item.quarantined:
        return ChangeResult(item=item_id, status="quarantined")
    old = reg.lock.items.get(item_id)
    with tempfile.TemporaryDirectory(prefix="skill-dojo-up-") as tmp:
        fetched = fetch_plugin(ctx, source, name, Path(tmp), item_id)
        # A new MCP Registry version may keep the package pin but change
        # arguments or env vars: then the built tree decides.
        if old and (old.upstream.commit, old.upstream.ref) == (
            fetched.commit,
            fetched.ref,
        ):
            return ChangeResult(item=item_id, status="up-to-date", pin=fetched.commit)
        files = upstream_files(fetched)
        check_representable(item_id, files)
        ns = reg.config.namespace
        root = ctx.repo / builder.plugin_dir(item_id)
        check_clean_folder(ctx.repo, builder.plugin_dir(item_id))
        skip = set(old.generated) if old else set()
        before = tree_of(root, ns, skip) if root.is_dir() and old else {}
        vendor_into(root, files)
        if old is not None and tree_of(root, ns) == before:
            builder.apply_build(reg)  # puts the generated files back
            return ChangeResult(item=item_id, status="unchanged", pin=fetched.commit)
        _record(reg, item_id, source, fetched)
    flags = flags_against_main(Registry.load(ctx.repo), item_id)
    return ChangeResult(
        item=item_id,
        status="updated" if old else "added",
        pin=fetched.commit,
        flags=flags,
    )


def mirror(
    ctx: Context, source_id: str, plugin: str, *, item_id: str | None = None
) -> ChangeResult:
    """Mirror one upstream plugin as a commit on the work branch."""
    with editing(ctx):
        reg = Registry.load(ctx.repo)
        source = get_source(reg, source_id)
        if item_id is None and source.type is SourceType.MCP_REGISTRY:
            item_id = mcp_registry.default_item_id(plugin)
        item_id = item_id or plugin
        check_item_id(item_id)
        if reg.items.get(item_id) is not None:
            raise ConflictError(f"'{item_id}' is already tracked; use 'sync'")
        if (ctx.repo / builder.plugin_dir(item_id)).exists():
            raise ConflictError(f"{builder.plugin_dir(item_id)} already exists")
        result = vendor_mirror(ctx, source, plugin, item_id)
        result = result.model_copy(
            update={
                "commit": commit_work(
                    ctx, f"mirror {item_id} {short_pin(result.pin)}".rstrip()
                )
            }
        )
    ctx.report(f"Mirrored {item_id} at {short_pin(result.pin)}")
    log.info("Mirrored %s at %s", item_id, result.pin)
    return result


def update_mirror(ctx: Context, item_id: str) -> ChangeResult:
    """Fetch a tracked mirror at its source's ref (``sync``; no lock taken)."""
    reg = Registry.load(ctx.repo)
    item = reg.items.get(item_id)
    if item is None or item.kind is not ItemKind.MIRROR or item.source is None:
        raise NotFoundError(f"'{item_id}' is not a mirror")
    if item.quarantined:
        return ChangeResult(item=item_id, status="quarantined")
    source = get_source(reg, item.source)
    return vendor_mirror(ctx, source, item.upstream_plugin or item_id, item_id)


def flags(ctx: Context, *, base: str | None = None) -> FlagsResult:
    """Risk flags of every item in the working tree against ``base``
    (default ``origin/<main>``)."""
    reg = Registry.load(ctx.repo)
    base = base or f"origin/{reg.config.main_branch}"
    ns = reg.config.namespace
    found: dict[str, list[RiskFlag]] = {}
    for item in reg.items.items:
        prefix = builder.plugin_dir(item.id)
        lock = reg.lock.items.get(item.id)
        skip = set(lock.generated) if lock else set()
        approved = tree_at(ctx.repo, base, prefix, ns, skip)
        root = ctx.repo / prefix
        current = tree_of(root, ns, skip) if root.is_dir() else {}
        if approved == current:
            continue
        found[item.id] = risk.compare(approved, current)
    sections = [
        f"### `{name}`\n\n{risk.render(items)}" for name, items in found.items()
    ]
    markdown = "\n\n".join(sections) or "No plugin changes."
    return FlagsResult(
        base=base, flags=found, markdown=f"## Risk flags\n\n{markdown}\n"
    )
