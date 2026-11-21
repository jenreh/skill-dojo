"""Repo-wide commands: ``init``, ``build``, ``validate``, ``flags``, ``vendor``."""

from typing import Annotated

import typer

from skill_dojo_cli.stub import not_implemented


def init(
    adopt: Annotated[
        bool, typer.Option(help="Register the existing plugins/ of this repo.")
    ] = False,
) -> None:
    """Scaffold a curated marketplace in this repo."""
    not_implemented("init")


def build(
    check: Annotated[
        bool, typer.Option(help="Fail if build would change any file.")
    ] = False,
) -> None:
    """Regenerate both catalogs, manifests and the layout."""
    not_implemented("build")


def validate() -> None:
    """Validate plugins, skills, catalogs and registry/."""
    not_implemented("validate")


def flags(
    base: Annotated[str, typer.Option(help="Compare against this ref.")] = "staging",
) -> None:
    """Print the risk flags of the current branch against a base."""
    not_implemented("flags")


def vendor(
    marketplace: Annotated[str, typer.Argument(help="Marketplace git URL.")] = "",
    update: Annotated[bool, typer.Option(help="Pull the subtree again.")] = False,
) -> None:
    """Vendor a marketplace's skills into this (consumer) repo."""
    not_implemented("vendor")
