"""Phase 8 end to end: the whole flow on one work branch, plus the migration.

add source (cached) -> browse -> mirror whole plugin -> parts into a new
plugin -> plugin new + hand-added skill + build -> finish (one PR, versions)
-> merge -> a fresh work branch -> sync reuses the open work branch -> release.
"""

import json
import os
from pathlib import Path

import pytest

from skill_dojo_core import (
    ConflictError,
    Context,
    NotFoundError,
    add_parts,
    browse,
    build,
    finish,
    mirror,
    plugin_new,
    release,
    remove_parts,
    set_version,
    source_add,
    status,
    sync,
    validate,
)
from skill_dojo_core.models import ItemKind, ItemsFile, LockFile
from skill_dojo_core.registry import ITEMS, LOCK, model_at
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import FixtureRepo, FixtureRepos, git, skill_md

WORK = "skill-dojo/changes"


def branch(ctx: Context) -> str:
    return git(ctx.repo, "branch", "--show-current")


def subjects(ctx: Context, since: str = "origin/main") -> list[str]:
    out = git(ctx.repo, "log", "--format=%s", f"{since}..HEAD")
    return out.splitlines()[::-1]


def version(ctx: Context, item: str, ref: str | None = None) -> str:
    rel = f"plugins/{item}/plugin.json"
    if ref is None:
        return json.loads((ctx.repo / rel).read_text())["version"]
    return json.loads(git(ctx.repo, "show", f"{ref}:{rel}"))["version"]


def merge_pr(ctx: Context, fake_github: FakeGitHub, number: int) -> None:
    assert fake_github.merge(number)
    git(ctx.repo, "fetch", "-q", "origin")


def test_the_whole_flow_on_one_work_branch(  # noqa: PLR0915 (one scenario)
    admin: Context,
    fixture_repos: FixtureRepos,
    fake_github: FakeGitHub,
    upstreams: tuple[FixtureRepo, ...],
) -> None:
    ap, cl = upstreams
    # Adding the sources moved the checkout onto the work branch.
    assert branch(admin) == WORK
    assert subjects(admin) == ["skill-dojo: source add ap", "skill-dojo: source add cl"]
    cache = admin.repo / ".skill-dojo"
    assert (cache / ".gitignore").read_text() == "*\n"
    assert git(admin.repo, "status", "--porcelain") == ""

    offered = browse(admin, "ap")
    assert offered.cached
    assert [p.name for p in offered.plugins] == ["hello"]
    assert [(p.kind, p.name) for p in offered.parts["hello"]] == [("skill", "greet")]

    mirrored = mirror(admin, "ap", "hello")
    assert (mirrored.status, mirrored.pin) == ("added", ap.head)
    assert mirrored.commit == git(admin.repo, "rev-parse", "HEAD")

    kit = add_parts(
        admin,
        "kit",
        ["ap:hello/skill/greet", "cl:tools/skill/lint"],
        create=True,
        description="Team kit.",
    )
    assert kit.status == "created"
    assert (admin.repo / "plugins/kit/skills/greet/SKILL.md").is_file()
    assert (admin.repo / "plugins/kit/skills/lint/SKILL.md").is_file()

    plugin_new(admin, "own", description="Our own skills.")
    (admin.repo / "plugins/own/skills/tidy").mkdir(parents=True)
    (admin.repo / "plugins/own/skills/tidy/SKILL.md").write_text(
        skill_md("tidy", "Tidies code. Use when cleaning up.")
    )
    build(admin)
    assert validate(admin).ok, validate(admin).errors
    assert [s.removeprefix("skill-dojo: ") for s in subjects(admin)][2:] == [
        f"mirror hello {ap.head[:12]}",
        "add-parts kit skill/greet, skill/lint",
        "plugin new own",
    ]

    done = finish(admin)
    assert done.status == "opened"
    assert done.pull_request is not None
    pr = fake_github.get(done.pull_request.number)
    assert (pr.head, pr.base) == (WORK, "main")
    versions = {p.item: p for p in done.pending}
    assert versions["hello"].branch_version == "1.0.0"  # upstream version kept
    assert not versions["hello"].editable
    assert versions["own"].branch_version == "0.1.0"
    assert versions["kit"].branch_version == "0.1.0"
    assert "| `hello` | mirror | added |" in pr.body
    assert "## Risk flags" in pr.body
    assert subjects(admin)[-1] == "skill-dojo: finish"
    assert git(admin.repo, "rev-parse", f"origin/{WORK}") == git(
        admin.repo, "rev-parse", "HEAD"
    )
    # A second finish updates the same PR; there is only one.
    assert finish(admin).status == "updated"
    assert len(fake_github.pulls) == 1

    merge_pr(admin, fake_github, pr.number)
    released = release(admin)
    assert released.status == "created"
    assert released.tag == "marketplace-v2026.11.21"
    assert fake_github.releases[0][0] == released.tag
    assert "Added:" in released.notes

    # The old branch is merged: the next change starts again from main.
    plugin_new(admin, "other")
    assert branch(admin) == WORK
    assert subjects(admin) == ["skill-dojo: plugin new other"]

    # Upstream moves; sync commits onto the same branch and finish updates a PR.
    ap.commit(
        {
            "plugins/hello/skills/greet/SKILL.md": skill_md(
                "greet", "Greets the user warmly. Use when saying hello."
            )
        }
    )
    synced = sync(admin)
    assert [(c.item, c.status) for c in synced.changes] == [
        ("hello", "updated"),
        ("kit", "updated"),
    ]
    assert synced.refreshed == ["ap", "cl"]
    assert subjects(admin)[-2:] == ["skill-dojo: sync hello", "skill-dojo: sync kit"]
    assert [c.status for c in sync(admin).changes] == ["up-to-date", "up-to-date"]
    second = finish(admin)
    assert second.status == "opened"
    pending = {p.item: p for p in second.pending}
    assert pending["kit"].main_version == "0.1.0"
    assert pending["kit"].branch_version == "0.1.1"
    assert pending["kit"].level == "patch"
    assert "hello" in pending
    assert "own" not in pending
    state = status(admin)
    assert state.on_branch
    assert state.pull_request is not None
    assert state.ahead >= 3

    # A chosen level wins over the automatic patch bump.
    set_version(admin, "kit", level="minor")
    assert version(admin, "kit") == "0.2.0"
    build(admin)
    assert version(admin, "kit") == "0.2.0"
    assert validate(admin).ok


def test_status_without_a_work_branch(admin: Context) -> None:
    state = status(admin)
    assert (state.exists, state.on_branch, state.pending) == (False, False, [])
    assert finish(admin).status == "nothing"


def test_unpushed_work_branch_is_kept(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    del upstreams
    head = git(admin.repo, "rev-parse", "HEAD")
    git(admin.repo, "checkout", "-q", "main")
    plugin_new(admin, "x")
    assert git(admin.repo, "rev-parse", "HEAD~1") == head


def test_old_repo_with_bundles_and_approvals_migrates(admin: Context) -> None:
    plugin_new(admin, "kit")
    items = admin.repo / "registry/items.yaml"
    items.write_text(
        items.read_text().replace("kind: local", "kind: bundle")
        + "    supported_channels: [beta, stable]\n"
    )
    lock = admin.repo / "registry/lock.json"
    lock.write_text(lock.read_text().replace('"kind": "local"', '"kind": "bundle"'))
    policy = admin.repo / "registry/channel-policy.yaml"
    policy.write_text(
        policy.read_text()
        + "reviewers:\n  restricted: 2\nchannels:\n  beta:\n    branch: staging\n"
    )
    (admin.repo / "registry/approvals.yaml").write_text("approvals: []\n")
    changed = build(admin).changed
    assert "registry/approvals.yaml" in changed
    assert "kind: local" in items.read_text()
    assert "supported_channels" not in items.read_text()
    assert "channels" not in policy.read_text()
    assert '"kind": "local"' in lock.read_text()
    assert not (admin.repo / "registry/approvals.yaml").exists()
    assert build(admin).changed == []
    assert validate(admin).ok
    # The migrated files are exactly what the tool writes today.
    assert git(admin.repo, "status", "--porcelain") == ""
    assert model_at(admin.repo, "HEAD", ITEMS, ItemsFile).get("kit") is not None
    assert model_at(admin.repo, "HEAD", LOCK, LockFile).items["kit"].kind is (
        ItemKind.LOCAL
    )


def test_cache_is_reused_and_refreshed(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    ap, _ = upstreams
    first = browse(admin, "ap")
    assert first.cached
    assert first.commit == ap.head
    ap.commit({"plugins/hello/skills/wave/SKILL.md": skill_md("wave", "Waves.")})
    assert browse(admin, "ap").commit == first.commit  # from the cache
    old = admin.repo / ".skill-dojo/cache/sources/ap" / first.commit
    fresh = browse(admin, "ap", refresh=True)
    assert old.is_dir()  # just used: kept, a command may still read it
    os.utime(old, (0, 0))
    os.utime(old / "checkout", (0, 0))
    browse(admin, "ap", refresh=True)
    assert (fresh.cached, fresh.commit) == (False, ap.head)
    assert {p.name for p in fresh.parts["hello"]} == {"greet", "wave"}
    folders = list((admin.repo / ".skill-dojo/cache/sources/ap").iterdir())
    assert sorted(p.name for p in folders) == sorted([ap.head, "current.json"])


def test_hook_parts(admin: Context, fixture_repos: FixtureRepos) -> None:
    hooks = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/guard.sh",
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/x.sh"}
                    ]
                }
            ],
        }
    }
    manifest = {"name": "guards", "version": "1.0.0", "description": "Guards."}
    catalog = {"name": "g", "plugins": [{"name": "guards", "source": "./guards"}]}
    up = fixture_repos.create(
        "guards-up",
        {
            ".claude-plugin/marketplace.json": json.dumps(catalog),
            "guards/.claude-plugin/plugin.json": json.dumps(manifest),
            "guards/hooks/hooks.json": json.dumps(hooks),
            "guards/scripts/guard.sh": "#!/bin/sh\nexit 0\n",
        },
    )
    source_add(admin, "g", up.url)
    assert {(p.kind, p.name) for p in browse(admin, "g").parts["guards"]} == {
        ("hook", "PreToolUse"),
        ("hook", "Stop"),
    }
    add_parts(admin, "safety", ["g:guards/hook/PreToolUse"], create=True)
    root = admin.repo / "plugins/safety"
    written = json.loads((root / "hooks/hooks.json").read_text())
    assert list(written["hooks"]) == ["PreToolUse"]
    assert (root / "scripts/guard.sh").read_text().startswith("#!/bin/sh")
    with pytest.raises(ConflictError, match="already has"):
        add_parts(admin, "safety", ["g:guards/hook/PreToolUse"])
    with pytest.raises(NotFoundError, match="missing upstream"):
        add_parts(admin, "safety", ["g:guards/hook/Stop"])
    remove_parts(admin, "safety", ["hook/PreToolUse"])
    assert not (root / "hooks/hooks.json").exists()
    assert not (root / "scripts/guard.sh").exists()
    assert validate(admin).ok


def test_finish_merges_what_sync_pushed(
    admin: Context,
    fixture_repos: FixtureRepos,
    fake_github: FakeGitHub,
    upstreams: tuple[FixtureRepo, ...],
    tmp_path: Path,
) -> None:
    ap, _ = upstreams
    mirror(admin, "ap", "hello")
    finish(admin)
    # The scheduled sync runs in another clone and pushes to the work branch.
    assert fake_github.remote is not None
    other = fixture_repos.clone(
        FixtureRepo("curated", fake_github.remote, tmp_path), "ci"
    )
    ci = Context(repo=other, github=fake_github, actor="bot", now=admin.now)
    ap.commit({"plugins/hello/NOTES.md": "new\n"})
    sync(ci)
    finish(ci)
    plugin_new(admin, "mine")
    result = finish(admin)
    assert result.status == "updated"
    files = git(admin.repo, "ls-tree", "-r", "--name-only", f"origin/{WORK}")
    assert "plugins/hello/NOTES.md" in files
    assert "plugins/mine/.claude-plugin/plugin.json" in files
    assert len([p for p in fake_github.pulls if p.state == "OPEN"]) == 1


def test_dirty_tree_off_the_work_branch_stops(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    del upstreams
    git(admin.repo, "checkout", "-q", "main")
    (admin.repo / "notes.txt").write_text("draft\n")
    with pytest.raises(ConflictError, match=r"notes\.txt"):
        plugin_new(admin, "x")
    assert branch(admin) == "main"
