import json
from pathlib import Path

import pytest

from skill_dojo_core.models import Branding, Layout, Namespace, RegistryConfig, ToolPin
from skill_dojo_core.validation import plugins, skills
from skill_dojo_core.validation.report import Collector

SCHEMA = plugins.PLUGIN_SCHEMA
MCP = plugins.MCP_SCHEMA


def manifest(tmp_path: Path, data: object, name: str = "p") -> Path:
    plugin = tmp_path / "plugins" / name
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "plugin.json").write_text(json.dumps(data))
    return plugin


def messages(rep: Collector, level: str = "error") -> str:
    return "\n".join(f.message for f in rep.findings if f.level == level)


def test_manifest_rules(tmp_path: Path) -> None:
    plugin = manifest(
        tmp_path,
        {
            "$schema": "wrong",
            "name": "Other",
            "version": 1,
            "keywords": "x",
            "author": {"name": "a", "phone": "1"},
            "extensions": {"bad": 1},
            "dependencies": [],
            "mystery": True,
        },
    )
    rep = Collector()
    plugins.check_manifest(tmp_path, plugin, Layout(), rep)
    errors = messages(rep)
    for text in (
        "$schema",
        "violates the spec pattern",
        "!= directory name",
        "'version' must be a string",
        "'keywords'",
        "author.phone",
        "reverse-domain",
        "extensions.bad must be an object",
    ):
        assert text in errors
    warnings = messages(rep, "warning")
    assert "Claude Code field" in warnings
    assert "unknown top-level field 'mystery'" in warnings


def test_manifest_missing_and_not_object(tmp_path: Path) -> None:
    rep = Collector()
    empty = tmp_path / "plugins" / "q"
    empty.mkdir(parents=True)
    plugins.check_manifest(tmp_path, empty, Layout(), rep)
    assert "missing" in messages(rep)
    rep = Collector()
    plugins.check_manifest(tmp_path, manifest(tmp_path, [1]), Layout(), rep)
    assert "top level must be an object" in messages(rep)
    rep = Collector()
    plugins.check_manifest(
        tmp_path, manifest(tmp_path, {"$schema": SCHEMA}), Layout(), rep
    )
    assert "'name' is required" in messages(rep)


def test_manifest_symlink_escape(tmp_path: Path) -> None:
    plugin = tmp_path / "plugins" / "p"
    plugin.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (plugin / "plugin.json").symlink_to(outside)
    rep = Collector()
    plugins.check_manifest(tmp_path, plugin, Layout(), rep)
    assert "outside the plugin root" in messages(rep)


def test_two_manifests(tmp_path: Path) -> None:
    plugin = manifest(tmp_path, {"$schema": SCHEMA, "name": "p", "version": "1"})
    (plugin / ".claude-plugin").mkdir()
    (plugin / ".claude-plugin/plugin.json").write_text('{"name": "p", "version": "2"}')
    rep = Collector()
    plugins.check_manifest(tmp_path, plugin, Layout(), rep)
    assert "'version' differs" in messages(rep)
    rep = Collector()
    plugins.check_manifest(tmp_path, plugin, Layout(manifest_symlinks=True), rep)
    assert "not the same file" in messages(rep)


@pytest.mark.parametrize(
    ("server", "expected"),
    [
        ("nope", "must be an object"),
        ({"type": "ws"}, "expected one of"),
        ({"type": "stdio"}, "missing required 'command'"),
        ({"type": "stdio", "command": "", "url": "x"}, "not allowed for stdio"),
        ({"type": "stdio", "command": ""}, "empty 'command'"),
        ({"type": "stdio", "command": "x", "args": "a"}, "args must be"),
        ({"type": "stdio", "command": "x", "env": []}, "env must be an object"),
        ({"type": "stdio", "command": "x", "env": {"PLUGIN_ROOT": "a"}}, "redefine"),
        ({"type": "stdio", "command": "x", "env": {"A": 1}}, "env.A must be"),
        ({"type": "stdio", "command": "x", "cwd": "/srv"}, "cwd must start"),
        ({"type": "sse", "url": "u", "headers": []}, "headers must be"),
        ({"type": "sse", "url": "u", "headers": {"a": 1}}, "header values"),
        ({"type": "stdio", "command": "npx", "args": ["pkg"]}, "floats"),
    ],
)
def test_server_rules(server: object, expected: str) -> None:
    rep = Collector()
    plugins.check_server("mcp.json", "s", server, rep)
    assert expected in messages(rep)


def test_mcp_file_rules(tmp_path: Path) -> None:
    plugin = manifest(tmp_path, {})
    (plugin / ".mcp.json").write_text("{}")
    rep = Collector()
    plugins.check_mcp(tmp_path, plugin, Layout(), rep)
    assert "missing next to .mcp.json" in messages(rep)
    (plugin / "mcp.json").write_text(json.dumps({"extra": 1, "mcpServers": []}))
    rep = Collector()
    plugins.check_mcp(tmp_path, plugin, Layout(mcp_symlink=True), rep)
    errors = messages(rep)
    assert "not the same file as .mcp.json" in errors
    assert "$schema" in errors
    assert "'extra' is not allowed" in errors
    assert "'mcpServers' is required" in errors


def test_openai_interface_icons(tmp_path: Path) -> None:
    ext = {"com.openai": {"interface": {"logo": "../x.svg", "composerIcon": "./a.svg"}}}
    plugin = manifest(tmp_path, {"extensions": ext})
    rep = Collector()
    plugins.check_openai_interface(tmp_path, plugin, rep)
    errors = messages(rep)
    assert "must stay inside" in errors
    assert "'./a.svg' not found" in errors


def test_catalog_rules(tmp_path: Path) -> None:
    plugin = manifest(tmp_path, {"name": "p", "version": "1.0.0"})
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin/marketplace.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {"name": "p", "source": "./x", "version": "2"},
                    {"name": "p"},
                    {"name": "ghost"},
                ]
            }
        )
    )
    (tmp_path / ".agents/plugins").mkdir(parents=True)
    (tmp_path / ".agents/plugins/marketplace.json").write_text(
        json.dumps({"plugins": [{"name": "p", "source": "x"}, {"name": "ghost"}]})
    )
    rep = Collector()
    plugins.check_claude_catalog(tmp_path, [plugin], rep)
    plugins.check_agents_catalog(tmp_path, [plugin], rep)
    errors = messages(rep)
    for text in (
        "listed twice",
        "source is",
        "version",
        "'ghost' has no plugins/ghost",
        "missing policy.installation",
        "missing category",
    ):
        assert text in errors


def test_catalog_missing_and_broken(tmp_path: Path) -> None:
    rep = Collector()
    plugins.check_agents_catalog(tmp_path, [], rep)
    assert "missing" in messages(rep)
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin/marketplace.json").write_text("{bad")
    rep = Collector()
    plugins.check_claude_catalog(tmp_path, [], rep)
    assert messages(rep)
    (tmp_path / ".claude-plugin/marketplace.json").write_text('{"plugins": {}}')
    rep = Collector()
    plugins.check_claude_catalog(tmp_path, [], rep)
    assert "must be an array" in messages(rep)


def config(**extra: object) -> RegistryConfig:
    return RegistryConfig(
        name="acme",
        namespace=Namespace.from_name("acme"),
        tool=ToolPin(version="1.0.0"),
        **extra,  # ty: ignore[invalid-argument-type]
    )


def skill(tmp_path: Path, text: str, name: str = "greet") -> Path:
    folder = tmp_path / "plugins/p/skills" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(text)
    return folder


def test_skill_rules(tmp_path: Path) -> None:
    long = "x" * 1600
    folder = skill(
        tmp_path,
        "---\nname: other\ndescription: short <b>\nallowed-tools: Bash, Read\n"
        "metadata:\n  acme.registry/id: 3\n  author: me\n  count: 4\n---\n"
        "python scripts/run.py\n" + "line\n" * 501,
    )
    (folder / "openai.yaml").write_text("")
    rep = Collector()
    skills.validate_skill(tmp_path, folder, config(), rep)
    errors, warnings = messages(rep), messages(rep, "warning")
    assert "!= folder name" in errors
    assert "too short" in errors
    assert "belongs in agents/openai.yaml" in errors
    assert "'acme.registry/id' must be a string" in errors
    assert "&lt;" in warnings
    assert "every Bash command" in warnings
    assert "cwd" in warnings
    assert "'author' is not namespaced" in warnings
    assert "'count' must be a string" in warnings
    assert "lines" in warnings
    folder2 = skill(tmp_path, f"---\nname: big\ndescription: {long}\n---\n", "big")
    rep = Collector()
    skills.validate_skill(tmp_path, folder2, config(), rep)
    assert "truncates" in messages(rep)


def test_skill_missing_parts(tmp_path: Path) -> None:
    rep = Collector()
    folder = tmp_path / "plugins/p/skills/none"
    folder.mkdir(parents=True)
    skills.validate_skill(tmp_path, folder, config(), rep)
    assert "no SKILL.md" in messages(rep)
    for text, expected in (
        ("no frontmatter", "missing"),
        ("---\nmetadata: 1\n---\n", "missing 'name'"),
    ):
        rep = Collector()
        skills.validate_skill(tmp_path, skill(tmp_path, text, "bad"), config(), rep)
        assert expected in messages(rep)
    rep = Collector()
    skills.validate_skill(
        tmp_path, skill(tmp_path, "---\nname: bad\n---\n", "bad"), config(), rep
    )
    assert "missing 'description'" in messages(rep)


def test_openai_yaml_rules(tmp_path: Path) -> None:
    folder = skill(
        tmp_path,
        "---\nname: greet\ndescription: Greets the user politely.\n"
        "disable-model-invocation: true\n---\n",
    )
    cfg = config(branding=Branding())
    rep = Collector()
    skills.validate_skill(tmp_path, folder, cfg, rep)
    assert "no agents/openai.yaml" in messages(rep)
    (folder / "agents").mkdir()
    (folder / "agents/openai.yaml").write_text(
        'interface:\n  short_description: "' + "y" * 70 + '"\n'
        '  icon_small: "./assets/i.svg"\n'
    )
    rep = Collector()
    skills.validate_skill(tmp_path, folder, cfg, rep)
    assert "icon_small" in messages(rep)
    warnings = messages(rep, "warning")
    assert "Codex may auto-invoke" in warnings
    assert "short_description" in warnings


def test_flat_view(tmp_path: Path) -> None:
    skill(tmp_path, "---\nname: greet\n---\n")
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills/gone").symlink_to("../plugins/p/skills/gone")
    rep = Collector()
    skills.check_flat_view(tmp_path, rep)
    errors = messages(rep)
    assert "broken link" in errors
    assert "missing link" in errors
