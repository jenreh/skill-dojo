import json

import pytest

from skill_dojo_core import jsontext

MANIFEST = """{
  "name": "p",
  "author": { "name": "Jens" },
  "keywords": ["a", "b"],
  "extensions": {
    "com.openai": { "interface": { "displayName": "P" } }
  }
}
"""


def test_insert_into_existing_extensions_keeps_other_lines() -> None:
    out = jsontext.set_extension(MANIFEST, "com.acme.registry", {"kind": "local"})
    assert json.loads(out)["extensions"]["com.acme.registry"] == {"kind": "local"}
    assert '"author": { "name": "Jens" },' in out
    assert '"keywords": ["a", "b"],' in out
    assert '"com.openai": { "interface": { "displayName": "P" } }' in out


def test_replace_existing_key() -> None:
    once = jsontext.set_extension(MANIFEST, "com.acme.registry", {"kind": "local"})
    twice = jsontext.set_extension(once, "com.acme.registry", {"kind": "mirror"})
    assert json.loads(twice)["extensions"]["com.acme.registry"] == {"kind": "mirror"}
    assert twice.count("com.acme.registry") == 1


def test_add_extensions_when_missing() -> None:
    text = '{\n  "name": "p"\n}\n'
    out = jsontext.set_extension(text, "com.x.registry", {"a": [1, 2]})
    assert json.loads(out) == {
        "name": "p",
        "extensions": {"com.x.registry": {"a": [1, 2]}},
    }
    assert out.startswith('{\n  "name": "p",\n  "extensions"')


def test_empty_extensions_object() -> None:
    text = '{\n  "name": "p",\n  "extensions": {}\n}\n'
    out = jsontext.set_extension(text, "com.x.registry", {"a": 1})
    assert json.loads(out)["extensions"] == {"com.x.registry": {"a": 1}}


def test_unchanged_value_returns_same_text() -> None:
    once = jsontext.set_extension(MANIFEST, "com.acme.registry", {"kind": "local"})
    assert jsontext.set_extension(once, "com.acme.registry", {"kind": "local"}) == once


def test_remove_key() -> None:
    once = jsontext.set_extension('{"name": "p"}', "com.x.registry", {"a": 1})
    gone = jsontext.set_extension(once, "com.x.registry", None)
    assert json.loads(gone) == {"name": "p"}


def test_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="object"):
        jsontext.set_extension("[1]", "com.x.registry", {})
