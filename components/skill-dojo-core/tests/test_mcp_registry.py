from pathlib import Path

import pytest

from skill_dojo_core import mcp_registry as reg
from skill_dojo_core.errors import ExternalToolError, InvalidInputError, NotFoundError


def package(**data: object) -> reg.Package:
    return reg.Package.model_validate({"transport": {"type": "stdio"}, **data})


def test_check_url() -> None:
    assert reg.check_url("https://r.example/") == "https://r.example"
    assert reg.check_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    for bad in (
        "http://r.example",
        "ftp://r.example",
        "https://u:p@r.example",
        "https://r.example/?x=1",
        "https://",
    ):
        with pytest.raises(InvalidInputError):
            reg.check_url(bad)


def test_default_item_id() -> None:
    assert reg.default_item_id("io.github.acme/Weather_MCP") == "weather-mcp"
    with pytest.raises(InvalidInputError, match="--as"):
        reg.default_item_id("io.github.acme/___")


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        ({"registryType": "cargo", "identifier": "x", "version": "1"}, "cargo"),
        ({"registryType": "npm", "identifier": "x", "version": "latest"}, "exact"),
        ({"registryType": "npm", "identifier": "x", "version": "1.x"}, "exact"),
        ({"registryType": "npm", "identifier": "x"}, "exact"),
        ({"registryType": "pypi", "identifier": "-x", "version": "1"}, "PyPI"),
        (
            {
                "registryType": "pypi",
                "identifier": "x",
                "version": "1",
                "registryBaseUrl": "https://test.pypi.org",
            },
            "another index",
        ),
        ({"registryType": "oci", "identifier": "Bad/Image"}, "image reference"),
        ({"registryType": "oci", "identifier": "acme/img"}, "no tag"),
        ({"registryType": "oci", "identifier": "a/../b:1"}, "image reference"),
    ],
)
def test_unpinnable_packages(data: dict[str, object], reason: str) -> None:
    with pytest.raises(InvalidInputError, match=reason):
        reg.pin(package(**data))


def test_non_stdio_and_first_usable_package() -> None:
    remote = package(
        registryType="npm",
        identifier="x",
        version="1.0.0",
        transport={"type": "sse", "url": "https://x"},
    )
    entry = reg.ServerEntry(
        name="a/b",
        version="1",
        packages=[remote, package(registryType="pypi", identifier="b", version="1.0")],
    )
    chosen = reg.choose(entry)
    assert isinstance(chosen, reg.Package)
    assert chosen.registry_type == "pypi"
    assert reg.unsupported(entry) is None
    only_remote = reg.ServerEntry(name="a/b", version="1", packages=[remote])
    assert "not stdio" in str(reg.unsupported(only_remote))


def test_pin_keeps_a_given_digest_without_network() -> None:
    digest = "sha256:" + "a" * 64
    pinned = reg.pin(package(registryType="oci", identifier=f"ghcr.io/acme/x@{digest}"))
    assert pinned.reference == f"ghcr.io/acme/x@{digest}"
    assert pinned.pin == f"oci:ghcr.io/acme/x@{digest}"


def test_api_base_and_challenge() -> None:
    assert reg._api_base("docker.io") == "https://registry-1.docker.io"
    assert reg._api_base("ghcr.io") == "https://ghcr.io"
    assert reg._api_base("localhost:5000") == "http://localhost:5000"
    header = 'Bearer realm="https://auth.example/token",service="reg",scope="pull"'
    assert reg._challenge(header) == {
        "realm": "https://auth.example/token",
        "service": "reg",
        "scope": "pull",
    }
    assert reg._challenge("Basic realm=x") == {}


def test_arguments() -> None:
    args = [
        reg.Argument(type="positional", value="serve"),
        reg.Argument(type="named", name="--port", value="8080"),
        reg.Argument(type="named", name="--debug"),
        reg.Argument(type="positional", value_hint="data dir", is_required=True),
        reg.Argument(type="positional", value_hint="optional"),
    ]
    assert reg._arguments(args) == ["serve", "--port", "8080", "${DATA_DIR}"]


def test_server_config_skips_bad_env_names() -> None:
    pkg = package(
        registryType="pypi",
        identifier="x",
        version="1.0",
        environmentVariables=[{"name": "OK_1"}, {"name": "$(rm -rf)"}],
    )
    config = reg.server_config(pkg, reg.pin(pkg))
    assert config["env"] == {"OK_1": "${OK_1}"}


def test_bad_responses() -> None:
    with pytest.raises(ExternalToolError, match="no 'server'"):
        reg._entry({"servers": []})
    with pytest.raises(ExternalToolError, match="bad server entry"):
        reg._entry({"server": {"name": "a/b"}})
    with pytest.raises(InvalidInputError, match="server name"):
        reg.get_server("https://r.example", "../etc")


def test_is_repository() -> None:
    assert reg.is_repository("https://github.com/acme/mcp")
    assert reg.is_repository("https://git.example/acme/mcp.git")
    assert reg.is_repository("file:///tmp/mcp.git")
    assert reg.is_repository("git@github.com:acme/mcp.git")
    assert not reg.is_repository("https://registry.modelcontextprotocol.io")


def remote(**data: object) -> reg.Remote:
    return reg.Remote.model_validate({"type": "streamable-http", **data})


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        ({"type": "websocket", "url": "https://x"}, "not supported"),
        ({"url": "http://x.example"}, "https"),
        ({"url": "https://u:p@x.example"}, "credentials"),
        ({"url": "https://{tenant}.example"}, "variables"),
    ],
)
def test_unusable_remotes(data: dict[str, object], reason: str) -> None:
    entry = reg.ServerEntry(name="a/b", version="1", remotes=[remote(**data)])
    assert reason in str(reg.unsupported(entry, remotes=True))


def test_remotes_only_count_for_a_pinned_server_json() -> None:
    entry = reg.ServerEntry(name="a/b", version="1", remotes=[remote(url="https://x")])
    assert "remote-only" in str(reg.unsupported(entry))
    assert reg.choose(entry, remotes=True) == entry.remotes[0]
    empty = reg.ServerEntry(name="a/b", version="1")
    assert "no package and no remote" in str(reg.unsupported(empty, remotes=True))


def test_remote_config_headers() -> None:
    config = reg.remote_config(
        remote(
            type="sse",
            url="https://x.example/sse",
            headers=[
                {"name": "Authorization", "value": "Bearer ${TOKEN}"},
                {"name": "X-Org", "value": "{org_id}"},
                {"name": "X-Key", "isRequired": True},
                {"name": "X-Optional"},
                {"name": "bad header", "value": "x"},
            ],
        )
    )
    assert config == {
        "type": "sse",
        "url": "https://x.example/sse",
        "headers": {
            "Authorization": "Bearer ${TOKEN}",
            "X-Org": "${ORG_ID}",
            "X-Key": "${X_KEY}",
        },
    }


def test_read_server_file(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError, match=r"server\.json"):
        reg.read_server_file(tmp_path)
    (tmp_path / "server.json").write_text("{", encoding="utf-8")
    with pytest.raises(InvalidInputError, match="unreadable"):
        reg.read_server_file(tmp_path)
    (tmp_path / "server.json").write_text(
        '{"name": "bad name", "version": "1"}', encoding="utf-8"
    )
    with pytest.raises(InvalidInputError, match="not an MCP server name"):
        reg.read_server_file(tmp_path)
