"""Read models (the web UI's data), end to end on fixture repos."""

from skill_dojo_core import (
    Context,
    add_parts,
    audit_log,
    browse,
    changes_overview,
    finish,
    marketplace_preview,
    mirror,
    plugin_parts,
    plugins_overview,
    release,
    release_overview,
    revoke,
    revoke_preview,
)
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import FixtureRepo, git


def merge(ctx: Context, fake_github: FakeGitHub, number: int) -> None:
    assert fake_github.merge(number)
    git(ctx.repo, "fetch", "-q", "origin")


def test_changes_plugins_and_parts(
    admin: Context, upstreams: tuple[FixtureRepo, ...]
) -> None:
    del upstreams
    mirror(admin, "ap", "hello")
    add_parts(admin, "kit", ["cl:tools/skill/lint"], create=True)
    changes = changes_overview(admin)
    assert changes.status.on_branch
    assert {p.item for p in changes.status.pending} == {"hello", "kit"}
    assert "hello" in changes.flags
    plugins = {p.id: p for p in plugins_overview(admin).plugins}
    assert plugins["hello"].kind == "mirror"
    assert plugins["hello"].pin
    assert plugins["kit"].version == "0.1.0"
    assert [p.spec for p in plugins["kit"].parts] == ["cl:tools/skill/lint"]
    assert plugins["kit"].parts[0].version == "1.4.0"
    assert plugins_overview(admin).local == ["kit"]
    cached = plugin_parts(admin, "cl", "tools")
    assert [(p.kind, p.name) for p in cached.parts] == [("skill", "lint")]
    assert cached.parts[0].description == "Lints code. Use when checking style."
    assert cached.parts[0].version == "1.4.0"
    assert browse(admin, "cl").version == "3.1.0"
    assert browse(admin, "ap").version is None
    fetched = plugin_parts(admin, "ap", "hello")
    assert fetched.parts[0].description == "Greets the user. Use when saying hello."
    local = plugin_parts(admin, "local", "kit")
    assert [(p.kind, p.name) for p in local.parts] == [("skill", "lint")]
    assert local.parts[0].description == "Lints code. Use when checking style."


def test_release_overview_preview_audit_and_revoke(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    del upstreams
    offered = browse(admin, "ap")
    hello = next(p for p in offered.plugins if p.name == "hello")
    assert hello.contents
    assert "skill" in hello.contents
    mirror(admin, "ap", "hello")
    assert browse(admin, "ap").tracked["hello"].startswith("mirror · pinned")
    done = finish(admin)
    assert done.pull_request is not None
    merge(admin, fake_github, done.pull_request.number)

    overview = release_overview(admin)
    assert overview.untagged
    assert overview.latest_tag is None
    assert any(c.subject == "skill-dojo: finish" for c in overview.commits)
    assert "hello" in overview.notes

    assert plugins_overview(admin).marketplace_version is None
    tagged = release(admin)
    assert plugins_overview(admin).marketplace_version == tagged.tag.removeprefix(
        "marketplace-v"
    )
    after = release_overview(admin)
    assert after.latest_tag == tagged.tag
    assert after.tags[0].items == 1
    assert not after.untagged
    assert after.commits == []

    preview = marketplace_preview(admin)
    paths = [e.path for e in preview.tree]
    assert ".agents/plugins/marketplace.json" in paths
    assert "plugins/hello/" in paths
    assert preview.errors == 0
    agents = preview.catalogs[0]
    assert agents.path == ".agents/plugins/marketplace.json"
    assert '"hello"' in agents.text
    assert agents.full

    kinds = {e.kind for e in audit_log(admin).events}
    assert {"merge", "change", "release"} <= kinds
    assert "at,kind,actor" in audit_log(admin).csv()

    (target,) = revoke_preview(admin).targets
    assert target.item == "hello"
    assert target.rollback_to is None

    revoked = revoke(admin, "hello")
    assert revoked.action == "removed"
    assert not (admin.repo / "plugins/hello").exists()
