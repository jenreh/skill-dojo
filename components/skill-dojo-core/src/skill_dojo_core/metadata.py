"""Provenance metadata stamped into ``SKILL.md`` and ``plugin.json``.

The same field set is written camelCase under ``extensions.<namespace>`` of a
manifest and as flat, string-only, prefixed kebab-case keys in skill ``metadata``.
Only the tool's own namespace is ever touched.
"""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from skill_dojo_core import frontmatter, jsontext
from skill_dojo_core.models import Namespace

# camelCase field -> skill metadata key (without prefix), where the plain
# kebab-case conversion is not the name the design uses.
SKILL_KEYS = {
    "registryId": "id",
    "upstreamMarketplace": "source-marketplace",
    "upstreamPlugin": "source-plugin",
    "upstreamRef": "source-ref",
    "upstreamCommit": "source-commit",
    "upstreamVersion": "source-version",
    "upstreamLicense": "source-license",
}
# Skill-level facts that a plugin manifest already carries or does not have.
NOT_IN_EXTENSION = frozenset({"version", "sourcePath"})


def _kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


class Provenance(BaseModel):
    """The design's field set. ``None`` fields are not written."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    registry_id: str
    kind: str
    version: str | None = None
    upstream_marketplace: str | None = None
    upstream_plugin: str | None = None
    upstream_ref: str | None = None
    upstream_commit: str | None = None
    upstream_version: str | None = None
    upstream_license: str | None = None
    source_path: str | None = None
    source_digest: str | None = None
    approved_version: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    risk_tier: str | None = None
    data_classification: str | None = None
    allowed_tools: list[str] | None = None
    review_evidence: str | None = None
    supported_channels: list[str] | None = None
    deprecation_replacement: str | None = None
    deprecation_removal_date: str | None = None
    parts: list[dict[str, Any]] | None = None

    def plugin_extension(self) -> dict[str, Any]:
        data = self.model_dump(by_alias=True, exclude_none=True)
        replacement = data.pop("deprecationReplacement", None)
        removal = data.pop("deprecationRemovalDate", None)
        if replacement or removal:
            data["deprecation"] = {
                k: v
                for k, v in (("replacement", replacement), ("removalDate", removal))
                if v
            }
        return {k: v for k, v in data.items() if k not in NOT_IN_EXTENSION}

    def skill_metadata(self, prefix: str) -> dict[str, str]:
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("parts", None)
        out: dict[str, str] = {}
        for key, value in data.items():
            text = ",".join(value) if isinstance(value, list) else str(value)
            out[prefix + SKILL_KEYS.get(key, _kebab(key))] = text
        return out


def stamped_skill(text: str, namespace: Namespace, provenance: Provenance) -> str:
    return frontmatter.set_metadata(
        text, namespace.skill, provenance.skill_metadata(namespace.skill)
    )


def stamped_manifest(text: str, namespace: Namespace, provenance: Provenance) -> str:
    return jsontext.set_extension(text, namespace.plugin, provenance.plugin_extension())


def stamp_skill(path: Path, namespace: Namespace, provenance: Provenance) -> bool:
    """Write the provenance into a ``SKILL.md``. Returns whether it changed."""
    text = path.read_text(encoding="utf-8")
    updated = stamped_skill(text, namespace, provenance)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def stamp_manifest(path: Path, namespace: Namespace, provenance: Provenance) -> bool:
    """Write the provenance into ``extensions.<ns>`` of a manifest."""
    text = path.read_text(encoding="utf-8")
    updated = stamped_manifest(text, namespace, provenance)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def read_skill_metadata(path: Path, namespace: Namespace) -> dict[str, Any]:
    """The tool's namespaced metadata keys of a ``SKILL.md`` (prefix removed)."""
    data, _ = frontmatter.load(path.read_text(encoding="utf-8"))
    metadata = data.get("metadata") or {}
    return {
        str(k)[len(namespace.skill) :]: v
        for k, v in metadata.items()
        if str(k).startswith(namespace.skill)
    }


def read_extension(path: Path, namespace: Namespace) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ext = (data.get("extensions") or {}).get(namespace.plugin)
    return ext if isinstance(ext, dict) else {}
