"""State unit tests: every page state against a fixture curated repo.

Git is real; GitHub is the shared fake. Event handlers are called through
``.fn`` on a state taken from a fresh root state.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
import reflex as rx
from reflex.state import State

import skill_dojo_core as core
from skill_dojo_core import Context, NotFoundError, finish, mirror
from skill_dojo_web import backend, server
from skill_dojo_web.components.common import work, working
from skill_dojo_web.pages.audit.state import AuditState, day_label
from skill_dojo_web.pages.changes.state import ChangesState
from skill_dojo_web.pages.plugins.state import PluginsState
from skill_dojo_web.pages.preview.state import PreviewState
from skill_dojo_web.pages.releases.state import ReleasesState
from skill_dojo_web.pages.revoke.state import RevokeState
from skill_dojo_web.pages.sources.state import NEW, SourcesState
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


def test_sources_state_part_targets_are_independent() -> None:
    st = state(SourcesState)
    st.local_plugins = ["kit", "team"]
    st.part_rows = [{"spec": "ap:hello/skill/a"}, {"spec": "ap:hello/skill/b"}]
    call(st, "set_part_target", "ap:hello/skill/a", "kit")
    assert [r["target"] for r in st.part_list] == ["kit", NEW]
    call(st, "set_part_target", "ap:hello/skill/b", "team")
    assert [r["target"] for r in st.part_list] == ["kit", "team"]


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
    spec = "ap:hello/skill/greet"
    call(st, "expand", "hello")
    [row] = st.part_list
    assert row["spec"] == spec
    assert row["description"] == "Greets the user. Use when saying hello."
    assert (row["on"], row["target"]) == (False, NEW)
    call(st, "toggle_part", spec, True)
    assert st.dialog
    assert st.cannot_create
    call(st, "set_target_name", "kit")
    call(st, "create_plugin")
    assert "kit: created" in st.notice, st.notice
    assert not st.dialog
    assert [o["value"] for o in st.target_options] == [NEW, "kit"]
    assert [(r["on"], r["target"]) for r in st.part_list] == [(True, "kit")]
    call(st, "toggle_part", spec, False)
    assert "Removed skill/greet from kit" in st.notice, st.notice
    assert [(r["on"], r["target"]) for r in st.part_list] == [(False, "kit")]
    call(st, "set_part_target", spec, NEW)
    assert st.part_list[0]["target"] == NEW
    call(st, "set_part_target", spec, "kit")
    call(st, "toggle_part", spec, True)
    assert not st.dialog
    assert "Added skill/greet to kit" in st.notice, st.notice
    assert st.part_list[0]["on"]
    call(st, "toggle_part", spec, True)
    call(st, "close_dialog")
    assert st.pending == ""
    call(st, "expand", "hello")
    assert st.expanded == ""
    call(st, "refresh")
    assert not st.cached
    call(st, "set_new_id", "bad")
    call(st, "set_new_repo", "not a repo")
    call(st, "add_source")
    assert st.notice_ok is False
    assert not fake_github.pulls


def test_sources_state_versions(ui: Context) -> None:
    st = state(SourcesState)
    call(st, "load")
    assert st.version == ""
    call(st, "select", "cl")
    assert st.version == "3.1.0"
    call(st, "expand", "tools")
    assert [r["version"] for r in st.part_list] == ["1.4.0"]


def test_plugins_state_new_plugin_and_scan(ui: Context) -> None:
    core.add_parts(ui, "kit", ["ap:hello/skill/greet"], create=True)
    st = state(PluginsState)
    call(st, "load")
    assert [p["id"] for p in st.plugins] == ["kit"]
    assert st.plugins[0]["parts"][0]["short"] == "skill/greet"
    assert st.plugins[0]["parts"][0]["version"] == ""
    assert st.marketplace_version == ""
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


def test_releases_revoke_preview_audit(ui: Context, fake_github: FakeGitHub) -> None:
    mirror(ui, "ap", "hello")
    done = finish(ui)
    assert done.pull_request is not None
    assert fake_github.merge(done.pull_request.number)
    rel = state(ReleasesState)
    call(rel, "load")
    assert rel.untagged
    assert not rel.nothing_new
    assert any(c["subject"] == "skill-dojo: finish" for c in rel.commits)
    call(rel, "set_notes", "Release notes by hand.")
    call(rel, "create")
    assert "Released marketplace-v" in rel.notice, rel.notice
    assert fake_github.releases[0][2] == "Release notes by hand.\n"
    assert rel.nothing_new
    assert rel.tags
    call(rel, "create")
    assert "has not changed" in rel.notice

    rev = state(RevokeState)
    call(rev, "load")
    assert rev.item == "hello"
    call(rev, "set_action", "remove")
    call(rev, "revoke")
    assert "Revoked hello (removed)" in rev.notice, rev.notice

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


def test_work_marks_the_clicked_control_busy() -> None:
    st = state(SourcesState)
    call(st, "start_work", "mirror:hello")
    assert st.working == "mirror:hello"
    call(st, "end_work")
    assert st.working == ""
    start, action, end = work("refresh", SourcesState.refresh)
    assert start.handler.fn.__name__ == "start_work"
    assert start.args[0][1].equals(rx.Var.create("refresh"))
    assert action is SourcesState.refresh
    assert end.fn.__name__ == "end_work"
    assert isinstance(working("refresh"), rx.Var)


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


def test_warm_actor_asks_gh_once_off_the_event_loop(
    ui: Context, fake_github: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(backend.warm_actor())
    assert backend.settings.actors == {ui.repo: fake_github.user}
    backend.make_context()
    assert fake_github.calls.count(("current_user", ())) == 1
    monkeypatch.delenv(backend.REPO_ENV)
    asyncio.run(backend.warm_actor())  # a failure waits for the page load


def test_prepare_and_command_for_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    work = server.prepare(server.cache_dir(), 8099, reload=True)
    config = (work / "rxconfig.py").read_text()
    assert "frontend_port=8099" in config
    assert "backend_port=8100" in config
    assert 'api_url="http://127.0.0.1:8100"' in config
    command = server.command(8099, reload=True)
    assert command[command.index("--env") + 1] == "dev"
    assert "--single-port" not in command
    assert command[command.index("--backend-port") + 1] == "8100"
