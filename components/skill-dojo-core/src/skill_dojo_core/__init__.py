"""skill-dojo-core: all behaviour of skill-dojo, front-end neutral.

Front ends (CLI, web UI, a later server) import only from this module.
"""

from skill_dojo_core.branches import WorkBranch, main_branch, work_branch
from skill_dojo_core.commands.adopt import AdoptResult, adopt
from skill_dojo_core.commands.items import (
    LocalAddResult,
    LockRefreshResult,
    local_add,
    lock_refresh,
)
from skill_dojo_core.commands.marketplace import (
    MarketplaceResult,
    marketplace_add,
    marketplace_update,
)
from skill_dojo_core.commands.mirror import ChangeResult, FlagsResult, flags, mirror
from skill_dojo_core.commands.overview import (
    AuditEvent,
    AuditResult,
    CatalogPreview,
    ChangesOverview,
    CommitInfo,
    PartInfo,
    PluginInfo,
    PluginParts,
    PluginsOverview,
    PreviewResult,
    ReleaseOverview,
    RevokePreview,
    RevokeTarget,
    TagInfo,
    TreeEntry,
    audit_log,
    changes_overview,
    marketplace_preview,
    plugin_parts,
    plugins_overview,
    release_overview,
    revoke_preview,
)
from skill_dojo_core.commands.plugins import add_parts, plugin_new, remove_parts
from skill_dojo_core.commands.release import (
    ReleaseResult,
    RevokeResult,
    release,
    revoke,
)
from skill_dojo_core.commands.repo import BuildResult, InitResult, build, init, validate
from skill_dojo_core.commands.sources import (
    BrowseResult,
    SourcesResult,
    browse,
    source_add,
    source_allow,
    source_list,
    source_refresh,
    source_remove,
    source_set_type,
)
from skill_dojo_core.commands.sync import SyncResult, sync
from skill_dojo_core.commands.versions import (
    PendingVersion,
    pending_versions,
    set_version,
)
from skill_dojo_core.commands.work import FinishResult, WorkStatus, finish, status
from skill_dojo_core.context import Context
from skill_dojo_core.diffs import DiffFile, DiffLine
from skill_dojo_core.errors import (
    ConflictError,
    ExternalToolError,
    InvalidInputError,
    NotFoundError,
    NotImplementedYetError,
    PolicyError,
    RegistryError,
    RepoLockedError,
    SkillDojoError,
    ValidationFailedError,
    not_implemented,
)
from skill_dojo_core.github import GhCli, GitHub, PullRequest
from skill_dojo_core.models import (
    RiskTier,
    Source,
    SourceType,
    ToolPin,
    tool_pin,
)
from skill_dojo_core.registry import Registry
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.results import Result
from skill_dojo_core.risk import RiskFlag
from skill_dojo_core.risk import severity as flag_severity
from skill_dojo_core.sources import UpstreamPlugin, web_url
from skill_dojo_core.validation import Finding, ValidationReport
from skill_dojo_core.versions import LEVELS

__all__ = [
    "LEVELS",
    "AdoptResult",
    "AuditEvent",
    "AuditResult",
    "BrowseResult",
    "BuildResult",
    "CatalogPreview",
    "ChangeResult",
    "ChangesOverview",
    "CommitInfo",
    "ConflictError",
    "Context",
    "DiffFile",
    "DiffLine",
    "ExternalToolError",
    "Finding",
    "FinishResult",
    "FlagsResult",
    "GhCli",
    "GitHub",
    "InitResult",
    "InvalidInputError",
    "LocalAddResult",
    "LockRefreshResult",
    "MarketplaceResult",
    "NotFoundError",
    "NotImplementedYetError",
    "PartInfo",
    "PendingVersion",
    "PluginInfo",
    "PluginParts",
    "PluginsOverview",
    "PolicyError",
    "PreviewResult",
    "PullRequest",
    "Registry",
    "RegistryError",
    "ReleaseOverview",
    "ReleaseResult",
    "RepoLockedError",
    "Result",
    "RevokePreview",
    "RevokeResult",
    "RevokeTarget",
    "RiskFlag",
    "RiskTier",
    "SkillDojoError",
    "Source",
    "SourceType",
    "SourcesResult",
    "SyncResult",
    "TagInfo",
    "ToolPin",
    "TreeEntry",
    "UpstreamPlugin",
    "ValidationFailedError",
    "ValidationReport",
    "WorkBranch",
    "WorkStatus",
    "add_parts",
    "adopt",
    "audit_log",
    "browse",
    "build",
    "changes_overview",
    "finish",
    "flag_severity",
    "flags",
    "init",
    "local_add",
    "lock_refresh",
    "main_branch",
    "marketplace_add",
    "marketplace_preview",
    "marketplace_update",
    "mirror",
    "not_implemented",
    "pending_versions",
    "plugin_new",
    "plugin_parts",
    "plugins_overview",
    "release",
    "release_overview",
    "remove_parts",
    "repo_lock",
    "revoke",
    "revoke_preview",
    "set_version",
    "source_add",
    "source_allow",
    "source_list",
    "source_refresh",
    "source_remove",
    "source_set_type",
    "status",
    "sync",
    "tool_pin",
    "validate",
    "web_url",
    "work_branch",
]
