"""``version`` and the pending versions that ``finish`` and the UI show.

An item is changed when its lock ``treeSha256`` (or file list) differs from
``origin/<main>``, or when it is new or removed. Versions live only in
``plugin.json`` on the branch; there is no extra state file.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from skill_dojo_core import builder, versions
from skill_dojo_core.branches import editing
from skill_dojo_core.context import Context
from skill_dojo_core.errors import InvalidInputError, NotFoundError
from skill_dojo_core.models import ItemKind, ItemLock, LockFile
from skill_dojo_core.overlay import Overlay
from skill_dojo_core.registry import LOCK, Registry, model_at
from skill_dojo_core.results import Result
from skill_dojo_core.versions import Level

log = logging.getLogger(__name__)


class PendingVersion(Result):
    item: str
    kind: str
    status: str  # added | changed | removed
    main_version: str | None = None
    branch_version: str | None = None
    level: str | None = None  # the bump main -> branch (None: not a bump)
    editable: bool = False
    pin: str | None = None


def _changed(old: ItemLock | None, new: ItemLock | None) -> str | None:
    if old is None and new is None:
        return None
    if old is None:
        return "added"
    if new is None:
        return "removed"
    if old.tree_sha256 != new.tree_sha256 or set(old.files) != set(new.files):
        return "changed"
    return None


def pending_between(
    main: LockFile,
    branch: LockFile,
    main_version: Callable[[str], str | None],
    branch_version: Callable[[str], str | None],
) -> list[PendingVersion]:
    found = []
    for item_id in sorted(set(main.items) | set(branch.items)):
        old, new = main.items.get(item_id), branch.items.get(item_id)
        status = _changed(old, new)
        if status is None:
            continue
        entry = new or old
        assert entry is not None  # noqa: S101 (one of them exists)
        before = main_version(item_id) if old else None
        after = branch_version(item_id) if new else None
        found.append(
            PendingVersion(
                item=item_id,
                kind=entry.kind.value,
                status=status,
                main_version=before,
                branch_version=after,
                level=versions.level_between(before, after) if new else None,
                editable=entry.kind is ItemKind.LOCAL and new is not None,
                pin=entry.upstream.commit if entry.kind is ItemKind.MIRROR else None,
            )
        )
    return found


def _main(repo: Path, reg: Registry) -> tuple[str | None, LockFile]:
    base = builder.main_ref(reg)
    return base, model_at(repo, base, LOCK, LockFile) if base else LockFile()


def pending_versions(ctx: Context) -> list[PendingVersion]:
    """Changed items of the checkout against ``origin/<main>``."""
    reg = Registry.load(ctx.repo)
    base, main = _main(ctx.repo, reg)
    return pending_between(
        main,
        reg.lock,
        lambda i: builder.manifest_version_at(ctx.repo, base, i) if base else None,
        lambda i: builder.manifest_version(ctx.repo / builder.plugin_dir(i)),
    )


def pending_at(repo: Path, ref: str) -> list[PendingVersion]:
    """Changed items of a branch that is not checked out."""
    reg = Registry.load(repo)
    base, main = _main(repo, reg)
    return pending_between(
        main,
        model_at(repo, ref, LOCK, LockFile),
        lambda i: builder.manifest_version_at(repo, base, i) if base else None,
        lambda i: builder.manifest_version_at(repo, ref, i),
    )


def write_version(
    reg: Registry, item_id: str, level: Level | None, exact: str | None
) -> str:
    """Set a local plugin's version relative to main, in the checkout."""
    item = reg.items.get(item_id)
    if item is None:
        raise NotFoundError(f"no item '{item_id}' in registry/items.yaml")
    if item.kind is not ItemKind.LOCAL:
        raise InvalidInputError(
            f"'{item_id}' is a mirror; it keeps the upstream version"
        )
    base = builder.main_ref(reg)
    on_main = builder.manifest_version_at(reg.repo, base, item_id) if base else None
    wanted = versions.target(on_main, level, exact)
    overlay = Overlay(reg.repo)
    builder.set_manifest_version(builder.PluginBuild(reg, overlay, item), wanted)
    overlay.apply()
    log.info("Version of %s set to %s", item_id, wanted)
    return wanted


def set_version(
    ctx: Context,
    item_id: str,
    *,
    level: str | None = None,
    exact: str | None = None,
) -> PendingVersion:
    """``version <item> --patch|--minor|--major|--set X.Y.Z`` on the work branch."""
    checked = versions.check_level(level) if level is not None else None
    with editing(ctx):
        reg = Registry.load(ctx.repo)
        wanted = write_version(reg, item_id, checked, exact)
        builder.apply_build(Registry.load(ctx.repo))
    found = {p.item: p for p in pending_versions(ctx)}
    if item_id in found:
        return found[item_id]
    return PendingVersion(
        item=item_id, kind="local", status="changed", branch_version=wanted
    )
