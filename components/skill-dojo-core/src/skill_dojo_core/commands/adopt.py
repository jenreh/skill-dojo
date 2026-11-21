"""``init --adopt``: turn an existing marketplace repo into a curated one.

Every ``plugins/*`` becomes a ``local`` item. Name, owner, layout, branding,
categories and policies are read from the existing catalogs and manifests, so a
following ``build`` reproduces them and only adds the provenance metadata.
"""

import json
import logging
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from skill_dojo_core import builder, catalogs, git
from skill_dojo_core.commands.items import register_local
from skill_dojo_core.commands.repo import ensure_no_config, scaffold
from skill_dojo_core.context import Context
from skill_dojo_core.errors import InvalidInputError, NotFoundError
from skill_dojo_core.models import (
    Branding,
    Item,
    ItemKind,
    Layout,
    Namespace,
    Owner,
    Policy,
    RegistryConfig,
    ToolPin,
)
from skill_dojo_core.registry import Registry
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result
from skill_dojo_core.validation.mcp_pins import floating_reference
from skill_dojo_core.validation.report import Finding

log = logging.getLogger(__name__)


class AdoptResult(Result):
    marketplace: str
    items: list[str]
    changed: list[str]
    floating_mcp: list[Finding]
    possibly_vendored: list[Finding]


def _read_json(path: Path) -> dict[str, Any]:
    """A JSON object, ``{}`` when the file is missing; broken files raise."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidInputError(
            f"{path.name}: cannot adopt a broken file: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise InvalidInputError(f"{path.name}: top level must be an object")
    return data


def _most_common(values: list[Any]) -> Any:
    counted = Counter(json.dumps(v, sort_keys=True) for v in values if v)
    return json.loads(counted.most_common(1)[0][0]) if counted else None


def _plugins(repo: Path) -> list[Path]:
    root = repo / builder.PLUGINS_DIR
    if not root.is_dir():
        raise NotFoundError("no plugins/ folder to adopt")
    return sorted(p for p in root.iterdir() if p.is_dir())


def _manifest(plugin: Path) -> dict[str, Any]:
    for rel in (builder.CLAUDE_MANIFEST, builder.ROOT_MANIFEST):
        data = _read_json(plugin / rel)
        if data:
            return data
    return {}


def _interface(manifest: dict[str, Any]) -> dict[str, Any]:
    ext = (manifest.get("extensions") or {}).get(builder.OPENAI) or {}
    interface = ext.get("interface") if isinstance(ext, dict) else None
    return interface if isinstance(interface, dict) else {}


def detect_layout(repo: Path, plugins: list[Path]) -> Layout:
    flat = repo / builder.FLAT_SKILLS_DIR
    return Layout(
        manifest_symlinks=any(
            (p / builder.ROOT_MANIFEST).is_symlink()
            or (p / builder.CLAUDE_MANIFEST).is_symlink()
            for p in plugins
        ),
        mcp_symlink=any((p / builder.ROOT_MCP).is_symlink() for p in plugins),
        flat_skills=flat.is_dir() and any(e.is_symlink() for e in flat.iterdir()),
    )


def detect_branding(repo: Path, plugins: list[Path]) -> Branding | None:
    interfaces = [_interface(_manifest(p)) for p in plugins]
    stubs = any(p.glob("skills/*/agents/openai.yaml") for p in plugins)
    if not any(interfaces) and not stubs:
        return None
    icon_ref = _most_common([i.get("composerIcon") for i in interfaces])
    icon = None
    if isinstance(icon_ref, str):
        candidate = f"assets/{PurePosixPath(icon_ref).name}"
        icon = candidate if (repo / candidate).is_file() else None
    return Branding(
        icon=icon,
        brand_color=_most_common([i.get("brandColor") for i in interfaces]),
        developer_name=_most_common([i.get("developerName") for i in interfaces]),
        website_url=_most_common([i.get("websiteURL") for i in interfaces]),
        openai_yaml_stubs=stubs,
    )


def adopt_config(
    repo: Path,
    plugins: list[Path],
    catalog_data: tuple[dict[str, Any], dict[str, Any]],
    tool: ToolPin,
    repository: str | None,
) -> RegistryConfig:
    """Config from the existing (claude, agents) catalogs and manifests."""
    claude, agents = catalog_data
    name = str(claude.get("name") or agents.get("name") or repo.name.lower())
    owner = claude.get("owner")
    entries = [e for e in agents.get("plugins") or [] if isinstance(e, dict)]
    policy = _most_common([e.get("policy") for e in entries])
    category = _most_common([e.get("category") for e in entries])
    return RegistryConfig(
        name=name,
        repository=repository,
        display_name=(agents.get("interface") or {}).get("displayName"),
        description=(claude.get("metadata") or {}).get("description"),
        owner=Owner.model_validate(owner) if isinstance(owner, dict) else None,
        namespace=Namespace.from_name(name),
        tool=tool,
        layout=detect_layout(repo, plugins),
        branding=detect_branding(repo, plugins),
        default_category=category or "Coding",
        default_policy=Policy.model_validate(policy) if policy else Policy(),
    )


def adopt_item(config: RegistryConfig, agents: dict[str, Any], plugin: Path) -> Item:
    """A local item whose catalog entry matches the existing one."""
    entry = next(
        (
            e
            for e in agents.get("plugins") or []
            if isinstance(e, dict) and e.get("name") == plugin.name
        ),
        {},
    )
    item = Item(id=plugin.name, kind=ItemKind.LOCAL)
    fallback = catalogs.category(
        catalogs.CatalogPlugin(item, _manifest(plugin)), config
    )
    if entry.get("category") and entry["category"] != fallback:
        item.category = entry["category"]
    policy = entry.get("policy")
    if (
        isinstance(policy, dict)
        and Policy.model_validate(policy) != config.default_policy
    ):
        item.policy = Policy.model_validate(policy)
    return item


def floating_servers(plugin: Path) -> list[Finding]:
    found = []
    for rel in (builder.CLAUDE_MCP, builder.ROOT_MCP):
        path = plugin / rel
        if not path.is_file() or path.is_symlink():
            continue
        servers = _read_json(path).get("mcpServers") or {}
        for name, server in servers.items():
            if isinstance(server, dict) and (problem := floating_reference(server)):
                found.append(
                    Finding(
                        level="error",
                        path=f"plugins/{plugin.name}/{rel}",
                        message=f"server '{name}': {problem}",
                    )
                )
    return found


def possibly_vendored(plugin: Path) -> list[Finding]:
    """Skills that carry their own license file were likely copied from upstream."""
    return [
        Finding(
            level="warning",
            path=f"plugins/{plugin.name}/skills/{skill.name}",
            message="has its own license; register it as a mirror or bundle part",
        )
        for skill in sorted((plugin / "skills").glob("*"))
        if skill.is_dir() and any(skill.glob("LICENSE*"))
    ]


def _check_adoptable(plugins: list[Path]) -> None:
    """Fail before writing anything when a plugin cannot be adopted."""
    for plugin in plugins:
        if not _manifest(plugin):
            raise InvalidInputError(
                f"plugins/{plugin.name}: no readable plugin.json or "
                ".claude-plugin/plugin.json"
            )


def adopt(ctx: Context, *, tool: ToolPin, repository: str | None = None) -> AdoptResult:
    """Register every ``plugins/*`` as a local item and add ``registry/``."""
    repo = ctx.repo
    with repo_lock(repo):
        ensure_no_config(repo)
        commit = git.head(repo)
        plugins = _plugins(repo)
        _check_adoptable(plugins)
        claude = _read_json(repo / catalogs.CLAUDE_CATALOG)
        agents = _read_json(repo / catalogs.AGENTS_CATALOG)
        config = adopt_config(repo, plugins, (claude, agents), tool, repository)
        changed = scaffold(repo, config)
        reg = Registry.load(repo)
        for plugin in plugins:
            item = adopt_item(config, agents, plugin)
            generated = register_local(reg, item, commit)
            changed += [f"plugins/{plugin.name}/{rel}" for rel in generated]
        reg.save_items()
        reg.save_lock()
        changed += builder.apply_build(reg)
    floating = [f for p in plugins for f in floating_servers(p)]
    vendored = [s for p in plugins for s in possibly_vendored(p)]
    ctx.report(f"Adopted {len(plugins)} plugin(s) into '{config.name}'")
    log.info("Adopted %d plugins into %s", len(plugins), config.name)
    return AdoptResult(
        marketplace=config.name,
        items=[p.name for p in plugins],
        changed=sorted(set(changed)),
        floating_mcp=floating,
        possibly_vendored=vendored,
    )
