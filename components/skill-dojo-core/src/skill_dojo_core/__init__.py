"""skill-dojo-core: all behaviour of skill-dojo, front-end neutral.

Front ends (CLI, web UI, a later server) import only from this module.
"""

from skill_dojo_core.commands.adopt import AdoptResult, adopt
from skill_dojo_core.commands.bundles import bundle_add, bundle_create, bundle_remove
from skill_dojo_core.commands.candidates import (
    CandidateResult,
    FlagsResult,
    flags,
    mirror,
)
from skill_dojo_core.commands.clients import (
    ClientsResult,
    clients_add,
    clients_list,
    clients_remove,
)
from skill_dojo_core.commands.items import (
    LocalAddResult,
    LockRefreshResult,
    local_add,
    lock_refresh,
)
from skill_dojo_core.commands.overview import (
    plugin_parts,
    bundles_overview,
    PartInfo,
    BundleInfo,
    AuditEvent,
    AuditResult,
    CatalogPreview,
    PreviewResult,
    PromotionItem,
    ReleaseOverview,
    ReviewDetail,
    RevokeTarget,
    TagInfo,
    TreeEntry,
    audit_log,
    marketplace_preview,
    release_overview,
    review_detail,
    revoke_preview,
)
from skill_dojo_core.commands.promote import PolicyBlock, PromoteResult, promote
from skill_dojo_core.commands.release import (
    ReleaseResult,
    RevokeResult,
    release,
    revoke,
)
from skill_dojo_core.commands.repo import BuildResult, InitResult, build, init, validate
from skill_dojo_core.commands.review import (
    ReviewActionResult,
    ReviewEntry,
    ReviewListResult,
    ReviewShowResult,
    review_approve,
    review_list,
    review_policy,
    review_quarantine,
    review_reject,
    review_show,
)
from skill_dojo_core.commands.sources import (
    BrowseResult,
    SourcesResult,
    browse,
    source_add,
    source_allow,
    source_list,
    source_remove,
)
from skill_dojo_core.commands.sync import SyncResult, sync
from skill_dojo_core.commands.vendor import VendorResult, vendor
from skill_dojo_core.branches import base_branch, main_branch
from skill_dojo_core.context import Context
from skill_dojo_core.models import Channel, RiskTier
from skill_dojo_core.registry import Registry
from skill_dojo_core.diffs import DiffFile, DiffLine
from skill_dojo_core.errors import (
    ConflictError,
    ExternalToolError,
    RegistryError,
    InvalidInputError,
    NotFoundError,
    NotImplementedYetError,
    PolicyError,
    RepoLockedError,
    SkillDojoError,
    ValidationFailedError,
    not_implemented,
)
from skill_dojo_core.github import GhCli, GitHub, PullRequest, Review
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.models import (
    Approval,
    Client,
    Source,
    SourceType,
    ToolPin,
    tool_pin,
)
from skill_dojo_core.risk import RiskFlag
from skill_dojo_core.sources import UpstreamPlugin
from skill_dojo_core.results import Result
from skill_dojo_core.validation import Finding, ValidationReport

__all__ = [
    "AdoptResult",
    "Approval",
    "AuditEvent",
    "AuditResult",
    "BrowseResult",
    "BuildResult",
    "BundleInfo",
    "CandidateResult",
    "CatalogPreview",
    "Channel",
    "Client",
    "ClientsResult",
    "ConflictError",
    "Context",
    "DiffFile",
    "DiffLine",
    "ExternalToolError",
    "Finding",
    "FlagsResult",
    "GhCli",
    "GitHub",
    "InitResult",
    "InvalidInputError",
    "LocalAddResult",
    "LockRefreshResult",
    "NotFoundError",
    "NotImplementedYetError",
    "PartInfo",
    "PolicyBlock",
    "PolicyError",
    "PreviewResult",
    "PromoteResult",
    "PromotionItem",
    "PullRequest",
    "Registry",
    "RegistryError",
    "ReleaseOverview",
    "ReleaseResult",
    "RepoLockedError",
    "Result",
    "Review",
    "ReviewActionResult",
    "ReviewDetail",
    "ReviewEntry",
    "ReviewListResult",
    "ReviewShowResult",
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
    "VendorResult",
    "adopt",
    "audit_log",
    "base_branch",
    "browse",
    "build",
    "bundle_add",
    "bundle_create",
    "bundle_remove",
    "bundles_overview",
    "clients_add",
    "clients_list",
    "clients_remove",
    "flags",
    "init",
    "local_add",
    "lock_refresh",
    "main_branch",
    "marketplace_preview",
    "mirror",
    "not_implemented",
    "plugin_parts",
    "promote",
    "release",
    "release_overview",
    "repo_lock",
    "review_approve",
    "review_detail",
    "review_list",
    "review_policy",
    "review_quarantine",
    "review_reject",
    "review_show",
    "revoke",
    "revoke_preview",
    "source_add",
    "source_allow",
    "source_list",
    "source_remove",
    "sync",
    "tool_pin",
    "validate",
    "vendor",
]
