"""Parts of local plugins, revoke and release on the work branch."""

import json

import pytest

from skill_dojo_core import (
    ConflictError,
    Context,
    ExternalToolError,
    InvalidInputError,
    NotFoundError,
    add_parts,
    finish,
    mirror,
    plugin_new,
    release,
    remove_parts,
    revoke,
    set_version,
    source_add,
    sync,
    validate,
)
from skill_dojo_core.models import ItemLock, LockFile, Part
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import (
    FixtureRepo,
    FixtureRepos,
    agent_plugin_manifest,
    git,
    skill_md,
    write_tree,
)


def lock(ctx: Context) -> LockFile:
    return LockFile.model_validate_json((ctx.repo / "registry/lock.json").read_text())


def ship(ctx: Context, fake_github: FakeGitHub) -> str:
    """finish, merge the PR, release; returns the tag."""
    done = finish(ctx)
    assert done.pull_request is not None
    assert fake_github.merge(done.pull_request.number)
    git(ctx.repo, "fetch", "-q", "origin")
    return release(ctx).tag


def test_parts_from_upstream_agent_mcp_and_local(
    admin: Context, fixture_repos: FixtureRepos
) -> None:
    servers = {
        "mcpServers": {
            "docs": {"type": "stdio", "command": "npx", "args": ["docs@1.2.3"]}
        }
    }
    up = fixture_repos.create(
        "mixed",
        {
            ".agents/plugins/marketplace.json": json.dumps(
                {
                    "name": "mixed",
                    "plugins": [
                        {
                            "name": "box",
                            "source": {"source": "local", "path": "./plugins/box"},
                        }
                    ],
                }
            ),
            "plugins/box/plugin.json": agent_plugin_manifest("box"),
            "plugins/box/agents/rev.md": "---\nname: rev\n---\nReview.\n",
            "plugins/box/.mcp.json": json.dumps(servers),
            "LICENSE": "MIT\n",
        },
    )
    source_add(admin, "mx", up.url)
    plugin_new(admin, "own")
    write_tree(
        admin.repo,
        {
            "plugins/own/skills/note/SKILL.md": skill_md(
                "note", "Takes notes. Use when writing notes."
            )
        },
    )
    with pytest.raises(ConflictError, match="uncommitted"):
        add_parts(admin, "kit", ["local:own/skill/note"], create=True)
    assert not (admin.repo / "plugins/kit").exists()  # rolled back
    git(admin.repo, "add", "-A")
    git(admin.repo, "commit", "-q", "-m", "own skill")
    result = add_parts(
        admin,
        "kit",
        ["mx:box/agent/rev", "mx:box/mcp_server/docs", "local:own/skill/note"],
        create=True,
    )
    root = admin.repo / "plugins/kit"
    assert "Review." in (root / "agents/rev.md").read_text()
    mcp = json.loads((root / ".mcp.json").read_text())
    assert mcp["mcpServers"]["docs"]["args"] == ["docs@1.2.3"]
    assert "MIT" in (root / "licenses/mx-box/LICENSE").read_text()
    assert "mcp-server-added" in {f.kind for f in result.flags}
    parts = {p.name: p for p in lock(admin).items["kit"].parts}
    assert parts["note"].upstream.repository == "acme/market"
    assert parts["docs"].path == "plugins/box/.mcp.json"
    assert validate(admin).ok

    assert (root / "mcp.json").exists()  # generated counterpart
    remove_parts(admin, "kit", ["mcp_server/docs", "agent/rev"])
    assert not (root / ".mcp.json").exists()
    assert not (root / "mcp.json").exists()
    assert "mcp.json" not in lock(admin).items["kit"].files
    assert not (root / "licenses/mx-box/LICENSE").exists()
    assert [p.name for p in lock(admin).items["kit"].parts] == ["note"]
    with pytest.raises(NotFoundError, match="no MCP server"):
        add_parts(admin, "kit", ["mx:box/mcp_server/nope"])
    with pytest.raises(NotFoundError, match="no agent"):
        add_parts(admin, "kit", ["mx:box/agent/nope"])
    with pytest.raises(NotFoundError, match="not a local plugin"):
        add_parts(admin, "kit", ["local:nope/skill/other"])
    with pytest.raises(NotFoundError, match="no source"):
        add_parts(admin, "kit", ["zz:box/agent/rev"])
    with pytest.raises(NotFoundError, match="no plugin"):
        add_parts(admin, "nope", ["mx:box/agent/rev"])
    with pytest.raises(NotFoundError, match="has no part"):
        remove_parts(admin, "kit", ["agent/rev"])
    with pytest.raises(ConflictError, match="already has"):
        add_parts(admin, "kit", ["local:own/skill/note"])
    with pytest.raises(InvalidInputError, match="is not a part"):
        add_parts(admin, "kit", ["box/agent/rev"])
    with pytest.raises(ConflictError, match="already exists"):
        add_parts(admin, "kit", [], create=True)


def test_parts_do_not_overwrite_hand_files_or_mirrors(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    del upstreams
    plugin_new(admin, "own")
    write_tree(
        admin.repo,
        {"plugins/own/skills/greet/SKILL.md": skill_md("greet", "Mine. Use it.")},
    )
    with pytest.raises(ConflictError, match="already has skill"):
        add_parts(admin, "own", ["ap:hello/skill/greet"])
    assert "Mine." in (admin.repo / "plugins/own/skills/greet/SKILL.md").read_text()
    mirror(admin, "ap", "hello")
    with pytest.raises(InvalidInputError, match="mirror"):
        add_parts(admin, "hello", ["cl:tools/skill/lint"])


def test_parts_refuse_symlinked_folders(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    del upstreams
    add_parts(admin, "kit", ["ap:hello/skill/greet"], create=True)
    (admin.repo / "plugins/kit/agents").symlink_to("../../registry")
    with pytest.raises(InvalidInputError, match="symlink"):
        add_parts(admin, "kit", ["cl:tools/skill/lint"])


def test_versions_bump_once_per_branch(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    del upstreams
    add_parts(admin, "kit", ["ap:hello/skill/greet"], create=True)
    ship(admin, fake_github)
    add_parts(admin, "kit", ["cl:tools/skill/lint"])
    manifest = admin.repo / "plugins/kit/.claude-plugin/plugin.json"
    assert json.loads(manifest.read_text())["version"] == "0.1.1"
    remove_parts(admin, "kit", ["skill/lint"])
    add_parts(admin, "kit", ["cl:tools/skill/lint"])
    assert json.loads(manifest.read_text())["version"] == "0.1.1"
    done = finish(admin, levels=["kit=major"])
    assert {p.item: p.branch_version for p in done.pending} == {"kit": "1.0.0"}
    with pytest.raises(InvalidInputError, match="not greater"):
        set_version(admin, "kit", exact="0.0.9")
    with pytest.raises(InvalidInputError, match="exact"):
        set_version(admin, "kit", exact="1.2")
    with pytest.raises(InvalidInputError, match="mirror"):
        mirror(admin, "ap", "hello")
        set_version(admin, "hello", level="patch")
    with pytest.raises(InvalidInputError, match="item=patch"):
        finish(admin, levels=["kit"])


def test_revoke_and_rollback(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    ap, _ = upstreams
    mirror(admin, "ap", "hello")
    first = ship(admin, fake_github)
    ap.commit({"plugins/hello/NEW.md": "new\n"})
    sync(admin, item="hello")
    second = ship(admin, fake_github)
    assert second == "marketplace-v2026.11.21.2"

    rolled = revoke(admin, "hello", to=first)
    assert rolled.action == "rolled-back"
    assert "quarantined: true" in (admin.repo / "registry/items.yaml").read_text()
    first_lock = LockFile.model_validate_json(
        git(admin.repo, "show", f"{first}:registry/lock.json")
    )
    assert (
        lock(admin).items["hello"].tree_sha256 == first_lock.items["hello"].tree_sha256
    )
    assert not (admin.repo / "plugins/hello/NEW.md").exists()
    assert sync(admin, item="hello").changes[0].status == "quarantined"
    with pytest.raises(InvalidInputError):
        revoke(admin, "hello", to="no-such-tag")
    with pytest.raises(ConflictError, match="already at that content"):
        revoke(admin, "hello", to=first)
    removed = revoke(admin, "hello")
    assert removed.action == "removed"
    assert not (admin.repo / "plugins/hello").exists()
    with pytest.raises(NotFoundError):
        revoke(admin, "nope")
    assert validate(admin).ok
    assert release(admin).status == "up-to-date"


def test_lock_and_part_paths_are_validated() -> None:
    with pytest.raises(ValueError, match="relative"):
        ItemLock.model_validate(
            {
                "kind": "bundle",
                "upstream": {"repository": "r", "commit": "c", "path": "p"},
                "treeSha256": "a" * 64,
                "files": {},
                "generated": ["../../etc/passwd"],
            }
        )
    with pytest.raises(ValueError):
        Part(kind="skill", name="s", source="a", upstream_plugin="b/../../..")
    with pytest.raises(ValueError):
        Part(kind="skill", name="../s")
    assert Part(kind="hook", name="PreToolUse").kind == "hook"


def test_failed_command_rolls_back_to_the_uncommitted_edits(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    del upstreams
    plugin_new(admin, "own")  # uncommitted, like every command's changes
    head = git(admin.repo, "rev-parse", "HEAD")
    notes = admin.repo / "NOTES.md"
    notes.write_text("my draft\n")
    with pytest.raises(NotFoundError):
        add_parts(
            admin, "kit", ["ap:hello/skill/greet", "ap:hello/skill/nope"], create=True
        )
    assert not (admin.repo / "plugins/kit").exists()
    items = (admin.repo / "registry/items.yaml").read_text()
    assert "kit" not in items
    assert "own" in items
    assert notes.read_text() == "my draft\n"
    mirror(admin, "ap", "hello")
    assert git(admin.repo, "rev-parse", "HEAD") == head
    finish(admin)
    committed = git(admin.repo, "show", "--name-only", "--format=", "HEAD")
    assert "NOTES.md" in committed
    assert "plugins/own/.claude-plugin/plugin.json" in committed


def test_release_publishes_a_missing_github_release(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    del upstreams
    mirror(admin, "ap", "hello")
    fake_github.release_fails = True
    with pytest.raises(ExternalToolError):
        ship(admin, fake_github)
    fake_github.release_fails = False
    again = release(admin)
    assert again.status == "published"
    assert fake_github.releases[0][0] == again.tag
    assert "Added:" in fake_github.releases[0][2]
    assert release(admin).status == "up-to-date"


def test_work_branch_must_differ_from_main(admin: Context) -> None:
    config = admin.repo / "registry/config.yaml"
    config.write_text(
        config.read_text().replace(
            "work_branch: skill-dojo/changes", "work_branch: main"
        )
    )
    with pytest.raises(InvalidInputError, match="must not be the main branch"):
        plugin_new(admin, "x")
