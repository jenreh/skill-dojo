"""Line diffs for display: a git diff of a branch, or two texts side by side."""

import difflib
from typing import Any, Literal

from skill_dojo_core.results import Result

type LineKind = Literal[" ", "+", "-", "…"]
MAX_LINES = 400


class DiffLine(Result):
    kind: LineKind
    number: int | None = None
    text: str


class DiffFile(Result):
    path: str
    added: int = 0
    removed: int = 0
    lines: list[DiffLine] = []


def parse_git_diff(text: str, max_lines: int = MAX_LINES) -> list[DiffFile]:
    """``git diff`` output -> files with numbered lines (new-side numbers)."""
    files: list[dict[str, Any]] = []
    number = shown = 0
    for line in text.splitlines():
        if line.startswith("diff --git "):
            files.append(
                {
                    "path": line.rsplit(" b/", 1)[-1],
                    "added": 0,
                    "removed": 0,
                    "lines": [],
                }
            )
            continue
        if not files or line.startswith(("---", "+++", "index ", "new file")):
            continue
        if line.startswith("@@"):
            number = _hunk_start(line)
            continue
        current = files[-1]
        kind: LineKind = "+" if line[:1] == "+" else "-" if line[:1] == "-" else " "
        if kind == "+":
            current["added"] += 1
        elif kind == "-":
            current["removed"] += 1
        if shown < max_lines:
            at = None if kind == "-" else number
            current["lines"].append(DiffLine(kind=kind, number=at, text=line[1:]))
            shown += 1
        if kind != "-":
            number += 1
    return [DiffFile(**f) for f in files]


def _hunk_start(header: str) -> int:
    """``@@ -1,2 +3,4 @@`` -> 3."""
    try:
        return int(header.split("+", 1)[1].split(",", 1)[0].split(" ", 1)[0])
    except IndexError, ValueError:
        return 1


def compare_texts(old: str, new: str, *, context: int | None = 3) -> list[DiffLine]:
    """``new`` against ``old``; ``context=None`` gives the whole file."""
    a, b = old.splitlines(), new.splitlines()
    lines: list[DiffLine] = []
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    groups = (
        [matcher.get_opcodes()]
        if context is None
        else list(matcher.get_grouped_opcodes(context))
    )
    for index, group in enumerate(groups):
        if index or (group and group[0][3] > 0 and context is not None):
            lines.append(DiffLine(kind="…", text=""))
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                lines += [
                    DiffLine(kind=" ", number=j1 + n + 1, text=b[j1 + n])
                    for n in range(j2 - j1)
                ]
                continue
            lines += [
                DiffLine(kind="-", number=j1 + 1, text=a[i]) for i in range(i1, i2)
            ]
            lines += [
                DiffLine(kind="+", number=j + 1, text=b[j]) for j in range(j1, j2)
            ]
    if groups and context is not None and groups[-1] and groups[-1][-1][4] < len(b):
        lines.append(DiffLine(kind="…", text=""))
    return lines
