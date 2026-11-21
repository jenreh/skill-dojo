"""``sync``: a candidate PR for every mirror and bundle whose upstream moved."""

from skill_dojo_core.branches import base_branch, remote_start
from skill_dojo_core.commands.bundles import refresh_bundle
from skill_dojo_core.commands.candidates import CandidateResult, make_candidate
from skill_dojo_core.context import Context
from skill_dojo_core.errors import NotFoundError
from skill_dojo_core.models import ItemKind, ItemsFile
from skill_dojo_core.registry import ITEMS, Registry, model_at
from skill_dojo_core.results import Result


class SyncResult(Result):
    candidates: list[CandidateResult]


def sync(ctx: Context, *, item: str | None = None) -> SyncResult:
    base = base_branch(Registry.load(ctx.repo))
    staged = model_at(ctx.repo, remote_start(ctx.repo, base), ITEMS, ItemsFile)
    tracked = {
        i.id: i.kind
        for i in staged.items
        if i.kind in {ItemKind.MIRROR, ItemKind.BUNDLE}
    }
    if item is not None:
        if item not in tracked:
            raise NotFoundError(f"no mirror or bundle '{item}' on {base}")
        tracked = {item: tracked[item]}
    results = [
        make_candidate(ctx, None, None, i, new=False)
        if kind is ItemKind.MIRROR
        else refresh_bundle(ctx, i)
        for i, kind in tracked.items()
    ]
    return SyncResult(candidates=results)
