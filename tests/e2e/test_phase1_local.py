"""Phase 1 end to end: init, local add, build, validate, drift."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from skill_dojo_core import (
    ConflictError,
    Context,
    InvalidInputError,
    NotFoundError,
    ToolPin,
    build,
    init,
    local_add,
    lock_refresh,
    validate,
)
from skill_dojo_core.registry import ITEMS, registry_path
from tests.support.fixture_repos import (
    FixtureRepos,
    agent_plugin_manifest,
    skill_md,
    write_tree,
)

PIN = ToolPin(git="0" * 40)
MakeContext = Callable[..., Context]


def errors(ctx: Context) -> list[str]:
    return [str(f) for f in validate(ctx).errors]


@pytest.fixture
def curated(fixture_repos: FixtureRepos, make_context: MakeContext) -> Context:
    _, clone = fixture_repos.curated()
    ctx = make_context(clone)
    init(ctx, name="acme", tool=PIN, repository="acme/marketplace")
    return ctx


def add_plugin(repo: Path, name: str = "hello", **files: str) -> None:
    write_tree(
        repo,
        {
            f"plugins/{name}/plugin.json": agent_plugin_manifest(name),
            f"plugins/{name}/skills/greet/SKILL.md": skill_md(
                "greet", "Greets the user. Use when saying hello."
            ),
            **{f"plugins/{name}/{k}": v for k, v in files.items()},
        },
    )


def test_init_scaffolds_a_valid_empty_marketplace(curated: Context) -> None:
    repo = curated.repo
    for name in ("config.yaml", "items.yaml", "lock.json", "channel-policy.yaml"):
        assert (repo / "registry" / name).is_file()
    workflow = (repo / ".github/workflows/validate-marketplace.yml").read_text()
    assert "uvx --with" in workflow
    assert "@3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert "registry/.lock" in (repo / ".gitignore").read_text()
    catalog = json.loads((repo / ".agents/plugins/marketplace.json").read_text())
    assert catalog == {
        "name": "acme",
        "interface": {"displayName": "acme"},
        "plugins": [],
    }
    assert errors(curated) == []
    assert build(curated, check=True).changed == []


def test_init_twice_conflicts(curated: Context) -> None:
    with pytest.raises(ConflictError):
        init(curated, tool=PIN)


def test_untracked_plugin_fails_until_local_add(curated: Context) -> None:
    add_plugin(curated.repo)
    assert any("not tracked" in e for e in errors(curated))
    result = local_add(curated, "plugins/hello", category="Productivity")
    assert result.item == "hello"
    assert errors(curated) == []
    assert build(curated, check=True).changed == []
    assert build(curated).changed == []
    manifest = json.loads((curated.repo / "plugins/hello/plugin.json").read_text())
    ext = manifest["extensions"]["com.acme.registry"]
    assert ext["registryId"] == "acme:hello"
    assert ext["kind"] == "local"
    assert ext["upstreamMarketplace"] == "acme/marketplace"
    assert ext["sourceDigest"] == result.tree_sha256
    skill = (curated.repo / "plugins/hello/skills/greet/SKILL.md").read_text()
    assert 'acme.registry/id: "acme:hello"' in skill
    assert (curated.repo / "plugins/hello/.claude-plugin/plugin.json").is_file()
    claude = json.loads((curated.repo / ".claude-plugin/marketplace.json").read_text())
    assert claude["plugins"][0]["source"] == "./plugins/hello"
    agents = json.loads((curated.repo / ".agents/plugins/marketplace.json").read_text())
    assert agents["plugins"][0]["category"] == "Productivity"


def test_local_add_errors(curated: Context) -> None:
    with pytest.raises(NotFoundError):
        local_add(curated, "plugins/missing")
    with pytest.raises(InvalidInputError):
        local_add(curated, "registry")
    add_plugin(curated.repo)
    local_add(curated, "plugins/hello")
    with pytest.raises(ConflictError):
        local_add(curated, "plugins/hello")


def test_edit_is_drift_until_lock_refresh(curated: Context) -> None:
    add_plugin(curated.repo)
    local_add(curated, "plugins/hello")
    skill = curated.repo / "plugins/hello/skills/greet/SKILL.md"
    skill.write_text(skill.read_text().replace("Do the thing.", "Do it differently."))
    (curated.repo / "plugins/hello/extra.md").write_text("new\n")
    found = errors(curated)
    assert any("SKILL.md: drift: changed" in e for e in found)
    assert any("extra.md: drift: extra" in e for e in found)
    result = lock_refresh(curated)
    assert result.refreshed == ["hello"]
    assert errors(curated) == []
    assert lock_refresh(curated).unchanged == ["hello"]


def test_stamping_alone_is_not_drift(curated: Context) -> None:
    add_plugin(curated.repo)
    local_add(curated, "plugins/hello")
    skill = curated.repo / "plugins/hello/skills/greet/SKILL.md"
    stamped = skill.read_text()
    skill.write_text(
        stamped.split("metadata:\n")[0] + "---\n" + stamped.split("---\n", 2)[2]
    )
    found = errors(curated)
    assert found
    assert all("drift" not in e for e in found)
    assert any("provenance metadata missing" in e for e in found)
    build(curated)
    assert skill.read_text() == stamped
    assert errors(curated) == []


def test_hand_edits_then_build_are_consistent(curated: Context) -> None:
    add_plugin(curated.repo)
    local_add(curated, "plugins/hello")
    items = registry_path(curated.repo, ITEMS)
    items.write_text(items.read_text() + "    category: Design # hand edit\n")
    catalog = curated.repo / ".agents/plugins/marketplace.json"
    catalog.write_text('{"name": "broken"}')
    assert errors(curated)
    assert build(curated, check=True).changed
    build(curated)
    assert errors(curated) == []
    assert json.loads(catalog.read_text())["plugins"][0]["category"] == "Design"
    assert "# hand edit" in items.read_text()


def test_floating_mcp_reference_fails(curated: Context) -> None:
    mcp = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {
            "docs": {"type": "stdio", "command": "npx", "args": ["-y", "docs-mcp"]}
        },
    }
    add_plugin(curated.repo, **{".mcp.json": json.dumps(mcp)})
    local_add(curated, "plugins/hello")
    assert (curated.repo / "plugins/hello/mcp.json").is_file()
    assert any("floats" in e for e in errors(curated))


def test_lock_refresh_rejects_unknown_and_mirrors(curated: Context) -> None:
    with pytest.raises(NotFoundError):
        lock_refresh(curated, item="nope")
    add_plugin(curated.repo)
    local_add(curated, "plugins/hello")
    items = registry_path(curated.repo, ITEMS)
    items.write_text(items.read_text().replace("kind: local", "kind: mirror"))
    with pytest.raises(InvalidInputError, match="sync"):
        lock_refresh(curated, item="hello")
    assert any("kind differs" in e for e in errors(curated))


def test_layout_and_branding(curated: Context) -> None:
    config = registry_path(curated.repo, "config.yaml")
    (curated.repo / "assets").mkdir()
    (curated.repo / "assets/logo.svg").write_text("<svg/>")
    text = config.read_text().replace(": false", ": true")
    config.write_text(
        text + "branding:\n  icon: assets/logo.svg\n  brand_color: '#123456'\n"
    )
    add_plugin(curated.repo)
    local_add(curated, "plugins/hello")
    plugin = curated.repo / "plugins/hello"
    assert (plugin / ".claude-plugin/plugin.json").is_symlink()
    assert (curated.repo / "skills/greet").is_symlink()
    assert (plugin / "assets/logo.svg").is_file()
    yaml_stub = (plugin / "skills/greet/agents/openai.yaml").read_text()
    assert 'display_name: "Greet"' in yaml_stub
    assert 'brand_color: "#123456"' in yaml_stub
    interface = json.loads((plugin / "plugin.json").read_text())["extensions"][
        "com.openai"
    ]["interface"]
    assert interface["composerIcon"] == "./assets/logo.svg"
    assert interface["displayName"] == "Hello"
    assert errors(curated) == []
    assert build(curated, check=True).changed == []


def test_build_refuses_symlinked_manifest_folder(curated: Context) -> None:
    add_plugin(curated.repo)
    target = curated.repo / ".github"
    (curated.repo / "plugins/hello/.claude-plugin").symlink_to(target)
    with pytest.raises(InvalidInputError, match="symlink"):
        local_add(curated, "plugins/hello")
    assert not (target / "plugin.json").exists()


def test_branding_icon_must_stay_in_repo(curated: Context, tmp_path: Path) -> None:
    secret = tmp_path / "secret.svg"
    secret.write_text("secret")
    config = registry_path(curated.repo, "config.yaml")
    config.write_text(config.read_text() + f"branding:\n  icon: {secret}\n")
    add_plugin(curated.repo)
    with pytest.raises(InvalidInputError, match="outside the repo"):
        local_add(curated, "plugins/hello")
