"""Phase 4 end to end: bundles, review, promote, release, revoke and clients."""

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from skill_dojo_core import (
    ConflictError,
    Context,
    InvalidInputError,
    NotFoundError,
    PolicyError,
    bundle_add,
    bundle_create,
    bundle_remove,
    clients_add,
    clients_list,
    clients_remove,
    local_add,
    mirror,
    promote,
    release,
    review_approve,
    review_list,
    review_quarantine,
    review_reject,
    review_show,
    revoke,
    source_add,
    sync,
    validate,
)
from skill_dojo_core.models import ApprovalsFile, Channel, ItemsFile, LockFile, RiskTier
from skill_dojo_core.registry import ITEMS, load_yaml_model, save_yaml_model, yaml_rt
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import (
    FixtureRepo,
    FixtureRepos,
    agent_plugin_manifest,
    git,
    skill_md,
    write_tree,
)

MakeContext = Callable[..., Context]
NS = "com.acme.registry"


def show(ctx: Context, ref: str, path: str) -> str:
    git(ctx.repo, "fetch", "-q", "origin")
    return git(ctx.repo, "show", f"{ref}:{path}")


def yaml_data(text: str) -> object:
    return json.loads(json.dumps(yaml_rt().load(text)))


def number(result: object) -> int:
    pr = getattr(result, "pull_request", None)
    assert pr is not None
    return pr.number


def worktree(ctx: Context, ref: str) -> Path:
    """A detached worktree at ``ref``; the admin's checkout stays as it is."""
    git(ctx.repo, "fetch", "-q", "origin")
    path = ctx.repo.parent / f"wt-{len(list(ctx.repo.parent.iterdir()))}"
    git(ctx.repo, "worktree", "add", "-q", "--detach", str(path), ref)
    return path


def edit_staging(ctx: Context, change: Callable[[str], str], path: str) -> None:
    """A hand edit pushed straight to staging (as an admin might)."""
    wt = worktree(ctx, "origin/staging")
    file = wt / path
    file.write_text(change(file.read_text()))
    git(wt, "commit", "-q", "-am", "hand edit")
    git(wt, "push", "-q", "origin", "HEAD:staging")


def edit_item(ctx: Context, item_id: str, **fields: object) -> None:
    """Change one item's fields in items.yaml on staging."""
    wt = worktree(ctx, "origin/staging")
    items = load_yaml_model(wt, ITEMS, ItemsFile)
    item = items.get(item_id)
    assert item is not None
    for key, value in fields.items():
        setattr(item, key, value)
    save_yaml_model(wt, ITEMS, items)
    git(wt, "commit", "-q", "-am", f"edit {item_id}")
    git(wt, "push", "-q", "origin", "HEAD:staging")


def test_bundle_lifecycle(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    created = bundle_create(
        admin, "kit", ["ap:hello/skill/greet"], description="A starter kit."
    )
    assert created.status == "opened"
    assert created.branch.startswith("candidate/kit/")
    manifest = json.loads(
        show(admin, f"origin/{created.branch}", "plugins/kit/plugin.json")
    )
    assert manifest["version"] == "0.1.0"
    with pytest.raises(ConflictError, match="open"):
        bundle_create(admin, "kit", [])
    # A second add before merging builds on the pending candidate.
    added = bundle_add(admin, "kit", ["cl:tools/skill/lint"])
    assert added.status == "opened"
    assert fake_github.get(number(created)).state == "CLOSED"
    lock = LockFile.model_validate_json(
        show(admin, f"origin/{added.branch}", "registry/lock.json")
    )
    kit = lock.items["kit"]
    assert [(p.kind, p.name) for p in kit.parts] == [
        ("skill", "greet"),
        ("skill", "lint"),
    ]
    assert {p.upstream.repository for p in kit.parts} == {
        upstreams[0].url,
        upstreams[1].url,
    }
    assert "licenses/ap-hello/LICENSE" in kit.files
    skill = show(admin, f"origin/{added.branch}", "plugins/kit/skills/lint/SKILL.md")
    assert f'acme.registry/source-marketplace: "{upstreams[1].url}"' in skill
    assert 'acme.registry/source-path: "plugins/tools/skills/lint"' in skill
    greet = show(admin, f"origin/{added.branch}", "plugins/kit/skills/greet/SKILL.md")
    assert 'acme.registry/source-license: "MIT"' in greet
    body = fake_github.get(number(added)).body
    assert "Validation errors" not in body
    assert "from `ap:hello`" in body
    assert "from `cl:tools`" in body
    with pytest.raises(ConflictError, match="already has"):
        bundle_add(admin, "kit", ["cl:tools/skill/lint"])
    assert review_approve(admin, number(added)).status == "merged"
    removed = bundle_remove(admin, "kit", ["skill/greet"])
    files = show(admin, f"origin/{removed.branch}", "registry/lock.json")
    entry = LockFile.model_validate_json(files).items["kit"]
    assert [p.name for p in entry.parts] == ["lint"]
    assert "licenses/ap-hello/LICENSE" not in entry.files
    assert entry.version == "0.1.1"
    with pytest.raises(NotFoundError):
        bundle_remove(admin, "kit", ["agent/nope"])
    with pytest.raises(InvalidInputError):
        bundle_add(admin, "kit", ["lint"])


def test_bundle_sync_bumps_on_part_change(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    ap, _ = upstreams
    first = bundle_create(admin, "kit", ["ap:hello/skill/greet"])
    review_approve(admin, number(first))
    assert sync(admin, item="kit").candidates[0].status == "up-to-date"
    ap.commit(
        {
            "plugins/hello/skills/greet/SKILL.md": skill_md(
                "greet", "Greets the user. Use when saying hello.", "Run $(whoami).\n"
            )
        }
    )
    update = sync(admin, item="kit").candidates[0]
    assert update.status == "opened"
    assert "shell-command" in {f.kind for f in update.flags}
    lock = LockFile.model_validate_json(
        show(admin, f"origin/{update.branch}", "registry/lock.json")
    )
    assert lock.items["kit"].version == "0.1.1"
    assert lock.items["kit"].parts[0].upstream.commit == ap.head


def test_review_commands(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    candidate = mirror(admin, "ap", "hello")
    other = mirror(admin, "cl", "tools")
    entries = review_list(admin).entries
    assert [(e.item, e.pull_request.number) for e in entries] == [
        ("hello", number(candidate)),
        ("tools", number(other)),
    ]
    shown = review_show(admin, number(candidate))
    assert any(line.endswith("plugins/hello/plugin.json") for line in shown.files)
    fake_github.blocked.add(number(candidate))
    fake_github.user = "bob"
    waiting = review_approve(dataclasses.replace(admin, actor="bob"), number(candidate))
    assert waiting.status == "waiting"
    assert ("approve", (number(candidate), "Approved with skill-dojo.")) in (
        fake_github.calls
    )
    rejected = review_reject(admin, number(other), reason="Not needed.")
    assert rejected.status == "closed"
    assert fake_github.comments[number(other)] == ["Not needed."]
    with pytest.raises(ConflictError):
        review_approve(admin, number(other))
    fake_github.blocked.clear()
    assert review_approve(admin, number(candidate)).status == "merged"
    ap = upstreams[0]
    ap.commit({"plugins/hello/NEW.md": "new\n"})
    update = sync(admin, item="hello").candidates[0]
    assert update.status == "opened", update
    quarantined = review_quarantine(admin, number(update))
    assert quarantined.status == "quarantined"
    assert quarantined.quarantine is not None
    assert quarantined.quarantine.head == "quarantine/hello"
    # Until that PR is merged, sync already treats the item as quarantined.
    ap.commit({"plugins/hello/NEWER.md": "newer\n"})
    assert sync(admin, item="hello").candidates[0].status == "quarantined"
    items = ItemsFile.model_validate(
        yaml_data(show(admin, "origin/quarantine/hello", "registry/items.yaml"))
    )
    hello = items.get("hello")
    assert hello is not None
    assert hello.quarantined
    human = fake_github.open_pull_request("feature/x", "staging", "x", "")
    with pytest.raises(InvalidInputError, match="not a skill-dojo PR"):
        review_show(admin, human.number)


def _approve_two(admin: Context, fake_github: FakeGitHub) -> tuple[int, int]:
    """A mirror merged by the tool and a bundle merged on github.com."""
    hello = mirror(admin, "ap", "hello")
    review_approve(admin, number(hello))
    kit = bundle_create(admin, "kit", ["ap:hello/skill/greet", "cl:tools/skill/lint"])
    fake_github.merge_on_github(number(kit), reviewers=["dave"], merged_by="carol")
    return number(hello), number(kit)


def test_promote_stamps_approvals_and_release_tags(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    hello, kit = _approve_two(admin, fake_github)
    result = promote(admin)
    assert result.status == "opened"
    assert result.branch == "promote/2026-11-21"
    assert result.items == ["hello", "kit"]
    pr = fake_github.get(number(result))
    assert pr.base == "main"
    ref = f"origin/{result.branch}"
    approvals = ApprovalsFile.model_validate(
        yaml_data(show(admin, ref, "registry/approvals.yaml"))
    )
    by_item = {a.item: a for a in approvals.approvals}
    assert by_item["hello"].reviewers == ["alice"]
    assert by_item["kit"].reviewers == ["carol", "dave"]
    assert by_item["kit"].pull_request.endswith(f"/pull/{kit}")
    assert by_item["kit"].version == "0.1.0"
    manifest = json.loads(show(admin, ref, "plugins/kit/plugin.json"))
    ext = manifest["extensions"][NS]
    assert ext["approvedBy"] == "carol,dave"
    assert ext["reviewEvidence"].endswith(f"/pull/{kit}")
    skill = show(admin, ref, "plugins/hello/skills/greet/SKILL.md")
    assert 'acme.registry/approved-by: "alice"' in skill
    assert promote(admin).status == "updated"
    fake_github.merge(number(result))
    on_main = dataclasses.replace(admin, repo=worktree(admin, "origin/main"))
    assert not validate(on_main).errors
    tagged = release(admin)
    assert tagged.status == "created"
    assert tagged.tag == "marketplace-v2026.11.21"
    assert "First release." in tagged.notes
    assert "- hello 1.0.0" in tagged.notes
    assert "- kit 0.1.0" in tagged.notes
    remote_tags = git(admin.repo, "ls-remote", "--tags", "origin")
    assert "refs/tags/marketplace-v2026.11.21" in remote_tags
    assert release(admin).status == "up-to-date"
    assert promote(admin).status == "up-to-date"
    assert hello != kit


def test_promote_blocks_on_policy(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    _approve_two(admin, fake_github)
    edit_item(admin, "kit", risk_tier=RiskTier.FORBIDDEN)
    with pytest.raises(PolicyError, match="kit: risk tier is forbidden"):
        promote(admin)
    # Restricted needs 2 reviewers: kit has carol (merged) and dave (approved).
    edit_item(admin, "kit", risk_tier=RiskTier.RESTRICTED)
    edit_item(admin, "hello", supported_channels=[Channel.BETA])
    with pytest.raises(PolicyError, match="hello: stable is not a supported") as err:
        promote(admin)
    assert "kit" not in str(err.value)


def test_promote_blocks_restricted_and_unapproved_content(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    hello = mirror(admin, "ap", "hello")
    review_approve(admin, number(hello))
    edit_item(admin, "hello", risk_tier=RiskTier.RESTRICTED)
    with pytest.raises(PolicyError, match="restricted needs 2 reviewers"):
        promote(admin)
    # An author who merges does not count as a second reviewer.
    tools = mirror(admin, "cl", "tools")
    fake_github.add_review(number(tools), "dave")
    review_approve(admin, number(tools))
    edit_item(admin, "tools", risk_tier=RiskTier.RESTRICTED)
    with pytest.raises(PolicyError, match=f"pull/{number(tools)} has 1"):
        promote(admin)
    edit_staging(
        admin, lambda t: t + "\nhand edit\n", "plugins/hello/skills/greet/SKILL.md"
    )

    def relock(text: str) -> str:
        data = json.loads(text)
        data["items"]["hello"]["treeSha256"] = "f" * 64
        return json.dumps(data)

    edit_staging(admin, relock, "registry/lock.json")
    with pytest.raises(PolicyError, match="no merged candidate PR approved"):
        promote(admin)
    # A forged approval in staging's approvals.yaml is ignored.
    forged = (
        "approvals:\n  - item: hello\n    digest: " + "f" * 64 + "\n"
        "    pull_request: https://github.invalid/acme/marketplace/pull/999\n"
        "    reviewers: [x, y]\n    approved_at: '2026-11-21T12:00:00Z'\n"
    )
    edit_staging(admin, lambda _: forged, "registry/approvals.yaml")
    with pytest.raises(PolicyError, match="no merged candidate PR approved"):
        promote(admin)


def test_revoke_lists_affected_clients(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    _approve_two(admin, fake_github)
    fake_github.merge(number(promote(admin)))
    tag = release(admin).tag
    clients_add(admin, "team-a", tag, contact="a@example.invalid")
    clients_add(admin, "team-b", "missing-tag")
    with pytest.raises(ConflictError):
        clients_add(admin, "team-a", tag)
    with pytest.raises(InvalidInputError):
        clients_add(admin, "team-c", "--upload-pack=x")
    assert [c.name for c in clients_list(admin).clients] == ["team-a", "team-b"]
    result = revoke(admin, "hello", reason="Leaks tokens.")
    assert result.action == "removed"
    assert [c.name for c in result.affected_clients] == ["team-a"]
    assert [c.name for c in result.unknown_clients] == ["team-b"]
    assert result.pull_request.base == "main"
    assert result.back_merge.base == "staging"
    assert result.back_merge.head == result.pull_request.head == "revoke/hello"
    assert "team-a" in fake_github.get(result.pull_request.number).body
    items = ItemsFile.model_validate(
        yaml_data(show(admin, "origin/revoke/hello", "registry/items.yaml"))
    )
    assert items.get("hello") is None
    with pytest.raises(NotFoundError):
        revoke(admin, "nope")
    clients_remove(admin, "team-b")
    with pytest.raises(NotFoundError):
        clients_remove(admin, "team-b")


def test_revoke_rolls_back_to_a_tag(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    ap, _ = upstreams
    hello = mirror(admin, "ap", "hello")
    review_approve(admin, number(hello))
    fake_github.merge(number(promote(admin)))
    first = release(admin).tag
    ap.commit({"plugins/hello/NEW.md": "new\n"})
    review_approve(admin, number(sync(admin, item="hello").candidates[0]))
    fake_github.merge(number(promote(admin)))
    second = release(admin)
    assert second.tag == "marketplace-v2026.11.21.2"
    assert "Updated:\n- hello 1.0.0 (content " in second.notes
    clients_add(admin, "old", first)
    clients_add(admin, "new", second.tag)
    result = revoke(admin, "hello", rollback=True)
    assert result.action == "rolled-back"
    assert [c.name for c in result.affected_clients] == ["new"]
    items = show(admin, "origin/revoke/hello", "registry/items.yaml")
    assert "quarantined: true" in items
    lock = LockFile.model_validate_json(
        show(admin, "origin/revoke/hello", "registry/lock.json")
    )
    first_lock = LockFile.model_validate_json(show(admin, first, "registry/lock.json"))
    assert lock.items["hello"].tree_sha256 == first_lock.items["hello"].tree_sha256
    skill = show(admin, "origin/revoke/hello", "plugins/hello/skills/greet/SKILL.md")
    assert 'acme.registry/approved-by: "alice"' in skill
    with pytest.raises(InvalidInputError):
        revoke(admin, "hello", to="no-such-tag")
    explicit = revoke(admin, "hello", to=first)
    assert explicit.pull_request.number == result.pull_request.number
    # The hotfix lands on main; staging has not taken the back-merge yet.
    fake_github.merge(result.pull_request.number)
    # Staging untouched: merging main keeps the flag, so main has it all.
    assert promote(admin).status == "up-to-date"
    # Main is at the first release now; nothing older is left.
    with pytest.raises(NotFoundError, match="no earlier approved release"):
        revoke(admin, "hello", rollback=True)
    # A staging edit that drops the flag in the merge is caught.
    edit_item(admin, "hello", quarantined=False, category="Edited")
    with pytest.raises(PolicyError, match="quarantined on main"):
        promote(admin)


def test_bundle_agent_mcp_and_local_parts(
    admin: Context, fixture_repos: FixtureRepos, fake_github: FakeGitHub
) -> None:
    servers = {"mcpServers": {"docs": {"command": "npx", "args": ["docs@1.2.3"]}}}
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
    on_staging = worktree(admin, "origin/staging")
    write_tree(
        on_staging,
        {
            "plugins/own/plugin.json": agent_plugin_manifest("own"),
            "plugins/own/skills/note/SKILL.md": skill_md(
                "note", "Takes notes. Use when writing notes."
            ),
        },
    )
    ctx = dataclasses.replace(admin, repo=on_staging)
    git(on_staging, "add", "-A")
    git(on_staging, "commit", "-q", "-m", "own")
    local_add(ctx, "plugins/own")
    git(on_staging, "add", "-A")
    git(on_staging, "commit", "-q", "-m", "register own")
    git(on_staging, "push", "-q", "origin", "HEAD:staging")
    result = bundle_create(
        admin,
        "kit",
        ["mx:box/agent/rev", "mx:box/mcp_server/docs", "local:own/skill/note"],
    )
    ref = f"origin/{result.branch}"
    assert "Review." in show(admin, ref, "plugins/kit/agents/rev.md")
    mcp = json.loads(show(admin, ref, "plugins/kit/mcp.json"))
    assert mcp["mcpServers"]["docs"]["args"] == ["docs@1.2.3"]
    assert "MIT" in show(admin, ref, "plugins/kit/licenses/mx-box/LICENSE")
    assert "mcp-server-added" in {f.kind for f in result.flags}
    lock = LockFile.model_validate_json(show(admin, ref, "registry/lock.json"))
    parts = {p.name: p for p in lock.items["kit"].parts}
    assert parts["note"].upstream.repository == "acme/market"
    assert parts["docs"].path == "plugins/box/.mcp.json"
    review_approve(admin, number(result))
    smaller = bundle_remove(admin, "kit", ["mcp_server/docs", "agent/rev"])
    files = git(admin.repo, "ls-tree", "-r", "--name-only", f"origin/{smaller.branch}")
    assert "plugins/kit/mcp.json" not in files
    assert "plugins/kit/licenses/mx-box/LICENSE" not in files
    with pytest.raises(NotFoundError, match="no MCP server"):
        bundle_add(admin, "kit", ["mx:box/mcp_server/nope"])
    with pytest.raises(NotFoundError, match="no agent"):
        bundle_add(admin, "kit", ["mx:box/agent/nope"])
    with pytest.raises(NotFoundError, match="not a local plugin"):
        bundle_add(admin, "kit", ["local:kit/skill/other"])
    with pytest.raises(NotFoundError, match="no source"):
        bundle_add(admin, "kit", ["zz:box/agent/rev"])
    with pytest.raises(NotFoundError, match="no bundle"):
        bundle_add(admin, "own", ["mx:box/agent/rev"])


def test_fork_prs_and_stale_approvals_do_not_count(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    candidate = mirror(admin, "ap", "hello")
    fork = fake_github.open_fork_pull_request(candidate.branch, "staging")
    assert [e.pull_request.number for e in review_list(admin).entries] == [
        number(candidate)
    ]
    with pytest.raises(InvalidInputError, match="fork"):
        review_approve(admin, fork.number)
    head = review_show(admin, number(candidate)).pull_request.head_oid
    assert head is not None
    fake_github.add_review(number(candidate), "dave")
    # A new commit lands on the branch after dave approved.
    wt = worktree(admin, f"origin/{candidate.branch}")
    (wt / "NOTES.md").write_text("later\n")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "later")
    git(wt, "push", "-q", "origin", f"HEAD:{candidate.branch}")
    with pytest.raises(ConflictError, match="review again"):
        review_approve(admin, number(candidate), head=head)
    fake_github.merge_on_github(number(candidate), reviewers=[], merged_by="carol")
    trap = fake_github.open_fork_pull_request("promote/2026-11-21", "main")
    result = promote(admin)
    assert result.status == "opened"
    assert number(result) != trap.number
    assert fake_github.get(trap.number).title == "fork"
    assert [a.reviewers for a in result.approvals] == [["carol"]]


def test_lock_and_part_paths_are_validated() -> None:
    from skill_dojo_core.models import ItemLock, Part

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


def test_bundle_refuses_symlinked_folders(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    kit = bundle_create(admin, "kit", ["ap:hello/skill/greet"])
    review_approve(admin, number(kit))
    wt = worktree(admin, "origin/staging")
    (wt / "plugins/kit/agents").symlink_to("../../registry")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "link")
    git(wt, "push", "-q", "origin", "HEAD:staging")
    with pytest.raises(InvalidInputError, match="symlink"):
        bundle_add(admin, "kit", ["cl:tools/skill/lint"])
