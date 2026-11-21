from pathlib import Path

import pytest

from skill_dojo_core import InvalidInputError
from skill_dojo_core.overlay import Link, Overlay, check_contained


def test_write_link_remove_and_apply(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("same")
    (tmp_path / "gone.txt").write_text("x")
    overlay = Overlay(tmp_path)
    overlay.write("keep.txt", "same")
    overlay.write("a/new.txt", "hello")
    overlay.write("a/bin", b"\x00")
    overlay.link("a/link", "new.txt")
    overlay.remove("gone.txt")
    assert overlay.changes() == ["a/bin", "a/link", "a/new.txt", "gone.txt"]
    assert overlay.read_text("a/link") == "hello"
    assert overlay.is_link("a/link")
    assert not overlay.exists("gone.txt")
    overlay.apply()
    assert overlay.changes() == []
    assert (tmp_path / "a/new.txt").read_text() == "hello"
    assert (tmp_path / "a/link").is_symlink()
    assert not (tmp_path / "gone.txt").exists()
    assert Overlay(tmp_path).current("a/link") == Link("new.txt")


def test_link_escaping_repo_reads_as_absent(tmp_path: Path) -> None:
    overlay = Overlay(tmp_path)
    overlay.link("x", "../outside")
    assert overlay.read_text("x") is None


def test_apply_replaces_a_directory(tmp_path: Path) -> None:
    (tmp_path / "skills/greet").mkdir(parents=True)
    overlay = Overlay(tmp_path)
    overlay.link("skills/greet", "../plugins/p/skills/greet")
    overlay.apply()
    assert (tmp_path / "skills/greet").is_symlink()


def test_refuses_symlinked_parent_and_dotdot(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = tmp_path / "repo"
    (repo / "plugins/p").mkdir(parents=True)
    (repo / "plugins/p/.claude-plugin").symlink_to(outside)
    overlay = Overlay(repo)
    with pytest.raises(InvalidInputError, match="symlink"):
        overlay.write("plugins/p/.claude-plugin/plugin.json", "{}")
    with pytest.raises(InvalidInputError, match="leaves"):
        check_contained(repo, "../x")
    with pytest.raises(InvalidInputError, match="leaves"):
        check_contained(repo, "/etc/passwd")
    assert not (outside / "plugin.json").exists()
