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

PR_FIELDS = (
    "number,url,title,body,headRefName,baseRefName,state,author,"
    "headRefOid,isCrossRepository,createdAt"
)
MERGED_FIELDS = f"{PR_FIELDS},mergedAt,mergeCommit,mergedBy"
MERGED_LIMIT = "1000"


class PullRequest(Result):
    number: int
    url: str
    title: str
    body: str = ""
    head: str
    base: str
    state: str = "OPEN"
    author: str = ""
    head_oid: str | None = None
    cross_repository: bool = False
    merged_at: str | None = None
    merge_commit: str | None = None
    merged_by: str | None = None
    created_at: str | None = None


class GitHub(Protocol):
    def current_user(self) -> str:
        """Login of the authenticated user."""
        ...

    def find_open_pull_request(self, head: str, base: str) -> PullRequest | None:
        """The open PR from ``head`` of this repository (never a fork) into
        ``base``, if any."""
        ...

    def open_pull_request(
        self, head: str, base: str, title: str, body: str
    ) -> PullRequest: ...

    def update_pull_request(
        self, number: int, title: str, body: str
    ) -> PullRequest: ...

    def list_open_pull_requests(self, base: str) -> list[PullRequest]: ...

    def get_pull_request(self, number: int) -> PullRequest: ...

    def list_merged_pull_requests(self, base: str) -> list[PullRequest]:
        """Recently merged PRs into ``base`` (newest first)."""
        ...

    def create_release(self, tag: str, title: str, notes: str) -> str:
        """A GitHub Release for the pushed ``tag``; returns its URL."""
        ...

    def release_url(self, tag: str) -> str | None:
        """The URL of the GitHub Release of ``tag``, or None when there is none."""
        ...


def _login(value: Any) -> str | None:
    return value.get("login") if isinstance(value, dict) else None


def _pull_request(data: dict[str, Any]) -> PullRequest:
    return PullRequest(
        number=data["number"],
        url=data["url"],
        title=data.get("title") or "",
        body=data.get("body") or "",
        head=data.get("headRefName") or "",
        base=data.get("baseRefName") or "",
        state=data.get("state") or "OPEN",
        author=_login(data.get("author")) or "",
        head_oid=data.get("headRefOid"),
        cross_repository=bool(data.get("isCrossRepository")),
        merged_at=data.get("mergedAt"),
        merge_commit=(data.get("mergeCommit") or {}).get("oid"),
        merged_by=_login(data.get("mergedBy")),
        created_at=data.get("createdAt"),
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
                "20",
            )
            or "[]"
        )
        # gh matches the branch name only; a fork may use the same name.
        own = [p for p in map(_pull_request, found) if not p.cross_repository]
        return own[0] if own else None

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
                MERGED_LIMIT,
            )
            or "[]"
        )
        return [_pull_request(item) for item in found]

    def get_pull_request(self, number: int) -> PullRequest:
        return self.view(str(number))

    def list_merged_pull_requests(self, base: str) -> list[PullRequest]:
        found = json.loads(
            self.run(
                "pr",
                "list",
                f"--base={base}",
                "--state=merged",
                "--json",
                MERGED_FIELDS,
                "--limit",
                "200",
            )
            or "[]"
        )
        return [_pull_request(item) for item in found]

    def create_release(self, tag: str, title: str, notes: str) -> str:
        out = self.run(
            "release",
            "create",
            tag,
            "--verify-tag",
            f"--title={title}",
            f"--notes={notes}",
        )
        return out.strip().splitlines()[-1] if out.strip() else ""

    def release_url(self, tag: str) -> str | None:
        exe = shutil.which(self.executable)
        if exe is None:
            raise ExternalToolError(f"{self.executable} is not installed")
        proc = subprocess.run(  # noqa: S603
            [exe, "release", "view", tag, "--json", "url"],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            if "not found" in (proc.stderr + proc.stdout).lower():
                return None
            raise ExternalToolError(f"gh release view failed: {proc.stderr.strip()}")
        return json.loads(proc.stdout or "{}").get("url")
