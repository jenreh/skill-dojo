import json
from pathlib import Path

import pytest

from skill_dojo_core import InvalidInputError, NotFoundError, sources
from skill_dojo_core.models import Source, SourceType


def test_repo_url() -> None:
    assert sources.repo_url("o/r") == "https://github.com/o/r.git"
    assert sources.repo_url("file:///tmp/x.git") == "file:///tmp/x.git"
    assert sources.repo_url("git@github.com:o/r.git") == "git@github.com:o/r.git"
    for bad in ("ext::sh -c x", "/abs", "o", "http://x/y"):
        with pytest.raises(InvalidInputError):
            sources.repo_url(bad)


def test_safe_path() -> None:
    assert sources.safe_path("./plugins/x") == "plugins/x"
    assert sources.safe_path("./") == "."
    for bad in ("../x", "/etc", "a/../../b"):
        with pytest.raises(InvalidInputError):
            sources.safe_path(bad)


def write(root: Path, rel: str, data: object) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_catalog_entries(tmp_path: Path) -> None:
    write(
        tmp_path,
        ".claude-plugin/marketplace.json",
        {
            "plugins": [
                {"name": "a", "source": "./plugins/a", "version": "1"},
                {
                    "name": "b",
                    "source": {"source": "github", "repo": "o/b", "ref": "v1"},
                },
                {
                    "name": "c",
                    "source": {"source": "url", "url": "https://x.invalid/c.git"},
                },
                {"name": "d", "source": {"source": "npm"}},
                {"source": "./x"},
                "junk",
            ]
        },
    )
    source = Source(id="s", type=SourceType.CLAUDE_MARKETPLACE, repository="o/r")
    found = {p.name: p for p in sources.list_plugins(source, tmp_path)}
    assert set(found) == {"a", "b", "c"}
    assert found["a"].repository == "o/r"
    assert (found["b"].repository, found["b"].ref) == ("o/b", "v1")
    allow = source.model_copy(update={"allowlist": ["a"]})
    assert [p.name for p in sources.list_plugins(allow, tmp_path)] == ["a"]


def test_catalog_errors(tmp_path: Path) -> None:
    source = Source(id="s", type=SourceType.AGENT_PLUGINS_MARKETPLACE, repository="o/r")
    with pytest.raises(NotFoundError):
        sources.list_plugins(source, tmp_path)
    write(tmp_path, ".agents/plugins/marketplace.json", {"plugins": {}})
    with pytest.raises(InvalidInputError):
        sources.list_plugins(source, tmp_path)
    mcp = Source(id="m", type=SourceType.MCP_REGISTRY, repository="o/r")
    with pytest.raises(InvalidInputError, match="no catalog"):
        sources.list_plugins(mcp, tmp_path)


def test_plain_git_plugins(tmp_path: Path) -> None:
    write(
        tmp_path, "plugins/p/.claude-plugin/plugin.json", {"name": "p", "version": "2"}
    )
    source = Source(id="g", type=SourceType.GIT, repository="o/r")
    assert [(p.name, p.version) for p in sources.list_plugins(source, tmp_path)] == [
        ("p", "2")
    ]
