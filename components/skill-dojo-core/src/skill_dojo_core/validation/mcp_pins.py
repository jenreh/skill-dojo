"""Detect floating MCP server references (``latest``, no version, no digest)."""

import re
from pathlib import PurePosixPath
from typing import Any

EXACT_VERSION = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
NPM_RUNNERS = frozenset({"npx", "bunx", "pnpx"})
NPM_VALUE_FLAGS = frozenset({"-p", "--package", "-c", "--call"})
UV_VALUE_FLAGS = frozenset(
    {"--from", "--with", "-p", "--python", "--index", "--with-requirements"}
)
CONTAINER_RUNNERS = frozenset({"docker", "podman"})
# Runner options that fetch the package from somewhere else than its registry.
INDEX_FLAGS = (
    "--registry",
    "--index",
    "--index-url",
    "--default-index",
    "--extra-index-url",
    "--find-links",
    "-i",
    "-f",
)
# ``docker run`` options that take a value, so the image is the next positional.
CONTAINER_VALUE_FLAGS = frozenset(
    {
        "-e", "--env", "--env-file", "-v", "--volume", "--mount", "-p", "--publish",
        "--name", "--network", "--net", "-w", "--workdir", "-u", "--user",
        "--entrypoint", "-l", "--label", "--add-host", "--platform", "--pull",
        "--cpus", "-m", "--memory", "--device", "--cap-add", "--cap-drop",
        "--security-opt", "--tmpfs", "-h", "--hostname", "--ulimit", "--restart",
        "--log-driver", "--log-opt", "--gpus", "--ipc", "--pid", "--runtime",
        "--shm-size", "--group-add", "--dns", "--expose", "--label-file",
    }
)  # fmt: skip


def npm_version(spec: str) -> str | None:
    """``@scope/name@1.2.3`` -> ``1.2.3``; ``name`` -> ``None``."""
    body = spec[1:] if spec.startswith("@") else spec
    if "@" not in body:
        return None
    return body.rsplit("@", 1)[1]


def python_version(spec: str) -> str | None:
    """``name==1.2.3`` or ``name@1.2.3`` -> ``1.2.3``; ranges -> ``None``."""
    if "==" in spec:
        return spec.split("==", 1)[1]
    if "@" in spec and "://" not in spec:
        return spec.rsplit("@", 1)[1]
    return None


def _first_positional(args: list[str], value_flags: frozenset[str]) -> str | None:
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in value_flags:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return None


def _index_override(args: list[str], value_flags: frozenset[str]) -> bool:
    """Whether a runner option before the package points at another index."""
    package = _first_positional(args, value_flags)
    runner_args = args[: args.index(package)] if package in args else args
    return any(
        a == f or a.startswith(f + "=") for a in runner_args for f in INDEX_FLAGS
    )


def _image(args: list[str]) -> str | None:
    """The image of ``docker run …``: the first positional after ``run``."""
    rest = args[args.index("run") + 1 :]
    return _first_positional(rest, CONTAINER_VALUE_FLAGS)


def _flag_values(args: list[str], flags: set[str]) -> list[str]:
    values = []
    for i, arg in enumerate(args):
        if arg in flags and i + 1 < len(args):
            values.append(args[i + 1])
        values.extend(
            arg.split("=", 1)[1] for flag in flags if arg.startswith(flag + "=")
        )
    return values


def _unpinned(spec: str, version: str | None) -> str | None:
    if version is None:
        return f"'{spec}' has no version"
    if not EXACT_VERSION.match(version):
        return f"'{spec}' is not pinned to an exact version"
    return None


def floating_reference(server: dict[str, Any]) -> str | None:
    """Why a stdio server's package reference floats, or ``None`` when pinned."""
    command = server.get("command")
    args = server.get("args") or []
    if not isinstance(command, str) or not all(isinstance(a, str) for a in args):
        return None
    runner = PurePosixPath(command).name
    if runner in NPM_RUNNERS:
        if _index_override(args, NPM_VALUE_FLAGS):
            return "package comes from another registry"
        packages = _flag_values(args, {"-p", "--package"}) or [
            _first_positional(args, NPM_VALUE_FLAGS) or ""
        ]
        for spec in packages:
            if problem := _unpinned(spec, npm_version(spec)):
                return problem
        return None
    if (
        runner == "uvx"
        or (runner == "pipx" and args[:1] == ["run"])
        or (runner == "uv" and args[:2] == ["tool", "run"])
    ):
        rest = args[2:] if runner == "uv" else args[1:] if runner == "pipx" else args
        if _index_override(rest, UV_VALUE_FLAGS):
            return "package comes from another index"
        packages = _flag_values(rest, {"--from", "--with"})
        if not _flag_values(rest, {"--from"}):
            packages.insert(0, _first_positional(rest, UV_VALUE_FLAGS) or "")
        for spec in packages:
            if problem := _unpinned(spec, python_version(spec)):
                return problem
        return None
    if runner in CONTAINER_RUNNERS and "run" in args:
        image = _image(args)
        if image is None or "@sha256:" not in image:
            return "container image is not pinned by digest"
    return None
