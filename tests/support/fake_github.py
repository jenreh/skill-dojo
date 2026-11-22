"""An in-memory ``GitHub`` for tests. Git stays real; only the GitHub API is fake.

With ``remote`` set (a bare repo), ``merge`` does what GitHub does: a merge
commit of the head branch into the base branch, pushed to the remote.
"""

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from skill_dojo_core.github import PullRequest

MERGED_AT = "2026-11-21T11:00:00Z"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@dataclass
class FakeGitHub:
    user: str = "alice"
    remote: Path | None = None
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    pulls: list[PullRequest] = field(default_factory=list)
    releases: list[tuple[str, str, str]] = field(default_factory=list)

    def current_user(self) -> str:
        self.calls.append(("current_user", ()))
        return self.user

    def _head_oid(self, head: str) -> str | None:
        if self.remote is None:
            return None
        out = subprocess.run(
            ["git", "rev-parse", "--verify", "-q", f"refs/heads/{head}"],
            cwd=self.remote,
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip() or None

    def _live(self, pr: PullRequest) -> PullRequest:
        """An open PR's head follows its branch, as on GitHub."""
        if pr.state != "OPEN" or pr.cross_repository:
            return pr
        return pr.model_copy(update={"head_oid": self._head_oid(pr.head)})

    def _replace(self, pr: PullRequest) -> PullRequest:
        self.pulls = [pr if p.number == pr.number else p for p in self.pulls]
        return pr

    def find_open_pull_request(self, head: str, base: str) -> PullRequest | None:
        return next(
            (
                p
                for p in self.pulls
                if p.head == head
                and p.base == base
                and p.state == "OPEN"
                and not p.cross_repository
            ),
            None,
        )

    def open_pull_request(
        self, head: str, base: str, title: str, body: str
    ) -> PullRequest:
        number = len(self.pulls) + 1
        pr = PullRequest(
            number=number,
            url=f"https://github.invalid/acme/marketplace/pull/{number}",
            title=title,
            body=body,
            head=head,
            base=base,
            author=self.user,
            created_at=f"2026-11-21T09:{number % 60:02d}:00Z",
        )
        self.pulls.append(pr)
        self.calls.append(("open_pull_request", (head, base)))
        return pr

    def update_pull_request(self, number: int, title: str, body: str) -> PullRequest:
        pr = self.get(number).model_copy(update={"title": title, "body": body})
        self.calls.append(("update_pull_request", (number,)))
        return self._replace(pr)

    def get(self, number: int) -> PullRequest:
        return self._live(next(p for p in self.pulls if p.number == number))

    def open_fork_pull_request(self, head: str, base: str) -> PullRequest:
        """A PR from someone's fork whose branch happens to have ``head``'s name."""
        pr = self.open_pull_request(head, base, "fork", "")
        return self._replace(
            pr.model_copy(
                update={
                    "cross_repository": True,
                    "author": "mallory",
                    "head_oid": "f" * 40,
                }
            )
        )

    def get_pull_request(self, number: int) -> PullRequest:
        return self.get(number)

    def list_open_pull_requests(self, base: str) -> list[PullRequest]:
        return [
            self._live(p) for p in self.pulls if p.base == base and p.state == "OPEN"
        ]

    def list_merged_pull_requests(self, base: str) -> list[PullRequest]:
        merged = [p for p in self.pulls if p.base == base and p.state == "MERGED"]
        return list(reversed(merged))

    def merge(
        self, number: int, head_oid: str | None = None, *, merged_by: str | None = None
    ) -> bool:
        self.calls.append(("merge", (number,)))
        pr = self.get(number)
        assert pr.state == "OPEN", f"PR {number} is {pr.state}"
        assert head_oid is None or head_oid == pr.head_oid, "head moved"
        assert self.remote is not None, "FakeGitHub.remote is not set"
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "w"
            _git(Path(tmp), "clone", "-q", str(self.remote), str(work))
            _git(work, "checkout", "-q", pr.base)
            _git(
                work,
                "merge",
                "-q",
                "--no-ff",
                "-m",
                f"Merge pull request #{number} from {pr.head}",
                f"origin/{pr.head}",
            )
            _git(work, "push", "-q", "origin", f"HEAD:{pr.base}")
            commit = _git(work, "rev-parse", "HEAD")
        self._replace(
            pr.model_copy(
                update={
                    "state": "MERGED",
                    "merged_at": MERGED_AT,
                    "merge_commit": commit,
                    "merged_by": merged_by or self.user,
                    "head_oid": pr.head_oid,
                }
            )
        )
        return True

    def create_release(self, tag: str, title: str, notes: str) -> str:
        self.calls.append(("create_release", (tag,)))
        self.releases.append((tag, title, notes))
        return f"https://github.invalid/acme/marketplace/releases/tag/{tag}"
