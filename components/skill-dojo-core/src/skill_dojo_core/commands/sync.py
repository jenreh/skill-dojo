"""``sync``: upstream updates as commits on the work branch.

Every source's cached catalog is fetched again first. Then each mirror, and
each local plugin with parts, is fetched at its source's ref; one that moved
becomes one commit. Quarantined items are skipped. Running it twice changes
nothing the second time.
"""

import logging

from skill_dojo_core.branches import commit_work, editing
from skill_dojo_core.commands.mirror import ChangeResult, update_mirror
from skill_dojo_core.commands.plugins import refresh_parts
from skill_dojo_core.commands.sources import refresh_sources
from skill_dojo_core.context import Context
from skill_dojo_core.errors import NotFoundError
from skill_dojo_core.models import Item, ItemKind
from skill_dojo_core.registry import Registry
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)

CHANGED = frozenset({"added", "updated"})


class SyncResult(Result):
    changes: list[ChangeResult]
    refreshed: list[str] = []


def _syncable(item: Item) -> bool:
    return item.kind is ItemKind.MIRROR or bool(item.parts)


def sync(ctx: Context, *, item: str | None = None) -> SyncResult:
    with editing(ctx):
        refreshed = refresh_sources(ctx)
        reg = Registry.load(ctx.repo)
        targets = [i for i in reg.items.items if _syncable(i)]
        if item is not None:
            targets = [i for i in targets if i.id == item]
            if not targets:
                raise NotFoundError(f"no mirror or plugin with parts '{item}'")
        results = []
        for target in targets:
            result = (
                update_mirror(ctx, target.id)
                if target.kind is ItemKind.MIRROR
                else refresh_parts(ctx, target.id)
            )
            if result.status in CHANGED:
                result = result.model_copy(
                    update={"commit": commit_work(ctx, f"sync {target.id}")}
                )
                ctx.report(f"Updated {target.id}")
            results.append(result)
    log.info("Sync: %d item(s) changed", sum(r.commit is not None for r in results))
    return SyncResult(changes=results, refreshed=refreshed)
