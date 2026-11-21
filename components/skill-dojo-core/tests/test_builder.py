import json
from pathlib import Path

import pytest

from skill_dojo_core import (
    ExternalToolError,
    InvalidInputError,
    builder,
    catalogs,
    git,
    workflows,
)
from skill_dojo_core.models import (
    Item,
    ItemKind,
    Namespace,
    Owner,
    Policy,
    RegistryConfig,
    ToolPin,
)
from skill_dojo_core.overlay import Overlay
from skill_dojo_core.registry import Registry


def test_display_and_short_description() -> None:
    assert builder.display_name("jenreh-core") == "Jenreh Core"
    assert builder.short_description("Does a thing. Then more.") == "Does a thing"
    long = "word " * 30
    short = builder.short_description(long)
    assert len(short) <= 64
    assert short.endswith("…")


def test_with_schema() -> None:
    assert json.loads(builder.with_schema('{"name": "p"}'))["$schema"]
    assert builder.with_schema("not json") == "not json"
    same = '{"$schema": "x"}'
    assert builder.with_schema(same) == same


def test_stub_yaml_quotes_values() -> None:
    text = builder.stub_yaml(
        "a-b",
        '---\nname: a-b\ndescription: Uses a \\\\ path "x".\n'
        "disable-model-invocation: true\n---\n",
        "./assets/i.svg",
        "#fff",
    )
    assert 'display_name: "A B"' in text
    assert "allow_implicit_invocation: false" in text
    assert 'icon_small: "./assets/i.svg"' in text
    assert builder.stub_yaml("x", "no frontmatter", None, None).count("icon") == 0


def config(**extra: object) -> RegistryConfig:
    return RegistryConfig(
        name="acme",
        namespace=Namespace.from_name("acme"),
        tool=ToolPin(version="1.0.0"),
        **extra,  # ty: ignore[invalid-argument-type]
    )


def test_catalogs() -> None:
    item = Item(id="p", kind=ItemKind.LOCAL, policy=Policy(authentication="ON_USE"))
    manifest = {
        "version": "1.0.0",
        "description": "P.",
        "author": {"name": "A"},
        "extensions": {"com.openai": {"interface": {"category": "Design"}}},
    }
    plugin = catalogs.CatalogPlugin(item, manifest)
    agents = json.loads(catalogs.agents_catalog(config(), [plugin]))
    assert agents["plugins"][0] == {
        "name": "p",
        "source": {"source": "local", "path": "./plugins/p"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
        "category": "Design",
    }
    claude_text = catalogs.claude_catalog(
        config(owner=Owner(name="Acme"), description="D"), [plugin]
    )
    claude = json.loads(claude_text)
    assert claude["owner"] == {"name": "Acme"}
    assert claude["metadata"] == {"description": "D"}
    assert claude["plugins"][0]["author"] == {"name": "A"}
    assert '"author": { "name": "A" }' in claude_text
    plain = catalogs.CatalogPlugin(Item(id="q", kind=ItemKind.LOCAL), {})
    assert catalogs.category(plain, config()) == "Coding"


def test_compact_dumps() -> None:
    data = {"a": [{"b": {"c": 1, "d": [1, 2]}}], "e": {}}
    text = catalogs.compact_dumps(data)
    assert json.loads(text) == data
    assert '"c": 1' in text


def test_tool_command() -> None:
    assert workflows.tool_command(ToolPin(version="1.2.3")) == "uvx skill-dojo==1.2.3"
    git_cmd = workflows.tool_command(ToolPin(git="a" * 40))
    assert "subdirectory=components/skill-dojo-core" in git_cmd
    assert git_cmd.endswith(" skill-dojo")
    assert "persist-credentials: false" in workflows.validate_workflow(
        ToolPin(version="1.2.3")
    )


def test_git_head_without_commits(tmp_path: Path) -> None:
    git.run(tmp_path, "init", "-q")
    with pytest.raises(ExternalToolError, match="rev-parse"):
        git.head(tmp_path)
    assert git.run(tmp_path, "rev-parse", "--verify", "HEAD", check=False) == ""


def test_git_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(ExternalToolError, match="not installed"):
        git.run(tmp_path, "status")


def test_flat_skills_conflicts(tmp_path: Path) -> None:
    for plugin in ("a", "b"):
        folder = tmp_path / "plugins" / plugin / "skills/same"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("---\nname: same\n---\n")
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry/config.yaml").write_text(
        "name: acme\nnamespace: {skill: acme.registry/, plugin: com.acme.registry}\n"
        "tool: {version: 1.0.0}\nlayout: {flat_skills: true}\n"
        "branding: null\n"
    )
    (tmp_path / "registry/items.yaml").write_text(
        "items:\n  - {id: a, kind: local}\n  - {id: b, kind: local}\n"
    )
    with pytest.raises(InvalidInputError, match="two plugins"):
        builder.flat_skills(Registry.load(tmp_path), Overlay(tmp_path))


def test_auth_config_forwards_checkout_header(tmp_path: Path) -> None:
    git.run(tmp_path, "init", "-q")
    key = "http.https://github.com/.extraheader"
    git.run(tmp_path, "config", key, "AUTHORIZATION: basic dGVzdA==")
    assert git.auth_config(tmp_path) == ["-c", f"{key}=AUTHORIZATION: basic dGVzdA=="]
