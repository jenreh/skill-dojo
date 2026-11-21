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
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)

PR_FIELDS = "number,url,title,body,headRefName,baseRefName,state"


class PullRequest(Result):
    number: int
    url: str
    title: str
    body: str = ""
    head: str
    base: str
    state: str = "OPEN"


class GitHub(Protocol):
    def current_user(self) -> str:
        """Login of the authenticated user."""
        ...

    def find_open_pull_request(self, head: str, base: str) -> PullRequest | None:
        """The open PR from ``head`` into ``base``, if any."""
        ...

    def open_pull_request(
        self, head: str, base: str, title: str, body: str
    ) -> PullRequest: ...

    def update_pull_request(
        self, number: int, title: str, body: str
    ) -> PullRequest: ...

    def comment(self, number: int, body: str) -> None: ...

    def list_open_pull_requests(self, base: str) -> list[PullRequest]: ...

    def close_pull_request(self, number: int, comment: str) -> None: ...


def _pull_request(data: dict[str, Any]) -> PullRequest:
    return PullRequest(
        number=data["number"],
        url=data["url"],
        title=data.get("title") or "",
        body=data.get("body") or "",
        head=data.get("headRefName") or "",
        base=data.get("baseRefName") or "",
        state=data.get("state") or "OPEN",
    )


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

    def view(self, ref: str) -> PullRequest:
        return _pull_request(
            json.loads(self.run("pr", "view", ref, "--json", PR_FIELDS))
        )

    def find_open_pull_request(self, head: str, base: str) -> PullRequest | None:
        found = json.loads(
            self.run(
                "pr",
                "list",
                f"--head={head}",
                f"--base={base}",
                "--state=open",
                "--json",
                PR_FIELDS,
                "--limit",
                "1",
            )
            or "[]"
        )
        return _pull_request(found[0]) if found else None

    def open_pull_request(
        self, head: str, base: str, title: str, body: str
    ) -> PullRequest:
        url = (
            self.run(
                "pr",
                "create",
                f"--head={head}",
                f"--base={base}",
                f"--title={title}",
                f"--body={body}",
            )
            .strip()
            .splitlines()[-1]
        )
        return self.view(url)

    def update_pull_request(self, number: int, title: str, body: str) -> PullRequest:
        self.run("pr", "edit", str(number), f"--title={title}", f"--body={body}")
        return self.view(str(number))

    def comment(self, number: int, body: str) -> None:
        self.run("pr", "comment", str(number), f"--body={body}")

    def list_open_pull_requests(self, base: str) -> list[PullRequest]:
        found = json.loads(
            self.run(
                "pr",
                "list",
                f"--base={base}",
                "--state=open",
                "--json",
                PR_FIELDS,
                "--limit",
                "200",
            )
            or "[]"
        )
        return [_pull_request(item) for item in found]

    def close_pull_request(self, number: int, comment: str) -> None:
        self.run("pr", "close", str(number), f"--comment={comment}")
