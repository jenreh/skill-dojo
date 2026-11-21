"""Core must not depend on any front end."""

import ast
from pathlib import Path

import skill_dojo_core

FORBIDDEN = {"typer", "reflex", "skill_dojo_cli", "skill_dojo_web", "click"}
SRC = Path(skill_dojo_core.__file__).parent


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_core_imports_no_front_end() -> None:
    offenders = {
        str(path.relative_to(SRC)): sorted(imported_roots(path) & FORBIDDEN)
        for path in SRC.rglob("*.py")
        if imported_roots(path) & FORBIDDEN
    }
    assert offenders == {}


def test_core_never_prints() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"print", "input"}
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
