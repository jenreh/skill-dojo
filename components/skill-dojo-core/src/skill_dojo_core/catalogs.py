"""The two marketplace catalogs, built from ``plugins/`` and ``registry/``.

* ``.agents/plugins/marketplace.json``: Agent Plugins / Codex (canonical)
* ``.claude-plugin/marketplace.json``: Claude Code

Every entry is a local source: content is vendored, never pointed upstream.
"""

import json
from dataclasses import dataclass
from typing import Any

from skill_dojo_core.models import Item, RegistryConfig

AGENTS_CATALOG = ".agents/plugins/marketplace.json"
CLAUDE_CATALOG = ".claude-plugin/marketplace.json"
CLAUDE_ENTRY_FIELDS = ("description", "version", "author", "license")
INLINE_WIDTH = 60
INLINE_DEPTH = 3


@dataclass(frozen=True)
class CatalogPlugin:
    item: Item
    manifest: dict[str, Any]

    @property
    def name(self) -> str:
        return self.item.id

    @property
    def path(self) -> str:
        return f"./plugins/{self.item.id}"


def category(plugin: CatalogPlugin, config: RegistryConfig) -> str:
    if plugin.item.category:
        return plugin.item.category
    interface = (
        (plugin.manifest.get("extensions") or {}).get("com.openai", {}).get("interface")
    )
    if isinstance(interface, dict) and interface.get("category"):
        return str(interface["category"])
    return config.default_category


def agents_catalog(config: RegistryConfig, plugins: list[CatalogPlugin]) -> str:
    entries = []
    for plugin in sorted(plugins, key=lambda p: p.name):
        policy = plugin.item.policy or config.default_policy
        entries.append(
            {
                "name": plugin.name,
                "source": {"source": "local", "path": plugin.path},
                "policy": {
                    "installation": policy.installation,
                    "authentication": policy.authentication,
                },
                "category": category(plugin, config),
            }
        )
    data = {
        "name": config.name,
        "interface": {"displayName": config.display_name or config.name},
        "plugins": entries,
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def claude_catalog(config: RegistryConfig, plugins: list[CatalogPlugin]) -> str:
    entries = []
    for plugin in sorted(plugins, key=lambda p: p.name):
        entry: dict[str, Any] = {"name": plugin.name, "source": plugin.path}
        for key in CLAUDE_ENTRY_FIELDS:
            if plugin.manifest.get(key) is not None:
                entry[key] = plugin.manifest[key]
        entries.append(entry)
    owner = (
        config.owner.model_dump(exclude_none=True)
        if config.owner
        else {"name": config.name}
    )
    data: dict[str, Any] = {"name": config.name, "owner": owner}
    if config.description:
        data["metadata"] = {"description": config.description}
    data["plugins"] = entries
    return compact_dumps(data) + "\n"


def compact_dumps(data: Any, depth: int = 1, indent: str = "  ") -> str:
    """JSON with small flat objects deep in the tree kept on one line."""
    if isinstance(data, dict | list) and data:
        flat = all(not isinstance(v, dict | list) for v in _values(data))
        if flat and depth >= INLINE_DEPTH:
            line = _inline(data)
            if len(line) <= INLINE_WIDTH:
                return line
        pad = indent * depth
        close = indent * (depth - 1)
        if isinstance(data, dict):
            parts = [
                f"{pad}{json.dumps(k, ensure_ascii=False)}: "
                f"{compact_dumps(v, depth + 1, indent)}"
                for k, v in data.items()
            ]
            return "{\n" + ",\n".join(parts) + f"\n{close}}}"
        parts = [f"{pad}{compact_dumps(v, depth + 1, indent)}" for v in data]
        return "[\n" + ",\n".join(parts) + f"\n{close}]"
    return json.dumps(data, ensure_ascii=False)


def _values(data: dict[str, Any] | list[Any]) -> list[Any]:
    return list(data.values()) if isinstance(data, dict) else data


def _inline(data: dict[str, Any] | list[Any]) -> str:
    if isinstance(data, dict):
        body = ", ".join(
            f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
            for k, v in data.items()
        )
        return "{ " + body + " }"
    return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in data) + "]"
