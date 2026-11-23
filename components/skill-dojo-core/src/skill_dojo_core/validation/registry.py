"""Checks that tie ``plugins/`` to ``registry/``: tracking, drift, provenance."""

import json
from collections.abc import Mapping
from pathlib import Path

from skill_dojo_core import hashing, metadata
from skill_dojo_core.builder import (
    CLAUDE_MANIFEST,
    PLUGINS_DIR,
    ROOT_MANIFEST,
    is_generated,
    plugin_dir,
    provenance,
)
from skill_dojo_core.models import Item, ItemLock, RiskTier
from skill_dojo_core.registry import Registry
from skill_dojo_core.validation.report import Collector
from skill_dojo_core.validation.skills import skill_folders

# Fields whose stamped value must equal what lock.json and items.yaml say.
EXTENSION_FIELDS = (
    "registryId",
    "kind",
    "upstreamCommit",
    "sourceDigest",
)
SKILL_FIELDS = (
    "id",
    "kind",
    "source-commit",
    "source-digest",
)


def check_tracking(reg: Registry, rep: Collector) -> None:
    tracked = {item.id for item in reg.items.items}
    root = reg.repo / PLUGINS_DIR
    present = {p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()
    for name in sorted(present - tracked):
        rep.error(
            f"{PLUGINS_DIR}/{name}",
            "not tracked in registry/items.yaml "
            "(run 'skill-dojo plugin new' or 'skill-dojo local add')",
        )
    for name in sorted(tracked - present):
        rep.error("registry/items.yaml", f"item '{name}' has no {plugin_dir(name)}")
    for name in sorted(set(reg.lock.items) - tracked):
        rep.error("registry/lock.json", f"'{name}' is not in registry/items.yaml")
    sources = {s.id for s in reg.sources.sources}
    for item in reg.items.items:
        if item.source and item.source not in sources:
            rep.error(
                "registry/items.yaml",
                f"'{item.id}' uses unknown source '{item.source}'",
            )
        tier = item.risk_tier or reg.policy.default_risk_tier
        if tier is RiskTier.FORBIDDEN:
            rep.error(
                "registry/items.yaml",
                f"'{item.id}' has risk tier forbidden; remove or revoke it",
            )
        classification = item.data_classification
        if classification and classification not in reg.policy.data_classifications:
            rep.error(
                "registry/items.yaml",
                f"'{item.id}' data_classification '{classification}' is not in "
                "registry/channel-policy.yaml",
            )


def current_files(reg: Registry, item: Item, lock: ItemLock) -> dict[str, object]:
    root = reg.repo / plugin_dir(item.id)
    return {
        rel: value
        for rel, value in hashing.hash_tree(root, reg.config.namespace).items()
        if not is_generated(rel, lock)
    }


def check_drift(reg: Registry, item: Item, lock: ItemLock, rep: Collector) -> None:
    current = current_files(reg, item, lock)
    for found in hashing.drift(lock.files, current):  # ty: ignore[invalid-argument-type]
        hint = (
            "run 'skill-dojo build'"
            if item.kind.value == "local"
            else "mirrored content must not be edited by hand"
        )
        rep.error(
            f"{plugin_dir(item.id)}/{found.path}",
            f"drift: {found.change} since lock.json ({hint})",
        )
    if hashing.tree_sha256(lock.files) != lock.tree_sha256:
        rep.error(
            "registry/lock.json", f"'{item.id}' treeSha256 does not match its files"
        )


def _compare(
    name: str,
    stamped: Mapping[str, object],
    expected: Mapping[str, object],
    fields: tuple[str, ...],
    rep: Collector,
) -> None:
    if not stamped:
        rep.error(name, "provenance metadata missing (run 'skill-dojo build')")
        return
    for key in fields:
        if stamped.get(key) != expected.get(key):
            rep.error(
                name,
                f"metadata {key} is {stamped.get(key)!r}, registry says "
                f"{expected.get(key)!r}",
            )


def check_provenance(reg: Registry, item: Item, lock: ItemLock, rep: Collector) -> None:
    root = reg.repo / plugin_dir(item.id)
    ns = reg.config.namespace
    manifest: dict[str, object] = {}
    for rel in (CLAUDE_MANIFEST, ROOT_MANIFEST):
        path = root / rel
        if not path.is_file() or path.is_symlink():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        manifest = manifest or data
        expected = provenance(reg.config, reg.policy, item, lock, data)
        _compare(
            f"{plugin_dir(item.id)}/{rel}",
            metadata.read_extension(path, ns),
            expected.plugin_extension(),
            EXTENSION_FIELDS,
            rep,
        )
    for folder in skill_folders(root):
        skill_md = folder / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            stamped = metadata.read_skill_metadata(skill_md, ns)
        except ValueError:
            continue
        expected = provenance(
            reg.config,
            reg.policy,
            item,
            lock,
            manifest,
            folder.name,
        )
        prefixed = expected.skill_metadata(ns.skill)
        plain = {k[len(ns.skill) :]: v for k, v in prefixed.items()}
        _compare(
            skill_md.relative_to(reg.repo).as_posix(), stamped, plain, SKILL_FIELDS, rep
        )


def check_registry(reg: Registry, rep: Collector) -> None:
    check_tracking(reg, rep)
    for item in reg.items.items:
        if not (reg.repo / plugin_dir(item.id)).is_dir():
            continue
        lock = reg.lock.items.get(item.id)
        if lock is None:
            rep.error(
                "registry/lock.json",
                f"'{item.id}' has no lock entry (run 'skill-dojo lock refresh')",
            )
            continue
        if lock.kind != item.kind:
            rep.error("registry/lock.json", f"'{item.id}' kind differs from items.yaml")
        check_drift(reg, item, lock, rep)
        check_provenance(reg, item, lock, rep)


def plugin_paths(repo: Path) -> list[Path]:
    root = repo / PLUGINS_DIR
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
