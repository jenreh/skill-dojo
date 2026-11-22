"""Risk flags: what a reviewer should look at in a candidate.

Pure functions over two trees (approved vs candidate), each a map of
plugin-relative path -> (git mode, bytes). Flags inform; they never block.
"""

import json
import posixpath
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from skill_dojo_core import frontmatter
from skill_dojo_core.results import Result

type Tree = Mapping[str, tuple[str, bytes]]

URL_RE = re.compile(r"\b(?:https?|wss?)://[^\s\"'`<>)\]]+")
SHELL_RE = re.compile(r"!`|```(?:bash|sh|shell|zsh)\b|\$\(")
MCP_FILES = frozenset({"mcp.json", ".mcp.json"})
MANIFESTS = frozenset({"plugin.json", ".claude-plugin/plugin.json"})
LICENSE_RE = re.compile(r"(?:^|/)(?:LICEN[CS]E|NOTICE|COPYING)(?:\.[A-Za-z]+)?$", re.I)
SERVER_KEYS = ("type", "command", "args", "env", "url", "headers", "cwd")
# Manifest keys that only describe a plugin; anything else changes behaviour.
DESCRIPTIVE_MANIFEST_KEYS = frozenset(
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
    }
)
DESCRIPTIVE_FRONTMATTER_KEYS = frozenset(
    {
        "name",
        "description",
        "when_to_use",
        "license",
        "metadata",
        "argument-hint",
        "version",
    }
)
COMPONENT_KEYS = (
    "mcpServers",
    "hooks",
    "commands",
    "agents",
    "skills",
    "lspServers",
    "outputStyles",
    "permissions",
)
TOOL_KEYS = ("allowed-tools", "allowedTools", "tools")
TOOL_DIRS = frozenset({"skills", "commands", "agents"})


# A flag row of ``render``'s table: | `kind` | ...
FLAG_ROW = re.compile(r"^\| `[a-z0-9-]+` \|", re.MULTILINE)


class RiskFlag(Result):
    kind: str
    path: str
    line: int | None = None
    detail: str


def _text(data: bytes) -> str | None:
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _added_lines(old: str, new: str) -> list[tuple[int, str]]:
    before = set(old.splitlines())
    return [
        (i, line) for i, line in enumerate(new.splitlines(), 1) if line not in before
    ]


def _json(data: bytes) -> Any:
    try:
        return json.loads(data)
    except UnicodeDecodeError, json.JSONDecodeError:
        return None


def _servers(data: bytes | None) -> dict[str, Any]:
    parsed = _json(data) if data is not None else None
    servers = parsed.get("mcpServers") if isinstance(parsed, dict) else None
    return servers if isinstance(servers, dict) else {}


def _line_of(text: str, needle: str) -> int | None:
    for i, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return i
    return None


def _frontmatter(data: bytes) -> dict[str, Any]:
    text = _text(data)
    if text is None:
        return {}
    try:
        parsed, _ = frontmatter.load(text)
    except ValueError:
        return {}
    return parsed


def mcp_flags(path: str, old: bytes | None, new: bytes) -> list[RiskFlag]:
    flags = []
    before, after = _servers(old), _servers(new)
    text = _text(new) or ""
    for name, server in after.items():
        if name not in before:
            flags.append(
                RiskFlag(
                    kind="mcp-server-added",
                    path=path,
                    line=_line_of(text, f'"{name}"'),
                    detail=f"new MCP server '{name}'",
                )
            )
            continue
        old_server = before[name] if isinstance(before[name], dict) else {}
        new_server = server if isinstance(server, dict) else {}
        changed = [k for k in SERVER_KEYS if old_server.get(k) != new_server.get(k)]
        if changed:
            flags.append(
                RiskFlag(
                    kind="mcp-server-changed",
                    path=path,
                    line=_line_of(text, f'"{name}"'),
                    detail=f"MCP server '{name}' changed {', '.join(changed)}",
                )
            )
    flags.extend(
        RiskFlag(
            kind="mcp-server-removed", path=path, detail=f"MCP server '{name}' removed"
        )
        for name in before
        if name not in after
    )
    return flags


def text_flags(path: str, old_text: str, new_text: str) -> list[RiskFlag]:
    flags = []
    added = _added_lines(old_text, new_text)
    known = set(URL_RE.findall(old_text))
    for line_no, line in added:
        for url in URL_RE.findall(line):
            if url not in known:
                known.add(url)
                flags.append(
                    RiskFlag(
                        kind="network-endpoint",
                        path=path,
                        line=line_no,
                        detail=f"new endpoint {url}",
                    )
                )
    parts = PurePosixPath(path).parts
    in_skill_or_command = bool(parts) and parts[0] in {"commands", "skills", "agents"}
    if in_skill_or_command:
        for line_no, line in added:
            if SHELL_RE.search(line):
                flags.append(
                    RiskFlag(
                        kind="shell-command",
                        path=path,
                        line=line_no,
                        detail="shell command in a command, skill or agent",
                    )
                )
                break
    return flags


def file_flags(
    path: str, old: tuple[str, bytes] | None, new: tuple[str, bytes]
) -> list[RiskFlag]:
    """Flags for one added or changed file."""
    mode, data = new
    flags: list[RiskFlag] = []
    verb = "new" if old is None else "changed"
    if mode == "120000":
        target = data.decode("utf-8", "replace")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        if target.startswith("/") or resolved.startswith(".."):
            flags.append(
                RiskFlag(kind="symlink-escape", path=path, detail=f"link to {target}")
            )
        return flags
    if mode == "100755":
        flags.append(
            RiskFlag(kind="executable", path=path, detail=f"{verb} executable")
        )
    parts = PurePosixPath(path).parts
    if "hooks" in parts or PurePosixPath(path).name == "hooks.json":
        flags.append(RiskFlag(kind="hook", path=path, detail=f"{verb} hook"))
    text = _text(data)
    if text is None:
        flags.append(RiskFlag(kind="binary", path=path, detail=f"{verb} binary file"))
        return flags
    if LICENSE_RE.search(path) and old is not None:
        flags.append(
            RiskFlag(kind="license-changed", path=path, detail="license text changed")
        )
    if path in MCP_FILES:
        flags += mcp_flags(path, old[1] if old else None, data)
    old_text = _text(old[1]) if old else ""
    flags += text_flags(path, old_text or "", text)
    if path in MANIFESTS:
        flags += manifest_flags(path, old[1] if old else None, data)
    if path.endswith(".md") and parts and parts[0] in TOOL_DIRS:
        flags += tool_flags(path, old[1] if old else None, data, text)
    return flags


def tool_flags(path: str, old: bytes | None, new: bytes, text: str) -> list[RiskFlag]:
    """New or changed tool permissions in a skill, command or agent file."""
    before = _frontmatter(old) if old is not None else {}
    after = _frontmatter(new)
    return [
        RiskFlag(
            kind="allowed-tools",
            path=path,
            line=_line_of(text, key),
            detail=f"{key} {'set' if key not in before else 'changed'} "
            f"to {after[key]!r}",
        )
        for key in TOOL_KEYS
        if key in after and after.get(key) != before.get(key)
    ]


def manifest_flags(path: str, old: bytes | None, new: bytes) -> list[RiskFlag]:
    """Components (MCP servers, hooks, commands, ...) declared in a manifest."""
    before = _json(old) if old is not None else {}
    after = _json(new)
    if not isinstance(after, dict):
        return []
    before = before if isinstance(before, dict) else {}
    text = _text(new) or ""
    flags = []
    if isinstance(after.get("mcpServers"), dict) or isinstance(
        before.get("mcpServers"), dict
    ):
        servers = {"mcpServers": after.get("mcpServers") or {}}
        old_servers = {"mcpServers": before.get("mcpServers") or {}}
        flags += mcp_flags(
            path,
            json.dumps(old_servers).encode(),
            json.dumps(servers).encode(),
        )
    for key in COMPONENT_KEYS:
        if key == "mcpServers" and isinstance(after.get(key), dict):
            continue
        if after.get(key) != before.get(key) and (key in after or key in before):
            flags.append(
                RiskFlag(
                    kind="hook" if key == "hooks" else "manifest-component",
                    path=path,
                    line=_line_of(text, f'"{key}"'),
                    detail=f"manifest '{key}' {'added' if key not in before else 'changed'}",
                )
            )
    return flags


def _license_of(tree: Tree) -> Any:
    for rel in MANIFESTS:
        if rel in tree:
            data = _json(tree[rel][1])
            if isinstance(data, dict):
                return data.get("license")
    return None


def _has_license_file(tree: Tree) -> bool:
    return any(LICENSE_RE.search(rel) for rel in tree)


def _descriptive_change(rel: str, old: bytes, new: bytes) -> bool:
    """True when only descriptive keys differ (and a SKILL.md body is unchanged)."""
    if rel in MANIFESTS:
        a, b = _json(old), _json(new)
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        keys = (set(a) | set(b)) - DESCRIPTIVE_MANIFEST_KEYS
        return all(a.get(k) == b.get(k) for k in keys)
    if _body((F_MODE, old)) != _body((F_MODE, new)):
        return False
    a, b = _frontmatter(old), _frontmatter(new)
    keys = (set(a) | set(b)) - DESCRIPTIVE_FRONTMATTER_KEYS
    return all(a.get(k) == b.get(k) for k in keys)


def compare(approved: Tree, candidate: Tree) -> list[RiskFlag]:
    """All risk flags of ``candidate`` against ``approved``.

    Both trees are expected without the tool's own provenance keys.
    """
    flags: list[RiskFlag] = []
    changed = [
        rel for rel, entry in sorted(candidate.items()) if approved.get(rel) != entry
    ]
    for rel in changed:
        flags += file_flags(rel, approved.get(rel), candidate[rel])
    removed = sorted(set(approved) - set(candidate))
    flags += [
        RiskFlag(kind="license-removed", path=rel, detail="license file removed")
        for rel in removed
        if LICENSE_RE.search(rel)
    ]
    if not _has_license_file(candidate) and not _license_of(candidate):
        flags.append(RiskFlag(kind="license-missing", path=".", detail="no license"))
    if approved and _license_of(approved) != _license_of(candidate):
        flags.append(
            RiskFlag(
                kind="license-changed",
                path="plugin.json",
                detail=f"license {_license_of(approved)!r} -> {_license_of(candidate)!r}",
            )
        )
    metadata_files = [
        rel
        for rel in changed
        if rel in MANIFESTS or PurePosixPath(rel).name == "SKILL.md"
    ]
    if (
        approved
        and changed
        and not flags
        and not removed
        and len(metadata_files) == len(changed)
        and all(rel in approved for rel in changed)
        and all(
            _descriptive_change(rel, approved[rel][1], candidate[rel][1])
            for rel in changed
        )
    ):
        flags.append(
            RiskFlag(
                kind="metadata-only",
                path=".",
                detail="upstream changed only descriptive manifest or frontmatter keys",
            )
        )
    return flags


F_MODE = "100644"


def _body(entry: tuple[str, bytes] | None) -> str | None:
    if entry is None:
        return None
    text = _text(entry[1])
    if text is None:
        return None
    doc = frontmatter.split(text)
    return doc.body if doc is not None else None


def render(flags: list[RiskFlag]) -> str:
    """Markdown for a PR body or comment."""
    if not flags:
        return "No risk flags."
    lines = ["| Flag | File | Line | Detail |", "| --- | --- | --- | --- |"]
    for flag in flags:
        line = str(flag.line) if flag.line else ""
        detail = flag.detail.replace("|", "\\|")
        lines.append(f"| `{flag.kind}` | `{flag.path}` | {line} | {detail} |")
    return "\n".join(lines)
