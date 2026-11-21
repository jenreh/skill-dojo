from pathlib import Path

from skill_dojo_core import hashing, metadata
from skill_dojo_core.models import Namespace
from tests.support.fixture_repos import git

NS = Namespace.from_name("acme")
SKILL = "---\nname: greet\ndescription: Greets.\n---\nbody\n"
MANIFEST = '{\n  "name": "hello",\n  "version": "1.0.0"\n}\n'


def make_plugin(root: Path) -> Path:
    plugin = root / "hello"
    (plugin / "skills" / "greet").mkdir(parents=True)
    (plugin / "skills" / "greet" / "SKILL.md").write_text(SKILL)
    (plugin / "plugin.json").write_text(MANIFEST)
    (plugin / "run.sh").write_text("#!/bin/sh\n")
    (plugin / "run.sh").chmod(0o755)
    (plugin / ".DS_Store").write_bytes(b"x")
    (plugin / "link.json").symlink_to("plugin.json")
    return plugin


def test_hash_tree_modes_and_ignores(tmp_path: Path) -> None:
    files = hashing.hash_tree(make_plugin(tmp_path), NS)
    assert sorted(files) == [
        "link.json",
        "plugin.json",
        "run.sh",
        "skills/greet/SKILL.md",
    ]
    assert files["run.sh"].mode == "100755"
    assert files["link.json"].mode == "120000"
    assert files["link.json"].sha256 == hashing.sha256_bytes(b"plugin.json")
    assert files["link.json"].normalized_sha256 is None
    assert files["plugin.json"].normalized_sha256 is not None
    assert files["run.sh"].normalized_sha256 is None


def test_hash_tree_honours_gitignore(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    plugin = make_plugin(tmp_path)
    (tmp_path / ".gitignore").write_text("*.log\n")
    (plugin / "debug.log").write_text("x")
    assert "debug.log" not in hashing.hash_tree(plugin, NS)


def test_stamping_is_not_drift(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    before = hashing.hash_tree(plugin, NS)
    prov = metadata.Provenance(registry_id="acme:hello", kind="local")
    metadata.stamp_skill(plugin / "skills/greet/SKILL.md", NS, prov)
    metadata.stamp_manifest(plugin / "plugin.json", NS, prov)
    after = hashing.hash_tree(plugin, NS)
    assert after["plugin.json"].sha256 != before["plugin.json"].sha256
    assert hashing.drift(before, after) == []
    assert hashing.tree_sha256(before) == hashing.tree_sha256(after)


def test_content_change_is_drift(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    before = hashing.hash_tree(plugin, NS)
    (plugin / "skills/greet/SKILL.md").write_text(SKILL.replace("body", "evil"))
    (plugin / "run.sh").unlink()
    (plugin / "new.txt").write_text("x")
    found = hashing.drift(before, hashing.hash_tree(plugin, NS))
    assert [(d.path, d.change) for d in found] == [
        ("run.sh", "missing"),
        ("skills/greet/SKILL.md", "changed"),
        ("new.txt", "extra"),
    ]


def test_mode_change_is_drift(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    before = hashing.hash_tree(plugin, NS)
    (plugin / "run.sh").chmod(0o644)
    assert [d.path for d in hashing.drift(before, hashing.hash_tree(plugin, NS))] == [
        "run.sh"
    ]


def test_foreign_extension_change_is_drift(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    before = hashing.hash_tree(plugin, NS)
    (plugin / "plugin.json").write_text(
        '{"name": "hello", "version": "1.0.0", "extensions": {"com.x": {}}}'
    )
    assert hashing.drift(before, hashing.hash_tree(plugin, NS))


def test_normalization_of_invalid_files(tmp_path: Path) -> None:
    assert hashing.normalized_sha256("SKILL.md", b"no frontmatter", NS) is None
    assert hashing.normalized_sha256("plugin.json", b"{not json", NS) is None
    assert hashing.normalized_sha256("plugin.json", b"[1]", NS) is None
    assert hashing.normalized_sha256("plugin.json", b"\xff", NS) is None
    assert hashing.normalized_sha256("README.md", b"x", NS) is None


def test_empty_metadata_normalizes_like_none() -> None:
    a = hashing.normalize_skill("---\nname: x\nmetadata:\n---\nb\n", NS.skill)
    b = hashing.normalize_skill("---\nname: x\n---\nb\n", NS.skill)
    assert a == b


def test_tree_hash_is_order_independent(tmp_path: Path) -> None:
    files = hashing.hash_tree(make_plugin(tmp_path), NS)
    reversed_files = dict(reversed(list(files.items())))
    assert hashing.tree_sha256(files) == hashing.tree_sha256(reversed_files)


def test_list_files_without_git(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(hashing, "_git_files", lambda root: None)
    plugin = make_plugin(tmp_path)
    (plugin / "skills-link").symlink_to("skills")
    assert "skills-link" in hashing.list_files(plugin)
    assert ".DS_Store" not in hashing.list_files(plugin)
