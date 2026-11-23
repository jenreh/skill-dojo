"""Phase 2 end to end: adopt an existing marketplace, add it to a consumer repo."""

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
    adopt,
    build,
    lock_refresh,
    marketplace_add,
    marketplace_update,
    validate,
)
from skill_dojo_core.catalogs import compact_dumps
from tests.support.fixture_repos import FixtureRepos, git, skill_md

MakeContext = Callable[..., Context]
PIN = ToolPin(git="0" * 40)
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
INTERFACE = {
    "displayName": "Team Core",
    "shortDescription": "Core skills",
    "longDescription": "Core skills.",
    "category": "Productivity",
    "brandColor": "#4476AF",
    "developerName": "Team",
    "composerIcon": "./assets/team.svg",
    "logo": "./assets/team.svg",
}


def legacy_marketplace(fixture_repos: FixtureRepos, mcp_args: list[str]) -> Path:
    """A hand-made marketplace like jenreh/agent-skills before adoption."""
    manifest = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "team-core",
        "description": "Core skills.",
        "version": "0.5.0",
        "author": {"name": "Team"},
        "license": "MIT",
        "extensions": {"com.openai": {"interface": INTERFACE}},
    }
    claude = {
        "name": "team",
        "owner": {"name": "Team", "url": "https://example.invalid/team"},
        "metadata": {"description": "Team skills."},
        "plugins": [
            {
                "name": "team-core",
                "source": "./plugins/team-core",
                "description": "Core skills.",
                "version": "0.5.0",
                "author": {"name": "Team"},
                "license": "MIT",
            }
        ],
    }
    agents = {
        "name": "team",
        "interface": {"displayName": "Team skills"},
        "plugins": [
            {
                "name": "team-core",
                "source": {"source": "local", "path": "./plugins/team-core"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }
        ],
    }
    mcp = {
        "$schema": MCP_SCHEMA,
        "mcpServers": {"docs": {"type": "stdio", "command": "npx", "args": mcp_args}},
    }
    stub = (
        'interface:\n  display_name: "Greet"\n  icon_small: "./assets/team.svg"\n'
        "policy:\n  allow_implicit_invocation: true\n"
    )
    remote = fixture_repos.create(
        "team-skills",
        {
            "assets/team.svg": "<svg/>",
            "plugins/team-core/.claude-plugin/plugin.json": json.dumps(
                manifest, indent=2
            )
            + "\n",
            "plugins/team-core/.mcp.json": json.dumps(mcp, indent=2) + "\n",
            "plugins/team-core/assets/team.svg": "<svg/>",
            "plugins/team-core/skills/greet/SKILL.md": skill_md(
                "greet", "Greets the user. Use when saying hello."
            ),
            "plugins/team-core/skills/greet/agents/openai.yaml": stub,
            "plugins/team-core/skills/greet/assets/team.svg": "<svg/>",
            "plugins/team-core/skills/vendored/SKILL.md": skill_md(
                "vendored", "Copied from upstream. Use for testing."
            ),
            "plugins/team-core/skills/vendored/agents/openai.yaml": stub,
            "plugins/team-core/skills/vendored/assets/team.svg": "<svg/>",
            "plugins/team-core/skills/vendored/LICENSE": "Apache-2.0\n",
            ".claude-plugin/marketplace.json": compact_dumps(claude) + "\n",
            ".agents/plugins/marketplace.json": json.dumps(agents, indent=2) + "\n",
        },
    )
    work = remote.work
    (work / "plugins/team-core/plugin.json").symlink_to(".claude-plugin/plugin.json")
    (work / "plugins/team-core/mcp.json").symlink_to(".mcp.json")
    (work / "skills").mkdir()
    for name in ("greet", "vendored"):
        (work / "skills" / name).symlink_to(f"../plugins/team-core/skills/{name}")
    remote.commit({}, "layout links")
    return work


def test_adopt_reproduces_catalogs_and_only_adds_metadata(
    fixture_repos: FixtureRepos, make_context: MakeContext
) -> None:
    repo = legacy_marketplace(fixture_repos, ["-y", "docs-mcp"])
    ctx = make_context(repo)
    result = adopt(ctx, tool=PIN, repository="team/skills")
    assert result.marketplace == "team"
    assert result.items == ["team-core"]
    assert [str(f) for f in result.floating_mcp] == [
        "plugins/team-core/.mcp.json: server 'docs': 'docs-mcp' has no version"
    ]
    assert [f.path for f in result.possibly_vendored] == [
        "plugins/team-core/skills/vendored"
    ]
    tracked = sorted(git(repo, "diff", "--name-only").splitlines())
    assert tracked == [
        "plugins/team-core/.claude-plugin/plugin.json",
        "plugins/team-core/skills/greet/SKILL.md",
        "plugins/team-core/skills/vendored/SKILL.md",
    ]
    diff = git(repo, "diff", "--", "plugins/team-core/.claude-plugin/plugin.json")
    removed = [
        line
        for line in diff.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]
    assert removed == []
    found = [str(e) for e in validate(ctx).errors]
    assert len(found) == 1
    assert "floats" in found[0]
    assert build(ctx, check=True).changed == []
    config = (repo / "registry/config.yaml").read_text()
    for text in (
        "manifest_symlinks: true",
        "flat_skills: true",
        "icon: assets/team.svg",
    ):
        assert text in config


def test_adopt_then_pin_and_refresh_is_valid(
    fixture_repos: FixtureRepos, make_context: MakeContext
) -> None:
    repo = legacy_marketplace(fixture_repos, ["-y", "docs-mcp"])
    ctx = make_context(repo)
    adopt(ctx, tool=PIN)
    mcp = repo / "plugins/team-core/.mcp.json"
    mcp.write_text(mcp.read_text().replace('"docs-mcp"', '"docs-mcp@1.2.3"'))
    lock_refresh(ctx)
    assert validate(ctx).errors == []


def test_adopt_errors(fixture_repos: FixtureRepos, make_context: MakeContext) -> None:
    _, clone = fixture_repos.curated()
    with pytest.raises(NotFoundError, match="plugins"):
        adopt(make_context(clone), tool=PIN)
    repo = legacy_marketplace(fixture_repos, ["pkg@1.0.0"])
    adopt(make_context(repo), tool=PIN)
    with pytest.raises(ConflictError):
        adopt(make_context(repo), tool=PIN)


def test_marketplace_add_update_and_refusals(
    fixture_repos: FixtureRepos, make_context: MakeContext
) -> None:
    market = fixture_repos.create(
        "market",
        {"skills/greet/SKILL.md": skill_md("greet", "Greets. Use when saying hello.")},
    )
    market.tag("marketplace-v2026.11.21")
    _, consumer = fixture_repos.curated("consumer")
    ctx = make_context(consumer)
    result = marketplace_add(ctx, market.url, ref="marketplace-v2026.11.21")
    assert result.prefix == ".agents/market"
    assert sorted(result.links) == [".agents/skills", ".claude/skills"]
    assert (consumer / ".claude/skills/greet/SKILL.md").is_file()
    assert (consumer / ".agents/skills/greet/SKILL.md").is_file()
    assert git(consumer, "status", "--porcelain") == ""
    with pytest.raises(ConflictError, match="marketplace update"):
        marketplace_add(ctx, market.url)
    market.commit({"skills/new/SKILL.md": skill_md("new", "New. Use when new.")})
    updated = marketplace_update(ctx, market.url, ref="main")
    assert updated.links == []
    assert (consumer / ".agents/market/skills/new/SKILL.md").is_file()
    (consumer / "README.md").write_text("dirty\n")
    with pytest.raises(ConflictError, match="dirty"):
        marketplace_update(ctx, market.url)


def test_marketplace_input_checks(
    fixture_repos: FixtureRepos, make_context: MakeContext
) -> None:
    _, consumer = fixture_repos.curated("consumer2")
    ctx = make_context(consumer)
    with pytest.raises(InvalidInputError):
        marketplace_add(ctx, "https://x.invalid/a.git", ref="--upload-pack=evil")
    for url in ("--evil", "ext::sh -c touch% /tmp/pwned", "/abs/path", "http://x/y"):
        with pytest.raises(InvalidInputError, match="URL"):
            marketplace_add(ctx, url)
    with pytest.raises(InvalidInputError):
        marketplace_add(ctx, "https://x.invalid/a.git", name="../up")
    with pytest.raises(ConflictError, match="marketplace add"):
        marketplace_update(ctx, "https://x.invalid/a.git")


def test_adopt_fails_before_writing(
    fixture_repos: FixtureRepos, make_context: MakeContext
) -> None:
    repo = legacy_marketplace(fixture_repos, ["pkg@1.0.0"])
    (repo / "plugins/zz-empty").mkdir()
    with pytest.raises(InvalidInputError, match="zz-empty"):
        adopt(make_context(repo), tool=PIN)
    assert not (repo / "registry").exists()
    assert git(repo, "status", "--porcelain") == ""
    (repo / "plugins/zz-empty").rmdir()
    (repo / ".agents/plugins/marketplace.json").write_text("{broken")
    with pytest.raises(InvalidInputError, match="broken"):
        adopt(make_context(repo), tool=PIN)
    assert not (repo / "registry").exists()


def test_marketplace_checks_links_before_the_subtree(
    fixture_repos: FixtureRepos, make_context: MakeContext
) -> None:
    market = fixture_repos.create("mk", {"skills/a/SKILL.md": "x\n"})
    remote, consumer = fixture_repos.curated("cons")
    (consumer / ".claude/skills").mkdir(parents=True)
    (consumer / ".claude/skills/own.md").write_text("mine\n")
    remote_head = git(consumer, "rev-parse", "HEAD")
    with pytest.raises(ConflictError, match="dirty"):
        marketplace_add(make_context(consumer), market.url)
    git(consumer, "add", ".claude")
    git(consumer, "commit", "-q", "-m", "own skills")
    with pytest.raises(ConflictError, match="not a link"):
        marketplace_add(make_context(consumer), market.url)
    assert not (consumer / ".agents/mk").exists()
    assert git(consumer, "rev-list", "--count", f"{remote_head}..HEAD") == "1"
