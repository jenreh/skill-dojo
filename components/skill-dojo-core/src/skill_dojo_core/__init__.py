"""skill-dojo-core: all behaviour of skill-dojo, front-end neutral.

Front ends (CLI, web UI, a later server) import only from this module.
"""

from skill_dojo_core.commands.adopt import AdoptResult, adopt
from skill_dojo_core.commands.candidates import (
    CandidateResult,
    FlagsResult,
    SyncResult,
    flags,
    mirror,
    sync,
)
from skill_dojo_core.commands.items import (
    LocalAddResult,
    LockRefreshResult,
    local_add,
    lock_refresh,
)
from skill_dojo_core.commands.repo import BuildResult, InitResult, build, init, validate
from skill_dojo_core.commands.sources import (
    BrowseResult,
    SourcesResult,
    browse,
    source_add,
    source_list,
    source_remove,
)
from skill_dojo_core.commands.vendor import VendorResult, vendor
from skill_dojo_core.context import Context
from skill_dojo_core.errors import (
    ConflictError,
    ExternalToolError,
    InvalidInputError,
    NotFoundError,
    NotImplementedYetError,
    PolicyError,
    RepoLockedError,
    SkillDojoError,
    ValidationFailedError,
    not_implemented,
)
from skill_dojo_core.github import GhCli, GitHub, PullRequest
from skill_dojo_core.repo_lock import repo_lock
from skill_dojo_core.models import Source, SourceType, ToolPin, tool_pin
from skill_dojo_core.risk import RiskFlag
from skill_dojo_core.sources import UpstreamPlugin
from skill_dojo_core.results import Result
from skill_dojo_core.validation import Finding, ValidationReport

__all__ = [
    "AdoptResult",
    "BrowseResult",
    "BuildResult",
    "CandidateResult",
    "ConflictError",
    "Context",
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
    "PolicyError",
    "PullRequest",
    "RepoLockedError",
    "Result",
    "RiskFlag",
    "SkillDojoError",
    "Source",
    "SourceType",
    "SourcesResult",
    "SyncResult",
    "ToolPin",
    "UpstreamPlugin",
    "ValidationFailedError",
    "ValidationReport",
    "VendorResult",
    "adopt",
    "browse",
    "build",
    "flags",
    "init",
    "local_add",
    "lock_refresh",
    "mirror",
    "not_implemented",
    "repo_lock",
    "source_add",
    "source_list",
    "source_remove",
    "sync",
    "tool_pin",
    "validate",
    "vendor",
]
