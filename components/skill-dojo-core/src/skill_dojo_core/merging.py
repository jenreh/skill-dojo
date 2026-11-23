"""Merging ``origin/<work>`` into the local work branch.

The scheduled sync and the admin both commit to the work branch, and both
touch ``registry/lock.json`` and ``registry/items.yaml``. git sees one text file
and reports a conflict whenever two items' entries sit next to each other. These
files are maps of entries, so they are merged entry by entry: an entry that only
one side changed takes that side. Generated catalogs take either side and are
rebuilt afterwards. Anything else (both sides changed the same item, or the
same plugin file) is a real conflict and stops the merge.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from skill_dojo_core import catalogs, git
from skill_dojo_core.errors import ConflictError
from skill_dojo_core.registry import (
    ITEMS,
    LOCK,
    REGISTRY_DIR,
    SOURCES,
    dump_yaml,
    merge,
    yaml_rt,
)

log = logging.getLogger(__name__)

MISSING = object()
# Registry YAML files that hold one list of entries, and each entry's key.
YAML_LISTS = {
    f"{REGISTRY_DIR}/{ITEMS}": ("items", "id"),
    f"{REGISTRY_DIR}/{SOURCES}": ("sources", "id"),
}
LOCK_PATH = f"{REGISTRY_DIR}/{LOCK}"
REBUILT = frozenset({catalogs.AGENTS_CATALOG, catalogs.CLAUDE_CATALOG})


def merge_maps(
    base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any], what: str
) -> dict[str, Any]:
    """Three-way merge of two maps, entry by entry (ours keeps its order)."""
    merged: dict[str, Any] = {}
    clashes = []
    for key in [*ours, *(k for k in theirs if k not in ours)]:
        b, o, t = (m.get(key, MISSING) for m in (base, ours, theirs))
        if t in (o, b):
            value = o
        elif o == b:
            value = t
        else:
            clashes.append(key)
            continue
        if value is not MISSING:
            merged[key] = value
    if clashes:
        raise ConflictError(
            f"both sides changed {what} entries {', '.join(sorted(clashes))}"
        )
    return merged


def _stage(repo: Path, stage: int, path: str) -> str | None:
    """The file as the merge base (1), ours (2) or theirs (3) has it."""
    if not git.succeeds(repo, "cat-file", "-e", f":{stage}:{path}"):
        return None
    return git.run(repo, "show", f":{stage}:{path}")


def _merge_lock(base: str | None, ours: str, theirs: str) -> str:
    b, o, t = (json.loads(x) if x else {} for x in (base, ours, theirs))
    items = merge_maps(
        b.get("items", {}), o.get("items", {}), t.get("items", {}), "lock"
    )
    merged = {**o, "items": dict(sorted(items.items()))}
    return json.dumps(merged, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _merge_yaml(key: str, match: str) -> Callable[[str | None, str, str], str]:
    def run(base: str | None, ours: str, theirs: str) -> str:
        docs = [yaml_rt().load(x) if x else None for x in (base, ours, theirs)]
        plain = [
            {
                str(e[match]): json.loads(json.dumps(e, default=str))
                for e in (d or {}).get(key) or []
                if isinstance(e, dict) and match in e
            }
            for d in docs
        ]
        merged = merge_maps(plain[0], plain[1], plain[2], key)
        target = docs[1] if docs[1] is not None else {}
        return dump_yaml(merge(target, {**dict(target), key: list(merged.values())}))

    return run


MERGERS: dict[str, Callable[[str | None, str, str], str]] = {
    LOCK_PATH: _merge_lock,
    **{path: _merge_yaml(k, m) for path, (k, m) in YAML_LISTS.items()},
}


def unmerged(repo: Path) -> list[str]:
    out = git.run(repo, "diff", "--name-only", "--diff-filter=U")
    return [p for p in out.splitlines() if p]


def merge_branch(repo: Path, other: str) -> None:
    """Merge ``other`` into ``HEAD``, resolving registry files entry by entry.

    Leaves the merge committed, or aborts it and raises ``ConflictError``.
    """
    if git.succeeds(repo, "merge", "-q", "--no-edit", "--no-verify", other):
        return
    try:
        left = []
        for path in unmerged(repo):
            ours, theirs = _stage(repo, 2, path), _stage(repo, 3, path)
            if path in REBUILT and ours is not None:
                git.run(repo, "checkout", "--ours", "--", path)
            elif path in MERGERS and ours is not None and theirs is not None:
                text = MERGERS[path](_stage(repo, 1, path), ours, theirs)
                (repo / path).write_text(text, encoding="utf-8")
            else:
                left.append(path)
                continue
            git.run(repo, "add", "--", path)
        if left:
            raise ConflictError(
                f"both sides changed {', '.join(left[:10])}; merge {other} by hand"
            )
        git.run(repo, "commit", "-q", "--no-edit", "--no-verify")
        log.info("Merged %s entry by entry", other)
    except ConflictError:
        git.run(repo, "merge", "--abort", check=False)
        raise
