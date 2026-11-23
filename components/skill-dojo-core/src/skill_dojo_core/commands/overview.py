"""Read models for the web UI: changes, plugins, parts, releases, preview, audit.

Every function reads git, the registry files, the cache and the GitHub API;
none writes to the repo (``plugin_parts`` may fill the cache).
"""

import csv
import io
import json
import logging
import tempfile
from pathlib import Path

from pydantic import Field

from skill_dojo_core import builder, cache, catalogs, git
from skill_dojo_core.branches import COMMIT_PREFIX, main_branch, work_branch
from skill_dojo_core.commands.mirror import flags
from skill_dojo_core.commands.release import (
    TAG_PREFIX,
    fetch_tags,
    previous_tag,
    release_notes,
)
from skill_dojo_core.commands.sources import get_source
from skill_dojo_core.commands.work import WorkStatus, status
from skill_dojo_core.context import Context
from skill_dojo_core.diffs import DiffLine, compare_texts
from skill_dojo_core.errors import SkillDojoError
from skill_dojo_core.models import ItemKind, LockFile
from skill_dojo_core.parts import LOCAL_SOURCE, Fetcher, file_version, index_parts
from skill_dojo_core.registry import LOCK, REGISTRY_DIR, Registry, model_at
from skill_dojo_core.results import Result
from skill_dojo_core.risk import RiskFlag
from skill_dojo_core.validation import validate_registry
from skill_dojo_core.validation.report import Finding

log = logging.getLogger(__name__)


def _short(sha: str | None) -> str:
    return (sha or "")[:7]


def _main_ref(reg: Registry) -> str | None:
    return builder.main_ref(reg)


# --- changes (the work branch) -------------------------------------------------------


class ChangesOverview(Result):
    status: WorkStatus
    flags: dict[str, list[RiskFlag]] = {}


def changes_overview(ctx: Context) -> ChangesOverview:
    """The work branch, its pending versions and risk flags against main."""
    found = status(ctx)
    risk: dict[str, list[RiskFlag]] = {}
    if found.on_branch and git.ref_exists(
        ctx.repo, f"refs/remotes/origin/{found.main}"
    ):
        risk = flags(ctx, base=f"refs/remotes/origin/{found.main}").flags
    return ChangesOverview(status=found, flags=risk)


# --- plugins ------------------------------------------------------------------------


class PartInfo(Result):
    kind: str
    name: str
    source: str | None = None
    plugin: str | None = None
    path: str = ""
    commit: str | None = None
    license: str | None = None
    description: str = ""
    version: str | None = None

    @property
    def spec(self) -> str:
        """``source:plugin/kind/name``, as ``add-parts`` takes it."""
        return f"{self.source}:{self.plugin}/{self.kind}/{self.name}"


class PluginInfo(Result):
    id: str
    kind: str
    version: str | None = None
    description: str = ""
    category: str | None = None
    path: str
    source: str | None = None
    pin: str | None = None
    quarantined: bool = False
    parts: list[PartInfo] = []


class PluginsOverview(Result):
    marketplace_version: str | None = Field(
        default=None, description="Newest release tag without its prefix"
    )
    plugins: list[PluginInfo] = []
    local: list[str] = Field(default_factory=list, description="Local plugin ids")


class PluginParts(Result):
    parts: list[PartInfo] = []


def _manifest(root: Path) -> dict[str, object]:
    for rel in (builder.ROOT_MANIFEST, builder.CLAUDE_MANIFEST):
        try:
            data = json.loads((root / rel).read_text(encoding="utf-8"))
        except OSError, UnicodeDecodeError, ValueError:
            continue
        if isinstance(data, dict):
            return data
    return {}


# Where a part's frontmatter lives inside the plugin; others carry no version.
_PART_FILES = {"skill": "skills/{}/SKILL.md", "agent": "agents/{}.md"}


def _part_version(root: Path, kind: str, name: str) -> str | None:
    pattern = _PART_FILES.get(kind)
    return file_version(root / pattern.format(name)) if pattern else None


def _marketplace_version(repo: Path) -> str | None:
    """The newest local release tag, as the version of this marketplace."""
    newest = git.run(
        repo,
        "for-each-ref",
        "--sort=-creatordate",
        "--count=1",
        "--format=%(refname:short)",
        f"refs/tags/{TAG_PREFIX}*",
    )
    return newest.removeprefix(TAG_PREFIX) or None


def plugins_overview(ctx: Context) -> PluginsOverview:
    """Every item in the checkout with kind, version and parts."""
    reg = Registry.load(ctx.repo)
    found = []
    for item in sorted(reg.items.items, key=lambda i: i.id):
        lock = reg.lock.items.get(item.id)
        locked = {(p.kind, p.name): p for p in (lock.parts if lock else [])}
        root = ctx.repo / builder.plugin_dir(item.id)
        data = _manifest(root)
        parts = [
            PartInfo(
                kind=p.kind,
                name=p.name,
                source=p.source,
                plugin=p.upstream_plugin,
                path=pinned.path if (pinned := locked.get((p.kind, p.name))) else "",
                commit=p.commit,
                license=pinned.upstream.license if pinned else None,
                version=_part_version(root, p.kind, p.name),
            )
            for p in item.parts
        ]
        found.append(
            PluginInfo(
                id=item.id,
                kind=item.kind.value,
                version=builder.manifest_version(root),
                description=str(data.get("description") or ""),
                category=item.category,
                path=builder.plugin_dir(item.id),
                source=item.source,
                pin=item.commit if item.kind is ItemKind.MIRROR else None,
                quarantined=item.quarantined,
                parts=parts,
            )
        )
    local = [i.id for i in found if i.kind == ItemKind.LOCAL.value]
    return PluginsOverview(
        marketplace_version=_marketplace_version(ctx.repo), plugins=found, local=local
    )


def plugin_parts(ctx: Context, source_id: str, plugin: str) -> PluginParts:
    """The skills, agents, MCP servers and hooks one plugin offers as parts."""
    reg = Registry.load(ctx.repo)
    if source_id != LOCAL_SOURCE:
        index = cache.read_index(ctx.repo, get_source(reg, source_id))
        hit = (
            next((c for c in index.plugins if c.plugin.name == plugin), None)
            if index
            else None
        )
        if hit is not None and hit.parts is not None and index is not None:
            commit = index.commit if index.commit != cache.LATEST else None
            return PluginParts(
                parts=[
                    PartInfo(
                        kind=p.kind,
                        name=p.name,
                        commit=commit,
                        license=hit.plugin.license,
                        source=source_id,
                        plugin=plugin,
                        description=p.description,
                        version=p.version,
                    )
                    for p in hit.parts
                ]
            )
    with tempfile.TemporaryDirectory(prefix="skill-dojo-parts-") as tmp:
        sources = {s.id: s for s in reg.sources.sources}
        files, upstream = Fetcher(ctx, sources, Path(tmp), pinning=False).plugin(
            source_id, plugin
        )
        refs = index_parts(files)
    return PluginParts(
        parts=[
            PartInfo(
                kind=p.kind,
                name=p.name,
                commit=upstream.commit,
                license=upstream.license,
                source=source_id,
                plugin=plugin,
                description=p.description,
                version=p.version,
            )
            for p in refs
        ]
    )


# --- releases ----------------------------------------------------------------------------


class TagInfo(Result):
    tag: str
    commit: str
    date: str = ""
    items: int = 0


class CommitInfo(Result):
    sha: str
    subject: str
    author: str = ""
    date: str = ""


class ReleaseOverview(Result):
    main: str
    main_head: str
    latest_tag: str | None = None
    latest_tag_date: str | None = None
    untagged: bool = False
    commits: list[CommitInfo] = []
    tags: list[TagInfo] = []
    notes: str = ""


def tags(repo: Path) -> list[TagInfo]:
    """Release tags, newest first, with item counts."""
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
            )
        )
    return found


def _commits(repo: Path, since: str | None, head: str) -> list[CommitInfo]:
    span = f"{since}..{head}" if since else head
    out = git.run(
        repo,
        "log",
        "--no-merges",
        "--format=%H%x09%an%x09%aI%x09%s",
        "-n",
        "200",
        span,
    )
    found = []
    for line in out.splitlines():
        sha, author, date, subject = [*line.split("\t", 3), "", "", ""][:4]
        found.append(
            CommitInfo(sha=_short(sha), subject=subject, author=author, date=date)
        )
    return found


def release_overview(ctx: Context) -> ReleaseOverview:
    """``origin/<main>`` against the last release: commits, notes, tags."""
    reg = Registry.load(ctx.repo)
    main = main_branch(reg)
    m_ref = git.fetch_branch(ctx.repo, main)
    fetch_tags(ctx.repo)
    head = git.run(ctx.repo, "rev-parse", f"{m_ref}^{{commit}}")
    previous = previous_tag(ctx.repo, head)
    found = tags(ctx.repo)
    latest = found[0] if found else None
    return ReleaseOverview(
        main=main,
        main_head=_short(head),
        latest_tag=latest.tag if latest else None,
        latest_tag_date=latest.date if latest else None,
        untagged=previous is None
        or git.run(ctx.repo, "rev-parse", f"{previous}^{{commit}}") != head,
        commits=_commits(ctx.repo, previous, head),
        tags=found,
        notes=release_notes(ctx.repo, previous, head, "next release"),
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


def _changed_paths(repo: Path, base: str | None, pending: list[str]) -> set[str]:
    diff = git.run(repo, "diff", "--name-only", base).splitlines() if base else []
    untracked = git.run(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return {p for p in (*diff, *untracked, *pending) if p}


def marketplace_preview(ctx: Context) -> PreviewResult:
    """What ``build`` would commit, against ``origin/<main>``."""
    reg = Registry.load(ctx.repo)
    base = _main_ref(reg)
    overlay = builder.plan(reg)
    pending = overlay.changes()
    changed = _changed_paths(ctx.repo, base, pending)

    def status_of(path: str) -> str:
        hit = [c for c in changed if c == path or c.startswith(path.rstrip("/") + "/")]
        if not hit:
            return ""
        exists = base is not None and git.succeeds(
            ctx.repo, "cat-file", "-e", f"{base}:{path.rstrip('/')}"
        )
        return "M" if exists else "A"

    tree: list[TreeEntry] = []
    registry_files = ["items.yaml", "lock.json", "sources.yaml", "channel-policy.yaml"]
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
        (f"{REGISTRY_DIR}/", [f"{REGISTRY_DIR}/{n}" for n in registry_files]),
    ):
        tree.append(TreeEntry(path=folder, depth=0))
        tree += [TreeEntry(path=f, depth=1, status=status_of(f)) for f in files]
    previews = []
    for rel in (catalogs.AGENTS_CATALOG, catalogs.CLAUDE_CATALOG):
        new = overlay.read_text(rel) or ""
        old = (
            (git.show_file(ctx.repo, base, rel) or b"").decode("utf-8", "replace")
            if base
            else ""
        )
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
        base=main_branch(reg),
        base_head=_short(git.run(ctx.repo, "rev-parse", base)) if base else "",
        tree=tree,
        catalogs=previews,
        pending=pending,
        errors=len(report.errors),
        warnings=report.warnings,
    )


# --- audit ---------------------------------------------------------------------------------


class AuditEvent(Result):
    kind: str  # change | sync | merge | release | revocation
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


def _commit_event(line: str) -> AuditEvent | None:
    sha, author, date, subject = [*line.split("\t", 3), "", "", ""][:4]
    if not subject.startswith(COMMIT_PREFIX):
        return None
    action, _, rest = subject.removeprefix(COMMIT_PREFIX).partition(" ")
    kind = {"sync": "sync", "revoke": "revocation"}.get(action, "change")
    return AuditEvent(
        kind=kind,
        at=date,
        actor=author,
        action=action,
        subject=rest,
        ref=_short(sha),
    )


def audit_log(ctx: Context) -> AuditResult:
    """Work-branch changes on main, merged work-branch PRs and release tags,
    newest first."""
    reg = Registry.load(ctx.repo)
    work, main = work_branch(reg), main_branch(reg)
    events: list[AuditEvent] = []
    for pr in ctx.github.list_merged_pull_requests(main):
        if pr.head != work or pr.cross_repository:
            continue
        events.append(
            AuditEvent(
                kind="merge",
                at=pr.merged_at or "",
                actor=pr.merged_by or pr.author,
                action="merged",
                subject=f"{work} → {main}",
                ref=f"PR #{pr.number}",
                url=pr.url,
            )
        )
    base = _main_ref(reg)
    if base is not None:
        out = git.run(
            ctx.repo, "log", "--format=%H%x09%an%x09%aI%x09%s", "-n", "500", base
        )
        events += [e for line in out.splitlines() if (e := _commit_event(line))]
    for tag in tags(ctx.repo):
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


class RevokeTarget(Result):
    item: str
    version: str | None = None
    rollback_to: str | None = None


class RevokePreview(Result):
    targets: list[RevokeTarget] = []


def _rollback_tag(repo: Path, item_id: str, current: str | None) -> str | None:
    """The newest release whose content of the item differs from main's."""
    for tag in git.run(
        repo, "tag", "--list", f"{TAG_PREFIX}*", "--sort=-creatordate"
    ).splitlines():
        entry = model_at(repo, tag, LOCK, LockFile).items.get(item_id)
        if entry is not None and entry.tree_sha256 != current:
            return tag
    return None


def revoke_preview(ctx: Context) -> RevokePreview:
    """Every item on main with the release a rollback could restore."""
    reg = Registry.load(ctx.repo)
    try:
        m_ref = git.fetch_branch(ctx.repo, main_branch(reg))
        fetch_tags(ctx.repo)
    except SkillDojoError as exc:
        log.warning("Could not fetch origin: %s", exc)
        return RevokePreview()
    lock = model_at(ctx.repo, m_ref, LOCK, LockFile)
    return RevokePreview(
        targets=[
            RevokeTarget(
                item=item_id,
                version=builder.manifest_version_at(ctx.repo, m_ref, item_id),
                rollback_to=_rollback_tag(
                    ctx.repo, item_id, lock.items[item_id].tree_sha256
                ),
            )
            for item_id in sorted(lock.items)
        ]
    )
