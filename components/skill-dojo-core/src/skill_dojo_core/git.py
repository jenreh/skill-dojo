"""Thin wrappers around the ``git`` command line (argument lists, no shell)."""

import logging
import shutil
import subprocess
from pathlib import Path

from skill_dojo_core.errors import ExternalToolError

log = logging.getLogger(__name__)


def run(cwd: Path, *args: str, check: bool = True) -> str:
    exe = shutil.which("git")
    if exe is None:
        raise ExternalToolError("git is not installed")
    log.debug("Running git %s", args[0] if args else "")
    proc = subprocess.run(  # noqa: S603
        [exe, *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if check and proc.returncode != 0:
        raise ExternalToolError(
            f"git {args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def head(cwd: Path) -> str:
    """The commit ``HEAD`` points at."""
    return run(cwd, "rev-parse", "--verify", "HEAD^{commit}")
