"""State unit tests: every page state against a fixture curated repo.

Git is real; GitHub is the shared fake. Event handlers are called through
``.fn`` on a state taken from a fresh root state.
"""

from pathlib import Path
from typing import Any

import pytest
from reflex.state import State

import skill_dojo_core as core
from skill_dojo_core import Context, NotFoundError, finish, mirror
from skill_dojo_web import backend, server
from skill_dojo_web.pages.audit.state import AuditState, day_label
from skill_dojo_web.pages.changes.state import ChangesState
from skill_dojo_web.pages.clients.state import ClientsState
from skill_dojo_web.pages.plugins.state import PluginsState
from skill_dojo_web.pages.preview.state import PreviewState
from skill_dojo_web.pages.releases.state import ReleasesState
from skill_dojo_web.pages.sources.state import SourcesState
from skill_dojo_web.state import failure
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


def test_changes_state_lists_versions_and_choices(
    ui: Context, fake_github: FakeGitHub
) -> None:
    mirror(ui, "ap", "hello")
    core.plugin_new(ui, "own")
    st = state(ChangesState)
    call(st, "load")
    assert st.notice == "", st.notice
    assert st.repository == "acme/market"
    assert st.branch == "skill-dojo/changes"
    assert st.queue_count == 2
    rows = {r["item"]: r for r in st.rows}
    assert rows["hello"]["editable"] is False
    assert rows["own"]["shown_branch"] == "0.1.0"
    assert rows["own"]["choice"] == "patch"
    assert "skill-dojo/changes (checked out)" in st.branch_line
    assert st.pr_label == "No open PR"
    assert any(f["item"] == "hello" for f in st.flags)
    call(st, "choose", "own", "custom")
    call(st, "set_custom", "own", " 2.0.0 ")
    assert st.levels() == {"own": "2.0.0"}
    call(st, "choose", "own", "major")
    assert st.levels() == {"own": "major"}
    finish(ui, levels=st.levels())
    call(st, "load")
    assert st.pr_label == "PR #1 open"
    assert st.pr_url
    assert {r["item"]: r["shown_branch"] for r in st.rows}["own"] == "1.0.0"
    assert st.chosen == {"own": "major"}


def test_sources_state_browse_mirror_and_parts(
    ui: Context, fake_github: FakeGitHub
) -> None:
    st = state(SourcesState)
    call(st, "load")
    assert [s["id"] for s in st.sources] == ["ap", "cl"]
    assert st.selected == "ap"
    assert st.cached
    assert any(p["name"] == "hello" for p in st.plugins)
    call(st, "set_query", "hel")
    assert [p["name"] for p in st.shown] == ["hello"]
    call(st, "mirror", "hello")
    assert "hello: added" in st.notice
    call(st, "expand", "hello")
    assert [r["spec"] for r in st.part_rows] == ["ap:hello/skill/greet"]
    call(st, "toggle_pick", "ap:hello/skill/greet")
    assert st.picked_count == 1
    call(st, "open_dialog")
    assert st.dialog
    assert st.creating
    assert st.cannot_add
    call(st, "set_target_name", "kit")
    call(st, "add_to_plugin")
    assert "kit: created" in st.notice, st.notice
    assert st.picked == []
    call(st, "open_dialog")
    assert [o["value"] for o in st.target_options][1:] == ["kit"]
    call(st, "close_dialog")
    call(st, "expand", "hello")
    assert st.expanded == ""
    call(st, "refresh")
    assert not st.cached
    call(st, "set_new_id", "bad")
    call(st, "set_new_repo", "not a repo")
    call(st, "add_source")
    assert st.notice_ok is False
    assert not fake_github.pulls


def test_plugins_state_new_plugin_and_scan(ui: Context) -> None:
    core.add_parts(ui, "kit", ["ap:hello/skill/greet"], create=True)
    st = state(PluginsState)
    call(st, "load")
    assert [p["id"] for p in st.plugins] == ["kit"]
    assert st.plugins[0]["parts"][0]["short"] == "skill/greet"
    assert st.cannot_create
    call(st, "set_new_name", "own")
    call(st, "set_new_description", "Our things.")
    call(st, "set_new_category", "Coding")
    assert st.new_path == "plugins/own/"
    call(st, "create")
    assert "plugins/own/" in st.notice
    skill = ui.repo / "plugins/own/skills/tidy/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: tidy\ndescription: Tidies code. Use when cleaning up.\n---\n"
    )
    call(st, "scan")
    assert "registry/lock.json" in st.scanned
    call(st, "set_query", "our")
    assert [p["id"] for p in st.shown] == ["own"]
    call(st, "remove_part", "kit", "skill/greet")
    assert "Removed" in st.notice
    call(st, "remove_part", "kit", "skill/greet")
    assert st.notice_ok is False


def test_releases_clients_preview_audit(ui: Context, fake_github: FakeGitHub) -> None:
    mirror(ui, "ap", "hello")
    done = finish(ui)
    assert done.pull_request is not None
    assert fake_github.merge(done.pull_request.number)
    rel = state(ReleasesState)
    call(rel, "load")
    assert rel.untagged
    assert not rel.nothing_new
    assert any("mirror hello" in c["subject"] for c in rel.commits)
    call(rel, "set_notes", "Release notes by hand.")
    call(rel, "create")
    assert "Released marketplace-v" in rel.notice, rel.notice
    assert fake_github.releases[0][2] == "Release notes by hand.\n"
    assert rel.nothing_new
    assert rel.tags
    call(rel, "create")
    assert "has not changed" in rel.notice

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
    call(clients, "set_action", "remove")
    call(clients, "revoke")
    assert "Revoked hello (removed)" in clients.notice, clients.notice

    preview = state(PreviewState)
    call(preview, "load")
    assert preview.current["path"] == ".agents/plugins/marketplace.json"
    call(preview, "set_catalog", "1")
    call(preview, "set_view", "full")
    assert preview.view == "full"
    assert preview.lines

    audit = state(AuditState)
    call(audit, "load")
    assert {"merge", "change", "release"} <= {e["kind"] for e in audit.events}
    call(audit, "set_kind", "release")
    assert all(e["kind"] == "release" for d in audit.days for e in d["events"])
    assert call(audit, "export") is not None


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
    assert (work / "assets" / "css" / "fonts.css").is_file()
    assert "backend_port=8099" in (work / "rxconfig.py").read_text()
    assert "skill_dojo_web.app" in (work / "rxconfig.py").read_text()
    assert '"http://localhost:8099"' in (work / "rxconfig.py").read_text()
    assert server.command(8099)[-3:] == ["8099", "--backend-host", "127.0.0.1"]
