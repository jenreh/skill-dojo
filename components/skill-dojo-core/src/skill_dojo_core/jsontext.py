"""Minimal, formatting-preserving edits of JSON files such as ``plugin.json``."""

import copy
import json
import re
from typing import Any

_DECODER = json.JSONDecoder()


def dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _indent_of(text: str) -> str:
    match = re.search(r'^([ \t]+)"', text, re.MULTILINE)
    return match.group(1) if match else "  "


def _format(value: Any, base: str, unit: str) -> str:
    rendered = json.dumps(value, indent=len(unit) or 2, ensure_ascii=False)
    return rendered.replace("\n", "\n" + base)


def set_extension(text: str, key: str, value: dict[str, Any] | None) -> str:
    """Set (or with ``None`` remove) ``extensions[key]`` of a JSON object.

    Everything else keeps its bytes when the edit can be made textually.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    expected = copy.deepcopy(data)
    extensions = expected.setdefault("extensions", {})
    if value is None:
        extensions.pop(key, None)
        if not extensions:
            del expected["extensions"]
    else:
        extensions[key] = value
    if expected == data:
        return text
    edited = _edit(text, key, value) if value is not None else None
    if edited is not None:
        try:
            if json.loads(edited) == expected:
                return edited
        except json.JSONDecodeError:
            pass
    return dump(expected)


def _edit(text: str, key: str, value: dict[str, Any]) -> str | None:
    unit = _indent_of(text)
    match = re.search(r'"extensions"\s*:\s*\{', text)
    if match is None:
        close = text.rstrip().rfind("}")
        if close < 0:
            return None
        head = text[:close].rstrip()
        inner = unit * 2
        block = (
            f',\n{unit}"extensions": {{\n{inner}"{key}": '
            f"{_format(value, inner, unit)}\n{unit}}}\n"
        )
        return head + block + text[close:]
    open_brace = match.end() - 1
    _, ext_end = _DECODER.raw_decode(text, open_brace)
    body = text[open_brace:ext_end]
    line_start = text.rfind("\n", 0, match.start()) + 1
    base = text[line_start : match.start()]
    inner = base + unit
    own = re.search(rf'"{re.escape(key)}"\s*:\s*', body)
    if own is not None:
        start = open_brace + own.end()
        _, end = _DECODER.raw_decode(text, start)
        return text[:start] + _format(value, inner, unit) + text[end:]
    empty = body[1:-1].strip() == ""
    sep = "\n" + base if empty else ","
    entry = f'\n{inner}"{key}": {_format(value, inner, unit)}{sep}'
    return (
        text[: open_brace + 1]
        + entry
        + text[open_brace + 1 :]
        .lstrip(" \t" if empty else "")
        .removeprefix("\n" if empty else "")
    )
