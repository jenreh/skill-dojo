from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_dojo_core import Context
from tests.support.fake_github import FakeGitHub


def test_context_is_frozen(tmp_path: Path) -> None:
    ctx = Context(
        repo=tmp_path,
        github=FakeGitHub(),
        actor="alice",
        now=datetime(2026, 11, 21, tzinfo=UTC),
    )
    with pytest.raises(AttributeError):
        ctx.actor = "bob"  # ty: ignore[invalid-assignment]


def test_report_calls_progress(tmp_path: Path) -> None:
    seen: list[str] = []
    ctx = Context(
        repo=tmp_path,
        github=FakeGitHub(),
        actor="alice",
        now=datetime(2026, 11, 21, tzinfo=UTC),
        progress=seen.append,
    )
    ctx.report("step one")
    assert seen == ["step one"]


def test_report_without_progress_is_silent(tmp_path: Path) -> None:
    ctx = Context(
        repo=tmp_path,
        github=FakeGitHub(),
        actor="alice",
        now=datetime(2026, 11, 21, tzinfo=UTC),
    )
    ctx.report("nothing happens")


def test_now_must_be_aware(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone"):
        Context(
            repo=tmp_path,
            github=FakeGitHub(),
            actor="alice",
            now=datetime(2026, 11, 21),  # noqa: DTZ001
        )
