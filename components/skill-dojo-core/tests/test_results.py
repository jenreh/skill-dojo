"""Every public result model must survive a JSON round trip."""

import inspect

import pytest
from pydantic import BaseModel

import skill_dojo_core
from skill_dojo_core import (
    AdoptResult,
    Approval,
    BrowseResult,
    BuildResult,
    CandidateResult,
    Client,
    ClientsResult,
    Finding,
    FlagsResult,
    InitResult,
    LocalAddResult,
    LockRefreshResult,
    PolicyBlock,
    PromoteResult,
    PullRequest,
    ReleaseResult,
    Result,
    Review,
    ReviewActionResult,
    ReviewEntry,
    ReviewListResult,
    ReviewShowResult,
    RevokeResult,
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
    Review(user="bob", state="APPROVED", submitted_at="2026-11-21T10:00:00Z"),
    ENTRY := ReviewEntry(pull_request=PR, item="p"),
    ReviewListResult(entries=[ENTRY]),
    ReviewShowResult(pull_request=PR, item="p", files=["M\tplugins/p/plugin.json"]),
    ReviewActionResult(pull_request=PR, item="p", status="quarantined", quarantine=PR),
    PolicyBlock(item="p", reason="risk tier is forbidden"),
    PromoteResult(
        status="opened",
        branch="promote/2026-11-21",
        pull_request=PR,
        approvals=[
            Approval(
                item="p",
                digest="a" * 64,
                pull_request="u",
                reviewers=["bob"],
                approved_at="2026-11-21T10:00:00Z",
            )
        ],
        items=["p"],
    ),
    ReleaseResult(status="created", tag="marketplace-v2026.11.21", commit="c" * 40),
    CLIENT := Client(name="team", ref="marketplace-v2026.11.21"),
    ClientsResult(clients=[CLIENT]),
    RevokeResult(
        item="p",
        action="removed",
        branch="revoke/p",
        pull_request=PR,
        back_merge=PR,
        affected_clients=[CLIENT],
    ),
    skill_dojo_core.ReviewDetail(
        number=1,
        url="u",
        title="t",
        item="hello",
        head="candidate/hello/abc",
        risk_tier="standard",
        data_classification="internal",
        flags=[RiskFlag(kind="mcp-server-added", path=".mcp.json", detail="d")],
        files=[
            skill_dojo_core.DiffFile(
                path="a",
                added=1,
                lines=[skill_dojo_core.DiffLine(kind="+", number=1, text="x")],
            )
        ],
    ),
    skill_dojo_core.ReleaseOverview(
        staging="staging",
        main="main",
        staging_head="abc",
        main_head="def",
        commits_ahead=2,
        items=[skill_dojo_core.PromotionItem(item="hello", reviewers=["bob"])],
        tags=[
            skill_dojo_core.TagInfo(tag="marketplace-v2026.11.21", commit="c", items=1)
        ],
    ),
    skill_dojo_core.PreviewResult(
        base="staging",
        base_head="abc",
        tree=[skill_dojo_core.TreeEntry(path="plugins/", depth=0)],
        catalogs=[
            skill_dojo_core.CatalogPreview(path="p", changes=[], full=[], text="{}")
        ],
        pending=[],
        errors=0,
        warnings=[],
    ),
    skill_dojo_core.AuditResult(
        events=[
            skill_dojo_core.AuditEvent(
                kind="release", at="2026-11-21", actor="a", action="released"
            )
        ]
    ),
    skill_dojo_core.RevokeTarget(item="hello", rollback_to="marketplace-v2026.11.21"),
    skill_dojo_core.BundleInfo(
        id="kit", parts=[skill_dojo_core.PartInfo(kind="skill", name="greet")]
    ),
    skill_dojo_core.PartInfo(kind="agent", name="helper"),
    skill_dojo_core.AuditEvent(kind="sync", at="", actor="a", action="opened"),
    skill_dojo_core.TreeEntry(path="plugins/hello/", depth=1, status="A"),
    skill_dojo_core.DiffLine(kind="…", text=""),
    skill_dojo_core.DiffFile(path="b"),
    skill_dojo_core.PromotionItem(item="kit", kind="bundle"),
    skill_dojo_core.TagInfo(tag="marketplace-v2026.11.21.2", commit="c"),
    skill_dojo_core.CatalogPreview(path="q", changes=[], full=[], text=""),
    skill_dojo_core.RevokePreview(targets=[]),
    skill_dojo_core.BundlesOverview(local=["tools"]),
    skill_dojo_core.PluginParts(parts=[]),
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
    assert exported_results() <= {type(e) for e in EXAMPLES}


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: type(e).__name__)
def test_round_trip(example: BaseModel) -> None:
    again = type(example).model_validate_json(example.model_dump_json())
    assert again == example
