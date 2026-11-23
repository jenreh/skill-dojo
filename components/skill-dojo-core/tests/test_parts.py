from pathlib import Path

from skill_dojo_core.parts import file_version, index_parts


def test_part_versions_from_frontmatter(tmp_path: Path) -> None:
    files = {
        "skills/a/SKILL.md": "---\nname: a\nmetadata:\n  version: 1.2.0\n---\nA\n",
        "skills/b/SKILL.md": "---\nname: b\n---\nB\n",
        "agents/c.md": "---\nname: c\nversion: 2.0\n---\nC\n",
        "agents/d.md": "no frontmatter\n",
    }
    paths = {}
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        paths[rel] = path
    found = {p.name: p.version for p in index_parts(paths)}
    assert found == {"a": "1.2.0", "b": None, "c": "2.0", "d": None}
    assert file_version(tmp_path / "missing.md") is None
    assert file_version(None) is None
