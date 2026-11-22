"""Candidates: ``mirror``, ``sync`` and ``flags``.

A candidate is a branch ``candidate/<item>/<short-sha>`` off ``staging`` with
the vendored upstream files, the item and lock entry and the upstream metadata,
opened as a PR into ``staging``. Every candidate is built in a throwaway git
worktree, so the admin's checkout is never switched or touched.
"""

import json
import logging
import posixpath
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from skill_dojo_core import (
    builder,
    frontmatter,
    git,
    hashing,
    jsontext,
    mcp_registry,
    risk,
    sources,
)
from skill_dojo_core.branches import (
    base_branch,
    candidate_branch,
    commit_and_push,
    open_or_update,
    remote_start,
    short_pin,
    view,
)
from skill_dojo_core.commands.sources import checkout_source, get_source
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError, InvalidInputError, NotFoundError
from skill_dojo_core.github import PullRequest
from skill_dojo_core.models import (
    ITEM_ID_RE,
    Item,
    ItemKind,
    ItemLock,
    Namespace,
    Source,
    SourceType,
    Upstream,
)
from skill_dojo_core.registry import (
    SOURCES,
    Registry,
    save_yaml_model,
)
from skill_dojo_core.results import Result
from skill_dojo_core.risk import RiskFlag, Tree
from skill_dojo_core.validation import validate_registry

log = logging.getLogger(__name__)

LICENSE_NAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "NOTICE",
    "NOTICE.md",
    "COPYING",
)
# Repo plumbing that is not part of a plugin at the repo root (its manifest in
# .claude-plugin/ is still vendored).
SKIPPED_TOP = frozenset({".git", ".github", ".agents", ".claude-plugin", "registry"})
MARKER = "<!-- skill-dojo:candidate"


class CandidateResult(Result):
    item: str
    commit: str
    branch: str
    pull_request: PullRequest | None = None
    flags: list[RiskFlag] = []
    status: str  # opened | updated | up-to-date | unchanged | quarantined


class FlagsResult(Result):
    base: str
    flags: dict[str, list[RiskFlag]]
    markdown: str


@dataclass(frozen=True)
class Fetched:
    """An upstream plugin checked out at a pinned commit."""

    root: Path
    plugin: sources.UpstreamPlugin
    repository: str
    ref: str
    commit: str


# --- trees ------------------------------------------------------------------


def unstamp(rel: str, data: bytes, namespace: Namespace) -> bytes:
    """``data`` without the tool's provenance keys (for risk comparison)."""
    name = PurePosixPath(rel).name
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    try:
        if name == "SKILL.md" and frontmatter.split(text) is not None:
            return frontmatter.set_metadata(text, namespace.skill, {}).encode()
        if rel in hashing.MANIFESTS:
            return jsontext.set_extension(text, namespace.plugin, None).encode()
    except ValueError:
        return data
    return data


def tree_of(root: Path, namespace: Namespace, skip: set[str] | None = None) -> Tree:
    files = {}
    for rel in hashing.list_files(root):
        if rel in (skip or set()):
            continue
        path = root / rel
        data = hashing.raw_bytes(path)
        files[rel] = (hashing.file_mode(path), unstamp(rel, data, namespace))
    return files


def tree_at(
    repo: Path, ref: str, prefix: str, namespace: Namespace, skip: set[str]
) -> Tree:
    files = {}
    for path, (mode, data) in git.files_at(repo, ref, prefix).items():
        rel = path.removeprefix(prefix + "/")
        if rel not in skip:
            files[rel] = (mode, unstamp(rel, data, namespace))
    return files


# --- fetching and normalizing --------------------------------------------------


def fetch_server(source: Source, name: str, item_id: str, tmp: Path) -> Fetched:
    """Pin the latest version of MCP server ``name`` and write its wrapper."""
    entry = mcp_registry.get_server(source.repository, name)
    package = mcp_registry.choose_package(entry)
    pinned = mcp_registry.pin(package)
    root = tmp / "mcp"
    for rel, text in mcp_registry.wrapper_files(
        item_id, entry, pinned, package
    ).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    plugin = sources.UpstreamPlugin(
        name=entry.name,
        path=".",
        repository=source.repository,
        version=entry.version,
        description=entry.description,
    )
    return Fetched(root, plugin, source.repository, entry.version, pinned.pin)


def fetch_plugin(
    ctx: Context, source: Source, name: str, tmp: Path, item_id: str | None = None
) -> Fetched:
    """Check out the source, find ``name`` and follow a remote plugin source.

    From the MCP Registry, the wrapper plugin of server ``name`` (named
    ``item_id``) is generated instead.
    """
    if source.allowlist and name not in source.allowlist:
        raise InvalidInputError(f"'{name}' is not in the allowlist of '{source.id}'")
    if source.type is SourceType.MCP_REGISTRY:
        return fetch_server(source, name, item_id or name, tmp)
    commit = checkout_source(ctx, source, tmp / "src")
    offered = {p.name: p for p in sources.list_plugins(source, tmp / "src")}
    plugin = offered.get(name)
    if plugin is None:
        raise NotFoundError(f"source '{source.id}' offers no plugin '{name}'")
    if plugin.unsupported:
        raise InvalidInputError(f"'{name}' cannot be mirrored: {plugin.unsupported}")
    if plugin.repository == source.repository:
        return Fetched(tmp / "src", plugin, source.repository, source.ref, commit)
    url = sources.repo_url(plugin.repository)
    local_source = sources.repo_url(source.repository).startswith("file://")
    if url.startswith("file://") and not local_source:
        raise InvalidInputError(
            f"'{name}' points at a local repository; only a local source may"
        )
    ref = plugin.ref or "HEAD"
    remote_commit = git.resolve(url, ref, ctx.repo)
    git.fetch_commit(url, remote_commit, tmp / "plugin", credentials_from=ctx.repo)
    return Fetched(tmp / "plugin", plugin, plugin.repository, ref, remote_commit)


def upstream_files(fetched: Fetched) -> dict[str, Path]:
    """Plugin-relative path -> source file of everything to vendor."""
    base = (
        fetched.root
        if fetched.plugin.path == "."
        else fetched.root / fetched.plugin.path
    )
    root = fetched.root.resolve()
    current = fetched.root
    for part in PurePosixPath(fetched.plugin.path).parts:
        current = current / part
        if current.is_symlink():
            raise InvalidInputError(f"upstream path {fetched.plugin.path} is a symlink")
    if base.resolve() != root and root not in base.resolve().parents:
        raise InvalidInputError(f"upstream path {fetched.plugin.path} leaves the repo")
    if not base.is_dir():
        raise NotFoundError(f"{fetched.plugin.path} not found upstream")
    files = {}
    for rel in hashing.list_files(base):
        top = PurePosixPath(rel).parts[0]
        if (
            fetched.plugin.path == "."
            and top in SKIPPED_TOP
            and rel not in hashing.MANIFESTS
        ):
            continue
        files[rel] = base / rel
    if fetched.plugin.path != "." and not any(
        PurePosixPath(r).name in LICENSE_NAMES for r in files
    ):
        for name in LICENSE_NAMES:
            if (fetched.root / name).is_file():
                files[f"licenses/{name}"] = fetched.root / name
    return files


def check_representable(item_id: str, base: dict[str, Path]) -> None:
    """Reject plugins that could only be vendored by rewriting their files."""
    manifests = [rel for rel in hashing.MANIFESTS if rel in base]
    if not manifests and not any(r.startswith("skills/") for r in base):
        raise InvalidInputError(f"'{item_id}' has no manifest and no skills")
    for rel in manifests:
        try:
            name = json.loads(base[rel].read_text(encoding="utf-8")).get("name")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise InvalidInputError(f"'{item_id}': unreadable {rel}: {exc}") from exc
        if name not in (None, item_id):
            raise InvalidInputError(
                f"upstream plugin is named '{name}'; mirroring it as '{item_id}' "
                "would rewrite its manifest"
            )
    for rel, path in base.items():
        if not path.is_symlink():
            continue
        target = str(path.readlink())
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
        if target.startswith("/") or resolved == ".." or resolved.startswith("../"):
            raise InvalidInputError(f"'{item_id}': {rel} links outside the plugin")


def vendor_into(dest: Path, files: dict[str, Path]) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    for rel, src in sorted(files.items()):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            target.symlink_to(src.readlink())
        else:
            shutil.copy2(src, target)


# --- the candidate branch --------------------------------------------------------


def pr_body(  # noqa: PLR0917
    item: Item,
    fetched: Fetched,
    old_commit: str | None,
    flags: list[RiskFlag],
    changes: dict[str, list[str]],
    errors: list[str],
) -> str:
    lines = [
        f"## Candidate: `{item.id}` ({item.kind.value})",
        "",
        f"- Source: `{item.source}` (`{fetched.repository}`), path `{fetched.plugin.path}`",
        f"- Ref `{fetched.ref}` = `{fetched.commit}`"
        + (f" (was `{old_commit}`)" if old_commit else " (first import)"),
    ]
    if fetched.plugin.version:
        lines.append(f"- Upstream version `{fetched.plugin.version}`")
    lines += ["", "### Changed files", ""]
    for kind in ("added", "changed", "removed"):
        paths = changes[kind]
        if paths:
            shown = ", ".join(f"`{p}`" for p in paths[:40])
            more = f" and {len(paths) - 40} more" if len(paths) > 40 else ""
            lines.append(f"- {kind} ({len(paths)}): {shown}{more}")
    if not any(changes.values()):
        lines.append("- no file changes")
    lines += ["", "### Risk flags", "", risk.render(flags), ""]
    if errors:
        lines += ["### Validation errors", "", *(f"- {e}" for e in errors), ""]
    lines.append(f"{MARKER} item={item.id} commit={fetched.commit} -->")
    return "\n".join(lines)


def file_changes(old: Tree, new: Tree) -> dict[str, list[str]]:
    return {
        "added": sorted(set(new) - set(old)),
        "changed": sorted(r for r in new if r in old and old[r] != new[r]),
        "removed": sorted(set(old) - set(new)),
    }


def check_item_id(item_id: str) -> None:
    if not (1 <= len(item_id) <= 64) or not ITEM_ID_RE.match(item_id):
        raise InvalidInputError(f"'{item_id}' is not a valid plugin name")


@dataclass(frozen=True)
class Built:
    flags: list[RiskFlag]
    body: str
    unchanged: bool


def build_candidate(
    wt: Path, staged: Registry, item_id: str, source: Source, fetched: Fetched
) -> Built:
    """Vendor ``fetched`` into the worktree and build it; nothing is committed."""
    old = staged.lock.items.get(item_id)
    files = upstream_files(fetched)
    check_representable(item_id, files)
    ns = staged.config.namespace
    plugin = wt / builder.plugin_dir(item_id)
    skip = set(old.generated) if old else set()
    approved = tree_of(plugin, ns, skip) if plugin.is_dir() and old else {}
    vendor_into(plugin, files)
    candidate = tree_of(plugin, ns)
    if old is not None and approved == candidate:
        return Built(flags=[], body="", unchanged=True)
    flags = risk.compare(approved, candidate)
    body = _write_candidate(
        wt, item_id, source, fetched, approved, candidate, flags, old
    )
    return Built(flags=flags, body=body, unchanged=False)


def publish(
    ctx: Context, item_id: str, *, branch: str, base: str, title: str, body: str
) -> tuple[PullRequest, str]:
    """Open or update the candidate PR and close older ones of the same item."""
    pr, status = open_or_update(ctx, branch, base, title, body)
    prefix = candidate_branch(item_id, "")
    for stale in ctx.github.list_open_pull_requests(base):
        if stale.head.startswith(prefix) and stale.number != pr.number:
            ctx.github.close_pull_request(stale.number, f"Superseded by {pr.url}.")
    return pr, status


def make_candidate(
    ctx: Context,
    source: Source | None,
    name: str | None,
    item_id: str,
    *,
    new: bool,
) -> CandidateResult:
    """Fetch, normalize, flag, commit, push and open or update the PR.

    The registry state comes from the base branch (``staging``), not from the
    admin's checkout. ``source`` and ``name`` default to the staged item's.
    """
    check_item_id(item_id)
    base = base_branch(Registry.load(ctx.repo))
    start = remote_start(ctx.repo, base)
    with view(ctx.repo, start) as wt:
        staged = Registry.load(wt)
        existing = staged.items.get(item_id)
        if new and existing is not None:
            raise ConflictError(f"'{item_id}' is already tracked; use 'sync'")
        if existing is not None and existing.quarantined:
            return CandidateResult(
                item=item_id, commit="", branch="", status="quarantined"
            )
        if source is None or name is None:
            if existing is None or existing.source is None:
                raise NotFoundError(f"'{item_id}' is not a mirror on {base}")
            source = get_source(staged, existing.source)
            name = existing.upstream_plugin or item_id
        with tempfile.TemporaryDirectory(prefix="skill-dojo-up-") as tmp:
            fetched = fetch_plugin(ctx, source, name, Path(tmp), item_id)
            old = staged.lock.items.get(item_id)
            if old is not None and old.upstream.commit == fetched.commit:
                return CandidateResult(
                    item=item_id, commit=fetched.commit, branch="", status="up-to-date"
                )
            built = build_candidate(wt, staged, item_id, source, fetched)
            if built.unchanged:
                return CandidateResult(
                    item=item_id, commit=fetched.commit, branch="", status="unchanged"
                )
            branch = candidate_branch(item_id, fetched.commit)
            message = f"candidate: {item_id} {short_pin(fetched.commit)}"
            commit_and_push(wt, branch, message)
    title = f"candidate: {item_id} @ {short_pin(fetched.commit)}"
    pr, status = publish(
        ctx, item_id, branch=branch, base=base, title=title, body=built.body
    )
    ctx.report(f"{status} candidate {item_id} -> {pr.url}")
    log.info("Candidate %s %s: %s", item_id, status, pr.url)
    return CandidateResult(
        item=item_id,
        commit=fetched.commit,
        branch=branch,
        pull_request=pr,
        flags=built.flags,
        status=status,
    )


def _write_candidate(  # noqa: PLR0917
    wt: Path,
    item_id: str,
    source: Source,
    fetched: Fetched,
    approved: Tree,
    candidate: Tree,
    flags: list[RiskFlag],
    old: ItemLock | None,
) -> str:
    """Record item + lock in the worktree, build it, and return the PR body."""
    reg = Registry.load(wt)
    # The source definition travels with the candidate, so staging always knows
    # where every item comes from.
    others = [s for s in reg.sources.sources if s.id != source.id]
    if others != reg.sources.sources or source not in reg.sources.sources:
        reg.sources.sources = [*others, source]
        save_yaml_model(wt, SOURCES, reg.sources)
    item = reg.items.get(item_id)
    if item is None:
        item = Item(id=item_id, kind=ItemKind.MIRROR, source=source.id)
        reg.items.items.append(item)
    item.upstream_plugin = fetched.plugin.name
    item.ref = fetched.ref
    item.commit = fetched.commit
    root = wt / builder.plugin_dir(item_id)
    files = hashing.hash_tree(root, reg.config.namespace)
    reg.lock.items[item_id] = ItemLock(
        kind=ItemKind.MIRROR,
        version=fetched.plugin.version or builder.manifest_version(root),
        upstream=Upstream(
            repository=fetched.repository,
            commit=fetched.commit,
            path=fetched.plugin.path,
            ref=fetched.ref,
            plugin=fetched.plugin.name,
        ),
        tree_sha256=hashing.tree_sha256(files),
        files=files,
    )
    reg.save_items()
    reg.save_lock()
    builder.apply_build(reg)
    errors = [str(e) for e in validate_registry(Registry.load(wt)).errors]
    return pr_body(
        item,
        fetched,
        old.upstream.commit if old else None,
        flags,
        file_changes(approved, candidate),
        errors,
    )


# --- the operations ----------------------------------------------------------------


def mirror(
    ctx: Context, source_id: str, plugin: str, *, item_id: str | None = None
) -> CandidateResult:
    """Open a candidate PR that mirrors one upstream plugin.

    The source comes from the admin's checkout (it may be new) and travels into
    the candidate branch.
    """
    source = get_source(Registry.load(ctx.repo), source_id)
    if item_id is None and source.type is SourceType.MCP_REGISTRY:
        item_id = mcp_registry.default_item_id(plugin)
    return make_candidate(ctx, source, plugin, item_id or plugin, new=True)


def flags(ctx: Context, *, base: str = "origin/staging") -> FlagsResult:
    """Risk flags of every item in the working tree against ``base``."""
    reg = Registry.load(ctx.repo)
    ns = reg.config.namespace
    found: dict[str, list[RiskFlag]] = {}
    for item in reg.items.items:
        prefix = builder.plugin_dir(item.id)
        lock = reg.lock.items.get(item.id)
        skip = set(lock.generated) if lock else set()
        approved = tree_at(ctx.repo, base, prefix, ns, skip)
        root = ctx.repo / prefix
        current = tree_of(root, ns, skip) if root.is_dir() else {}
        if approved == current:
            continue
        found[item.id] = risk.compare(approved, current)
    sections = [
        f"### `{name}`\n\n{risk.render(items)}" for name, items in found.items()
    ]
    markdown = "\n\n".join(sections) or "No plugin changes."
    return FlagsResult(
        base=base, flags=found, markdown=f"## Risk flags\n\n{markdown}\n"
    )
