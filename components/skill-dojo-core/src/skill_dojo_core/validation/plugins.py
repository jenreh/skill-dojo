"""Agent Plugins 1.0.0 checks of ``plugins/*`` and both catalogs.

Port of ``scripts/validate_plugins.py`` from jenreh/agent-skills. It mirrors
https://agent-plugins.org/schemas/1.0.0/plugin.schema.json and mcp.schema.json
instead of fetching them. Unknown top-level manifest fields are warnings; anything
that would make a client reject the plugin is an error.
"""

import json
import re
from pathlib import Path
from typing import Any

from skill_dojo_core.catalogs import AGENTS_CATALOG, CLAUDE_CATALOG
from skill_dojo_core.hashing import list_files
from skill_dojo_core.models import Layout
from skill_dojo_core.validation.mcp_pins import floating_reference
from skill_dojo_core.validation.report import Collector

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
CWD_RE = re.compile(r"^(?:\./|\$\{PLUGIN_ROOT\}(?:/|$)|\$\{PLUGIN_DATA\}(?:/|$))")
NAMESPACE_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
MANIFEST_FIELDS = frozenset(
    {
        "$schema",
        "name",
        "displayName",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
)
AUTHOR_FIELDS = frozenset({"name", "email", "url"})
KNOWN_CLIENT_FIELDS = {"dependencies": "Claude Code"}
SERVER_FIELDS = {
    "stdio": ({"type", "command"}, {"type", "command", "args", "env", "cwd"}),
    "streamable-http": ({"type", "url"}, {"type", "url", "headers"}),
    "sse": ({"type", "url"}, {"type", "url", "headers"}),
}


def label(repo: Path, path: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path, plugin: Path, name: str, rep: Collector) -> Any:
    """A JSON object inside the plugin root (symlinks may not escape it)."""
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        rep.error(name, f"cannot resolve ({exc})")
        return None
    root = plugin.resolve()
    if root not in resolved.parents:
        rep.error(name, "resolves outside the plugin root")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        rep.error(name, str(exc))
        return None
    if not isinstance(data, dict):
        rep.error(name, "top level must be an object")
        return None
    return data


def check_manifest(repo: Path, plugin: Path, layout: Layout, rep: Collector) -> None:
    path = plugin / "plugin.json"
    name = label(repo, path)
    if not path.is_file():
        rep.error(name, "missing (the spec requires the manifest at the plugin root)")
        return
    claude = plugin / ".claude-plugin" / "plugin.json"
    data = load_json(path, plugin, name, rep)
    if data is None:
        return
    if claude.is_file() and path.resolve() != claude.resolve():
        if layout.manifest_symlinks:
            rep.error(name, "not the same file as .claude-plugin/plugin.json")
        else:
            other = load_json(claude, plugin, label(repo, claude), rep) or {}
            keys = (set(data) | set(other)) - {"$schema"}
            for key in sorted(k for k in keys if other.get(k) != data.get(k)):
                rep.error(name, f"'{key}' differs from .claude-plugin/plugin.json")

    if data.get("$schema") != PLUGIN_SCHEMA:
        rep.error(name, f"$schema must be '{PLUGIN_SCHEMA}'")
    plugin_name = data.get("name")
    if not isinstance(plugin_name, str) or not plugin_name:
        rep.error(name, "'name' is required")
    else:
        if not (1 <= len(plugin_name) <= 64) or not NAME_RE.match(plugin_name):
            rep.error(name, f"name '{plugin_name}' violates the spec pattern")
        if plugin_name != plugin.name:
            rep.error(name, f"name '{plugin_name}' != directory name '{plugin.name}'")
    for field in ("version", "description", "homepage", "repository", "license"):
        if field in data and not isinstance(data[field], str):
            rep.error(name, f"'{field}' must be a string")
    keywords = data.get("keywords")
    if keywords is not None and (
        not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords)
    ):
        rep.error(name, "'keywords' must be an array of strings")
    author = data.get("author")
    if author is not None:
        if not isinstance(author, dict):
            rep.error(name, "'author' must be an object")
        else:
            for key in sorted(set(author) - AUTHOR_FIELDS):
                rep.error(name, f"author.{key} is not allowed by the spec")
    check_extensions(name, data.get("extensions"), rep)
    for field in sorted(set(data) - MANIFEST_FIELDS):
        owner = KNOWN_CLIENT_FIELDS.get(field)
        if owner:
            rep.warn(
                name, f"'{field}' is a {owner} field; conformant clients ignore it"
            )
        else:
            rep.warn(name, f"unknown top-level field '{field}'")


def check_extensions(name: str, extensions: Any, rep: Collector) -> None:
    if extensions is None:
        return
    if not isinstance(extensions, dict):
        rep.error(name, "'extensions' must be an object")
        return
    for ns, value in extensions.items():
        if not NAMESPACE_RE.match(ns):
            rep.error(name, f"extension key '{ns}' is not a reverse-domain namespace")
        if not isinstance(value, dict):
            rep.error(name, f"extensions.{ns} must be an object")


def check_server(name: str, server_name: str, server: Any, rep: Collector) -> None:
    where = f"server '{server_name}'"
    if not isinstance(server, dict):
        rep.error(name, f"{where} must be an object")
        return
    transport = server.get("type")
    if transport not in SERVER_FIELDS:
        rep.error(
            name,
            f"{where} has type {transport!r}; expected one of "
            f"{', '.join(sorted(SERVER_FIELDS))}",
        )
        return
    required, allowed = SERVER_FIELDS[transport]
    for field in sorted(required - set(server)):
        rep.error(name, f"{where} is missing required '{field}'")
    for field in sorted(set(server) - allowed):
        rep.error(name, f"{where} has '{field}', not allowed for {transport}")
    for field in ("command", "url"):
        if field in server and not (isinstance(server[field], str) and server[field]):
            rep.error(name, f"{where} has an empty '{field}'")
    args = server.get("args")
    if args is not None and (
        not isinstance(args, list) or not all(isinstance(a, str) for a in args)
    ):
        rep.error(name, f"{where} args must be an array of strings")
    env = server.get("env")
    if env is not None:
        if not isinstance(env, dict):
            rep.error(name, f"{where} env must be an object")
        else:
            for key, value in env.items():
                if key in ("PLUGIN_ROOT", "PLUGIN_DATA"):
                    rep.error(name, f"{where} must not redefine env '{key}'")
                if not isinstance(value, str):
                    rep.error(name, f"{where} env.{key} must be a string")
    cwd = server.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not CWD_RE.match(cwd)):
        rep.error(
            name,
            f"{where} cwd must start with './', '${{PLUGIN_ROOT}}' or '${{PLUGIN_DATA}}'",
        )
    headers = server.get("headers")
    if headers is not None:
        if not isinstance(headers, dict):
            rep.error(name, f"{where} headers must be an object")
        elif not all(isinstance(v, str) for v in headers.values()):
            rep.error(name, f"{where} header values must be strings")
    if transport == "stdio" and (problem := floating_reference(server)):
        rep.error(name, f"{where} floats: {problem}; pin an exact version or digest")


def check_mcp(repo: Path, plugin: Path, layout: Layout, rep: Collector) -> None:
    """``mcp.json`` (Agent Plugins) and ``.mcp.json`` (Claude Code), both checked."""
    path = plugin / "mcp.json"
    claude = plugin / ".mcp.json"
    name = label(repo, path)
    if not path.exists():
        if claude.is_file():
            rep.error(name, "missing next to .mcp.json (run 'skill-dojo build')")
            check_servers(
                label(repo, claude),
                load_json(claude, plugin, label(repo, claude), rep),
                rep,
            )
        return
    data = load_json(path, plugin, name, rep)
    if data is None:
        return
    if data.get("$schema") != MCP_SCHEMA:
        rep.error(name, f"$schema must be '{MCP_SCHEMA}'")
    for field in sorted(set(data) - {"$schema", "mcpServers"}):
        rep.error(name, f"'{field}' is not allowed by the spec")
    check_servers(name, data, rep)
    if claude.is_file() and path.resolve() != claude.resolve():
        claude_name = label(repo, claude)
        if layout.mcp_symlink:
            rep.error(name, "not the same file as .mcp.json")
        other = load_json(claude, plugin, claude_name, rep)
        if other is not None and other.get("mcpServers") != data.get("mcpServers"):
            rep.error(claude_name, "mcpServers differ from mcp.json")
            check_servers(claude_name, other, rep)


def check_servers(name: str, data: Any, rep: Collector) -> None:
    if data is None:
        return
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        rep.error(name, "'mcpServers' is required and must be an object")
        return
    for server_name, server in servers.items():
        check_server(name, server_name, server, rep)


def check_symlinks(repo: Path, plugin: Path, rep: Collector) -> None:
    """Every symlink in a plugin resolves inside the plugin root."""
    root = plugin.resolve()
    for rel in list_files(plugin):
        path = plugin / rel
        if not path.is_symlink():
            continue
        target = path.resolve()
        if target != root and root not in target.parents:
            rep.error(label(repo, path), "symlink points outside the plugin")


def check_openai_interface(repo: Path, plugin: Path, rep: Collector) -> None:
    """Icon paths in ``extensions.com.openai.interface`` exist inside the plugin."""
    try:
        manifest = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return
    if not isinstance(manifest, dict):
        return
    interface = (
        (manifest.get("extensions") or {}).get("com.openai", {}).get("interface", {})
    )
    for key in ("composerIcon", "logo"):
        ref = interface.get(key) if isinstance(interface, dict) else None
        if ref is None:
            continue
        target = (plugin / ref).resolve()
        name = label(repo, plugin / "plugin.json")
        if not str(ref).startswith("./") or plugin.resolve() not in target.parents:
            rep.error(name, f"com.openai interface.{key} '{ref}' must stay inside")
        elif not target.is_file():
            rep.error(name, f"com.openai interface.{key} '{ref}' not found")


def _catalog_entries(repo: Path, rel: str, rep: Collector) -> list[Any] | None:
    path = repo / rel
    if not path.is_file():
        rep.error(rel, "missing (run 'skill-dojo build')")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        rep.error(rel, str(exc))
        return None
    entries = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        rep.error(rel, "'plugins' must be an array")
        return None
    return entries


def check_claude_catalog(repo: Path, plugins: list[Path], rep: Collector) -> None:
    entries = _catalog_entries(repo, CLAUDE_CATALOG, rep)
    if entries is None:
        return
    listed: dict[Any, Any] = {}
    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        if name in listed:
            rep.error(CLAUDE_CATALOG, f"plugin '{name}' listed twice")
        listed[name] = entry
    for plugin in plugins:
        entry = listed.pop(plugin.name, None)
        if entry is None:
            rep.error(CLAUDE_CATALOG, f"plugin '{plugin.name}' is not listed")
            continue
        if entry.get("source") != f"./plugins/{plugin.name}":
            rep.error(
                CLAUDE_CATALOG, f"'{plugin.name}' source is {entry.get('source')!r}"
            )
        try:
            manifest = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, json.JSONDecodeError:
            continue
        if isinstance(manifest, dict) and entry.get("version") != manifest.get(
            "version"
        ):
            rep.error(
                CLAUDE_CATALOG,
                f"'{plugin.name}' version {entry.get('version')!r} != plugin.json "
                f"version {manifest.get('version')!r}",
            )
    for name in listed:
        rep.error(CLAUDE_CATALOG, f"'{name}' has no plugins/{name} directory")


def check_agents_catalog(repo: Path, plugins: list[Path], rep: Collector) -> None:
    entries = _catalog_entries(repo, AGENTS_CATALOG, rep)
    if entries is None:
        return
    listed = {e.get("name"): e for e in entries if isinstance(e, dict)}
    for plugin in plugins:
        entry = listed.pop(plugin.name, None)
        if entry is None:
            rep.error(AGENTS_CATALOG, f"plugin '{plugin.name}' is not listed")
            continue
        source = entry.get("source")
        if source != {"source": "local", "path": f"./plugins/{plugin.name}"}:
            rep.error(AGENTS_CATALOG, f"'{plugin.name}' source is {source!r}")
        policy = entry.get("policy") or {}
        for field in ("installation", "authentication"):
            if not policy.get(field):
                rep.error(AGENTS_CATALOG, f"'{plugin.name}' is missing policy.{field}")
        if not entry.get("category"):
            rep.error(AGENTS_CATALOG, f"'{plugin.name}' is missing category")
    for name in listed:
        rep.error(AGENTS_CATALOG, f"'{name}' has no plugins/{name} directory")


def check_plugins(
    repo: Path, plugins: list[Path], layout: Layout, rep: Collector
) -> None:
    for plugin in plugins:
        check_manifest(repo, plugin, layout, rep)
        check_mcp(repo, plugin, layout, rep)
        check_openai_interface(repo, plugin, rep)
        check_symlinks(repo, plugin, rep)
    check_claude_catalog(repo, plugins, rep)
    check_agents_catalog(repo, plugins, rep)
