"""Plain-text presentation of core results."""

import typer

from skill_dojo_core import ValidationReport


def echo_lines(lines: list[str], prefix: str = "  ") -> None:
    for line in lines:
        typer.echo(f"{prefix}{line}")


def echo_report(report: ValidationReport) -> None:
    for finding in report.warnings:
        typer.echo(f"WARN  {finding}")
    for finding in report.errors:
        typer.echo(f"ERROR {finding}")
    typer.echo(
        f"\nValidated {report.plugins} plugin(s) and {report.skills} skill(s): "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)."
    )
