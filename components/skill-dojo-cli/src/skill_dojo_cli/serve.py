"""``serve``: start the local web UI (needs the ``web`` extra)."""

import importlib
from pathlib import Path
from typing import Annotated

import typer

from skill_dojo_cli.context import find_repo_root

INSTALL_HINT = 'The web UI needs the web extra: uv tool install "skill-dojo[web]"'


def serve(
    port: Annotated[int, typer.Option(help="Port on 127.0.0.1.")] = 8080,
) -> None:
    """Start the local web UI on 127.0.0.1."""
    try:
        web = importlib.import_module("skill_dojo_web")
    except ModuleNotFoundError:
        typer.echo(INSTALL_HINT, err=True)
        raise typer.Exit(2) from None
    repo = find_repo_root(Path.cwd())
    typer.echo(f"skill-dojo UI for {repo} on http://127.0.0.1:{port}")
    raise typer.Exit(web.serve(repo, port))
