"""Phase 6 read models (the web UI's data), end to end on fixture repos."""

import dataclasses

from skill_dojo_core import (
    Context,
    audit_log,
    browse,
    clients_add,
    marketplace_preview,
    mirror,
    promote,
    release,
    release_overview,
    review_detail,
    review_policy,
    revoke_preview,
)
from skill_dojo_core.models import Channel, ItemsFile, RiskTier
from skill_dojo_core.registry import ITEMS, model_at
from tests.e2e.test_phase4_release import number, worktree
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import FixtureRepo


def test_review_detail_and_policy(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    made = mirror(admin, "ap", "hello")
    detail = review_detail(admin, number(made))
    assert detail.item == "hello"
    assert detail.kind == "mirror"
    assert detail.old_version is None
    assert detail.new_version == "1.0.0"
    assert detail.contents.startswith("1 skill")
    assert detail.files
    assert any(f.path.endswith("SKILL.md") for f in detail.files)
    assert all(line.kind in {" ", "+", "-"} for f in detail.files for line in f.lines)
    assert detail.risk_tier == "standard"
    assert detail.reviewers_needed == 1
    assert detail.approvals == []

    changed = review_policy(
        admin,
        number(made),
        risk_tier=RiskTier.RESTRICTED,
        data_classification="confidential",
        channels=[Channel.BETA],
    )
    assert changed.status == "updated"
    items = model_at(admin.repo, f"origin/{made.branch}", ITEMS, ItemsFile)
    item = items.get("hello")
    assert item is not None
    assert item.risk_tier is RiskTier.RESTRICTED
    assert item.supported_channels == [Channel.BETA]
    again = review_detail(admin, number(made))
    assert again.reviewers_needed == 2
    assert again.data_classification == "confidential"


def test_release_overview_preview_audit_and_revoke(
    admin: Context, upstreams: tuple[FixtureRepo, ...], fake_github: FakeGitHub
) -> None:
    offered = browse(admin, "ap")
    hello = next(p for p in offered.plugins if p.name == "hello")
    assert hello.contents
    assert "skill" in hello.contents
    made = mirror(admin, "ap", "hello")
    fake_github.merge_on_github(number(made), ["bob"])
    assert browse(admin, "ap").tracked["hello"].startswith("mirror · pinned")

    overview = release_overview(admin)
    assert overview.commits_ahead > 0
    assert [i.item for i in overview.items] == ["hello"]
    assert overview.items[0].reviewers == ["bob", "carol"]
    assert overview.items[0].new_version == "1.0.0"
    assert overview.blocks == []
    assert overview.latest_tag is None
    assert "hello" in overview.notes

    fake_github.merge(number(promote(admin)))
    tagged = release(admin)
    clients_add(admin, "web", tagged.tag, contact="#web")
    after = release_overview(admin)
    assert after.latest_tag == tagged.tag
    assert after.tags[0].items == 1
    assert after.tags[0].clients == 1
    assert not after.untagged

    on_main = dataclasses.replace(admin, repo=worktree(admin, "origin/main"))
    preview = marketplace_preview(on_main)
    paths = [e.path for e in preview.tree]
    assert ".agents/plugins/marketplace.json" in paths
    assert "plugins/hello/" in paths
    assert preview.errors == 0
    agents = preview.catalogs[0]
    assert agents.path == ".agents/plugins/marketplace.json"
    assert '"hello"' in agents.text
    assert agents.full

    kinds = {e.kind for e in audit_log(admin).events}
    assert {"approval", "promotion", "release"} <= kinds
    assert "at,kind,actor" in audit_log(admin).csv()

    (target,) = revoke_preview(admin)
    assert target.item == "hello"
    assert [c.name for c in target.affected] == ["web"]
    assert target.rollback_to is None
