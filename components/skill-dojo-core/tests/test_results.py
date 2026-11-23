"""Every public result model must survive a JSON round trip."""

import inspect

import pytest
from pydantic import BaseModel

import skill_dojo_core as sd
from skill_dojo_core import (
    AdoptResult,
    BrowseResult,
    BuildResult,
    ChangeResult,
    Finding,
    FinishResult,
    FlagsResult,
    InitResult,
    LocalAddResult,
    LockRefreshResult,
    MarketplaceResult,
    PendingVersion,
    PullRequest,
    ReleaseResult,
    RevokeResult,
    RiskFlag,
    Source,
    SourcesResult,
    SyncResult,
    UpstreamPlugin,
    ValidationReport,
    WorkBranch,
    WorkStatus,
)
from skill_dojo_core.cache import CachedPlugin, PartRef, SourceIndex

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
    MarketplaceResult(prefix=".agents/m", ref="main", updated=False, links=[]),
    SourcesResult(sources=[Source(id="s", type="git", repository="o/r")]),
    UPSTREAM := UpstreamPlugin(name="p", path="plugins/p", repository="o/r"),
    BrowseResult(
        source="s",
        commit="c" * 40,
        plugins=[UPSTREAM],
        parts={"p": [PartRef(kind="hook", name="Stop")]},
    ),
    SourceIndex(
        source="s",
        commit="c" * 40,
        settings="k",
        plugins=[CachedPlugin(plugin=UPSTREAM, parts=None)],
    ),
    FLAG := RiskFlag(kind="hook", path="hooks/x", line=1, detail="new hook"),
    PR := PullRequest(number=1, url="u", title="t", head="h", base="b"),
    CHANGE := ChangeResult(item="p", status="added", pin="c", flags=[FLAG]),
    SyncResult(changes=[CHANGE], refreshed=["s"]),
    FlagsResult(base="origin/main", flags={"p": [FLAG]}, markdown="m"),
    PENDING := PendingVersion(
        item="p", kind="local", status="changed", main_version="1.0.0", level="patch"
    ),
    WorkBranch(name="skill-dojo/changes", status="created"),
    WorkStatus(
        branch="skill-dojo/changes", main="main", pull_request=PR, pending=[PENDING]
    ),
    FinishResult(status="opened", branch="w", pull_request=PR, pending=[PENDING]),
    ReleaseResult(status="created", tag="marketplace-v2026.11.21", commit="c" * 40),
    RevokeResult(item="p", action="removed"),
    sd.ChangesOverview(status=WorkStatus(branch="w", main="main"), flags={"p": [FLAG]}),
    sd.ReleaseOverview(
        main="main",
        main_head="def",
        commits=[sd.CommitInfo(sha="abc", subject="skill-dojo: mirror x")],
        tags=[sd.TagInfo(tag="marketplace-v2026.11.21", commit="c", items=1)],
    ),
    sd.CommitInfo(sha="a", subject="s"),
    sd.PreviewResult(
        base="main",
        base_head="abc",
        tree=[sd.TreeEntry(path="plugins/", depth=0)],
        catalogs=[sd.CatalogPreview(path="p", changes=[], full=[], text="{}")],
        pending=[],
        errors=0,
        warnings=[],
    ),
    sd.AuditResult(
        events=[sd.AuditEvent(kind="release", at="2026-11-21", actor="a", action="x")]
    ),
    sd.RevokeTarget(item="hello", rollback_to="marketplace-v2026.11.21"),
    sd.PluginInfo(
        id="kit",
        kind="local",
        path="plugins/kit",
        parts=[sd.PartInfo(kind="skill", name="greet")],
    ),
    sd.PartInfo(kind="agent", name="helper"),
    sd.AuditEvent(kind="sync", at="", actor="a", action="sync"),
    sd.TreeEntry(path="plugins/hello/", depth=1, status="A"),
    sd.DiffLine(kind="…", text=""),
    sd.DiffFile(path="b"),
    sd.TagInfo(tag="marketplace-v2026.11.21.2", commit="c"),
    sd.CatalogPreview(path="q", changes=[], full=[], text=""),
    sd.RevokePreview(targets=[]),
    sd.PluginsOverview(local=["tools"]),
    sd.PluginParts(parts=[]),
]


def exported_results() -> set[type[BaseModel]]:
    return {
        obj
        for name in sd.__all__
        if inspect.isclass(obj := getattr(sd, name))
        and issubclass(obj, sd.Result)
        and obj is not sd.Result
    }


def test_every_result_has_an_example() -> None:
    assert exported_results() <= {type(e) for e in EXAMPLES}


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: type(e).__name__)
def test_round_trip(example: BaseModel) -> None:
    again = type(example).model_validate_json(example.model_dump_json())
    assert again == example
