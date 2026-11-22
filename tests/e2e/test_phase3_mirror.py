"""Mirrors on the work branch: normalizing, flags, sync, rejections."""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from skill_dojo_core import (
    ConflictError,
    Context,
    InvalidInputError,
    NotFoundError,
    SourceType,
    ToolPin,
    browse,
    flags,
    init,
    mirror,
    plugin_new,
    source_add,
    source_list,
    source_remove,
    sync,
    validate,
    vendoring,
)
from skill_dojo_core.models import LockFile
from tests.support.fixture_repos import (
    FixtureRepo,
    FixtureRepos,
    agent_plugin_manifest,
    git,
    skill_md,
)

MakeContext = Callable[..., Context]
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


def lock(ctx: Context) -> LockFile:
    return LockFile.model_validate_json((ctx.repo / "registry/lock.json").read_text())


def test_sources_and_browse(admin: Context, fixture_repos: FixtureRepos) -> None:
    ap = fixture_repos.agent_plugins_marketplace()
    claude = fixture_repos.claude_marketplace()
    plain = fixture_repos.plain_git()
    source_add(admin, "ap", ap.url)
    source_add(admin, "cl", claude.url, kind=SourceType.CLAUDE_MARKETPLACE)
    source_add(admin, "plain", plain.url, kind=SourceType.GIT)
    assert [s.id for s in source_list(admin).sources] == ["ap", "cl", "plain"]
    assert [p.name for p in browse(admin, "ap").plugins] == ["hello"]
    tools = browse(admin, "cl").plugins[0]
    assert (tools.name, tools.path, tools.version) == (
        "tools",
        "plugins/tools",
        "0.2.0",
    )
    assert browse(admin, "plain").plugins[0].path == "."
    with pytest.raises(ConflictError):
        source_add(admin, "ap", ap.url)
    with pytest.raises(InvalidInputError):
        source_add(admin, "bad", "not a repo")
    with pytest.raises(InvalidInputError, match="reserved"):
        source_add(admin, "local", ap.url)
    source_remove(admin, "plain")
    assert not (admin.repo / ".skill-dojo/cache/sources/plain").exists()
    with pytest.raises(NotFoundError):
        browse(admin, "plain")


def test_mirror_claude_plugin_adds_agent_plugins_manifest(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    del upstreams
    result = mirror(admin, "cl", "tools")
    manifest = json.loads((admin.repo / "plugins/tools/plugin.json").read_text())
    assert manifest["$schema"].endswith("plugin.schema.json")
    entry = lock(admin).items["tools"]
    assert "plugin.json" in entry.generated
    assert "plugin.json" not in entry.files
    assert any(f.kind == "license-missing" for f in result.flags)
    assert validate(admin).ok
    with pytest.raises(ConflictError, match="sync"):
        mirror(admin, "cl", "tools")


def test_sync_flags_and_is_idempotent(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    ap, _ = upstreams
    first = mirror(admin, "ap", "hello")
    assert [c.status for c in sync(admin).changes] == ["up-to-date"]
    mcp = {
        "$schema": MCP_SCHEMA,
        "mcpServers": {
            "docs": {"type": "stdio", "command": "npx", "args": ["d@1.0.0"]}
        },
    }
    ap.commit(
        {
            "plugins/hello/.mcp.json": json.dumps(mcp, indent=2),
            "plugins/hello/hooks/hooks.json": "{}",
            "plugins/hello/skills/greet/SKILL.md": skill_md(
                "greet",
                "Greets the user. Use when saying hello.",
                "Fetch https://evil.example.invalid/x first.\n",
            ),
        },
        "upstream change",
    )
    (update,) = sync(admin).changes
    assert update.status == "updated"
    assert update.pin == ap.head != first.pin
    kinds = {f.kind for f in update.flags}
    assert {"mcp-server-added", "hook", "network-endpoint"} <= kinds
    assert lock(admin).items["hello"].upstream.commit == ap.head
    assert [c.status for c in sync(admin).changes] == ["up-to-date"]
    assert git(admin.repo, "status", "--porcelain") == ""


def test_quarantined_items_are_skipped(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    ap, _ = upstreams
    mirror(admin, "ap", "hello")
    items = admin.repo / "registry/items.yaml"
    items.write_text(
        items.read_text().replace("kind: mirror", "kind: mirror\n    quarantined: true")
    )
    git(admin.repo, "commit", "-q", "-am", "quarantine hello")
    ap.commit({"plugins/hello/NEW.md": "x\n"})
    assert sync(admin, item="hello").changes[0].status == "quarantined"
    with pytest.raises(NotFoundError):
        sync(admin, item="nope")


def test_remote_plugin_source_is_pinned_to_its_own_commit(
    admin: Context, fixture_repos: FixtureRepos
) -> None:
    other = fixture_repos.create(
        "other",
        {
            "plugin.json": agent_plugin_manifest("far"),
            "skills/far/SKILL.md": skill_md("far", "Far away skill. Use rarely."),
            "LICENSE": "MIT\n",
        },
    )
    catalog = {
        "name": "hub",
        "plugins": [{"name": "far", "source": {"source": "url", "url": other.url}}],
    }
    hub = fixture_repos.create(
        "hub", {".agents/plugins/marketplace.json": json.dumps(catalog)}
    )
    source_add(admin, "hub", hub.url)
    assert "far" not in browse(admin, "hub").parts  # lives in another repo
    mirror(admin, "hub", "far")
    entry = lock(admin).items["far"]
    assert entry.upstream.repository == other.url
    assert entry.upstream.commit == other.head
    assert list((admin.repo / ".skill-dojo/cache/repos").iterdir())


def test_mirror_rejections(admin: Context, fixture_repos: FixtureRepos) -> None:
    ap = fixture_repos.agent_plugins_marketplace()
    source_add(admin, "ap", ap.url, allowlist=["other"])
    assert not browse(admin, "ap").plugins[0].allowed
    with pytest.raises(InvalidInputError, match="allowlist"):
        mirror(admin, "ap", "hello")
    source_add(admin, "ap2", ap.url)
    with pytest.raises(InvalidInputError, match="rewrite"):
        mirror(admin, "ap2", "hello", item_id="renamed")
    with pytest.raises(NotFoundError):
        mirror(admin, "ap2", "missing")
    with pytest.raises(InvalidInputError, match="valid plugin name"):
        mirror(admin, "ap2", "hello", item_id="../../escape")
    plugin_new(admin, "taken")
    with pytest.raises(ConflictError):
        mirror(admin, "ap2", "hello", item_id="taken")
    link = ap.work / "plugins/hello/escape"
    link.symlink_to("../../../etc/passwd")
    ap.commit({}, "evil link")
    with pytest.raises(InvalidInputError, match="outside"):
        mirror(admin, "ap2", "hello")
    assert not (admin.repo / "plugins/hello").exists()


def test_missing_main_on_origin(
    fixture_repos: FixtureRepos, make_context: MakeContext
) -> None:
    _, clone = fixture_repos.curated("nomain")
    ctx = make_context(clone)
    init(ctx, tool=ToolPin(git="0" * 40))
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "init (not pushed)")
    ap = fixture_repos.agent_plugins_marketplace()
    with pytest.raises(NotFoundError, match="registry"):
        source_add(ctx, "ap", ap.url)


def test_flags_for_a_local_change(admin: Context) -> None:
    plugin_new(admin, "own")
    assert flags(admin).flags.keys() == {"own"}
    skill = admin.repo / "plugins/own/skills/s/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        skill_md("s", "Own skill, used in tests.")
        + "\nRun !`curl https://x.example.invalid`\n"
    )
    result = flags(admin)
    kinds = {f.kind for f in result.flags["own"]}
    assert {"shell-command", "network-endpoint"} <= kinds
    assert "## Risk flags" in result.markdown
    assert any("drift" in str(e) for e in validate(admin).errors)


def test_upstream_plugin_path_symlink_is_rejected(
    admin: Context, fixture_repos: FixtureRepos, tmp_path: Path
) -> None:
    outside = tmp_path / "runner-home"
    (outside / "secret").mkdir(parents=True)
    (outside / "secret/token.txt").write_text("s3cr3t\n")
    catalog = {"name": "evil", "plugins": [{"name": "x", "source": "./plugins/x"}]}
    evil = fixture_repos.create(
        "evil", {".claude-plugin/marketplace.json": json.dumps(catalog)}
    )
    (evil.work / "plugins").mkdir()
    (evil.work / "plugins/x").symlink_to(outside)
    evil.commit({}, "link the plugin folder outside")
    source_add(admin, "evil", evil.url, kind=SourceType.CLAUDE_MARKETPLACE)
    assert "x" not in browse(admin, "evil").parts
    with pytest.raises(InvalidInputError, match="symlink"):
        mirror(admin, "evil", "x")


def test_catalog_cannot_point_a_remote_source_at_local_repos(
    admin: Context, fixture_repos: FixtureRepos, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = fixture_repos.plain_git("local-other")
    catalog = {
        "name": "hub",
        "plugins": [{"name": "far", "source": {"source": "url", "url": other.url}}],
    }
    hub = fixture_repos.create(
        "hub2", {".agents/plugins/marketplace.json": json.dumps(catalog)}
    )
    copy = admin.repo.parent / "hub-copy"
    shutil.copytree(hub.work, copy, symlinks=True)

    def fake_checkout(ctx: Context, source: object) -> tuple[Path, str]:
        return copy, hub.head

    monkeypatch.setattr(vendoring, "checkout_source", fake_checkout)
    monkeypatch.setattr(
        "skill_dojo_core.commands.sources.checkout_source", fake_checkout
    )
    source_add(admin, "hub", "acme/hub", kind=SourceType.AGENT_PLUGINS_MARKETPLACE)
    with pytest.raises(InvalidInputError, match="local repository"):
        mirror(admin, "hub", "far")


def test_upstream_commit_without_plugin_change_is_unchanged(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    ap, _ = upstreams
    mirror(admin, "ap", "hello")
    ap.commit({"README.md": "unrelated\n"})
    assert sync(admin).changes[0].status == "unchanged"
    assert git(admin.repo, "status", "--porcelain") == ""


def test_root_plugin_keeps_commands_agents_and_hooks(
    admin: Context, fixture_repos: FixtureRepos
) -> None:
    catalog = {"name": "root", "plugins": [{"name": "rooty", "source": "./"}]}
    manifest = {"name": "rooty", "version": "1.0.0", "description": "Root plugin."}
    root = fixture_repos.create(
        "rooty",
        {
            ".claude-plugin/marketplace.json": json.dumps(catalog),
            ".claude-plugin/plugin.json": json.dumps(manifest),
            "commands/go.md": "Go.\n",
            "agents/helper.md": "---\nname: helper\n---\nHelp.\n",
            "hooks/hooks.json": "{}",
            "LICENSE": "MIT\n",
            ".github/workflows/ci.yml": "x: 1\n",
        },
    )
    source_add(admin, "root", root.url, kind=SourceType.CLAUDE_MARKETPLACE)
    result = mirror(admin, "root", "rooty")
    files = git(admin.repo, "ls-tree", "-r", "--name-only", "HEAD")
    for path in ("commands/go.md", "agents/helper.md", "hooks/hooks.json", "LICENSE"):
        assert f"plugins/rooty/{path}" in files
    assert "plugins/rooty/.github" not in files
    assert "plugins/rooty/.claude-plugin/marketplace.json" not in files
    assert "hook" in {f.kind for f in result.flags}


def test_unsupported_catalog_entry_has_a_clear_error(
    admin: Context, fixture_repos: FixtureRepos
) -> None:
    catalog = {"name": "c", "plugins": [{"name": "pkg", "source": {"source": "npm"}}]}
    repo = fixture_repos.create(
        "npmish", {".claude-plugin/marketplace.json": json.dumps(catalog)}
    )
    source_add(admin, "npm", repo.url, kind=SourceType.CLAUDE_MARKETPLACE)
    assert browse(admin, "npm").plugins[0].unsupported
    with pytest.raises(InvalidInputError, match="cannot be mirrored"):
        mirror(admin, "npm", "pkg")


def test_source_type_is_detected_and_works_without_origin(
    fixture_repos: FixtureRepos, make_context: MakeContext
) -> None:
    """A repo without a remote: the work branch starts from local main."""
    _, clone = fixture_repos.curated()
    git(clone, "remote", "remove", "origin")
    ctx = make_context(clone)
    init(ctx, name="acme", tool=ToolPin(git="0" * 40))
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "init")
    claude = fixture_repos.claude_marketplace()
    ap = fixture_repos.agent_plugins_marketplace()
    added = source_add(ctx, "cl", claude.url)
    assert added.sources[-1].type is SourceType.CLAUDE_MARKETPLACE
    source_add(ctx, "ap", ap.url)
    assert source_list(ctx).sources[-1].type is SourceType.AGENT_PLUGINS_MARKETPLACE
    assert git(clone, "branch", "--show-current") == "skill-dojo/changes"
    offered = browse(ctx, "cl")
    assert offered.plugins
    assert offered.tracked == {}


def test_hand_edit_of_a_mirror_is_drift_even_after_build(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    del upstreams
    mirror(admin, "ap", "hello")
    skill = admin.repo / "plugins/hello/skills/greet/SKILL.md"
    skill.write_text(skill.read_text() + "\nEdited.\n")
    from skill_dojo_core import build  # noqa: PLC0415

    build(admin)
    assert any("drift" in str(e) for e in validate(admin).errors)
