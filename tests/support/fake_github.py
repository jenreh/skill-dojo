"""An in-memory ``GitHub`` for tests. Git stays real; only the GitHub API is fake."""

from dataclasses import dataclass, field


@dataclass
class FakeGitHub:
    user: str = "alice"
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def current_user(self) -> str:
        self.calls.append(("current_user", ()))
        return self.user
