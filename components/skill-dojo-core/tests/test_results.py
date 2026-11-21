"""Every public result model must survive a JSON round trip."""

import inspect

import pytest
from pydantic import BaseModel

import skill_dojo_core
from skill_dojo_core import (
    AdoptResult,
    BrowseResult,
    BuildResult,
    CandidateResult,
    Finding,
    FlagsResult,
    InitResult,
    LocalAddResult,
    LockRefreshResult,
    PullRequest,
    Result,
    RiskFlag,
    Source,
    SourcesResult,
    SyncResult,
    UpstreamPlugin,
    ValidationReport,
    VendorResult,
)

FINDING = Finding(level="error", path="plugins/x", message="drift")
EXAMPLES: list[BaseModel] = [
    InitResult(created=["registry/config.yaml"]),
    BuildResult(changed=["a"], applied=False),
    ValidationReport(plugins=1, skills=2, errors=[FINDING], warnings=[]),
    FINDING,
    LocalAddResult(item="x", tree_sha256="a" * 64, changed=["b"]),
    LockRefreshResult(refreshed=["x"], unchanged=[]),
    AdoptResult(
        marketplace="m", items=["x"], changed=[], floating_mcp=[], possibly_vendored=[]
    ),
    VendorResult(prefix=".agents/m", ref="main", updated=False, links=[]),
    SourcesResult(sources=[Source(id="s", type="git", repository="o/r")]),
    UPSTREAM := UpstreamPlugin(name="p", path="plugins/p", repository="o/r"),
    BrowseResult(source="s", commit="c" * 40, plugins=[UPSTREAM]),
    FLAG := RiskFlag(kind="hook", path="hooks/x", line=1, detail="new hook"),
    PR := PullRequest(number=1, url="u", title="t", head="h", base="b"),
    CANDIDATE := CandidateResult(
        item="p", commit="c", branch="b", pull_request=PR, flags=[FLAG], status="opened"
    ),
    SyncResult(candidates=[CANDIDATE]),
    FlagsResult(base="origin/staging", flags={"p": [FLAG]}, markdown="m"),
]


def exported_results() -> set[type[BaseModel]]:
    return {
        obj
        for name in skill_dojo_core.__all__
        if inspect.isclass(obj := getattr(skill_dojo_core, name))
        and issubclass(obj, Result)
        and obj is not Result
    }


def test_every_result_has_an_example() -> None:
    assert {type(e) for e in EXAMPLES} == exported_results()


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: type(e).__name__)
def test_round_trip(example: BaseModel) -> None:
    again = type(example).model_validate_json(example.model_dump_json())
    assert again == example
