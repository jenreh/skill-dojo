"""An in-memory ``GitHub`` for tests. Git stays real; only the GitHub API is fake."""

from dataclasses import dataclass, field

from skill_dojo_core.github import PullRequest


@dataclass
class FakeGitHub:
    user: str = "alice"
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    pulls: list[PullRequest] = field(default_factory=list)
    comments: dict[int, list[str]] = field(default_factory=dict)

    def current_user(self) -> str:
        self.calls.append(("current_user", ()))
        return self.user

    def _replace(self, pr: PullRequest) -> PullRequest:
        self.pulls = [pr if p.number == pr.number else p for p in self.pulls]
        return pr

    def find_open_pull_request(self, head: str, base: str) -> PullRequest | None:
        return next(
            (
                p
                for p in self.pulls
                if p.head == head and p.base == base and p.state == "OPEN"
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
        )
        self.pulls.append(pr)
        self.calls.append(("open_pull_request", (head, base)))
        return pr

    def update_pull_request(self, number: int, title: str, body: str) -> PullRequest:
        pr = self.get(number).model_copy(update={"title": title, "body": body})
        self.calls.append(("update_pull_request", (number,)))
        return self._replace(pr)

    def comment(self, number: int, body: str) -> None:
        self.comments.setdefault(number, []).append(body)

    def get(self, number: int) -> PullRequest:
        return next(p for p in self.pulls if p.number == number)
