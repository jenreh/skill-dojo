"""``serve``: start the local web UI (needs the ``web`` extra)."""

import importlib
import importlib.metadata
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from skill_dojo_cli.context import find_repo_root
from skill_dojo_core import NotFoundError

log = logging.getLogger(__name__)

REEXEC_ENV = "SKILL_DOJO_WEB_REEXEC"
INSTALL_HINT = 'The web UI needs the web extra: uv tool install "skill-dojo[web]"'


def resolve_serve_repo(repo: Path | None) -> Path:
    """The git root of ``repo`` (``~`` expanded), else of the working directory."""
    start = repo.expanduser() if repo else Path.cwd()
    if not start.is_dir():
        raise NotFoundError(f"{start} is not a directory")
    return find_repo_root(start)


def _rerun_with_web(repo: Path | None, port: int) -> int | None:
    """Run ``serve`` in a uv tool env that has the web extra; ``None`` if impossible."""
    uv = shutil.which("uv")
    if uv is None or os.environ.get(REEXEC_ENV):
        return None
    root = resolve_serve_repo(repo)
    version = importlib.metadata.version("skill-dojo")
    log.info("Web extra missing, re-running through uv with skill-dojo[web]")
    command = [
        uv, "tool", "run", "--from", f"skill-dojo[web]=={version}",
        "skill-dojo", "serve", "--port", str(port), "--repo", str(root),
    ]  # fmt: skip
    env = {**os.environ, REEXEC_ENV: "1"}
    return subprocess.run(command, env=env, check=False).returncode  # noqa: S603


def serve(
    port: Annotated[int, typer.Option(help="Port on 127.0.0.1.")] = 8080,
    repo: Annotated[
        Path | None,
        typer.Option(help="Repo to work in (default: the current directory)."),
    ] = None,
) -> None:
    """Start the local web UI on 127.0.0.1."""
    try:
        web = importlib.import_module("skill_dojo_web")
    except ModuleNotFoundError:
        code = _rerun_with_web(repo, port)
        if code is not None:
            raise typer.Exit(code) from None
        typer.echo(INSTALL_HINT, err=True)
        raise typer.Exit(2) from None
    root = resolve_serve_repo(repo)
    typer.echo(f"skill-dojo UI for {root} on http://127.0.0.1:{port}")
    raise typer.Exit(web.serve(root, port))
