"""Read models for the web UI: review detail, releases, preview, audit, revoke.

Every function reads git, the registry files and the GitHub API; none writes.
The CLI has its own text views of most of these.
"""

import csv
import io
import json
import logging
import tempfile
from pathlib import Path, PurePosixPath

from pydantic import Field

from skill_dojo_core import builder, catalogs, git, risk
from skill_dojo_core.branches import (
    CANDIDATE,
    QUARANTINE,
    base_branch,
    candidate_item,
    main_branch,
    remote_start,
    view,
)
from skill_dojo_core.commands.bundles import (
    FIRST_VERSION,
    Fetcher,
    bump_patch,
    plugin_servers,
)
from skill_dojo_core.commands.candidates import tree_at
from skill_dojo_core.commands.promote import check_policy, collect_approvals
from skill_dojo_core.commands.release import (
    TAG_PREFIX,
    affected,
    last_approved,
    release_notes,
)
from skill_dojo_core.commands.review import tool_pull_request
from skill_dojo_core.context import Context
from skill_dojo_core.diffs import DiffFile, DiffLine, compare_texts, parse_git_diff
from skill_dojo_core.errors import NotFoundError
from skill_dojo_core.models import (
    ApprovalsFile,
    Client,
    Item,
    ItemKind,
    ItemLock,
    ItemsFile,
    LockFile,
)
from skill_dojo_core.registry import (
    APPROVALS,
    ITEMS,
    LOCK,
    REGISTRY_DIR,
    Registry,
    model_at,
)
from skill_dojo_core.results import Result
from skill_dojo_core.risk import RiskFlag
from skill_dojo_core.sources import contents_summary
from skill_dojo_core.validation import validate_registry
from skill_dojo_core.validation.report import Finding

log = logging.getLogger(__name__)

PROMOTE, REVOKE = "promote/", "revoke/"


# --- shared --------------------------------------------------------------------------


def _short(sha: str | None) -> str:
    return (sha or "")[:7]


# --- review detail ---------------------------------------------------------------------


class ReviewDetail(Result):
    number: int
    url: str
    title: str
    item: str | None
    kind: str | None = None
    source: str | None = None
    upstream: str | None = None
    head: str
    old_version: str | None = None
    new_version: str | None = None
    old_commit: str | None = None
    new_commit: str | None = None
    ref: str | None = None
    tree_sha256: str | None = None
    contents: str = ""
    flags: list[RiskFlag] = []
    files: list[DiffFile] = []
    risk_tier: str
    data_classification: str
    channels: list[str] = []
    approvals: list[str] = []
    reviewers_needed: int = 1
    quarantined: bool = False


def _item_at(repo: Path, ref: str, item_id: str) -> tuple[Item | None, ItemLock | None]:
    return (
        model_at(repo, ref, ITEMS, ItemsFile).get(item_id),
        model_at(repo, ref, LOCK, LockFile).items.get(item_id),
    )


def review_detail(ctx: Context, number: int) -> ReviewDetail:
    """A candidate PR as the review page shows it: versions, flags, diff, policy."""
    pr = tool_pull_request(ctx, number)
    base, head = (
        git.fetch_branch(ctx.repo, pr.base),
        git.fetch_branch(ctx.repo, pr.head),
    )
    item_id = candidate_item(pr.head) or ""
    reg = Registry.load(ctx.repo)
    ns = reg.config.namespace
    old_item, old_lock = _item_at(ctx.repo, base, item_id)
    new_item, new_lock = _item_at(ctx.repo, head, item_id)
    item = new_item or old_item
    prefix = builder.plugin_dir(item_id)
    old_tree = tree_at(
        ctx.repo, base, prefix, ns, set(old_lock.generated) if old_lock else set()
    )
    new_tree = tree_at(
        ctx.repo, head, prefix, ns, set(new_lock.generated) if new_lock else set()
    )
    tier = item.risk_tier if item and item.risk_tier else reg.policy.default_risk_tier
    approvals = sorted(
        {
            r.user
            for r in ctx.github.reviews(number)
            if r.state == "APPROVED" and r.commit in {None, pr.head_oid}
        }
    )
    diff = git.run(ctx.repo, "diff", "--no-color", f"{base}...{head}", "--", prefix)
    return ReviewDetail(
        number=pr.number,
        url=pr.url,
        title=pr.title,
        item=item_id or None,
        kind=item.kind.value if item else None,
        source=item.source if item else None,
        upstream=new_lock.upstream.repository if new_lock else None,
        head=pr.head,
        old_version=builder.manifest_version_at(ctx.repo, base, item_id),
        new_version=builder.manifest_version_at(ctx.repo, head, item_id),
        old_commit=old_lock.upstream.commit if old_lock else None,
        new_commit=new_lock.upstream.commit if new_lock else None,
        ref=new_lock.upstream.ref if new_lock else None,
        tree_sha256=new_lock.tree_sha256 if new_lock else None,
        contents=contents_summary(sorted(new_tree), _servers(new_tree)),
        flags=risk.compare(old_tree, new_tree),
        files=parse_git_diff(diff),
        risk_tier=tier.value,
        data_classification=(item.data_classification if item else None)
        or reg.policy.default_data_classification,
        channels=[c.value for c in item.supported_channels] if item else [],
        approvals=approvals,
        reviewers_needed=reg.policy.reviewers.get(tier, 1),
        quarantined=bool(item and item.quarantined),
    )


def _servers(tree: risk.Tree) -> int:
    for rel in (builder.CLAUDE_MCP, builder.ROOT_MCP):
        if rel in tree:
            try:
                data = json.loads(tree[rel][1])
            except ValueError:
                return 0
            servers = data.get("mcpServers") if isinstance(data, dict) else None
            return len(servers) if isinstance(servers, dict) else 0
    return 0


# --- releases ----------------------------------------------------------------------------


class PromotionItem(Result):
    item: str
    kind: str | None = None
    old_version: str | None = None
    new_version: str | None = None
    pull_request: str | None = None
    reviewers: list[str] = []


class TagInfo(Result):
    tag: str
    commit: str
    date: str = ""
    items: int = 0
    clients: int = 0


class ReleaseOverview(Result):
    staging: str
    main: str
    staging_head: str
    main_head: str
    commits_ahead: int
    latest_tag: str | None = None
    latest_tag_date: str | None = None
    untagged: bool = False
    items: list[PromotionItem] = []
    blocks: list[str] = []
    errors: list[str] = []
    tags: list[TagInfo] = []
    notes: str = ""


def tags(repo: Path, clients: list[Client]) -> list[TagInfo]:
    """Release tags, newest first, with item and client counts."""
    out = git.run(
        repo,
        "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname:short)\t%(objectname)\t%(creatordate:iso-strict)",
        f"refs/tags/{TAG_PREFIX}*",
    )
    found = []
    for line in out.splitlines():
        name, _, rest = line.partition("\t")
        _sha, _, date = rest.partition("\t")
        commit = git.run(repo, "rev-parse", f"{name}^{{commit}}")
        found.append(
            TagInfo(
                tag=name,
                commit=commit,
                date=date,
                items=len(model_at(repo, commit, LOCK, LockFile).items),
                clients=sum(1 for c in clients if c.ref == name),
            )
        )
    return found


def release_overview(ctx: Context) -> ReleaseOverview:
    """Staging against main: what a promote would bring, checks and tags."""
    admin = Registry.load(ctx.repo)
    staging, main = base_branch(admin), main_branch(admin)
    s_ref, m_ref = git.fetch_branch(ctx.repo, staging), git.fetch_branch(ctx.repo, main)
    git.run(ctx.repo, "fetch", "-q", "--tags", "--force", "origin")
    staged = model_at(ctx.repo, s_ref, LOCK, LockFile)
    main_lock = model_at(ctx.repo, m_ref, LOCK, LockFile)
    staged_items = model_at(ctx.repo, s_ref, ITEMS, ItemsFile)
    main_items = model_at(ctx.repo, m_ref, ITEMS, ItemsFile)
    collected = collect_approvals(ctx, staging, s_ref, set())
    approvals = {a.item: a for a in collected}
    changed = sorted(
        i
        for i in set(staged.items) | set(main_lock.items)
        if (staged.items.get(i) and staged.items[i].tree_sha256)
        != (main_lock.items.get(i) and main_lock.items[i].tree_sha256)
    )
    items = []
    for item_id in changed:
        entry = staged.items.get(item_id) or main_lock.items[item_id]
        approval = approvals.get(item_id)
        items.append(
            PromotionItem(
                item=item_id,
                kind=entry.kind.value,
                old_version=builder.manifest_version_at(ctx.repo, m_ref, item_id),
                new_version=builder.manifest_version_at(ctx.repo, s_ref, item_id),
                pull_request=approval.pull_request if approval else None,
                reviewers=approval.reviewers if approval else [],
            )
        )
    staged_reg = Registry.load(ctx.repo)
    staged_reg.items, staged_reg.lock = staged_items, staged
    on_main = model_at(ctx.repo, m_ref, APPROVALS, ApprovalsFile).approvals
    staged_reg.approvals = ApprovalsFile(approvals=[*on_main, *collected])
    blocks = [
        f"{b.item}: {b.reason}" for b in check_policy(staged_reg, main_lock, main_items)
    ]
    found = tags(ctx.repo, admin.clients.clients)
    latest = found[0] if found else None
    head = git.run(ctx.repo, "rev-parse", s_ref)
    return ReleaseOverview(
        staging=staging,
        main=main,
        staging_head=_short(head),
        main_head=_short(git.run(ctx.repo, "rev-parse", m_ref)),
        commits_ahead=int(
            git.run(ctx.repo, "rev-list", "--count", f"{m_ref}..{s_ref}")
        ),
        latest_tag=latest.tag if latest else None,
        latest_tag_date=latest.date if latest else None,
        untagged=latest is None
        or latest.commit != git.run(ctx.repo, "rev-parse", m_ref),
        items=items,
        blocks=blocks,
        tags=found,
        notes=release_notes(
            ctx.repo, latest.tag if latest else None, head, "next release"
        ),
    )


# --- marketplace preview ---------------------------------------------------------------


class TreeEntry(Result):
    path: str
    depth: int
    status: str = ""  # A | M | ""


class CatalogPreview(Result):
    path: str
    changes: list[DiffLine]
    full: list[DiffLine]
    text: str


class PreviewResult(Result):
    base: str
    base_head: str
    tree: list[TreeEntry]
    catalogs: list[CatalogPreview]
    pending: list[str]
    errors: int
    warnings: list[Finding]


def _changed_paths(repo: Path, base: str, pending: list[str]) -> set[str]:
    diff = git.run(repo, "diff", "--name-only", base).splitlines()
    untracked = git.run(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return {p for p in (*diff, *untracked, *pending) if p}


def marketplace_preview(ctx: Context) -> PreviewResult:
    """What ``build`` would commit, against staging: tree, catalogs, checks."""
    reg = Registry.load(ctx.repo)
    base = git.fetch_branch(ctx.repo, base_branch(reg))
    overlay = builder.plan(reg)
    pending = overlay.changes()
    changed = _changed_paths(ctx.repo, base, pending)

    def status(path: str) -> str:
        hit = [c for c in changed if c == path or c.startswith(path.rstrip("/") + "/")]
        if not hit:
            return ""
        exists = git.succeeds(ctx.repo, "cat-file", "-e", f"{base}:{path.rstrip('/')}")
        return "M" if exists else "A"

    tree: list[TreeEntry] = []
    for folder, files in (
        (".agents/plugins/", [catalogs.AGENTS_CATALOG]),
        (".claude-plugin/", [catalogs.CLAUDE_CATALOG]),
        (
            "plugins/",
            [
                f"{builder.plugin_dir(i.id)}/"
                for i in sorted(reg.items.items, key=lambda i: i.id)
            ],
        ),
        (
            f"{REGISTRY_DIR}/",
            [
                f"{REGISTRY_DIR}/{n}"
                for n in (
                    "items.yaml",
                    "lock.json",
                    "sources.yaml",
                    "channel-policy.yaml",
                )
            ],
        ),
    ):
        tree.append(TreeEntry(path=folder, depth=0))
        tree += [TreeEntry(path=f, depth=1, status=status(f)) for f in files]
    previews = []
    for rel in (catalogs.AGENTS_CATALOG, catalogs.CLAUDE_CATALOG):
        new = overlay.read_text(rel) or ""
        old = (git.show_file(ctx.repo, base, rel) or b"").decode("utf-8", "replace")
        previews.append(
            CatalogPreview(
                path=rel,
                changes=compare_texts(old, new),
                full=compare_texts(old, new, context=None),
                text=new,
            )
        )
    report = validate_registry(reg)
    return PreviewResult(
        base=base_branch(reg),
        base_head=_short(git.run(ctx.repo, "rev-parse", base)),
        tree=tree,
        catalogs=previews,
        pending=pending,
        errors=len(report.errors),
        warnings=report.warnings,
    )


# --- audit ---------------------------------------------------------------------------------


class AuditEvent(Result):
    kind: str  # sync | approval | promotion | release | revocation | quarantine
    at: str
    actor: str
    action: str
    subject: str = ""
    detail: str = ""
    ref: str = ""
    url: str = ""


class AuditResult(Result):
    events: list[AuditEvent]

    def csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["at", "kind", "actor", "action", "subject", "detail", "ref", "url"]
        )
        for e in self.events:
            writer.writerow(
                [e.at, e.kind, e.actor, e.action, e.subject, e.detail, e.ref, e.url]
            )
        return out.getvalue()


def _pr_event(pr_head: str) -> tuple[str, str] | None:
    for prefix, kind, action in (
        (CANDIDATE, "approval", "merged"),
        (PROMOTE, "promotion", "merged promote"),
        (REVOKE, "revocation", "revoked"),
        (QUARANTINE, "quarantine", "quarantined"),
    ):
        if pr_head.startswith(prefix):
            return kind, action
    return None


def audit_log(ctx: Context) -> AuditResult:
    """Approvals, promotions, revocations, quarantines (merged PRs), candidate PRs
    opened by sync, and release tags, newest first."""
    reg = Registry.load(ctx.repo)
    events: list[AuditEvent] = []
    seen: set[int] = set()
    for base in (base_branch(reg), main_branch(reg)):
        for pr in ctx.github.list_merged_pull_requests(base):
            found = _pr_event(pr.head)
            if found is None or pr.number in seen or pr.cross_repository:
                continue
            seen.add(pr.number)
            kind, action = found
            subject = pr.head.split("/")[1] if "/" in pr.head else ""
            if kind == "promotion":
                subject = f"{base_branch(reg)} → {main_branch(reg)}"
            events.append(
                AuditEvent(
                    kind=kind,
                    at=pr.merged_at or "",
                    actor=pr.merged_by or pr.author,
                    action=action,
                    subject=subject,
                    ref=f"PR #{pr.number}",
                    url=pr.url,
                )
            )
        events.extend(
            AuditEvent(
                kind="sync",
                at=pr.created_at or "",
                actor=pr.author,
                action="opened a candidate for",
                subject=candidate_item(pr.head) or "",
                ref=f"PR #{pr.number}",
                url=pr.url,
            )
            for pr in ctx.github.list_open_pull_requests(base)
            if pr.head.startswith(CANDIDATE) and not pr.cross_repository
        )
    for tag in tags(ctx.repo, reg.clients.clients):
        tagger = git.run(
            ctx.repo, "for-each-ref", "--format=%(taggername)", f"refs/tags/{tag.tag}"
        )
        events.append(
            AuditEvent(
                kind="release",
                at=tag.date,
                actor=tagger or "",
                action="released",
                subject=tag.tag,
                detail=f"{tag.items} items",
                ref=_short(tag.commit),
            )
        )
    return AuditResult(events=sorted(events, key=lambda e: e.at, reverse=True))


# --- revoke preview ---------------------------------------------------------------------


class RevokePreview(Result):
    targets: list[RevokeTarget] = []


class RevokeTarget(Result):
    item: str
    version: str | None = None
    rollback_to: str | None = None
    affected: list[Client] = []
    unknown: list[Client] = []


def revoke_preview(ctx: Context) -> RevokePreview:
    """Every item on main with the clients a revoke would warn and the release a
    rollback would restore."""
    admin = Registry.load(ctx.repo)
    m_ref = git.fetch_branch(ctx.repo, main_branch(admin))
    git.run(ctx.repo, "fetch", "-q", "--tags", "--force", "origin")
    lock = model_at(ctx.repo, m_ref, LOCK, LockFile)
    found = []
    for item_id in sorted(lock.items):
        hit, unknown = affected(ctx.repo, admin.clients.clients, item_id, None)
        try:
            commit = last_approved(ctx.repo, m_ref, item_id)
            target = git.run(
                ctx.repo, "describe", "--tags", "--exact-match", commit, check=False
            ) or _short(commit)
        except NotFoundError:
            target = None
        found.append(
            RevokeTarget(
                item=item_id,
                version=builder.manifest_version_at(ctx.repo, m_ref, item_id),
                rollback_to=target,
                affected=hit,
                unknown=unknown,
            )
        )
    return RevokePreview(targets=found)


# --- bundles -------------------------------------------------------------------------------


class PartInfo(Result):
    kind: str
    name: str
    source: str | None = None
    plugin: str | None = None
    path: str = ""
    commit: str | None = None
    license: str | None = None

    @property
    def spec(self) -> str:
        """``source:plugin/kind/name``, as bundle commands take it."""
        return f"{self.source}:{self.plugin}/{self.kind}/{self.name}"


class BundleInfo(Result):
    id: str
    version: str | None = None
    next_version: str = FIRST_VERSION
    description: str = ""
    category: str | None = None
    parts: list[PartInfo] = []


class BundlesOverview(Result):
    bundles: list[BundleInfo] = []
    local: list[str] = Field(default_factory=list, description="Local plugins")


class PluginParts(Result):
    parts: list[PartInfo] = []


def bundles_overview(ctx: Context) -> BundlesOverview:
    """The bundles on staging with every part's pin and license, and the
    local plugins that can give parts."""
    start = remote_start(ctx.repo, base_branch(Registry.load(ctx.repo)))
    items = model_at(ctx.repo, start, ITEMS, ItemsFile)
    locks = model_at(ctx.repo, start, LOCK, LockFile).items
    found = []
    for item in items.items:
        if item.kind is not ItemKind.BUNDLE:
            continue
        lock = locks.get(item.id)
        locked = {(p.kind, p.name): p for p in (lock.parts if lock else [])}
        manifest = git.show_file(
            ctx.repo, start, f"{builder.plugin_dir(item.id)}/{builder.ROOT_MANIFEST}"
        )
        data = json.loads(manifest) if manifest else {}
        parts = []
        for part in item.parts:
            pinned = locked.get((part.kind, part.name))
            parts.append(
                PartInfo(
                    kind=part.kind,
                    name=part.name,
                    source=part.source,
                    plugin=part.upstream_plugin,
                    path=pinned.path if pinned else "",
                    commit=part.commit,
                    license=pinned.upstream.license if pinned else None,
                )
            )
        version = data.get("version") if isinstance(data, dict) else None
        found.append(
            BundleInfo(
                id=item.id,
                version=version,
                next_version=bump_patch(version),
                description=str(data.get("description") or "")
                if isinstance(data, dict)
                else "",
                category=item.category,
                parts=parts,
            )
        )
    local = [i.id for i in items.items if i.kind is ItemKind.LOCAL]
    return BundlesOverview(bundles=found, local=local)


def plugin_parts(ctx: Context, source_id: str, plugin: str) -> PluginParts:
    """The skills, agents and MCP servers one plugin offers as bundle parts."""
    reg = Registry.load(ctx.repo)
    start = remote_start(ctx.repo, base_branch(reg))
    with (
        view(ctx.repo, start) as wt,
        tempfile.TemporaryDirectory(prefix="skill-dojo-parts-") as tmp,
    ):
        sources = {
            s.id: s for s in [*Registry.load(wt).sources.sources, *reg.sources.sources]
        }
        files, upstream = Fetcher(ctx, wt, sources, Path(tmp)).plugin(source_id, plugin)
        _, servers = plugin_servers(files)
    skills = sorted(
        {
            r.split("/")[1]
            for r in files
            if r.startswith("skills/") and r.endswith("/SKILL.md")
        }
    )
    agents = sorted(
        PurePosixPath(r).stem
        for r in files
        if r.startswith("agents/") and r.endswith(".md")
    )
    common = {
        "source": source_id,
        "plugin": plugin,
        "commit": upstream.commit,
        "license": upstream.license,
    }
    return PluginParts(
        parts=[
            *(
                PartInfo(kind="skill", name=n, path=f"skills/{n}", **common)
                for n in skills
            ),
            *(
                PartInfo(kind="agent", name=n, path=f"agents/{n}.md", **common)
                for n in agents
            ),
            *(
                PartInfo(kind="mcp_server", name=n, path="mcp", **common)
                for n in sorted(servers)
            ),
        ]
    )
