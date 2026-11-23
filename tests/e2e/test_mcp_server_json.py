"""An MCP Registry source that is a git repo: its ``server.json`` is the server."""

import json

import pytest

from skill_dojo_core import Context, SourceType, add_parts, browse, mirror, source_add
from skill_dojo_core.errors import NotFoundError
from tests.support.fixture_repos import FixtureRepo, FixtureRepos

NAME = "com.atlassian/atlassian-mcp-server"
REMOTE_ONLY = {
    "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
    "name": NAME,
    "description": "Connect to Atlassian Jira and Confluence.",
    "version": "2.0.0",
    "repository": {"url": "https://github.com/atlassian/atlassian-mcp-server"},
    "remotes": [
        {
            "type": "streamable-http",
            "url": "https://mcp.atlassian.com/v2/mcp",
            "headers": [{"name": "X-Tenant", "value": "{tenant}"}],
        },
    ],
}


@pytest.fixture
def server_repo(admin: Context, fixture_repos: FixtureRepos) -> FixtureRepo:
    repo = fixture_repos.create(
        "atlassian", {"server.json": json.dumps(REMOTE_ONLY), "README.md": "x\n"}
    )
    source_add(admin, "atl", repo.url, kind=SourceType.MCP_REGISTRY)
    return repo


def read(ctx: Context, path: str) -> dict:
    return json.loads((ctx.repo / path).read_text())


EXPECTED = {
    "type": "http",
    "url": "https://mcp.atlassian.com/v2/mcp",
    "headers": {"X-Tenant": "${TENANT}"},
}


def test_browse_offers_the_server_of_server_json(
    admin: Context,
    server_repo: FixtureRepo,
) -> None:
    result = browse(admin, "atl")
    assert result.commit == server_repo.head
    assert [p.name for p in result.plugins] == [NAME]
    assert result.plugins[0].unsupported is None
    assert [r.name for r in result.parts[NAME]] == ["atlassian-mcp-server"]


def test_part_goes_into_the_plugins_mcp_json(
    admin: Context,
    server_repo: FixtureRepo,
) -> None:
    add_parts(
        admin, "kit", [f"atl:{NAME}/mcp_server/atlassian-mcp-server"], create=True
    )
    servers = read(admin, "plugins/kit/.mcp.json")["mcpServers"]
    assert servers == {"atlassian-mcp-server": EXPECTED}


def test_mirror_pins_a_remote_server_to_the_commit(
    admin: Context,
    server_repo: FixtureRepo,
) -> None:
    made = mirror(admin, "atl", NAME)
    assert made.item == "atlassian-mcp-server"
    assert made.pin == server_repo.head
    servers = read(admin, "plugins/atlassian-mcp-server/.mcp.json")["mcpServers"]
    assert servers == {"atlassian-mcp-server": EXPECTED}


def test_repo_without_server_json_is_refused(
    admin: Context,
    fixture_repos: FixtureRepos,
) -> None:
    repo = fixture_repos.create("empty", {"README.md": "x\n"})
    with pytest.raises(NotFoundError, match=r"server\.json"):
        source_add(admin, "none", repo.url, kind=SourceType.MCP_REGISTRY)
