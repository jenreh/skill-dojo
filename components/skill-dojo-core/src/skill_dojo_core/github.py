"""The GitHub seam: a Protocol and its ``gh`` CLI implementation.

This is the only abstraction in core with a fake (in the test suite). Git and the
filesystem are always real.
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Protocol

from skill_dojo_core.errors import ExternalToolError

log = logging.getLogger(__name__)


class GitHub(Protocol):
    def current_user(self) -> str:
        """Login of the authenticated user."""
        ...


class GhCli:
    """``GitHub`` through the ``gh`` command line tool.

    Locally ``gh`` uses ``gh auth``; in GitHub Actions it reads ``GH_TOKEN``.
    """

    def __init__(self, cwd: Path, executable: str = "gh") -> None:
        self.cwd = cwd
        self.executable = executable

    def run(self, *args: str) -> str:
        exe = shutil.which(self.executable)
        if exe is None:
            raise ExternalToolError(f"{self.executable} is not installed")
        log.debug("Running gh %s", args[0] if args else "")
        proc = subprocess.run(  # noqa: S603
            [exe, *args],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ExternalToolError(
                f"gh {args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout

    def api(self, *args: str) -> Any:
        return json.loads(self.run("api", *args) or "null")

    def current_user(self) -> str:
        return self.run("api", "user", "--jq", ".login").strip()
