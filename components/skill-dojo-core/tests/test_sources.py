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
            "metadata": {"pluginRoot": "./packs"},
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
                {"name": "e", "source": "./plugins/e", "strict": False, "commands": []},
                {
                    "name": "f",
                    "source": {
                        "source": "github",
                        "repo": "o/f",
                        "ref": "main",
                        "sha": "a" * 40,
                    },
                },
                {"name": "g", "source": "g-plugin"},
                {"name": "h"},
                {"source": "./x"},
                "junk",
            ],
        },
    )
    source = Source(id="s", type=SourceType.CLAUDE_MARKETPLACE, repository="o/r")
    found = {p.name: p for p in sources.list_plugins(source, tmp_path)}
    assert set(found) == {"a", "b", "c", "d", "e", "f", "g", "h"}
    assert "npm" in (found["d"].unsupported or "")
    assert "commands" in (found["e"].unsupported or "")
    assert found["f"].ref == "a" * 40
    assert found["g"].path == "packs/g-plugin"
    assert found["h"].unsupported == "no source"
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


def test_relative_url_source_is_local_and_bad_remote_is_unsupported(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        ".agents/plugins/marketplace.json",
        {
            "plugins": [
                {"name": "root", "source": {"source": "url", "url": "./"}},
                {"name": "sub", "source": {"source": "url", "url": "./plugins/s"}},
                {"name": "bad", "source": {"source": "github", "repo": "nope"}},
            ]
        },
    )
    source = Source(id="s", type=SourceType.AGENT_PLUGINS_MARKETPLACE, repository="o/r")
    found = {p.name: p for p in sources.list_plugins(source, tmp_path)}
    assert (found["root"].path, found["root"].repository) == (".", "o/r")
    assert found["root"].unsupported is None
    assert found["sub"].path == "plugins/s"
    assert "nope" in (found["bad"].unsupported or "")


def test_catalogs_merge_when_repo_ships_both(tmp_path: Path) -> None:
    write(
        tmp_path,
        ".agents/plugins/marketplace.json",
        {
            "plugins": [
                {"name": "a", "source": {"source": "local", "path": "./plugins/a"}},
                {"name": "x", "source": {"source": "local", "path": "./plugins/x"}},
            ]
        },
    )
    write(
        tmp_path,
        ".claude-plugin/marketplace.json",
        {
            "plugins": [
                {"name": "a", "source": "./plugins/a", "version": "9"},
                {"name": "b", "source": "./plugins/b"},
            ]
        },
    )
    source = Source(id="s", type=SourceType.AGENT_PLUGINS_MARKETPLACE, repository="o/r")
    found = {p.name: p for p in sources.list_plugins(source, tmp_path)}
    assert set(found) == {"a", "b", "x"}
    assert found["a"].version is None
    claude = source.model_copy(update={"type": SourceType.CLAUDE_MARKETPLACE})
    assert sources.list_plugins(claude, tmp_path)[0].version == "9"
    pinned = source.model_copy(
        update={"marketplace_path": ".claude-plugin/marketplace.json"}
    )
    assert [p.name for p in sources.list_plugins(pinned, tmp_path)] == ["a", "b"]


def test_plain_git_plugins(tmp_path: Path) -> None:
    write(
        tmp_path, "plugins/p/.claude-plugin/plugin.json", {"name": "p", "version": "2"}
    )
    source = Source(id="g", type=SourceType.GIT, repository="o/r")
    assert [(p.name, p.version) for p in sources.list_plugins(source, tmp_path)] == [
        ("p", "2")
    ]


def single_plugin_repo(root: Path) -> None:
    write(
        root,
        ".claude-plugin/plugin.json",
        {"name": "mlflow", "version": "1.0.0", "skills": ["./a", "./packs"]},
    )
    for rel in ("a/SKILL.md", "packs/b/SKILL.md", "skills/c/SKILL.md", "x/SKILL.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("---\nname: s\n---\n")


@pytest.mark.parametrize("kind", [SourceType.GIT, SourceType.CLAUDE_MARKETPLACE])
def test_root_manifest_is_one_plugin(tmp_path: Path, kind: SourceType) -> None:
    single_plugin_repo(tmp_path)
    source = Source(id="mlflow-skills", type=kind, repository="o/r")
    [plugin] = sources.list_plugins(source, tmp_path)
    assert (plugin.name, plugin.path, plugin.version) == ("mlflow", ".", "1.0.0")
    assert sources.describe(plugin, tmp_path).contents == "3 skills"


def test_explicit_catalog_path_does_not_fall_back(tmp_path: Path) -> None:
    single_plugin_repo(tmp_path)
    source = Source(
        id="s",
        type=SourceType.CLAUDE_MARKETPLACE,
        repository="o/r",
        marketplace_path=".claude-plugin/marketplace.json",
    )
    with pytest.raises(NotFoundError):
        sources.list_plugins(source, tmp_path)


@pytest.mark.parametrize(
    ("repository", "url"),
    [
        ("https://github.com/o/r", "https://github.com/o/r"),
        ("https://github.com/o/r.git", "https://github.com/o/r"),
        ("https://registry.example.org/", "https://registry.example.org/"),
        ("o/r", "https://github.com/o/r"),
        ("git@github.com:o/r.git", "https://github.com/o/r"),
        ("ssh://git@gitlab.com/g/r.git", "https://gitlab.com/g/r"),
        ("file:///tmp/x.git", ""),
        ("", ""),
    ],
)
def test_web_url(repository: str, url: str) -> None:
    assert sources.web_url(repository) == url


def test_normalize_repository() -> None:
    github = "https://github.com/anthropics/skills"
    assert sources.normalize_repository("anthropics/skills") == github
    assert sources.normalize_repository(" anthropics/skills ") == github
    assert sources.normalize_repository("github.com/anthropics/skills") == github
    assert sources.normalize_repository(f"{github}.git") == f"{github}.git"
    assert (
        sources.normalize_repository("git@github.com:o/r.git")
        == "git@github.com:o/r.git"
    )
    assert sources.normalize_repository("file:///tmp/x.git") == "file:///tmp/x.git"
    for bad in ("", "skills", "a/b/c", "-o/r", "http//x"):
        with pytest.raises(InvalidInputError):
            sources.normalize_repository(bad)


def test_marketplace_version(tmp_path: Path) -> None:
    source = Source(id="s", type=SourceType.CLAUDE_MARKETPLACE, repository="o/r")
    assert sources.marketplace_version(source, tmp_path) is None
    write(tmp_path, ".claude-plugin/marketplace.json", {"plugins": [], "version": "2"})
    assert sources.marketplace_version(source, tmp_path) == "2"
    write(
        tmp_path,
        ".claude-plugin/marketplace.json",
        {"plugins": [], "version": "2", "metadata": {"version": "1.5.0"}},
    )
    assert sources.marketplace_version(source, tmp_path) == "1.5.0"
    git = Source(id="g", type=SourceType.GIT, repository="o/r")
    assert sources.marketplace_version(git, tmp_path) is None
