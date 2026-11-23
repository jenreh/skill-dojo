"""Plugin versions: semver bumps and formatting-preserving manifest edits.

A local plugin that changed on the work branch gets a patch bump relative to its
version on ``origin/main``; a mirror keeps the upstream version.
"""

import json
import re
from typing import Literal

from skill_dojo_core import jsontext
from skill_dojo_core.errors import InvalidInputError

FIRST_VERSION = "0.1.0"
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.+-]*)?$")
EXACT_RE = re.compile(r"^\d+\.\d+\.\d+$")
type Level = Literal["patch", "minor", "major"]
LEVELS: tuple[Level, ...] = ("patch", "minor", "major")


def parse(version: str | None) -> tuple[int, int, int] | None:
    """``(major, minor, patch)`` of a semver string, else None."""
    match = SEMVER_RE.match(version or "")
    if match is None:
        return None
    major, minor, patch = (int(g) for g in match.groups())
    return major, minor, patch


def check_level(level: str) -> Level:
    if level not in LEVELS:
        raise InvalidInputError(f"'{level}' is not one of {', '.join(LEVELS)}")
    return level


def bump(version: str | None, level: Level = "patch") -> str:
    """The next version after ``version``; ``0.1.0`` (or ``1.0.0``) without one."""
    if version is None:
        return "1.0.0" if level == "major" else FIRST_VERSION
    parsed = parse(version)
    if parsed is None:
        raise InvalidInputError(f"version '{version}' is not semver")
    major, minor, patch = parsed
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def is_greater(new: str | None, old: str | None) -> bool:
    """Whether ``new`` is a higher semver than ``old`` (anything beats None)."""
    a = parse(new)
    if a is None:
        return False
    b = parse(old)
    return b is None or a > b


def level_between(old: str | None, new: str | None) -> Level | None:
    """The level that turns ``old`` into ``new`` (None when not a bump)."""
    a, b = parse(old), parse(new)
    if b is None or (a is not None and b <= a):
        return None
    if a is None or b[0] > a[0]:
        return "major" if a is not None else "patch"
    return "minor" if b[1] > a[1] else "patch"


def check_exact(version: str) -> str:
    if not EXACT_RE.match(version):
        raise InvalidInputError(f"'{version}' is not an exact X.Y.Z version")
    return version


def target(main: str | None, level: Level | None, exact: str | None) -> str:
    """The version ``version --<level>`` or ``--set`` asks for, relative to main."""
    if (level is None) == (exact is None):
        raise InvalidInputError("give exactly one of a level or --set")
    if exact is not None:
        check_exact(exact)
        if main is not None and not is_greater(exact, main):
            raise InvalidInputError(f"{exact} is not greater than {main} on main")
        return exact
    return bump(main, level or "patch")


VERSION_KEY_RE = re.compile(r'("version"\s*:\s*)"(?:[^"\\]|\\.)*"')


def with_version(text: str, version: str) -> str:
    """``text`` (a manifest) with its top-level ``version`` set to ``version``."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise InvalidInputError("manifest must be a JSON object")
    if data.get("version") == version:
        return text
    expected = {**data, "version": version} if "version" in data else None
    if expected is not None:
        edited = VERSION_KEY_RE.sub(lambda m: f'{m.group(1)}"{version}"', text, count=1)
        try:
            if json.loads(edited) == expected:
                return edited
        except json.JSONDecodeError:
            pass
        return jsontext.dump(expected)
    ordered: dict[str, object] = {}
    for key, value in data.items():
        ordered[key] = value
        if key == "name":
            ordered["version"] = version
    ordered.setdefault("version", version)
    return jsontext.dump(ordered)
