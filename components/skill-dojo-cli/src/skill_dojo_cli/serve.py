"""``serve``: start the local web UI (needs the ``web`` extra)."""

import importlib
from pathlib import Path
from typing import Annotated

import typer

from skill_dojo_cli.context import find_repo_root
from skill_dojo_core import NotFoundError

INSTALL_HINT = 'The web UI needs the web extra: uv tool install "skill-dojo[web]"'


def resolve_serve_repo(repo: Path | None) -> Path:
    """The git root of ``repo`` (``~`` expanded), else of the working directory."""
    start = repo.expanduser() if repo else Path.cwd()
    if not start.is_dir():
        raise NotFoundError(f"{start} is not a directory")
    return find_repo_root(start)


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
        typer.echo(INSTALL_HINT, err=True)
        raise typer.Exit(2) from None
    root = resolve_serve_repo(repo)
    typer.echo(f"skill-dojo UI for {root} on http://127.0.0.1:{port}")
    raise typer.Exit(web.serve(root, port))
