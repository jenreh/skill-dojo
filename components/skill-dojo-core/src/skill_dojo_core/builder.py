"""``build``: regenerate catalogs, missing manifests, branding, stamps and layout.

Port of ``codex_metadata.py`` and ``link-plugins.sh`` from jenreh/agent-skills,
driven by data in ``registry/`` and the manifests instead of hardcoded lists.
Idempotent: a second run changes nothing.
"""

import fnmatch
import json
import logging
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from skill_dojo_core import catalogs, frontmatter, jsontext, metadata
from skill_dojo_core.errors import InvalidInputError
from skill_dojo_core.models import (
    ChannelPolicy,
    Item,
    ItemKind,
    ItemLock,
    RegistryConfig,
)
from skill_dojo_core.overlay import Overlay
from skill_dojo_core.registry import Registry

log = logging.getLogger(__name__)

PLUGINS_DIR = "plugins"
FLAT_SKILLS_DIR = "skills"
ROOT_MANIFEST = "plugin.json"
CLAUDE_MANIFEST = ".claude-plugin/plugin.json"
ROOT_MCP = "mcp.json"
CLAUDE_MCP = ".mcp.json"
OPENAI = "com.openai"
MAX_SHORT = 64
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
# Paths inside a plugin that build may generate. A generated path is one that
# matches these and is not part of the item's locked (upstream) files.
BASE_PATTERNS = (ROOT_MANIFEST, CLAUDE_MANIFEST, ROOT_MCP, CLAUDE_MCP)


def plugin_dir(item_id: str) -> str:
    return f"{PLUGINS_DIR}/{item_id}"


def generated_patterns(config: RegistryConfig) -> tuple[str, ...]:
    patterns = list(BASE_PATTERNS)
    branding = config.branding
    if branding is not None:
        if branding.openai_yaml_stubs:
            patterns.append("skills/*/agents/openai.yaml")
        if branding.icon:
            icon = PurePosixPath(branding.icon).name
            patterns += [f"assets/{icon}", f"skills/*/assets/{icon}"]
    return tuple(patterns)


def matches(rel: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(rel, pattern) for pattern in patterns)


def is_generated(
    rel: str, locked: dict[str, Any] | None, config: RegistryConfig
) -> bool:
    """Whether ``rel`` (inside a plugin) is owned by build rather than upstream."""
    if locked is None or rel in locked:
        return False
    return matches(rel, generated_patterns(config))


def display_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def short_description(text: str) -> str:
    """First sentence of a description, cut to 64 characters."""
    sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0].rstrip(".")
    if len(sentence) > MAX_SHORT:
        sentence = sentence[: MAX_SHORT - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return sentence


def registry_id(config: RegistryConfig, item: Item) -> str:
    return f"{config.name}:{item.id}"


def provenance(  # noqa: PLR0917
    config: RegistryConfig,
    policy: ChannelPolicy,
    item: Item,
    lock: ItemLock,
    manifest: dict[str, Any],
    skill: str | None = None,
) -> metadata.Provenance:
    """The provenance stamped into an item's manifest or one of its skills."""
    upstream = lock.upstream
    source_path = f"{upstream.path}/skills/{skill}" if skill else None
    license_ = manifest.get("license")
    return metadata.Provenance(
        registry_id=registry_id(config, item),
        kind=item.kind.value,
        version=manifest.get("version"),
        upstream_marketplace=upstream.repository,
        upstream_plugin=upstream.plugin,
        upstream_ref=upstream.ref,
        upstream_commit=upstream.commit,
        upstream_version=lock.version,
        upstream_license=license_ if isinstance(license_, str) else None,
        source_path=source_path,
        source_digest=lock.tree_sha256,
        risk_tier=(item.risk_tier or policy.default_risk_tier).value,
        data_classification=item.data_classification
        or policy.default_data_classification,
        allowed_tools=item.allowed_tools or None,
        supported_channels=[c.value for c in item.supported_channels],
        deprecation_replacement=item.deprecation.replacement
        if item.deprecation
        else None,
        deprecation_removal_date=item.deprecation.removal_date
        if item.deprecation
        else None,
        parts=[p.model_dump(by_alias=True) for p in lock.parts] or None,
    )


@dataclass
class PluginBuild:
    """Builds one plugin directory inside an overlay."""

    reg: Registry
    overlay: Overlay
    item: Item

    @property
    def base(self) -> str:
        return plugin_dir(self.item.id)

    @property
    def lock(self) -> ItemLock | None:
        return self.reg.lock.items.get(self.item.id)

    def rel(self, path: str) -> str:
        return f"{self.base}/{path}"

    def generated(self, path: str) -> bool:
        if self.lock is None:
            return not self.overlay.exists(self.rel(path)) and matches(
                path, generated_patterns(self.reg.config)
            )
        return is_generated(path, self.lock.files, self.reg.config)

    def source_manifest(self) -> str:
        """The manifest path that holds real upstream content."""
        real = self.real_manifests()
        if real:
            return real[0]
        for path in (CLAUDE_MANIFEST, ROOT_MANIFEST):
            if self.overlay.read_text(self.rel(path)) is not None:
                return path
        raise InvalidInputError(
            f"{self.base}: no plugin.json or .claude-plugin/plugin.json"
        )

    def manifest_data(self) -> dict[str, Any]:
        text = self.overlay.read_text(self.rel(self.source_manifest()))
        try:
            data = json.loads(text or "")
        except json.JSONDecodeError as exc:
            raise InvalidInputError(f"{self.base}: invalid manifest: {exc}") from exc
        if not isinstance(data, dict):
            raise InvalidInputError(f"{self.base}: manifest must be a JSON object")
        return data

    def real_manifests(self) -> list[str]:
        return [
            path
            for path in (CLAUDE_MANIFEST, ROOT_MANIFEST)
            if self.overlay.exists(self.rel(path))
            and not self.overlay.is_link(self.rel(path))
            and not self.generated(path)
        ]

    def run(self) -> None:
        source = self.source_manifest()
        self.brand(source)
        for path in self.real_manifests() or [source]:
            self.stamp_manifest(path)
        other = ROOT_MANIFEST if source == CLAUDE_MANIFEST else CLAUDE_MANIFEST
        self.counterpart(source, other, self.reg.config.layout.manifest_symlinks)
        self.mcp()
        self.skills()

    def counterpart(self, source: str, other: str, use_link: bool) -> None:
        """Generate ``other`` from ``source`` when it is missing or generated."""
        full = self.rel(other)
        keep = self.overlay.exists(full) and not self.generated(other)
        if keep and not (use_link and self.overlay.is_link(full)):
            return
        if use_link:
            target = PurePosixPath(source)
            depth = len(PurePosixPath(other).parts) - 1
            self.overlay.link(full, "/".join([".."] * depth + list(target.parts)))
            return
        text = self.overlay.read_text(self.rel(source)) or ""
        if other == ROOT_MANIFEST:
            text = with_schema(text)
        self.overlay.write(full, text)

    def mcp(self) -> None:
        use_link = self.reg.config.layout.mcp_symlink
        for source, other in ((CLAUDE_MCP, ROOT_MCP), (ROOT_MCP, CLAUDE_MCP)):
            full = self.rel(source)
            if (
                self.overlay.exists(full)
                and not self.overlay.is_link(full)
                and not self.generated(source)
            ):
                self.counterpart(source, other, use_link)
                return

    def brand(self, source: str) -> None:
        branding = self.reg.config.branding
        if branding is None or self.item.kind is ItemKind.MIRROR:
            return
        full = self.rel(source)
        text = self.overlay.read_text(full) or ""
        data = self.manifest_data()
        ext = dict((data.get("extensions") or {}).get(OPENAI) or {})
        interface = dict(ext.get("interface") or {})
        description = str(data.get("description") or "")
        icon = self.icon_ref()
        defaults = {
            "displayName": display_name(self.item.id),
            "shortDescription": short_description(description),
            "longDescription": description,
            "developerName": branding.developer_name,
            "category": catalogs.category(
                catalogs.CatalogPlugin(self.item, data), self.reg.config
            ),
            "websiteURL": branding.website_url,
            "brandColor": branding.brand_color,
            "composerIcon": icon,
            "logo": icon,
        }
        for key, value in defaults.items():
            if value and key not in interface:
                interface[key] = value
        if ext.get("interface") == interface:
            return
        ext["interface"] = interface
        self.overlay.write(full, jsontext.set_extension(text, OPENAI, ext))
        if icon:
            self.copy_icon(f"assets/{PurePosixPath(icon).name}")

    def icon_ref(self) -> str | None:
        branding = self.reg.config.branding
        if branding is None or branding.icon is None:
            return None
        return f"./assets/{PurePosixPath(branding.icon).name}"

    def copy_icon(self, path: str) -> None:
        branding = self.reg.config.branding
        if branding is None or branding.icon is None:
            return
        icon = self.reg.repo / branding.icon
        if not icon.is_file():
            raise InvalidInputError(f"branding icon {branding.icon} not found")
        full = self.rel(path)
        if self.overlay.exists(full) and not self.generated(path):
            return
        self.overlay.write(full, icon.read_bytes())

    def stamp_manifest(self, source: str) -> None:
        if self.lock is None:
            return
        full = self.rel(source)
        prov = provenance(
            self.reg.config,
            self.reg.policy,
            self.item,
            self.lock,
            self.manifest_data(),
        )
        text = self.overlay.read_text(full) or ""
        self.overlay.write(
            full, metadata.stamped_manifest(text, self.reg.config.namespace, prov)
        )

    def skill_names(self) -> list[str]:
        root = self.reg.repo / self.base / "skills"
        if not root.is_dir():
            return []
        return sorted(
            p.name
            for p in root.iterdir()
            if p.is_dir() and not p.is_symlink() and (p / "SKILL.md").is_file()
        )

    def skills(self) -> None:
        manifest = self.manifest_data()
        for name in self.skill_names():
            skill_md = self.rel(f"skills/{name}/SKILL.md")
            text = self.overlay.read_text(skill_md) or ""
            if self.lock is not None and frontmatter.split(text) is not None:
                prov = provenance(
                    self.reg.config,
                    self.reg.policy,
                    self.item,
                    self.lock,
                    manifest,
                    skill=name,
                )
                text = metadata.stamped_skill(text, self.reg.config.namespace, prov)
                self.overlay.write(skill_md, text)
            self.openai_yaml(name, text)

    def openai_yaml(self, name: str, skill_text: str) -> None:
        branding = self.reg.config.branding
        if branding is None or not branding.openai_yaml_stubs:
            return
        path = f"skills/{name}/agents/openai.yaml"
        if self.overlay.exists(self.rel(path)) and not self.generated(path):
            text = self.overlay.read_text(self.rel(path)) or ""
        else:
            text = stub_yaml(name, skill_text, self.icon_ref(), branding.brand_color)
            self.overlay.write(self.rel(path), text)
        icon = self.icon_ref()
        if icon and icon in text:
            self.copy_icon(f"skills/{name}/assets/{PurePosixPath(icon).name}")


def with_schema(text: str) -> str:
    """An Agent Plugins manifest needs ``$schema``; add it first when missing."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(data, dict) or "$schema" in data:
        return text
    return jsontext.dump({"$schema": PLUGIN_SCHEMA, **data})


def stub_yaml(
    name: str, skill_text: str, icon: str | None, brand_color: str | None
) -> str:
    try:
        data, _ = frontmatter.load(skill_text)
    except ValueError:
        data = {}
    implicit = str(data.get("disable-model-invocation", "")).lower() != "true"
    short = short_description(str(data.get("description") or "")).replace('"', "'")
    lines = [
        "interface:",
        f'  display_name: "{display_name(name)}"',
        f'  short_description: "{short}"',
    ]
    if icon:
        lines += [f'  icon_small: "{icon}"', f'  icon_large: "{icon}"']
    if brand_color:
        lines.append(f'  brand_color: "{brand_color}"')
    lines += [
        "policy:",
        f"  allow_implicit_invocation: {'true' if implicit else 'false'}",
    ]
    return "\n".join(lines) + "\n"


def flat_skills(reg: Registry, overlay: Overlay) -> None:
    """``skills/<name>`` -> ``../plugins/<plugin>/skills/<name>`` for every skill."""
    wanted: dict[str, str] = {}
    for item in reg.items.items:
        for name in PluginBuild(reg, overlay, item).skill_names():
            target = f"../{plugin_dir(item.id)}/skills/{name}"
            if name in wanted and wanted[name] != target:
                raise InvalidInputError(
                    f"skill '{name}' exists in two plugins; the flat view needs "
                    "unique names"
                )
            wanted[name] = target
    root = reg.repo / FLAT_SKILLS_DIR
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_symlink() and entry.name not in wanted:
                overlay.remove(f"{FLAT_SKILLS_DIR}/{entry.name}")
    for name, target in sorted(wanted.items()):
        path = root / name
        if path.exists() and not path.is_symlink():
            raise InvalidInputError(
                f"{FLAT_SKILLS_DIR}/{name} is a real path; expected a generated link"
            )
        overlay.link(f"{FLAT_SKILLS_DIR}/{name}", target)


def plan(reg: Registry) -> Overlay:
    """Every change ``build`` would make, without touching the disk."""
    overlay = Overlay(reg.repo)
    plugins: list[catalogs.CatalogPlugin] = []
    for item in sorted(reg.items.items, key=lambda i: i.id):
        if not (reg.repo / plugin_dir(item.id)).is_dir():
            log.warning("Item %s has no %s directory", item.id, plugin_dir(item.id))
            continue
        builder = PluginBuild(reg, overlay, item)
        builder.run()
        plugins.append(catalogs.CatalogPlugin(item, builder.manifest_data()))
    if reg.config.layout.flat_skills:
        flat_skills(reg, overlay)
    overlay.write(catalogs.AGENTS_CATALOG, catalogs.agents_catalog(reg.config, plugins))
    overlay.write(catalogs.CLAUDE_CATALOG, catalogs.claude_catalog(reg.config, plugins))
    return overlay
