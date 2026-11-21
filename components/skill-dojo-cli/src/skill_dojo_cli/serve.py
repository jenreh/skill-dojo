"""``serve``: start the local web UI (needs the ``web`` extra)."""

import importlib

import typer

INSTALL_HINT = 'The web UI needs the web extra: uv tool install "skill-dojo[web]"'


def serve() -> None:
    """Start the local web UI on 127.0.0.1."""
    try:
        web = importlib.import_module("skill_dojo_web")
    except ModuleNotFoundError:
        typer.echo(INSTALL_HINT, err=True)
        raise typer.Exit(2) from None
    web.serve()
