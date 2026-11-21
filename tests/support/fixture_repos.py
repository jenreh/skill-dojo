"""Build local git repos for end-to-end tests (no network).

Each fixture repo is a bare repo (the "remote") plus a work tree used to author
commits. Core reads the bare repo through its file URL, just like a GitHub remote.
"""

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

FileTree = Mapping[str, str | bytes | None]

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def write_tree(root: Path, files: FileTree) -> None:
    for rel, content in files.items():
        path = root / rel
        if content is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")


@dataclass
class FixtureRepo:
    name: str
    bare: Path
    work: Path

    @property
    def url(self) -> str:
        return self.bare.as_uri()

    @property
    def head(self) -> str:
        return git(self.work, "rev-parse", "HEAD")

    def commit(self, files: FileTree, message: str = "update") -> str:
        write_tree(self.work, files)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", message)
        git(self.work, "push", "-q", "origin", "HEAD")
        return self.head

    def tag(self, name: str) -> None:
        git(self.work, "tag", name)
        git(self.work, "push", "-q", "origin", name)


def skill_md(name: str, description: str, body: str = "Do the thing.\n") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"


def agent_plugin_manifest(name: str, version: str = "1.0.0", **extra: object) -> str:
    data = {
        "$schema": PLUGIN_SCHEMA,
        "name": name,
        "version": version,
        "description": f"The {name} plugin.",
        "license": "MIT",
        **extra,
    }
    return json.dumps(data, indent=2) + "\n"


class FixtureRepos:
    """Factory for fixture repos under one temp directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self, name: str, files: FileTree, branch: str = "main") -> FixtureRepo:
        bare = self.root / "remotes" / f"{name}.git"
        work = self.root / "work" / name
        bare.parent.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        git(bare.parent, "init", "-q", "--bare", "-b", branch, bare.name)
        git(work, "init", "-q", "-b", branch)
        git(work, "remote", "add", "origin", bare.as_uri())
        repo = FixtureRepo(name=name, bare=bare, work=work)
        repo.commit(files, "initial")
        git(work, "branch", "-q", "--set-upstream-to", f"origin/{branch}")
        return repo

    def clone(self, repo: FixtureRepo, name: str) -> Path:
        dest = self.root / "clones" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        git(dest.parent, "clone", "-q", repo.url, name)
        return dest

    def agent_plugins_marketplace(self, name: str = "ap-upstream") -> FixtureRepo:
        catalog = {
            "name": name,
            "plugins": [
                {
                    "name": "hello",
                    "source": {"source": "local", "path": "./plugins/hello"},
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": "Coding",
                }
            ],
        }
        return self.create(
            name,
            {
                ".agents/plugins/marketplace.json": json.dumps(catalog, indent=2),
                "plugins/hello/plugin.json": agent_plugin_manifest("hello"),
                "plugins/hello/skills/greet/SKILL.md": skill_md(
                    "greet", "Greets the user. Use when saying hello."
                ),
                "plugins/hello/LICENSE": "MIT License\n",
            },
        )

    def claude_marketplace(self, name: str = "claude-upstream") -> FixtureRepo:
        catalog = {
            "name": name,
            "owner": {"name": "Upstream"},
            "plugins": [
                {
                    "name": "tools",
                    "source": "./plugins/tools",
                    "description": "Claude tools.",
                    "version": "0.2.0",
                }
            ],
        }
        manifest = {"name": "tools", "version": "0.2.0", "description": "Tools."}
        return self.create(
            name,
            {
                ".claude-plugin/marketplace.json": json.dumps(catalog, indent=2),
                "plugins/tools/.claude-plugin/plugin.json": json.dumps(manifest),
                "plugins/tools/skills/lint/SKILL.md": skill_md(
                    "lint", "Lints code. Use when checking style."
                ),
                "plugins/tools/commands/fmt.md": "Run the formatter.\n",
            },
        )

    def plain_git(self, name: str = "plain-upstream") -> FixtureRepo:
        return self.create(
            name,
            {
                "skills/review/SKILL.md": skill_md(
                    "review", "Reviews code. Use when reviewing a change."
                ),
                "README.md": "Some skills.\n",
            },
        )

    def curated(self, name: str = "curated") -> tuple[FixtureRepo, Path]:
        """An empty curated repo remote and an admin's clone of it."""
        remote = self.create(name, {"README.md": "Curated marketplace.\n"})
        return remote, self.clone(remote, f"{name}-admin")
