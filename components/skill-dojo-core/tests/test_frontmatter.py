import pytest

from skill_dojo_core import frontmatter

SKILL = """---
name: greet
description: >
  Greets the user. Use when
  saying hello.
allowed-tools: [Read, Grep]
---

# Greet

Body stays.
"""


def test_split_and_render_round_trip() -> None:
    doc = frontmatter.split(SKILL)
    assert doc is not None
    assert doc.render() == SKILL
    assert doc.body == "\n# Greet\n\nBody stays.\n"


def test_split_without_frontmatter() -> None:
    assert frontmatter.split("# no frontmatter\n") is None
    assert frontmatter.split("---\nname: x\n") is None


def test_empty_frontmatter() -> None:
    doc = frontmatter.split("---\n---\nbody\n")
    assert doc is not None
    assert doc.frontmatter == ""
    assert frontmatter.parse(doc.frontmatter) == {}


def test_parse_rejects_non_mapping_and_bad_yaml() -> None:
    with pytest.raises(ValueError, match="mapping"):
        frontmatter.parse("- a\n- b\n")
    with pytest.raises(ValueError, match="invalid YAML"):
        frontmatter.parse("a: [unclosed\n")
    with pytest.raises(ValueError, match="invalid YAML"):
        frontmatter.parse("a: 1\na: 2\n")


def test_load_requires_frontmatter() -> None:
    with pytest.raises(ValueError, match="missing"):
        frontmatter.load("body only\n")


def test_set_metadata_appends_block_without_touching_the_rest() -> None:
    out = frontmatter.set_metadata(SKILL, "acme.registry/", {"acme.registry/id": "a:b"})
    assert out == SKILL.replace(
        "allowed-tools: [Read, Grep]\n",
        'allowed-tools: [Read, Grep]\nmetadata:\n  acme.registry/id: "a:b"\n',
    )


def test_set_metadata_keeps_foreign_keys_and_replaces_own() -> None:
    text = (
        "---\nname: x\nmetadata:\n  author: jens\n"
        '  acme.registry/id: "old"\n  acme.registry/gone: "x"\n---\nbody\n'
    )
    out = frontmatter.set_metadata(text, "acme.registry/", {"acme.registry/id": "new"})
    assert out == (
        "---\nname: x\nmetadata:\n  author: jens\n"
        '  acme.registry/id: "new"\n---\nbody\n'
    )


def test_set_metadata_is_idempotent() -> None:
    once = frontmatter.set_metadata(SKILL, "p/", {"p/a": "1", "p/b": "two words"})
    assert (
        frontmatter.set_metadata(once, "p/", {"p/a": "1", "p/b": "two words"}) == once
    )
    data, _ = frontmatter.load(once)
    assert data["metadata"] == {"p/a": "1", "p/b": "two words"}


def test_set_metadata_flow_style_falls_back_to_dump() -> None:
    text = "---\nname: x\nmetadata: {author: jens}\n---\nbody\n"
    out = frontmatter.set_metadata(text, "p/", {"p/id": "1"})
    data, doc = frontmatter.load(out)
    assert data == {"name": "x", "metadata": {"author": "jens", "p/id": "1"}}
    assert doc.body == "body\n"


def test_set_metadata_removing_all_own_keys() -> None:
    text = '---\nname: x\nmetadata:\n  p/id: "1"\n---\nbody\n'
    out = frontmatter.set_metadata(text, "p/", {})
    data, _ = frontmatter.load(out)
    assert data == {"name": "x"}


def test_set_metadata_rejects_non_mapping_metadata() -> None:
    with pytest.raises(ValueError, match="mapping"):
        frontmatter.set_metadata("---\nmetadata: 3\n---\n", "p/", {})


def test_values_with_quotes_survive() -> None:
    out = frontmatter.set_metadata(SKILL, "p/", {"p/x": 'say "hi": now'})
    data, _ = frontmatter.load(out)
    assert data["metadata"]["p/x"] == 'say "hi": now'
