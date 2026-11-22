"""Repo-wide operations: ``init``, ``build`` and ``validate``."""

import logging
from pathlib import Path

from skill_dojo_core import builder, registry, workflows
from skill_dojo_core.context import Context
from skill_dojo_core.errors import ConflictError
from skill_dojo_core.models import (
    ChannelPolicy,
    ClientsFile,
    ItemsFile,
    LockFile,
    Namespace,
    RegistryConfig,
    SourcesFile,
    ToolPin,
)
from skill_dojo_core.registry import Registry
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result
from skill_dojo_core.validation import ValidationReport, validate_registry

log = logging.getLogger(__name__)

GITIGNORE_LINE = "registry/.lock"


class InitResult(Result):
    created: list[str]


class BuildResult(Result):
    changed: list[str]
    applied: bool


def _ensure_gitignore(repo: Path) -> bool:
    path = repo / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if GITIGNORE_LINE in text.splitlines():
        return False
    prefix = "" if not text or text.endswith("\n") else "\n"
    path.write_text(f"{text}{prefix}{GITIGNORE_LINE}\n", encoding="utf-8")
    return True


def scaffold(repo: Path, config: RegistryConfig) -> list[str]:
    """Write the registry files, the validate workflow and the .gitignore line.

    The caller holds the repo lock and has checked that no config exists.
    """
    created: list[str] = []
    files = {
        registry.CONFIG: config,
        registry.SOURCES: SourcesFile(),
        registry.ITEMS: ItemsFile(),
        registry.POLICY: ChannelPolicy(),
        registry.CLIENTS: ClientsFile(),
    }
    for file_name, model in files.items():
        registry.save_yaml_model(
            repo, file_name, model, defaults=file_name == registry.CONFIG
        )
        created.append(f"registry/{file_name}")
    registry.save_lock(repo, LockFile())
    created.append(f"registry/{registry.LOCK}")
    workflow = repo / workflows.VALIDATE_WORKFLOW
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        workflows.validate_workflow(config.tool, config.main_branch), encoding="utf-8"
    )
    created.append(workflows.VALIDATE_WORKFLOW)
    if _ensure_gitignore(repo):
        created.append(".gitignore")
    return created


def ensure_no_config(repo: Path) -> None:
    if registry.registry_path(repo, registry.CONFIG).exists():
        raise ConflictError("registry/config.yaml already exists")


def init(
    ctx: Context,
    *,
    name: str | None = None,
    tool: ToolPin,
    repository: str | None = None,
) -> InitResult:
    """Scaffold ``registry/``, empty catalogs and the validate workflow."""
    repo = ctx.repo
    market = name or repo.name.lower()
    config = RegistryConfig(
        name=market,
        repository=repository,
        namespace=Namespace.from_name(market),
        tool=tool,
    )
    with repo_lock(repo):
        ensure_no_config(repo)
        created = scaffold(repo, config)
        created += builder.apply_build(Registry.load(repo))
    ctx.report(f"Initialized marketplace '{market}'")
    log.info("Initialized marketplace %s", market)
    return InitResult(created=sorted(set(created)))


def build(ctx: Context, *, check: bool = False) -> BuildResult:
    """Regenerate catalogs, manifests, stamps and layout (or only report)."""
    if check:
        overlay = builder.plan(Registry.load(ctx.repo))
        return BuildResult(changed=overlay.changes(), applied=False)
    with repo_lock(ctx.repo):
        changed = builder.apply_build(Registry.load(ctx.repo))
    ctx.report(f"Build changed {len(changed)} file(s)")
    return BuildResult(changed=changed, applied=True)


def validate(ctx: Context) -> ValidationReport:
    """Validate plugins, skills, catalogs and ``registry/``."""
    return validate_registry(Registry.load(ctx.repo))
