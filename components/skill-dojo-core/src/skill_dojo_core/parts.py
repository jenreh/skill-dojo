"""Parts: one skill, agent, MCP server or hook copied into a local plugin.

A part is written as ``source:plugin/kind/name`` (``mcp:<server>/mcp_server/<key>``
for the MCP Registry, ``local:<plugin>/...`` for this repo's own plugins). Each
part is pinned to the commit it was copied at and recorded in the lock.

A hook part is one event of the upstream ``hooks/hooks.json`` (or the manifest's
``hooks``) plus the script files its commands reference through
``${CLAUDE_PLUGIN_ROOT}``.
"""

import json
import os
import posixpath
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, cast

from skill_dojo_core import builder, git, hashing, jsontext
from skill_dojo_core.branches import check_clean_folder
from skill_dojo_core.cache import PartRef
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError, NotFoundError
from skill_dojo_core.models import (
    ItemKind,
    Part,
    PartKind,
    PartLock,
    Source,
    Upstream,
)
from skill_dojo_core.registry import Registry
from skill_dojo_core.vendoring import LICENSE_NAMES, fetch_plugin, upstream_files

# ``plugin`` may be an MCP Registry server name, which holds one ``/``.
PART_RE = re.compile(
    r"^(?:(?P<source>[a-z0-9][a-z0-9.-]*):"
    r"(?P<plugin>[A-Za-z0-9][A-Za-z0-9.-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?)/)?"
    r"(?P<kind>skill|agent|mcp_server|hook)/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)$"
)
# Bundle parts from this repo's own plugins use this source id.
LOCAL_SOURCE = "local"
HOOKS_FILE = "hooks/hooks.json"
ROOT_REF_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s\"'`;|&<>()$\\]+)")


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
            f"'{text}' is not a part; use {form} with kind skill, agent, "
            "mcp_server or hook"
        )
    kind = cast("PartKind", match["kind"])
    return PartSpec(kind, match["name"], match["source"], match["plugin"])


def spec_of(part: Part) -> PartSpec:
    return PartSpec(part.kind, part.name, part.source, part.upstream_plugin)


# --- reading a plugin's parts ------------------------------------------------------


def _json_file(path: Path, rel: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise InvalidInputError(f"unreadable upstream {rel}: {exc}") from exc


def plugin_servers(files: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    """The first MCP config (file, servers) of a plugin."""
    for rel in (builder.CLAUDE_MCP, builder.ROOT_MCP, *hashing.MANIFESTS):
        if rel not in files:
            continue
        data = _json_file(files[rel], rel)
        servers = data.get("mcpServers") if isinstance(data, dict) else None
        if isinstance(servers, dict) and servers:
            return rel, servers
    return "", {}


def _events(data: Any) -> dict[str, Any] | None:
    """``{event: [entries]}`` from a hooks file or a manifest's ``hooks`` value."""
    if isinstance(data, dict) and isinstance(data.get("hooks"), dict):
        data = data["hooks"]
    if isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
        return data
    return None


def plugin_hooks(files: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    """The hook events of a plugin: (file they are in, events)."""
    if HOOKS_FILE in files:
        events = _events(_json_file(files[HOOKS_FILE], HOOKS_FILE))
        return HOOKS_FILE, events or {}
    for rel in (builder.CLAUDE_MANIFEST, builder.ROOT_MANIFEST):
        if rel not in files:
            continue
        data = _json_file(files[rel], rel)
        value = data.get("hooks") if isinstance(data, dict) else None
        if isinstance(value, str):
            path = posixpath.normpath(value.removeprefix("./"))
            if path in files and not path.startswith("../"):
                events = _events(_json_file(files[path], path))
                return path, events or {}
        events = _events(value)
        if events:
            return rel, events
    return "", {}


def index_parts(files: dict[str, Path]) -> list[PartRef]:
    """Every part a plugin offers, for the cache and the Sources page."""
    skills = sorted(
        {
            r.split("/")[1]
            for r in files
            if r.startswith("skills/") and r.endswith("/SKILL.md") and r.count("/") == 2
        }
    )
    agents = sorted(
        PurePosixPath(r).stem
        for r in files
        if r.startswith("agents/") and r.endswith(".md") and r.count("/") == 1
    )
    try:
        servers = sorted(plugin_servers(files)[1])
        events = sorted(plugin_hooks(files)[1])
    except InvalidInputError:
        servers, events = [], []
    return [
        *(PartRef(kind="skill", name=n) for n in skills),
        *(PartRef(kind="agent", name=n) for n in agents),
        *(PartRef(kind="mcp_server", name=n) for n in servers),
        *(PartRef(kind="hook", name=n) for n in events),
    ]


def manifest_license(files: dict[str, Path]) -> str | None:
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


# --- one part ------------------------------------------------------------------


@dataclass
class Picked:
    """A part fetched at a pinned commit, ready to be written into a plugin."""

    spec: PartSpec
    upstream: Upstream
    path: str
    files: dict[str, Path] = field(default_factory=dict)
    server: dict[str, Any] | None = None
    hook: list[Any] | None = None
    licenses: dict[str, Path] = field(default_factory=dict)

    def lock(self) -> PartLock:
        return PartLock(
            kind=self.spec.kind,
            name=self.spec.name,
            path=self.path,
            upstream=self.upstream,
        )


def hook_refs(entries: Any) -> set[str]:
    """Plugin-relative files the hook commands reference."""
    text = json.dumps(entries)
    return {posixpath.normpath(m) for m in ROOT_REF_RE.findall(text)}


def _hook_files(spec: PartSpec, entries: Any, files: dict[str, Path]) -> dict:
    chosen: dict[str, Path] = {}
    for rel in sorted(hook_refs(entries)):
        if rel.startswith(("../", "/")) or rel in {".", ".."}:
            raise InvalidInputError(f"hook {spec.name}: {rel} is outside the plugin")
        src = files.get(rel)
        if src is None:
            raise NotFoundError(f"hook {spec.name}: {rel} is missing upstream")
        chosen[rel] = src
    return chosen


def pick(spec: PartSpec, files: dict[str, Path], upstream: Upstream) -> Picked:
    """The files (or MCP server, or hook event) of one part of a plugin."""
    base = upstream.path
    licenses = {
        posixpath.basename(r): p
        for r, p in files.items()
        if posixpath.basename(r) in LICENSE_NAMES
        and posixpath.dirname(r) in {"", "licenses"}
        and not p.is_symlink()
    }
    hook = None
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
    elif spec.kind == "hook":
        rel, events = plugin_hooks(files)
        hook = events.get(spec.name)
        if not isinstance(hook, list):
            raise NotFoundError(f"{spec.plugin} has no hook event '{spec.name}'")
        chosen, path = _hook_files(spec, hook, files), f"{base}/{rel}"
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
    return Picked(
        spec, upstream, posixpath.normpath(path), chosen, None, hook, licenses
    )


def check_no_links(root: Path) -> None:
    """Plugin folders are written and deleted in place: no symlinked folders."""
    if root.is_symlink():
        raise InvalidInputError(f"plugin folder {root.name} is a symlink")
    for folder, dirs, _ in os.walk(root):
        for name in dirs:
            if (Path(folder) / name).is_symlink():
                rel = (Path(folder) / name).relative_to(root)
                raise InvalidInputError(f"plugin folder {rel} is a symlink")


def license_dir(spec: PartSpec) -> str:
    plugin = (spec.plugin or "").replace("/", "-")
    return f"licenses/{spec.source}-{plugin}"


# --- the plugin tree -----------------------------------------------------------------


@dataclass
class PluginTree:
    """A local plugin folder, edited part by part.

    ``generated`` are the paths build made (never edited: build rewrites them).
    """

    root: Path
    generated: set[str] = field(default_factory=set)

    def _real(self, rel: str) -> bool:
        path = self.root / rel
        return path.is_file() and not path.is_symlink() and rel not in self.generated

    def mcp_file(self) -> str:
        """The MCP config that holds real content (it is created when missing)."""
        for rel in (builder.CLAUDE_MCP, builder.ROOT_MCP):
            if self._real(rel):
                return rel
        if self._real(builder.ROOT_MANIFEST):
            return builder.ROOT_MCP
        return builder.CLAUDE_MCP

    def _load(self, rel: str) -> dict[str, Any]:
        path = self.root / rel
        if not path.is_file():
            return {}
        data = _json_file(path, rel)
        if not isinstance(data, dict):
            raise InvalidInputError(f"{rel} must be a JSON object")
        return data

    def mcp(self) -> dict[str, Any]:
        return dict(self._load(self.mcp_file()).get("mcpServers") or {})

    def save_mcp(self, servers: dict[str, Any]) -> None:
        rel = self.mcp_file()
        data = {k: v for k, v in self._load(rel).items() if k != "mcpServers"}
        path = self.root / rel
        if servers:
            path.write_text(jsontext.dump({**data, "mcpServers": servers}), "utf-8")
        elif set(data) - {"$schema"}:
            path.write_text(jsontext.dump(data), encoding="utf-8")
        elif path.is_file():
            path.unlink()

    def hooks(self) -> dict[str, Any]:
        return dict(_events(self._load(HOOKS_FILE)) or {})

    def save_hooks(self, events: dict[str, Any]) -> None:
        data = {k: v for k, v in self._load(HOOKS_FILE).items() if k != "hooks"}
        path = self.root / HOOKS_FILE
        if events:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(jsontext.dump({**data, "hooks": events}), "utf-8")
        elif data:
            path.write_text(jsontext.dump(data), encoding="utf-8")
        elif path.is_file():
            path.unlink()

    def check_free(self, picked: Picked) -> None:
        """A new part must not take over files or entries that are already there."""
        spec = picked.spec
        if spec.kind == "skill":
            taken = (self.root / "skills" / spec.name).exists()
        elif spec.kind == "agent":
            taken = (self.root / "agents" / f"{spec.name}.md").exists()
        elif spec.kind == "mcp_server":
            taken = spec.name in self.mcp()
        else:
            taken = spec.name in self.hooks()
        if taken:
            raise ConflictError(
                f"{self.root.name} already has {spec.kind} '{spec.name}'"
            )
        if spec.kind == "hook":
            for rel, src in picked.files.items():
                target = self.root / rel
                if target.exists() and target.read_bytes() != src.read_bytes():
                    raise ConflictError(f"{self.root.name} already has {rel}")

    def remove(self, part: Part, keep_licenses: bool) -> None:
        if part.kind == "skill":
            shutil.rmtree(self.root / "skills" / part.name, ignore_errors=True)
        elif part.kind == "agent":
            (self.root / "agents" / f"{part.name}.md").unlink(missing_ok=True)
        elif part.kind == "hook":
            events = self.hooks()
            gone = hook_refs(events.pop(part.name, []))
            still = hook_refs(events)
            for rel in gone - still:
                (self.root / rel).unlink(missing_ok=True)
            self.save_hooks(events)
        else:
            servers = self.mcp()
            servers.pop(part.name, None)
            self.save_mcp(servers)
        if not keep_licenses and part.source and part.upstream_plugin:
            shutil.rmtree(self.root / license_dir(spec_of(part)), ignore_errors=True)

    def write(self, picked: Picked) -> None:
        spec = picked.spec
        if spec.kind == "mcp_server":
            servers = self.mcp()
            servers[spec.name] = picked.server
            self.save_mcp(servers)
        if spec.kind == "hook":
            events = self.hooks()
            events[spec.name] = picked.hook
            self.save_hooks(events)
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


# --- fetching parts -------------------------------------------------------------


@dataclass
class Fetcher:
    """Fetches each (source, plugin) once per command."""

    ctx: Context
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
            license=manifest_license(files),
        )
        return files, upstream

    def _local(self, plugin: str) -> tuple[dict[str, Path], Upstream]:
        repo = self.ctx.repo
        reg = Registry.load(repo)
        item = reg.items.get(plugin)
        if item is None or item.kind is not ItemKind.LOCAL:
            raise NotFoundError(f"'{plugin}' is not a local plugin")
        root = repo / builder.plugin_dir(plugin)
        # The part is pinned to HEAD, so its files must be the ones at HEAD.
        check_clean_folder(repo, builder.plugin_dir(plugin))
        lock = reg.lock.items.get(plugin)
        skip = set(lock.generated) if lock else set()
        files = {r: root / r for r in hashing.list_files(root) if r not in skip}
        upstream = Upstream(
            repository=reg.config.repository or reg.config.name,
            commit=git.head(repo),
            path=builder.plugin_dir(plugin),
            plugin=plugin,
            license=manifest_license(files),
        )
        return files, upstream

    def part(self, spec: PartSpec) -> Picked:
        if spec.source is None or spec.plugin is None:
            raise InvalidInputError(f"part {spec.name} needs source:plugin/")
        files, upstream = self.plugin(spec.source, spec.plugin)
        return pick(spec, files, upstream)
