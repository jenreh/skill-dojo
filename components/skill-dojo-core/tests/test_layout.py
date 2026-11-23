import json
from pathlib import Path

from skill_dojo_core import layout


def skill(root: Path, rel: str) -> None:
    (root / rel).mkdir(parents=True, exist_ok=True)
    (root / rel / "SKILL.md").write_text("---\nname: s\n---\n")


def test_skill_roots() -> None:
    assert layout.skill_roots(None) == ["skills"]
    assert layout.skill_roots({"skills": "./one/"}) == ["skills", "one"]
    listed = {"skills": ["./a", "../out", "/abs", "./skills", 3, "./", "a"]}
    assert layout.skill_roots(listed) == ["skills", "a"]


def test_skill_dirs(tmp_path: Path) -> None:
    plugin = tmp_path / "p"
    (plugin / ".claude-plugin").mkdir(parents=True)
    manifest = {"skills": ["./direct", "./pack", "./linked", "./missing"]}
    (plugin / ".claude-plugin/plugin.json").write_text(json.dumps(manifest))
    for rel in ("skills/same", "direct", "pack/same", "pack/other", "outside/x"):
        skill(plugin, rel)
    (plugin / "pack/no-skill").mkdir()
    (plugin / "linked").symlink_to(plugin / "outside")
    assert layout.skill_dirs(plugin) == {
        "same": "skills/same",
        "direct": "direct",
        "other": "pack/other",
    }
