"""Entry point of the ``skill-dojo`` command."""

import logging
import sys
from importlib.metadata import version
from typing import Annotated

import typer

from skill_dojo_cli import clients, items, release, repo, serve, sources
from skill_dojo_cli.errors import exit_code_for
from skill_dojo_core import SkillDojoError

app = typer.Typer(
    name="skill-dojo",
    help="Curate agent plugin marketplaces, skills and MCP servers in a git repo.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def show_version(value: bool) -> None:
    if value:
        typer.echo(f"skill-dojo {version('skill-dojo')}")
        raise typer.Exit


@app.callback()
def root(
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Log debug output.")
    ] = False,
    _version: Annotated[
        bool,
        typer.Option(
            "--version", callback=show_version, is_eager=True, help="Show version."
        ),
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


app.command()(repo.init)
app.add_typer(sources.source_app, name="source")
app.command()(sources.browse)
app.command()(items.mirror)
app.command("add-parts")(items.add_parts)
app.command("remove-parts")(items.remove_parts)
app.add_typer(items.plugin_app, name="plugin")
app.add_typer(items.local_app, name="local")
app.add_typer(items.lock_app, name="lock")
app.command()(items.version)
app.command()(items.sync)
app.command()(release.status)
app.command()(release.finish)
app.command()(release.release)
app.command()(release.revoke)
app.command()(repo.build)
app.command()(repo.validate)
app.command()(repo.flags)
app.add_typer(clients.clients_app, name="clients")
app.add_typer(repo.marketplace_app, name="marketplace")
app.command()(serve.serve)


def main() -> None:
    """Run the CLI and turn core errors into an exit code and a message."""
    try:
        app()
    except SkillDojoError as error:
        typer.echo(f"error: {error}", err=True)
        sys.exit(exit_code_for(error))
