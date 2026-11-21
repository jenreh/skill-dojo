"""Read and minimally edit ``SKILL.md`` YAML frontmatter.

Edits are textual where possible, so upstream formatting survives and a stamp
shows up in a diff as the added lines only.
"""

import io
import json
import re
from dataclasses import dataclass
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

DELIMITER = "---"


@dataclass(frozen=True)
class Document:
    """A Markdown file split into its frontmatter text and body."""

    frontmatter: str
    body: str

    def render(self) -> str:
        return f"{DELIMITER}\n{self.frontmatter}{DELIMITER}\n{self.body}"


def split(text: str) -> Document | None:
    """Split ``---`` frontmatter from the body, or ``None`` without one."""
    if not text.startswith(DELIMITER + "\n"):
        return None
    rest = text[len(DELIMITER) + 1 :]
    if rest.startswith(DELIMITER + "\n"):
        return Document(frontmatter="", body=rest[len(DELIMITER) + 1 :])
    match = re.search(r"^---[ \t]*(?:\n|$)", rest, re.MULTILINE)
    if match is None:
        return None
    return Document(frontmatter=rest[: match.start()], body=rest[match.end() :])


def _safe_yaml() -> YAML:
    yaml = YAML(typ="safe", pure=True)
    yaml.allow_duplicate_keys = False
    return yaml


def parse(frontmatter: str) -> dict[str, Any]:
    """Parse frontmatter into plain data. Raises ``ValueError`` when invalid."""
    try:
        data = _safe_yaml().load(frontmatter) if frontmatter.strip() else {}
    except YAMLError as exc:
        raise ValueError(f"invalid YAML frontmatter: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data


def load(text: str) -> tuple[dict[str, Any], Document]:
    doc = split(text)
    if doc is None:
        raise ValueError("missing '---' frontmatter block")
    return parse(doc.frontmatter), doc


def _yaml_string(value: str) -> str:
    """A double-quoted YAML scalar (JSON strings are valid YAML)."""
    return json.dumps(value, ensure_ascii=False)


def _metadata_block(lines: list[str]) -> tuple[int, int, str] | None:
    """(start, end, indent) of a block-style top-level ``metadata:`` mapping."""
    for i, line in enumerate(lines):
        if re.match(r"^metadata:\s*(#.*)?$", line):
            end = i + 1
            indent = "  "
            first = True
            while end < len(lines) and (
                not lines[end].strip() or lines[end][:1] in (" ", "\t")
            ):
                if first and lines[end].strip():
                    indent = lines[end][: len(lines[end]) - len(lines[end].lstrip())]
                    first = False
                end += 1
            while end > i + 1 and not lines[end - 1].strip():
                end -= 1
            return i, end, indent
    return None


def set_metadata(text: str, prefix: str, values: dict[str, str]) -> str:
    """Replace every ``metadata`` key starting with ``prefix`` by ``values``.

    Other frontmatter keys, other metadata keys and the body stay byte-identical
    where the frontmatter uses block style; otherwise the frontmatter is
    re-serialized.
    """
    data, doc = load(text)
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("frontmatter 'metadata' must be a mapping")
    expected = {
        **{k: v for k, v in (metadata or {}).items() if not str(k).startswith(prefix)},
        **values,
    }
    edited = _edit_textually(doc.frontmatter, prefix, values)
    if edited is not None:
        candidate = Document(frontmatter=edited, body=doc.body)
        try:
            again = parse(edited)
        except ValueError:
            again = None
        if again is not None and _same_except_metadata(data, again, expected):
            return candidate.render()
    return Document(
        frontmatter=_dump_with_metadata(doc.frontmatter, prefix, values),
        body=doc.body,
    ).render()


def _same_except_metadata(
    before: dict[str, Any], after: dict[str, Any], metadata: dict[str, Any]
) -> bool:
    rest_before = {k: v for k, v in before.items() if k != "metadata"}
    rest_after = {k: v for k, v in after.items() if k != "metadata"}
    return rest_before == rest_after and (after.get("metadata") or {}) == metadata


def _edit_textually(
    frontmatter: str, prefix: str, values: dict[str, str]
) -> str | None:
    lines = frontmatter.splitlines()
    block = _metadata_block(lines)
    if block is None:
        if re.search(r"^metadata\s*:", frontmatter, re.MULTILINE):
            return None  # flow style or inline value: re-serialize instead
        if not values:
            return frontmatter
        new = [f"  {key}: {_yaml_string(val)}" for key, val in values.items()]
        return "\n".join([*lines, "metadata:", *new]) + "\n"
    start, end, indent = block
    own = re.compile(rf"^{re.escape(indent)}{re.escape(prefix)}[^:]*:")
    kept = [line for line in lines[start + 1 : end] if not own.match(line)]
    if any(line.strip() and not line.startswith(indent) for line in kept):
        return None
    new = [f"{indent}{key}: {_yaml_string(val)}" for key, val in values.items()]
    body = kept + new
    head = lines[:start] if not body else [*lines[:start], lines[start]]
    return "\n".join([*head, *body, *lines[end:]]) + "\n"


def _dump_with_metadata(frontmatter: str, prefix: str, values: dict[str, str]) -> str:
    yaml = YAML()
    yaml.width = 4096
    yaml.preserve_quotes = True
    data = yaml.load(frontmatter) or {}
    metadata = data.get("metadata") or {}
    for key in [k for k in metadata if str(k).startswith(prefix)]:
        del metadata[key]
    metadata.update(values)
    if metadata:
        data["metadata"] = metadata
    elif "metadata" in data:
        del data["metadata"]
    out = io.StringIO()
    yaml.dump(data, out)
    return out.getvalue()
