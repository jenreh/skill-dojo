from pathlib import Path

import pytest

from skill_dojo_core import InvalidInputError, NotFoundError, registry
from skill_dojo_core.models import (
    FileLock,
    Item,
    ItemKind,
    ItemLock,
    ItemsFile,
    LockFile,
    Namespace,
    RegistryConfig,
    RiskTier,
    ToolPin,
    Upstream,
)

SHA = "a" * 64


def write(repo: Path, name: str, text: str) -> None:
    path = registry.registry_path(repo, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def config_yaml() -> str:
    return (
        "name: acme\nnamespace:\n  skill: acme.registry/\n"
        "  plugin: com.acme.registry\ntool:\n  version: 1.2.3\n"
    )


def test_load_requires_config(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError, match="skill-dojo init"):
        registry.Registry.load(tmp_path)


def test_load_defaults_for_optional_files(tmp_path: Path) -> None:
    write(tmp_path, registry.CONFIG, config_yaml())
    reg = registry.Registry.load(tmp_path)
    assert reg.config.name == "acme"
    assert reg.items.items == []
    assert reg.lock.items == {}
    assert reg.policy.default_risk_tier is RiskTier.STANDARD


def test_invalid_yaml_and_schema(tmp_path: Path) -> None:
    write(tmp_path, registry.CONFIG, "name: [unclosed\n")
    with pytest.raises(InvalidInputError, match="invalid YAML"):
        registry.Registry.load(tmp_path)
    write(tmp_path, registry.CONFIG, "name: acme\n")
    with pytest.raises(InvalidInputError, match="namespace"):
        registry.Registry.load(tmp_path)


def test_save_keeps_comments_and_unknown_keys(tmp_path: Path) -> None:
    write(tmp_path, registry.CONFIG, config_yaml())
    write(
        tmp_path,
        registry.ITEMS,
        "# curated items\nitems:\n  - id: one # first\n    kind: local\n"
        "    owner: team-a\n  - id: two\n    kind: local\n",
    )
    reg = registry.Registry.load(tmp_path)
    reg.items.items[1].quarantined = True
    reg.items.items.append(Item(id="three", kind=ItemKind.LOCAL))
    assert reg.save_items()
    text = registry.registry_path(tmp_path, registry.ITEMS).read_text()
    assert "# curated items" in text
    assert "id: one # first" in text
    assert "owner: team-a" in text
    assert "quarantined: true" in text
    assert "id: three" in text
    assert not reg.save_items()


def test_save_new_file(tmp_path: Path) -> None:
    items = ItemsFile(items=[Item(id="x", kind=ItemKind.LOCAL)])
    assert registry.save_yaml_model(tmp_path, registry.ITEMS, items)
    loaded = registry.load_yaml_model(tmp_path, registry.ITEMS, ItemsFile)
    assert loaded == items


def test_lock_round_trip_is_stable(tmp_path: Path) -> None:
    lock = LockFile(
        items={
            "x": ItemLock(
                kind=ItemKind.LOCAL,
                upstream=Upstream(repository="o/r", commit="c" * 40, path="plugins/x"),
                tree_sha256=SHA,
                files={"a": FileLock(mode="100644", sha256=SHA)},
            )
        }
    )
    assert registry.save_lock(tmp_path, lock)
    assert not registry.save_lock(tmp_path, lock)
    text = registry.registry_path(tmp_path, registry.LOCK).read_text()
    assert '"treeSha256"' in text
    assert registry.load_lock(tmp_path) == lock


def test_invalid_lock(tmp_path: Path) -> None:
    write(tmp_path, registry.LOCK, '{"items": {"x": {}}}')
    with pytest.raises(InvalidInputError):
        registry.load_lock(tmp_path)


def test_merge_replaces_unmatched_lists() -> None:
    raw = registry.yaml_rt().load("a: [1, 2]\nb: x\n")
    merged = registry.merge(raw, {"a": [3], "c": 1})
    assert registry.dump_yaml(merged) == "a: [3]\nc: 1\n"


def test_merge_does_not_match_lists_by_a_repeated_key() -> None:
    raw = registry.yaml_rt().load("a:\n  - item: x\n    n: 1\n")
    new = {"a": [{"item": "x", "n": 1}, {"item": "x", "n": 2}]}
    text = registry.dump_yaml(registry.merge(raw, new))
    assert "&" not in text
    assert text.count("item: x") == 2
    assert "n: 2" in text


def test_models_validate_pins() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ToolPin()
    with pytest.raises(ValueError, match="40-character"):
        ToolPin(git="abc")
    with pytest.raises(ValueError, match="exact"):
        ToolPin(version="1.2")
    with pytest.raises(ValueError, match="duplicate"):
        ItemsFile(items=[Item(id="a", kind="local"), Item(id="a", kind="local")])
    with pytest.raises(ValueError, match="valid plugin name"):
        Item(id="Bad Name", kind="local")
    with pytest.raises(ValueError, match="single"):
        Namespace(skill="a/b/", plugin="com.a.b")
    with pytest.raises(ValueError, match="reverse-domain"):
        Namespace(skill="a/", plugin="nope")
    with pytest.raises(ValueError, match="sha256"):
        FileLock(mode="100644", sha256="x")
    assert (
        RegistryConfig(
            name="acme",
            namespace=Namespace.from_name("acme"),
            tool=ToolPin(version="1.0.0"),
        ).layout.flat_skills
        is False
    )
