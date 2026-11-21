"""Typed errors of skill-dojo-core.

Front ends map ``code`` to their own signal: the CLI to an exit code, a server to an
HTTP status.
"""

from typing import ClassVar


class SkillDojoError(Exception):
    """Base of every error core raises on purpose."""

    code: ClassVar[str] = "error"


class NotImplementedYetError(SkillDojoError):
    code = "not_implemented"


class RepoLockedError(SkillDojoError):
    code = "repo_locked"


class NotFoundError(SkillDojoError):
    code = "not_found"


class ConflictError(SkillDojoError):
    code = "conflict"


class InvalidInputError(SkillDojoError):
    code = "invalid_input"


class ValidationFailedError(SkillDojoError):
    code = "validation_failed"


class PolicyError(SkillDojoError):
    code = "policy"


class ExternalToolError(SkillDojoError):
    """A ``git`` or ``gh`` call failed."""

    code = "external_tool"
