import json
from pathlib import Path

from skill_dojo_core.models import Upstream
from skill_dojo_core.parts import PartSpec, file_version, index_parts, pick


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


def test_manifest_listed_skills_are_parts(tmp_path: Path) -> None:
    files = {
        ".claude-plugin/plugin.json": json.dumps({"skills": ["./ml-trace", "./pack"]}),
        "ml-trace/SKILL.md": "---\nname: ml-trace\ndescription: Traces.\n---\n",
        "ml-trace/scripts/run.sh": "echo\n",
        "pack/eval/SKILL.md": "---\nname: eval\n---\n",
        "other/SKILL.md": "---\nname: other\n---\n",
    }
    paths = {}
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        paths[rel] = path
    found = {p.name: p.description for p in index_parts(paths) if p.kind == "skill"}
    assert found == {"ml-trace": "Traces.", "eval": ""}
    upstream = Upstream(repository="o/r", commit="c" * 40, path=".")
    picked = pick(PartSpec(kind="skill", name="ml-trace"), paths, upstream)
    assert sorted(picked.files) == [
        "skills/ml-trace/SKILL.md",
        "skills/ml-trace/scripts/run.sh",
    ]
    assert picked.path == "ml-trace"
