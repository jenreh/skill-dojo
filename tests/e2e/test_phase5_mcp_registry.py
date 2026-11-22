"""Phase 5 end to end: the MCP Registry as a source, against a fake registry."""

import json
from collections.abc import Callable

import pytest
from pytest_httpserver import HTTPServer

from skill_dojo_core import (
    Context,
    ExternalToolError,
    InvalidInputError,
    NotFoundError,
    SourceType,
    ToolPin,
    browse,
    bundle_create,
    init,
    mirror,
    source_add,
    sync,
)
from skill_dojo_core.models import ItemsFile, LockFile
from skill_dojo_core.registry import ITEMS, model_at
from tests.support.fake_github import FakeGitHub
from tests.support.fake_mcp_registry import FakeMcpRegistry, npm, oci, pypi
from tests.support.fixture_repos import FixtureRepos, git

MakeContext = Callable[..., Context]
WEATHER = "io.github.acme/weather"
FILES = "io.github.acme/files"
SEARCH = "io.github.acme/search"
REMOTE = "com.example/remote-only"


@pytest.fixture
def registry(httpserver: HTTPServer) -> FakeMcpRegistry:
    fake = FakeMcpRegistry(httpserver)
    fake.publish(
        WEATHER,
        "1.0.0",
        [
            npm(
                "@acme/weather-mcp",
                "1.0.0",
                packageArguments=[
                    {"type": "named", "name": "--units", "value": "metric"},
                    {"type": "positional", "valueHint": "city", "isRequired": True},
                ],
                environmentVariables=[
                    {"name": "WEATHER_API_KEY", "isRequired": True, "isSecret": True}
                ],
            )
        ],
        websiteUrl="https://weather.example",
    )
    fake.publish(SEARCH, "2.0.0", [pypi("acme-search-mcp", "2.0.0")])
    fake.publish(
        FILES,
        "0.3.0",
        [oci(f"{fake.host}/mcp/files:0.3.0", environmentVariables=[{"name": "ROOT"}])],
    )
    fake.publish(
        REMOTE, "1.0.0", remotes=[{"type": "streamable-http", "url": "https://x"}]
    )
    return fake


@pytest.fixture
def admin(
    fixture_repos: FixtureRepos,
    make_context: MakeContext,
    fake_github: FakeGitHub,
    registry: FakeMcpRegistry,
) -> Context:
    remote, clone = fixture_repos.curated()
    fake_github.remote = remote.bare
    ctx = make_context(clone)
    init(ctx, name="acme", tool=ToolPin(git="0" * 40), repository="acme/market")
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "init marketplace")
    git(clone, "push", "-q", "origin", "HEAD:main")
    git(clone, "push", "-q", "origin", "HEAD:staging")
    source_add(ctx, "mcp", registry.url, kind=SourceType.MCP_REGISTRY)
    return ctx


def show(ctx: Context, ref: str, path: str) -> str:
    git(ctx.repo, "fetch", "-q", "origin")
    return git(ctx.repo, "show", f"{ref}:{path}")


def staged_lock(ctx: Context) -> LockFile:
    return LockFile.model_validate_json(
        show(ctx, "origin/staging", "registry/lock.json")
    )


def test_browse_lists_servers_and_what_cannot_be_pinned(admin: Context) -> None:
    result = browse(admin, "mcp")
    offered = {p.name: p for p in result.plugins}
    assert sorted(offered) == sorted([WEATHER, FILES, SEARCH, REMOTE])  # 2 pages
    assert offered[WEATHER].version == "1.0.0"
    assert offered[WEATHER].unsupported is None
    assert "remote-only" in str(offered[REMOTE].unsupported)
    assert [p.name for p in browse(admin, "mcp", search="weather").plugins] == [WEATHER]


def test_wrapper_plugin_is_pinned_and_sync_follows_new_versions(
    admin: Context, registry: FakeMcpRegistry, fake_github: FakeGitHub
) -> None:
    made = mirror(admin, "mcp", WEATHER)
    assert made.item == "weather"
    assert made.status == "opened"
    assert made.commit == "npm:@acme/weather-mcp@1.0.0"
    assert made.branch.startswith("candidate/weather/")
    assert {f.kind for f in made.flags} >= {"mcp-server-added"}
    branch = f"origin/{made.branch}"
    servers = json.loads(show(admin, branch, "plugins/weather/.mcp.json"))
    assert servers["mcpServers"]["weather"] == {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@acme/weather-mcp@1.0.0", "--units", "metric", "${CITY}"],
        "env": {"WEATHER_API_KEY": "${WEATHER_API_KEY}"},
    }
    manifest = json.loads(show(admin, branch, "plugins/weather/plugin.json"))
    assert manifest["name"] == "weather"
    assert manifest["version"] == "1.0.0"
    stamp = manifest["extensions"]["com.acme.registry"]
    assert stamp["upstreamCommit"] == "npm:@acme/weather-mcp@1.0.0"
    assert stamp["upstreamPlugin"] == WEATHER
    assert made.pull_request is not None
    assert "Validation errors" not in made.pull_request.body
    assert fake_github.merge(made.pull_request.number)

    lock = staged_lock(admin).items["weather"]
    assert lock.upstream.commit == "npm:@acme/weather-mcp@1.0.0"
    assert lock.upstream.ref == "1.0.0"
    assert [c.status for c in sync(admin).candidates] == ["up-to-date"]

    registry.publish(WEATHER, "1.1.0", [npm("@acme/weather-mcp", "1.1.0")])
    (update,) = sync(admin).candidates
    assert update.status == "opened"
    assert update.commit == "npm:@acme/weather-mcp@1.1.0"
    assert update.pull_request is not None
    assert "was `npm:@acme/weather-mcp@1.0.0`" in update.pull_request.body
    assert {f.kind for f in update.flags} >= {"mcp-server-changed"}


def test_pypi_and_oci_servers_pin_version_and_digest(
    admin: Context, registry: FakeMcpRegistry
) -> None:
    digest = registry.image("mcp/files:0.3.0", {"schemaVersion": 2, "manifests": []})
    searched = mirror(admin, "mcp", SEARCH, item_id="acme-search")
    servers = json.loads(
        show(admin, f"origin/{searched.branch}", "plugins/acme-search/.mcp.json")
    )
    assert servers["mcpServers"]["search"]["args"] == ["acme-search-mcp==2.0.0"]

    kit = bundle_create(admin, "kit", [f"mcp:{FILES}/mcp_server/files"])
    assert kit.status == "opened"
    bundle = json.loads(show(admin, f"origin/{kit.branch}", "plugins/kit/mcp.json"))
    image = f"{registry.host}/mcp/files@{digest}"
    assert bundle["mcpServers"]["files"] == {
        "type": "stdio",
        "command": "docker",
        "args": ["run", "-i", "--rm", "-e", "ROOT", image],
        "env": {"ROOT": "${ROOT}"},
    }
    items = model_at(admin.repo, f"origin/{kit.branch}", ITEMS, ItemsFile)
    kit_item = items.get("kit")
    assert kit_item is not None
    (part,) = kit_item.parts
    assert (part.source, part.upstream_plugin) == ("mcp", FILES)
    assert part.commit == f"oci:{image}"


def test_unpinnable_or_unsafe_servers_are_refused(
    admin: Context, registry: FakeMcpRegistry
) -> None:
    with pytest.raises(InvalidInputError, match="https"):
        source_add(
            admin, "bad", "http://registry.example", kind=SourceType.MCP_REGISTRY
        )
    with pytest.raises(InvalidInputError, match="remote-only"):
        mirror(admin, "mcp", REMOTE)
    registry.publish("io.github.acme/ranged", "1.0.0", [npm("ranged", "^1.0.0")])
    with pytest.raises(InvalidInputError, match="exact version"):
        mirror(admin, "mcp", "io.github.acme/ranged")
    registry.publish(
        "io.github.acme/elsewhere",
        "1.0.0",
        [npm("elsewhere", "1.0.0", registryBaseUrl="https://npm.evil.example")],
    )
    with pytest.raises(InvalidInputError, match="another registry"):
        mirror(admin, "mcp", "io.github.acme/elsewhere")
    registry.publish("io.github.acme/flag", "1.0.0", [npm("--registry=x", "1.0.0")])
    with pytest.raises(InvalidInputError, match="not an npm package"):
        mirror(admin, "mcp", "io.github.acme/flag")
    registry.publish("io.github.acme/gone", "1.0.0", [npm("gone", "1.0.0")])
    registry.status["io.github.acme/gone", "1.0.0"] = "deleted"
    with pytest.raises(NotFoundError, match="deleted"):
        mirror(admin, "mcp", "io.github.acme/gone")
    with pytest.raises(NotFoundError):
        mirror(admin, "mcp", "io.github.acme/unknown")
    registry.image("mcp/files:0.3.0", {"schemaVersion": 2})
    registry.bad_digest.add("mcp/files:0.3.0")
    with pytest.raises(ExternalToolError, match="digest"):
        mirror(admin, "mcp", FILES)
    assert staged_lock(admin).items == {}
