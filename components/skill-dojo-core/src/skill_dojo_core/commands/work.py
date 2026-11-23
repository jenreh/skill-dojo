"""``status`` and ``finish`` of the work branch.

``finish`` runs build and the version step, commits what is left, pushes the
branch and opens or updates the one PR into main. Merging that PR is the
approval; branch protection does the review.
"""

import logging

from skill_dojo_core import builder, git, versions
from skill_dojo_core.branches import (
    commit_work,
    current_branch,
    dirty_files,
    editing,
    fetch,
    main_branch,
    open_or_update,
    push_work,
    short_pin,
    work_branch,
)
from skill_dojo_core.commands.mirror import flags
from skill_dojo_core.commands.versions import (
    PendingVersion,
    pending_at,
    pending_versions,
    write_version,
)
from skill_dojo_core.context import Context
from skill_dojo_core.errors import InvalidInputError, SkillDojoError
from skill_dojo_core.github import PullRequest
from skill_dojo_core.registry import Registry
from skill_dojo_core.results import Result

log = logging.getLogger(__name__)

MARKER = "<!-- skill-dojo:work-branch -->"
TITLE = "skill-dojo: registry changes"
# GitHub refuses PR bodies over 65536 characters; the table needs room too.
MAX_FLAGS = 40_000


class WorkStatus(Result):
    branch: str
    main: str
    current: str | None = None
    on_branch: bool = False
    exists: bool = False
    pushed: bool = False
    merged: bool = False
    ahead: int = 0
    behind: int = 0
    dirty: list[str] = []
    pull_request: PullRequest | None = None
    pending: list[PendingVersion] = []


class FinishResult(Result):
    status: str  # opened | updated | pushed | nothing
    branch: str
    commit: str | None = None
    pull_request: PullRequest | None = None
    pending: list[PendingVersion] = []
    flags: str = ""


def _counts(ctx: Context, main: str, ref: str) -> tuple[int, int]:
    """(ahead, behind) of ``ref`` against ``main``."""
    out = git.run(
        ctx.repo, "rev-list", "--left-right", "--count", f"{main}...{ref}", check=False
    )
    behind, _, ahead = out.partition("\t")
    try:
        return int(ahead or 0), int(behind or 0)
    except ValueError:
        return 0, 0


def _open_pr(ctx: Context, work: str, main: str) -> PullRequest | None:
    """The work-branch PR; None when GitHub cannot be asked (offline, no gh)."""
    try:
        return ctx.github.find_open_pull_request(work, main)
    except SkillDojoError as exc:
        log.warning("Could not look up the PR: %s", exc)
        return None


def status(ctx: Context) -> WorkStatus:
    """Where the work branch stands: commits, dirty files, PR, pending versions."""
    try:
        fetch(ctx.repo)
    except SkillDojoError as exc:
        log.warning("Could not fetch origin: %s", exc)
    reg = Registry.load(ctx.repo)
    work, main = work_branch(reg), main_branch(reg)
    current = current_branch(ctx.repo)
    on_branch = current == work
    local = git.ref_exists(ctx.repo, f"refs/heads/{work}")
    remote = git.ref_exists(ctx.repo, f"refs/remotes/origin/{work}")
    main_ref = f"refs/remotes/origin/{main}"
    has_main = git.ref_exists(ctx.repo, main_ref)
    ref = (
        "HEAD"
        if on_branch
        else f"refs/heads/{work}"
        if local
        else f"refs/remotes/origin/{work}"
        if remote
        else None
    )
    ahead, behind = _counts(ctx, main_ref, ref) if ref and has_main else (0, 0)
    merged = bool(
        remote
        and has_main
        and git.is_ancestor(ctx.repo, f"refs/remotes/origin/{work}", main_ref)
    )
    if on_branch:
        pending = pending_versions(ctx)
    elif ref is not None and not merged:
        pending = pending_at(ctx.repo, ref)
    else:
        pending = []
    return WorkStatus(
        branch=work,
        main=main,
        current=current,
        on_branch=on_branch,
        exists=local or remote,
        pushed=remote,
        merged=merged,
        ahead=ahead,
        behind=behind,
        dirty=dirty_files(ctx.repo),
        pull_request=_open_pr(ctx, work, main),
        pending=pending,
    )


def pr_body(pending: list[PendingVersion], flag_text: str) -> str:
    lines = ["## Changed plugins", ""]
    if pending:
        lines += [
            "| Plugin | Kind | Change | Version on main | New version | Upstream |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| `{p.item}` | {p.kind} | {p.status} | {p.main_version or '-'} "
            f"| {p.branch_version or '-'} | "
            f"{'`' + short_pin(p.pin) + '`' if p.pin else '-'} |"
            for p in pending
        ]
    else:
        lines.append("- none (registry files only)")
    flag_text = flag_text.strip()
    if len(flag_text) > MAX_FLAGS:
        cut = flag_text[:MAX_FLAGS].rsplit("\n", 1)[0]
        flag_text = f"{cut}\n\n(cut; run `skill-dojo flags` for all risk flags)"
    lines += ["", flag_text, "", MARKER]
    return "\n".join(lines)


def parse_levels(levels: list[str] | dict[str, str] | None) -> dict[str, str]:
    """``item=level`` pairs (CLI) or a mapping (UI) -> ``{item: level}``."""
    if levels is None:
        return {}
    if isinstance(levels, dict):
        return dict(levels)
    found = {}
    for text in levels:
        item, sep, level = text.partition("=")
        if not sep or not item:
            raise InvalidInputError(f"'{text}' is not item=patch|minor|major|X.Y.Z")
        found[item] = level
    return found


def _set_levels(reg: Registry, levels: dict[str, str]) -> None:
    for item, level in levels.items():
        if level in versions.LEVELS:
            write_version(reg, item, versions.check_level(level), None)
        else:
            write_version(reg, item, None, level)


def finish(
    ctx: Context,
    *,
    levels: list[str] | dict[str, str] | None = None,
    open_pr: bool = True,
) -> FinishResult:
    """Build, set the chosen versions, commit, push, open or update the PR."""
    chosen = parse_levels(levels)
    with editing(ctx):
        fetch(ctx.repo)
        reg = Registry.load(ctx.repo)
        work, main = work_branch(reg), main_branch(reg)
        _set_levels(reg, chosen)
        builder.apply_build(Registry.load(ctx.repo))
        commit = commit_work(ctx, "finish", everything=True)
        main_ref = f"refs/remotes/origin/{main}"
        if git.run(ctx.repo, "rev-parse", "HEAD^{tree}") == git.run(
            ctx.repo, "rev-parse", f"{main_ref}^{{tree}}"
        ):
            return FinishResult(status="nothing", branch=work)
        if push_work(ctx, work):
            # origin had commits (sync) that were merged: build the union again.
            builder.apply_build(Registry.load(ctx.repo))
            commit = commit_work(ctx, "finish", everything=True) or commit
            push_work(ctx, work)
        pending = pending_versions(ctx)
        flag_text = flags(ctx, base=main_ref).markdown
    if not open_pr:
        ctx.report(f"Pushed {work}; open the PR into {main} by hand")
        return FinishResult(
            status="pushed",
            branch=work,
            commit=commit,
            pending=pending,
            flags=flag_text,
        )
    pr, state = open_or_update(ctx, work, main, TITLE, pr_body(pending, flag_text))
    ctx.report(f"{state} PR {pr.url}")
    log.info("Work branch PR %s: %s", state, pr.url)
    return FinishResult(
        status=state,
        branch=work,
        commit=commit,
        pull_request=pr,
        pending=pending,
        flags=flag_text,
    )
