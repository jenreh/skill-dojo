import json
from pathlib import Path

from skill_dojo_core import metadata
from skill_dojo_core.models import Namespace

NS = Namespace.from_name("Acme")


def prov(**extra: object) -> metadata.Provenance:
    return metadata.Provenance(
        registry_id="acme:greet",
        kind="mirror",
        version="1.4.2",
        upstream_marketplace="openai/community-plugins",
        upstream_commit="8f2c1a9",
        source_path="plugins/x/skills/greet",
        **extra,  # ty: ignore[invalid-argument-type]
    )


def test_namespace_from_name() -> None:
    assert NS.skill == "acme.registry/"
    assert NS.plugin == "com.acme.registry"
    assert Namespace.from_name("My Tools!").plugin == "com.my-tools.registry"


def test_skill_metadata_is_flat_prefixed_strings() -> None:
    data = prov(deprecation_replacement="acme:new").skill_metadata(NS.skill)
    assert data == {
        "acme.registry/id": "acme:greet",
        "acme.registry/kind": "mirror",
        "acme.registry/version": "1.4.2",
        "acme.registry/source-marketplace": "openai/community-plugins",
        "acme.registry/source-commit": "8f2c1a9",
        "acme.registry/source-path": "plugins/x/skills/greet",
        "acme.registry/deprecation-replacement": "acme:new",
    }
    assert all(isinstance(v, str) for v in data.values())


def test_plugin_extension_is_camel_case_with_lists() -> None:
    ext = prov(
        deprecation_replacement="acme:new",
        deprecation_removal_date="2027-01-01",
        parts=[{"name": "greet"}],
    ).plugin_extension()
    assert ext == {
        "registryId": "acme:greet",
        "kind": "mirror",
        "upstreamMarketplace": "openai/community-plugins",
        "upstreamCommit": "8f2c1a9",
        "deprecation": {"replacement": "acme:new", "removalDate": "2027-01-01"},
        "parts": [{"name": "greet"}],
    }


def test_stamp_and_read_back(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: greet\nmetadata:\n  author: up\n---\nbody\n")
    manifest = tmp_path / "plugin.json"
    manifest.write_text('{"name": "greet", "extensions": {"com.openai": {"a": 1}}}')
    assert metadata.stamp_skill(skill, NS, prov())
    assert not metadata.stamp_skill(skill, NS, prov())
    assert metadata.stamp_manifest(manifest, NS, prov())
    assert not metadata.stamp_manifest(manifest, NS, prov())
    assert metadata.read_skill_metadata(skill, NS)["id"] == "acme:greet"
    assert metadata.read_extension(manifest, NS)["kind"] == "mirror"
    data = json.loads(manifest.read_text())
    assert data["extensions"]["com.openai"] == {"a": 1}
    assert "author: up" in skill.read_text()


def test_read_extension_without_namespace(tmp_path: Path) -> None:
    manifest = tmp_path / "plugin.json"
    manifest.write_text('{"name": "x"}')
    assert metadata.read_extension(manifest, NS) == {}
