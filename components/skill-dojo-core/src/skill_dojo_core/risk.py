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
    if PurePosixPath(path).name == "SKILL.md" and old is not None:
        before = _frontmatter(old[1]).get("allowed-tools")
        after = _frontmatter(data).get("allowed-tools")
        if before != after:
            flags.append(
                RiskFlag(
                    kind="allowed-tools",
                    path=path,
                    line=_line_of(text, "allowed-tools"),
                    detail=f"allowed-tools changed to {after!r}",
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


def _strip_namespace(data: bytes, rel: str, prefixes: tuple[str, str]) -> Any:
    """Content of a manifest or SKILL.md without the tool's own keys."""
    if rel in MANIFESTS:
        parsed = _json(data)
        if isinstance(parsed, dict):
            ext = dict(parsed.get("extensions") or {})
            ext.pop(prefixes[1], None)
            return {**parsed, "extensions": ext}
        return data
    parsed = _frontmatter(data)
    metadata = {
        k: v
        for k, v in (parsed.get("metadata") or {}).items()
        if not str(k).startswith(prefixes[0])
    }
    return {**parsed, "metadata": metadata}


def compare(
    approved: Tree, candidate: Tree, prefixes: tuple[str, str] = ("", "")
) -> list[RiskFlag]:
    """All risk flags of ``candidate`` against ``approved``.

    ``prefixes`` are the tool's (skill, plugin) namespaces, ignored when deciding
    whether an upstream change touched only metadata.
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
    if approved and changed and len(metadata_files) == len(changed) and not removed:
        only_metadata = all(
            _body(approved.get(rel)) == _body(candidate[rel]) for rel in metadata_files
        )
        real = any(
            _strip_namespace(approved[rel][1], rel, prefixes)
            != _strip_namespace(candidate[rel][1], rel, prefixes)
            for rel in metadata_files
            if rel in approved
        )
        if only_metadata and real:
            flags.append(
                RiskFlag(
                    kind="metadata-only",
                    path=".",
                    detail="upstream changed only manifest or frontmatter metadata",
                )
            )
    return flags


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
