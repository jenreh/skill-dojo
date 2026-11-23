"""Where a plugin keeps its skills: ``skills/`` plus the paths its manifest lists.

Claude Code plugins may list skill folders in ``plugin.json`` (``"skills":
["./a", "./packs"]``); each entry is a skill folder or a folder of skills.
"""

import json
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


def _no_links(plugin: Path, rel: str) -> bool:
    current = plugin
    for part in PurePosixPath(rel).parts:
        current = current / part
        if current.is_symlink():
            return False
    return True


def skill_dirs(plugin: Path) -> dict[str, str]:
    """Skill name -> plugin-relative folder with its ``SKILL.md``.

    ``skills/`` comes first; on a name clash the first folder wins.
    """
    found: dict[str, str] = {}
    for root in skill_roots(read_manifest(plugin)):
        base = plugin / root
        if not base.is_dir() or not _no_links(plugin, root):
            continue
        if (base / "SKILL.md").is_file():
            found.setdefault(base.name, root)
            continue
        for folder in sorted(base.iterdir()):
            if (
                folder.is_dir()
                and not folder.is_symlink()
                and (folder / "SKILL.md").is_file()
            ):
                found.setdefault(folder.name, f"{root}/{folder.name}")
    return found
