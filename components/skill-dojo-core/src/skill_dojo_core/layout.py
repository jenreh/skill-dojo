"""Where a plugin keeps its skills: ``skills/`` plus the paths its manifest lists.

Claude Code plugins may list skill folders in ``plugin.json`` (``"skills":
["./a", "./packs"]``); each entry is a skill folder or a folder of skills.
"""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

SKILLS_DIR = "skills"
MANIFESTS = (".claude-plugin/plugin.json", "plugin.json")


def read_manifest(plugin: Path) -> dict[str, Any] | None:
    """The first readable manifest object of ``plugin``, else ``None``."""
    for rel in MANIFESTS:
        try:
            data = json.loads((plugin / rel).read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def skill_roots(manifest: dict[str, Any] | None) -> list[str]:
    """``skills`` plus the repo-relative skill paths a manifest lists."""
    listed = (manifest or {}).get("skills")
    if isinstance(listed, str):
        listed = [listed]
    roots = [SKILLS_DIR]
    for entry in listed if isinstance(listed, list) else []:
        if not isinstance(entry, str) or PurePosixPath(entry).is_absolute():
            continue
        parts = PurePosixPath(entry.removeprefix("./")).parts
        root = "/".join(parts)
        if root and ".." not in parts and root not in roots:
            roots.append(root)
    return roots


def find_skills(rels: Iterable[str], manifest: dict[str, Any] | None) -> dict[str, str]:
    """Skill name -> folder, from plugin-relative file paths.

    A skill is ``<root>/SKILL.md`` or ``<root>/<name>/SKILL.md``; ``skills/``
    comes first and on a name clash the first folder wins.
    """
    folders = {
        str(PurePosixPath(r).parent)
        for r in rels
        if PurePosixPath(r).name == "SKILL.md"
    }
    found: dict[str, str] = {}
    for root in skill_roots(manifest):
        if root in folders:
            found.setdefault(PurePosixPath(root).name, root)
            continue
        for folder in sorted(folders):
            if str(PurePosixPath(folder).parent) == root:
                found.setdefault(PurePosixPath(folder).name, folder)
    return found


def files_manifest(files: Mapping[str, Path]) -> dict[str, Any] | None:
    """The manifest object among a plugin's files (path -> source file)."""
    for rel in MANIFESTS:
        if rel not in files:
            continue
        try:
            data = json.loads(files[rel].read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _no_links(plugin: Path, rel: str) -> bool:
    current = plugin
    for part in PurePosixPath(rel).parts:
        current = current / part
        if current.is_symlink():
            return False
    return True


def skill_dirs(plugin: Path) -> dict[str, str]:
    """Skill name -> plugin-relative folder with its ``SKILL.md``."""
    manifest = read_manifest(plugin)
    rels = []
    for root in skill_roots(manifest):
        base = plugin / root
        if not base.is_dir() or not _no_links(plugin, root):
            continue
        candidates = [base, *(c for c in base.iterdir() if c.is_dir())]
        rels += [
            f"{c.relative_to(plugin).as_posix()}/SKILL.md"
            for c in candidates
            if not c.is_symlink() and (c / "SKILL.md").is_file()
        ]
    return find_skills(rels, manifest)
