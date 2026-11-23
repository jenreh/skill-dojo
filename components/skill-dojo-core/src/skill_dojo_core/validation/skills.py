"""``SKILL.md`` checks shared by Claude Code, Codex and Copilot.

Port of ``scripts/validate_skills.py`` from jenreh/agent-skills, plus the
provenance metadata rules: the tool's namespaced ``metadata`` values must be
strings.
"""

import re
from pathlib import Path
from typing import Any

from skill_dojo_core import frontmatter, layout
from skill_dojo_core.models import RegistryConfig
from skill_dojo_core.validation.report import Collector

MIN_DESC = 20
MAX_LISTING = 1536
MAX_BODY_LINES = 500
MAX_SHORT_DESC = 64
RELATIVE_SCRIPT = re.compile(r"\b(?:python3?|node|bash|sh) scripts/")
BARE_BASH = re.compile(r"(?:^|[\s,\[])Bash(?=$|[\s,\]])")
YAML_SCALAR = r"^\s+{key}:\s*[\"']?(.*?)[\"']?\s*$"


def yaml_value(text: str, key: str) -> str | None:
    match = re.search(YAML_SCALAR.format(key=re.escape(key)), text, re.MULTILINE)
    return match.group(1) if match else None


def check_openai_yaml(
    name: str, folder: Path, data: dict[str, Any], rep: Collector, *, required: bool
) -> None:
    path = folder / "agents" / "openai.yaml"
    if not path.is_file():
        if required:
            rep.error(name, "no agents/openai.yaml (run 'skill-dojo build')")
        return
    text = path.read_text(encoding="utf-8")
    implicit = yaml_value(text, "allow_implicit_invocation") or "true"
    manual_only = str(data.get("disable-model-invocation", "")).lower() == "true"
    if manual_only and implicit != "false":
        rep.warn(name, "manual-only in Claude, but Codex may auto-invoke it")
    elif not manual_only and implicit == "false":
        rep.warn(name, "manual-only in Codex, but Claude may auto-invoke it")
    for key in ("icon_small", "icon_large"):
        ref = yaml_value(text, key)
        if ref and not (folder / ref).is_file():
            rep.error(name, f"agents/openai.yaml {key} '{ref}' not found")
    short = yaml_value(text, "short_description") or ""
    if len(short) > MAX_SHORT_DESC:
        rep.warn(name, f"short_description is {len(short)} chars (>{MAX_SHORT_DESC})")


def check_metadata(
    name: str, data: dict[str, Any], prefix: str, rep: Collector
) -> None:
    """The tool's own values must be strings (error). Other non-string or
    non-namespaced keys only warn: vendored upstream skills use them and cannot
    be edited without forking."""
    metadata = data.get("metadata")
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        rep.error(name, "'metadata' must be a mapping")
        return
    for key, value in metadata.items():
        own = str(key).startswith(prefix)
        if not isinstance(value, str):
            message = f"metadata '{key}' must be a string"
            (rep.error if own else rep.warn)(name, message)
        if not own and "/" not in str(key):
            rep.warn(name, f"metadata '{key}' is not namespaced")


def validate_skill(
    repo: Path,
    folder: Path,
    config: RegistryConfig,
    rep: Collector,
) -> None:
    name = folder.relative_to(repo).as_posix()
    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        rep.error(name, "no SKILL.md")
        return
    text = skill_md.read_text(encoding="utf-8")
    try:
        data, doc = frontmatter.load(text)
    except ValueError as exc:
        rep.error(name, str(exc))
        return
    skill_name = str(data.get("name") or "").strip()
    desc = str(data.get("description") or "").strip()
    if not skill_name:
        rep.error(name, "frontmatter missing 'name'")
    elif skill_name != folder.name:
        rep.error(name, f"name '{skill_name}' != folder name")
    if not desc:
        rep.error(name, "frontmatter missing 'description'")
    else:
        listing = desc + str(data.get("when_to_use") or "")
        if len(desc) < MIN_DESC:
            rep.error(name, f"description too short ({len(desc)} chars)")
        if len(listing) > MAX_LISTING:
            rep.error(
                name,
                f"description + when_to_use is {len(listing)} chars; Claude Code "
                f"truncates at {MAX_LISTING}",
            )
        if "<" in listing or ">" in listing:
            rep.warn(name, "'<' or '>' in description shows as &lt;/&gt; in Claude")
    for match in sorted(set(RELATIVE_SCRIPT.findall(doc.body))):
        rep.warn(
            name,
            f"'{match}' runs from the user's cwd; use '${{CLAUDE_SKILL_DIR}}/scripts/'",
        )
    if BARE_BASH.search(str(data.get("allowed-tools") or "")):
        rep.warn(name, "allowed-tools pre-approves every Bash command; narrow it")
    if (folder / "openai.yaml").exists():
        rep.error(name, "openai.yaml belongs in agents/openai.yaml")
    stubs = config.branding is not None and config.branding.openai_yaml_stubs
    check_openai_yaml(name, folder, data, rep, required=stubs)
    check_metadata(name, data, config.namespace.skill, rep)
    body_lines = len(doc.body.splitlines())
    if body_lines > MAX_BODY_LINES:
        rep.warn(
            name,
            f"SKILL.md body is {body_lines} lines (>{MAX_BODY_LINES}; consider "
            "moving detail to references/)",
        )


def skill_folders(plugin: Path) -> list[Path]:
    """Every folder in ``skills/`` plus the skills the manifest lists elsewhere."""
    root = plugin / "skills"
    found = (
        [p for p in root.iterdir() if p.is_dir() and not p.is_symlink()]
        if root.is_dir()
        else []
    )
    listed = layout.skill_dirs(plugin).values()
    found += [plugin / rel for rel in listed if not rel.startswith("skills/")]
    return sorted(found)


def check_flat_view(repo: Path, rep: Collector) -> None:
    """The flat ``skills/`` view links every skill of ``plugins/*`` exactly."""
    flat = repo / "skills"
    if flat.is_dir():
        for entry in sorted(flat.iterdir()):
            if entry.is_symlink() and not entry.exists():
                rep.error(
                    f"skills/{entry.name}", "broken link (run 'skill-dojo build')"
                )
    plugins = sorted(p for p in (repo / "plugins").glob("*") if p.is_dir())
    for folder in (f for p in plugins for f in skill_folders(p)):
        if not (flat / folder.name).exists():
            rep.error(
                f"skills/{folder.name}",
                f"missing link to {folder.relative_to(repo).as_posix()} "
                "(run 'skill-dojo build')",
            )


def check_skills(
    repo: Path,
    plugins: list[Path],
    config: RegistryConfig,
    rep: Collector,
) -> int:
    count = 0
    for plugin in plugins:
        root = plugin / "skills"
        if root.exists() and not root.is_dir():
            rep.error(
                root.relative_to(repo).as_posix(), "exists but is not a directory"
            )
            continue
        for folder in skill_folders(plugin):
            validate_skill(repo, folder, config, rep)
            count += 1
    if config.layout.flat_skills:
        check_flat_view(repo, rep)
    return count
