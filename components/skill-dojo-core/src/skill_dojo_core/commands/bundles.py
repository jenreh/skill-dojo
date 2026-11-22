"""Bundles: ``bundle create|add|remove`` and the bundle half of ``sync``.

A bundle is a new plugin made of parts (a skill, an agent or an MCP server)
picked from upstream plugins or from this repo's own local plugins
(source ``local``). Each part is pinned to a commit and recorded in the lock.
Every change is a candidate PR into staging with a semver patch bump.

The bundle is always rebuilt on a fresh staging worktree. A pending (open)
candidate of the same bundle is carried over first, so several ``bundle add``
calls before a merge add up instead of replacing each other.
"""

import json
import logging
import os
import posixpath
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from skill_dojo_core import builder, git, hashing, jsontext, risk
from skill_dojo_core.branches import (
    base_branch,
    candidate_branch,
    commit_and_push,
    remote_start,
    view,
)
from skill_dojo_core.commands.candidates import (
    LICENSE_NAMES,
    MARKER,
    CandidateResult,
    check_item_id,
    fetch_plugin,
    file_changes,
    publish,
    tree_at,
    tree_of,
    upstream_files,
)
from skill_dojo_core.commands.sources import LOCAL_SOURCE
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError, NotFoundError
from skill_dojo_core.models import (
    Item,
    ItemKind,
    ItemLock,
    ItemsFile,
    LockFile,
    Part,
    PartLock,
    Source,
    SourcesFile,
    Upstream,
)
from skill_dojo_core.registry import (
    ITEMS,
    LOCK,
    SOURCES,
    Registry,
    model_at,
    save_yaml_model,
)
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.risk import RiskFlag
from skill_dojo_core.validation import validate_registry

log = logging.getLogger(__name__)

# ``plugin`` may be an MCP Registry server name, which holds one ``/``.
PART_RE = re.compile(
    r"^(?:(?P<source>[a-z0-9][a-z0-9.-]*):"
    r"(?P<plugin>[A-Za-z0-9][A-Za-z0-9.-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?)/)?"
    r"(?P<kind>skill|agent|mcp_server)/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)$"
)
FIRST_VERSION = "0.1.0"
SCHEMA = builder.PLUGIN_SCHEMA
type PartKind = Literal["skill", "agent", "mcp_server"]


@dataclass(frozen=True)
class PartSpec:
    kind: PartKind
    name: str
    source: str | None = None
    plugin: str | None = None

    @property
    def key(self) -> tuple[str, str]:  # noqa: D102
        return (self.kind, self.name)


def parse_part(text: str, *, need_source: bool = True) -> PartSpec:
    """``source:plugin/kind/name`` (``kind/name`` is enough to remove a part)."""
    match = PART_RE.match(text)
    if match is None or ".." in text or (need_source and not match["source"]):
        form = "source:plugin/kind/name" if need_source else "kind/name"
        raise InvalidInputError(
            f"'{text}' is not a part; use {form} with kind skill, agent or mcp_server"
        )
    kind = cast("PartKind", match["kind"])
    return PartSpec(kind, match["name"], match["source"], match["plugin"])


def bump_patch(version: str | None) -> str:
    if version is None:
        return FIRST_VERSION
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise InvalidInputError(f"bundle version '{version}' is not semver")
    major, minor, patch = (int(g) for g in match.groups())
    return f"{major}.{minor}.{patch + 1}"


# --- one part ------------------------------------------------------------------


@dataclass
class Picked:
    """A part fetched at a pinned commit, ready to be written into the bundle."""

    spec: PartSpec
    upstream: Upstream
    path: str
    files: dict[str, Path] = field(default_factory=dict)
    server: dict[str, Any] | None = None
    licenses: dict[str, Path] = field(default_factory=dict)


def plugin_servers(files: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    """The first MCP config (file, servers) of a plugin."""
    for rel in (builder.CLAUDE_MCP, builder.ROOT_MCP, *hashing.MANIFESTS):
        if rel not in files:
            continue
        try:
            data = json.loads(files[rel].read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise InvalidInputError(f"unreadable upstream {rel}: {exc}") from exc
        servers = data.get("mcpServers") if isinstance(data, dict) else None
        if isinstance(servers, dict) and servers:
            return rel, servers
    return "", {}


def _license(files: dict[str, Path]) -> str | None:
    """The ``license`` a plugin's manifest declares."""
    for rel in (builder.ROOT_MANIFEST, builder.CLAUDE_MANIFEST):
        if rel not in files:
            continue
        try:
            data = json.loads(files[rel].read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, ValueError:
            continue
        value = data.get("license") if isinstance(data, dict) else None
        if isinstance(value, str):
            return value
    return None


def pick(spec: PartSpec, files: dict[str, Path], upstream: Upstream) -> Picked:
    """The files (or MCP server) of one part out of a plugin's files."""
    base = upstream.path
    licenses = {
        posixpath.basename(r): p
        for r, p in files.items()
        if posixpath.basename(r) in LICENSE_NAMES
        and posixpath.dirname(r) in {"", "licenses"}
        and not p.is_symlink()
    }
    if spec.kind == "skill":
        prefix = f"skills/{spec.name}/"
        chosen = {r: p for r, p in files.items() if r.startswith(prefix)}
        if f"{prefix}SKILL.md" not in chosen:
            raise NotFoundError(f"{spec.plugin} has no skill '{spec.name}'")
        path = f"{base}/skills/{spec.name}"
    elif spec.kind == "agent":
        rel = f"agents/{spec.name}.md"
        if rel not in files:
            raise NotFoundError(f"{spec.plugin} has no agent '{spec.name}'")
        chosen, path = {rel: files[rel]}, f"{base}/{rel}"
    else:
        rel, servers = plugin_servers(files)
        server = servers.get(spec.name)
        if not isinstance(server, dict):
            raise NotFoundError(f"{spec.plugin} has no MCP server '{spec.name}'")
        path = posixpath.normpath(f"{base}/{rel}")
        return Picked(spec, upstream, path, server=server, licenses=licenses)
    for rel, src in chosen.items():
        if src.is_symlink():
            raise InvalidInputError(f"part {spec.name}: {rel} is a symlink")
    return Picked(spec, upstream, posixpath.normpath(path), chosen, None, licenses)


def check_no_links(root: Path) -> None:
    """Bundle folders are written and deleted in place: no symlinked folders."""
    if root.is_symlink():
        raise InvalidInputError(f"bundle folder {root.name} is a symlink")
    for folder, dirs, _ in os.walk(root):
        for name in dirs:
            if (Path(folder) / name).is_symlink():
                rel = (Path(folder) / name).relative_to(root)
                raise InvalidInputError(f"bundle folder {rel} is a symlink")


def license_dir(spec: PartSpec) -> str:
    plugin = (spec.plugin or "").replace("/", "-")
    return f"licenses/{spec.source}-{plugin}"


# --- the bundle tree ---------------------------------------------------------------


@dataclass
class BundleTree:
    """The bundle folder in a worktree, edited part by part."""

    root: Path

    def mcp(self) -> dict[str, Any]:
        path = self.root / builder.ROOT_MCP
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data.get("mcpServers") or {})

    def save_mcp(self, servers: dict[str, Any]) -> None:
        path = self.root / builder.ROOT_MCP
        if servers:
            path.write_text(jsontext.dump({"mcpServers": servers}), encoding="utf-8")
        elif path.is_file():
            path.unlink()

    def remove(self, part: Part, keep_licenses: bool) -> None:
        if part.kind == "skill":
            shutil.rmtree(self.root / "skills" / part.name, ignore_errors=True)
        elif part.kind == "agent":
            (self.root / "agents" / f"{part.name}.md").unlink(missing_ok=True)
        else:
            servers = self.mcp()
            servers.pop(part.name, None)
            self.save_mcp(servers)
        if not keep_licenses and part.source and part.upstream_plugin:
            spec = PartSpec(part.kind, part.name, part.source, part.upstream_plugin)
            shutil.rmtree(self.root / license_dir(spec), ignore_errors=True)

    def write(self, picked: Picked) -> None:
        spec = picked.spec
        if spec.kind == "mcp_server":
            servers = self.mcp()
            servers[spec.name] = picked.server
            self.save_mcp(servers)
        if spec.kind == "skill":
            shutil.rmtree(self.root / "skills" / spec.name, ignore_errors=True)
        for rel, src in picked.files.items():
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        for name, src in picked.licenses.items():
            target = self.root / license_dir(spec) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)


# --- assembling a candidate -----------------------------------------------------


@dataclass
class Change:
    """What one bundle command asks for."""

    create: bool = False
    description: str | None = None
    category: str | None = None
    add: list[PartSpec] = field(default_factory=list)
    remove: list[PartSpec] = field(default_factory=list)
    refresh: bool = False


@dataclass
class Fetcher:
    """Fetches each (source, plugin) once per command."""

    ctx: Context
    wt: Path
    sources: dict[str, Source]
    tmp: Path
    cache: dict[tuple[str, str], tuple[dict[str, Path], Upstream]] = field(
        default_factory=dict
    )

    def plugin(self, source_id: str, plugin: str) -> tuple[dict[str, Path], Upstream]:
        key = (source_id, plugin)
        if key not in self.cache:
            self.cache[key] = self._fetch(source_id, plugin)
        return self.cache[key]

    def _fetch(self, source_id: str, plugin: str) -> tuple[dict[str, Path], Upstream]:
        if source_id == LOCAL_SOURCE:
            return self._local(plugin)
        source = self.sources.get(source_id)
        if source is None:
            raise NotFoundError(f"no source '{source_id}' in registry/sources.yaml")
        fetched = fetch_plugin(
            self.ctx, source, plugin, self.tmp / f"{len(self.cache)}-{source_id}"
        )
        files = upstream_files(fetched)
        upstream = Upstream(
            repository=fetched.repository,
            commit=fetched.commit,
            path=fetched.plugin.path,
            ref=fetched.ref,
            plugin=fetched.plugin.name,
            license=_license(files),
        )
        return files, upstream

    def _local(self, plugin: str) -> tuple[dict[str, Path], Upstream]:
        reg = Registry.load(self.wt)
        item = reg.items.get(plugin)
        if item is None or item.kind is not ItemKind.LOCAL:
            raise NotFoundError(f"'{plugin}' is not a local plugin on staging")
        root = self.wt / builder.plugin_dir(plugin)
        lock = reg.lock.items.get(plugin)
        skip = set(lock.generated) if lock else set()
        files = {r: root / r for r in hashing.list_files(root) if r not in skip}
        upstream = Upstream(
            repository=reg.config.repository or reg.config.name,
            commit=git.head(self.wt),
            path=builder.plugin_dir(plugin),
            plugin=plugin,
            license=_license(files),
        )
        return files, upstream

    def part(self, spec: PartSpec) -> Picked:
        if spec.source is None or spec.plugin is None:
            raise InvalidInputError(f"part {spec.name} needs source:plugin/")
        files, upstream = self.plugin(spec.source, spec.plugin)
        return pick(spec, files, upstream)


def _pending(ctx: Context, item_id: str, base: str) -> str | None:
    """``origin/<head>`` of the open candidate PR of ``item_id``, if any."""
    for pr in ctx.github.list_open_pull_requests(base):
        own = not pr.cross_repository and git.is_ref(pr.head)
        if own and pr.head.startswith(candidate_branch(item_id, "")):
            return git.fetch_branch(ctx.repo, pr.head)
    return None


def _carry_over(wt: Path, pending: str, item_id: str) -> None:
    """Put the pending candidate's bundle state onto the staging worktree."""
    prefix = builder.plugin_dir(item_id)
    shutil.rmtree(wt / prefix, ignore_errors=True)
    git.run(wt, "checkout", pending, "--", prefix)
    reg = Registry.load(wt)
    item = model_at(wt, pending, ITEMS, ItemsFile).get(item_id)
    lock = model_at(wt, pending, LOCK, LockFile).items.get(item_id)
    if item is None or lock is None:
        raise ConflictError(f"pending candidate {pending} has no '{item_id}' entry")
    reg.items.items = [i for i in reg.items.items if i.id != item_id] + [item]
    reg.lock.items[item_id] = lock
    used = {p.source for p in item.parts}
    pending_sources = model_at(wt, pending, SOURCES, SourcesFile).sources
    for source in pending_sources:
        if source.id in used and source not in reg.sources.sources:
            reg.sources.sources = [
                *(s for s in reg.sources.sources if s.id != source.id),
                source,
            ]
    save_yaml_model(wt, SOURCES, reg.sources)
    reg.save_items()
    reg.save_lock()


def _new_manifest(item_id: str, description: str | None) -> str:
    return jsontext.dump(
        {
            "$schema": SCHEMA,
            "name": item_id,
            "version": FIRST_VERSION,
            "description": description or f"Bundle {item_id}.",
        }
    )


def _set_version(root: Path, version: str) -> None:
    path = root / builder.ROOT_MANIFEST
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = version
    path.write_text(jsontext.dump(data), encoding="utf-8")


def _part_lock(picked: Picked) -> PartLock:
    return PartLock(
        kind=picked.spec.kind,
        name=picked.spec.name,
        path=picked.path,
        upstream=picked.upstream,
    )


def _body(  # noqa: PLR0917
    item: Item,
    version: str,
    flags: list[RiskFlag],
    changes: dict[str, list[str]],
    errors: list[str],
    tree: str,
) -> str:
    lines = [f"## Candidate: `{item.id}` (bundle {version})", "", "### Parts", ""]
    for part in item.parts:
        where = f"{part.source}:{part.upstream_plugin}"
        lines.append(
            f"- {part.kind} `{part.name}` from `{where}` at `{part.commit or '?'}`"
        )
    if not item.parts:
        lines.append("- no parts yet")
    lines += ["", "### Changed files", ""]
    for kind in ("added", "changed", "removed"):
        if changes[kind]:
            shown = ", ".join(f"`{p}`" for p in changes[kind][:40])
            lines.append(f"- {kind} ({len(changes[kind])}): {shown}")
    lines += ["", "### Risk flags", "", risk.render(flags), ""]
    if errors:
        lines += ["### Validation errors", "", *(f"- {e}" for e in errors), ""]
    lines.append(f"{MARKER} item={item.id} tree={tree} -->")
    return "\n".join(lines)


def _apply_parts(
    item: Item, tree: BundleTree, change: Change, fetcher: Fetcher
) -> dict[tuple[str, str], Picked]:
    """Remove and add parts in the tree; returns the parts fetched now."""
    parts: dict[tuple[str, str], Part] = {(p.kind, p.name): p for p in item.parts}
    for spec in change.remove:
        part = parts.pop(spec.key, None)
        if part is None:
            raise NotFoundError(f"'{item.id}' has no {spec.kind} '{spec.name}'")
        same_origin = any(
            (p.source, p.upstream_plugin) == (part.source, part.upstream_plugin)
            for p in parts.values()
        )
        tree.remove(part, keep_licenses=same_origin)
    wanted = list(change.add)
    for spec in change.add:
        if spec.key in parts:
            raise ConflictError(f"'{item.id}' already has {spec.kind} '{spec.name}'")
    if change.refresh:
        wanted += [
            PartSpec(p.kind, p.name, p.source, p.upstream_plugin)
            for p in parts.values()
        ]
    picked: dict[tuple[str, str], Picked] = {}
    for spec in wanted:
        got = fetcher.part(spec)
        tree.write(got)
        picked[spec.key] = got
        parts[spec.key] = Part(
            kind=spec.kind,
            name=spec.name,
            source=spec.source,
            upstream_plugin=spec.plugin,
            ref=got.upstream.ref,
            commit=got.upstream.commit,
        )
    item.parts = sorted(parts.values(), key=lambda p: (p.kind, p.name))
    return picked


def _target(reg: Registry, root: Path, item_id: str, change: Change) -> Item:
    """The bundle item to change (a new one for ``create``)."""
    item = reg.items.get(item_id)
    if not change.create:
        if item is None or item.kind is not ItemKind.BUNDLE:
            raise NotFoundError(f"no bundle '{item_id}' on staging")
        return item
    if item is not None or root.exists():
        raise ConflictError(f"'{item_id}' already exists on staging")
    item = Item(id=item_id, kind=ItemKind.BUNDLE, category=change.category)
    reg.items.items.append(item)
    root.mkdir(parents=True)
    (root / builder.ROOT_MANIFEST).write_text(
        _new_manifest(item_id, change.description), encoding="utf-8"
    )
    return item


def _record(  # noqa: PLR0917
    reg: Registry,
    item: Item,
    picked: dict[tuple[str, str], Picked],
    sources: dict[str, Source],
    version: str,
    base: str,
) -> None:
    """Write sources, item, lock entry and build the worktree."""
    used = {p.source for p in item.parts if p.source}
    reg.sources.sources = [
        *(s for s in reg.sources.sources if s.id not in used),
        *(sources[s] for s in sorted(used) if s in sources),
    ]
    save_yaml_model(reg.repo, SOURCES, reg.sources)
    old = reg.lock.items.get(item.id)
    old_parts = {(p.kind, p.name): p for p in old.parts} if old else {}
    part_locks = [
        _part_lock(picked[key]) if key in picked else old_parts[key]
        for key in ((p.kind, p.name) for p in item.parts)
    ]
    root = reg.repo / builder.plugin_dir(item.id)
    files = hashing.hash_tree(root, reg.config.namespace)
    reg.lock.items[item.id] = ItemLock(
        kind=ItemKind.BUNDLE,
        version=version,
        upstream=Upstream(
            repository=reg.config.repository or reg.config.name,
            commit=git.head(reg.repo),
            path=builder.plugin_dir(item.id),
            ref=base,
        ),
        parts=part_locks,
        tree_sha256=hashing.tree_sha256(files),
        files=files,
    )
    reg.save_items()
    reg.save_lock()
    builder.apply_build(reg)


def _review(
    repo: Path, staging: str, wt: Path, item: Item, version: str
) -> tuple[ItemLock, list[RiskFlag], str]:
    """Lock entry, risk flags against staging and the PR body."""
    final = Registry.load(wt)
    ns = final.config.namespace
    lock = final.lock.items[item.id]
    prefix = builder.plugin_dir(item.id)
    candidate = tree_of(wt / prefix, ns, set(lock.generated))
    staged = model_at(repo, staging, LOCK, LockFile).items.get(item.id)
    approved = tree_at(
        repo, staging, prefix, ns, set(staged.generated) if staged else set()
    )
    flags = risk.compare(approved, candidate)
    body = _body(
        item,
        version,
        flags,
        changes=file_changes(approved, candidate),
        errors=[str(e) for e in validate_registry(final).errors],
        tree=lock.tree_sha256,
    )
    return lock, flags, body


def bundle_candidate(ctx: Context, item_id: str, change: Change) -> CandidateResult:
    check_item_id(item_id)
    with repo_lock(ctx.repo):
        return _bundle_candidate(ctx, item_id, change)


def _bundle_candidate(ctx: Context, item_id: str, change: Change) -> CandidateResult:
    admin = Registry.load(ctx.repo)
    base = base_branch(admin)
    staging = remote_start(ctx.repo, base)
    pending = _pending(ctx, item_id, base)
    if change.create and pending is not None:
        raise ConflictError(f"a candidate of '{item_id}' is open: {pending}")
    with view(ctx.repo, staging) as wt:
        if pending is not None:
            _carry_over(wt, pending, item_id)
        reg = Registry.load(wt)
        ns = reg.config.namespace
        root = wt / builder.plugin_dir(item_id)
        item = _target(reg, root, item_id, change)
        if item.quarantined:
            return CandidateResult(
                item=item_id, commit="", branch="", status="quarantined"
            )
        check_no_links(root)
        old = reg.lock.items.get(item_id)
        for rel in old.generated if old else []:
            (root / rel).unlink(missing_ok=True)
        before = tree_of(root, ns)
        sources = {s.id: s for s in [*admin.sources.sources, *reg.sources.sources]}
        with tempfile.TemporaryDirectory(prefix="skill-dojo-up-") as tmp:
            fetcher = Fetcher(ctx, wt, sources, Path(tmp))
            picked = _apply_parts(item, BundleTree(root), change, fetcher)
            if not change.create and tree_of(root, ns) == before:
                return CandidateResult(
                    item=item_id, commit="", branch="", status="up-to-date"
                )
            version = bump_patch(
                builder.manifest_version_at(ctx.repo, staging, item_id)
            )
            _set_version(root, version)
            _record(reg, item, picked, sources, version, base)
        lock, flags, body = _review(ctx.repo, staging, wt, item, version)
        branch = candidate_branch(item_id, lock.tree_sha256)
        commit_and_push(wt, branch, f"candidate: bundle {item_id} {version}")
    title = f"candidate: bundle {item_id} {version}"
    pr, status = publish(ctx, item_id, branch=branch, base=base, title=title, body=body)
    ctx.report(f"{status} bundle candidate {item_id} -> {pr.url}")
    log.info("Bundle candidate %s %s: %s", item_id, status, pr.url)
    return CandidateResult(
        item=item_id,
        commit=lock.tree_sha256,
        branch=branch,
        pull_request=pr,
        flags=flags,
        status=status,
    )


# --- the operations ----------------------------------------------------------------


def bundle_create(
    ctx: Context,
    item_id: str,
    parts: list[str] | None = None,
    *,
    description: str | None = None,
    category: str | None = None,
) -> CandidateResult:
    """A candidate PR with a new bundle plugin (version 0.1.0)."""
    change = Change(
        create=True,
        description=description,
        category=category,
        add=[parse_part(p) for p in parts or []],
    )
    return bundle_candidate(ctx, item_id, change)


def bundle_add(ctx: Context, item_id: str, parts: list[str]) -> CandidateResult:
    if not parts:
        raise InvalidInputError("give at least one part")
    return bundle_candidate(ctx, item_id, Change(add=[parse_part(p) for p in parts]))


def bundle_remove(ctx: Context, item_id: str, parts: list[str]) -> CandidateResult:
    if not parts:
        raise InvalidInputError("give at least one part")
    specs = [parse_part(p, need_source=False) for p in parts]
    return bundle_candidate(ctx, item_id, Change(remove=specs))


def refresh_bundle(ctx: Context, item_id: str) -> CandidateResult:
    """Re-fetch every part at its source's ref (``sync``)."""
    return bundle_candidate(ctx, item_id, Change(refresh=True))
