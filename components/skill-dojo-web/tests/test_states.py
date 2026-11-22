"""State unit tests: every page state against a fixture curated repo.

Git is real; GitHub is the shared fake. Event handlers are called through
``.fn`` on a state taken from a fresh root state.
"""

from pathlib import Path
from typing import Any

import pytest
from reflex.state import State

import skill_dojo_core as core
from skill_dojo_core import Context, NotFoundError, mirror
from skill_dojo_web import backend, server
from skill_dojo_web.pages.audit import AuditState, day_label
from skill_dojo_web.pages.bundles import BundlesState
from skill_dojo_web.pages.clients import ClientsState
from skill_dojo_web.pages.preview import PreviewState
from skill_dojo_web.pages.releases import ReleasesState
from skill_dojo_web.pages.review import ReviewState
from skill_dojo_web.pages.sources import SourcesState
from skill_dojo_web.state import failure
from tests.e2e.test_phase4_release import number
from tests.support.fake_github import FakeGitHub
from tests.support.fixture_repos import FixtureRepo


def state(cls: type[Any]) -> Any:
    return State(_reflex_internal_init=True).get_substate(
        cls.get_full_name().split(".")
    )


def call(st: Any, name: str, *args: Any) -> Any:
    return getattr(type(st), name).fn(st, *args)


@pytest.fixture
def ui(
    admin: Context,
    upstreams: tuple[FixtureRepo, ...],
    fake_github: FakeGitHub,
    monkeypatch: pytest.MonkeyPatch,
) -> Context:
    monkeypatch.setenv(backend.REPO_ENV, str(admin.repo))
    monkeypatch.setattr(backend.settings, "github", lambda repo: fake_github)
    monkeypatch.setattr(backend.settings, "actors", {})
    return admin


def test_review_state_approves_and_merges(ui: Context, fake_github: FakeGitHub) -> None:
    made = mirror(ui, "ap", "hello")
    st = state(ReviewState)
    call(st, "load")
    assert st.notice == ""
    assert st.repository == "acme/market"
    assert st.queue_count == 1
    assert [e["item"] for e in st.entries] == ["hello"]
    assert st.selected == number(made)
    assert st.detail["new_version"] == "1.0.0"
    assert st.files
    call(st, "set_filter", "flagged")
    assert st.rows == [e for e in st.entries if e["flags"]]
    call(st, "set_filter", "all")
    call(st, "set_tier", "low")
    call(st, "approve")
    assert fake_github.get(number(made)).state == "MERGED"
    assert st.notice.endswith("merged")
    assert st.entries == []


def test_review_state_reject_and_errors(ui: Context, fake_github: FakeGitHub) -> None:
    made = mirror(ui, "ap", "hello")
    st = state(ReviewState)
    call(st, "load")
    call(st, "reject")
    assert fake_github.get(number(made)).state == "CLOSED"
    call(st, "select", 999)
    assert st.notice_ok is False


def test_sources_state_browse_mirror_and_add(
    ui: Context, fake_github: FakeGitHub
) -> None:
    st = state(SourcesState)
    call(st, "load")
    assert [s["id"] for s in st.sources] == ["ap", "cl"]
    assert st.selected == "ap"
    assert any(p["name"] == "hello" for p in st.plugins)
    call(st, "set_query", "hel")
    assert [p["name"] for p in st.shown] == ["hello"]
    call(st, "mirror", "hello")
    assert "hello: opened" in st.notice
    assert fake_github.pulls
    call(st, "set_new_id", "bad")
    call(st, "set_new_repo", "not a repo")
    call(st, "add_source")
    assert st.notice_ok is False


def test_releases_clients_preview_audit_bundles(
    ui: Context, fake_github: FakeGitHub
) -> None:
    fake_github.merge_on_github(number(mirror(ui, "ap", "hello")), ["bob"])
    rel = state(ReleasesState)
    call(rel, "load")
    assert [i["item"] for i in rel.items] == ["hello"]
    assert rel.items[0]["change"].startswith("new")
    call(rel, "set_notes", "Release notes by hand.")
    rel_promote = core.promote(ui)
    assert rel_promote.status == "opened"
    promote_pr = next(p for p in fake_github.pulls if p.head.startswith("promote/"))
    fake_github.merge(promote_pr.number)
    call(rel, "tag")
    assert "marketplace-v" in rel.notice

    clients = state(ClientsState)
    call(clients, "load")
    for key, value in (("name", "web"), ("ref", "main"), ("contact", "#web")):
        call(clients, "set_field", key, value)
    call(clients, "add_client")
    assert [c["name"] for c in clients.clients] == ["web"]
    assert clients.item == "hello"
    assert clients.affected_names == ["web"]
    call(clients, "edit_client", "web")
    call(clients, "set_field", "contact", "#web-guild")
    call(clients, "add_client")
    assert clients.clients[0]["contact"] == "#web-guild", clients.notice
    call(clients, "remove_client", "web")
    assert clients.clients == []

    preview = state(PreviewState)
    call(preview, "load")
    assert preview.current["path"] == ".agents/plugins/marketplace.json"
    call(preview, "show_catalog", 1)
    call(preview, "set_full", True)
    assert preview.lines

    audit = state(AuditState)
    call(audit, "load")
    assert {"approval", "release"} <= {e["kind"] for e in audit.events}
    call(audit, "set_kind", "release")
    assert all(e["kind"] == "release" for d in audit.days for e in d["events"])
    assert call(audit, "export") is not None

    bundles = state(BundlesState)
    call(bundles, "load")
    assert bundles.notice == ""
    assert bundles.bundle == ""


def test_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert core.flag_severity("mcp-server-added") == "bad"
    assert core.flag_severity("hook-added") == "warn"
    assert core.flag_severity("description-changed") == "info"
    assert failure(NotFoundError("gone")) == "gone"
    assert failure(RuntimeError("boom")).startswith("Unexpected error")
    from datetime import UTC, datetime

    now = datetime(2026, 11, 21, 12, tzinfo=UTC)
    assert day_label("2026-11-21T10:00:00Z", now) == "Today"
    assert day_label("2026-11-20T10:00:00Z", now) == "Yesterday"
    assert day_label("2026-11-14T10:00:00Z", now) == "Nov 14"
    assert day_label("", now) == "Undated"
    monkeypatch.delenv(backend.REPO_ENV, raising=False)
    with pytest.raises(NotFoundError):
        backend.repo_path()
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    work = server.prepare(server.cache_dir(), 8099)
    assert (work / "assets" / "css" / "skill-dojo.css").is_file()
    assert "backend_port=8099" in (work / "rxconfig.py").read_text()
    assert "skill_dojo_web.app" in (work / "rxconfig.py").read_text()
    assert server.command(8099)[-3:] == ["8099", "--backend-host", "127.0.0.1"]
