import json

from skill_dojo_core import risk

F = "100644"


def tree(**files: str | bytes) -> dict[str, tuple[str, bytes]]:
    return {
        k.replace("__", "/").replace("_dot_", "."): (
            F,
            v.encode() if isinstance(v, str) else v,
        )
        for k, v in files.items()
    }


def kinds(flags: list[risk.RiskFlag]) -> set[str]:
    return {f.kind for f in flags}


def test_new_plugin_flags() -> None:
    candidate = {
        "run.sh": ("100755", b"#!/bin/sh\n"),
        "hooks/hooks.json": (F, b"{}"),
        "logo.png": (F, b"\x89PNG\x00"),
        "escape": ("120000", b"../../etc"),
        "inside": ("120000", b"skills"),
        "commands/x.md": (F, b"Run !`ls` and see https://a.example.invalid\n"),
    }
    found = kinds(risk.compare({}, candidate))
    assert {
        "executable",
        "hook",
        "binary",
        "symlink-escape",
        "shell-command",
        "network-endpoint",
        "license-missing",
    } <= found


def test_mcp_changes() -> None:
    def mcp(servers: dict) -> bytes:
        return json.dumps({"mcpServers": servers}).encode()

    old = {".mcp.json": (F, mcp({"a": {"command": "x"}, "b": {"command": "y"}}))}
    new = {".mcp.json": (F, mcp({"a": {"command": "z"}, "c": {"command": "w"}}))}
    found = risk.compare(old, new)
    assert kinds(found) >= {
        "mcp-server-added",
        "mcp-server-changed",
        "mcp-server-removed",
    }
    changed = next(f for f in found if f.kind == "mcp-server-changed")
    assert "command" in changed.detail


def test_license_and_allowed_tools() -> None:
    skill = "---\nname: s\nallowed-tools: Read\n---\nbody\n"
    old = {
        "plugin.json": (F, b'{"license": "MIT"}'),
        "LICENSE": (F, b"MIT"),
        "NOTICE": (F, b"n"),
        "skills/s/SKILL.md": (F, skill.encode()),
    }
    new = {
        "plugin.json": (F, b'{"license": "GPL-3.0"}'),
        "LICENSE": (F, b"GPL"),
        "skills/s/SKILL.md": (F, skill.replace("Read", "Bash").encode()),
    }
    found = kinds(risk.compare(old, new))
    assert {"license-changed", "license-removed", "allowed-tools"} <= found


def test_metadata_only_change() -> None:
    old = {"plugin.json": (F, b'{"version": "1", "license": "MIT"}')}
    new = {"plugin.json": (F, b'{"version": "2", "license": "MIT"}')}
    assert "metadata-only" in kinds(risk.compare(old, new))
    body = {"skills/s/SKILL.md": (F, b"---\nname: s\n---\nnew body\n")}
    assert "metadata-only" not in kinds(
        risk.compare(
            {**old, "skills/s/SKILL.md": (F, b"---\nname: s\n---\nold\n")},
            {**new, **body},
        )
    )


def test_known_urls_are_not_flagged_again() -> None:
    old = {"README.md": (F, b"see https://a.example.invalid\n")}
    new = {"README.md": (F, b"see https://a.example.invalid\nmore\n")}
    assert "network-endpoint" not in kinds(risk.compare(old, new))


def test_render() -> None:
    assert risk.render([]) == "No risk flags."
    flag = risk.RiskFlag(kind="hook", path="a|b", line=3, detail="x|y")
    text = risk.render([flag])
    assert "| `hook` | `a|b` | 3 | x\\|y |" in text
