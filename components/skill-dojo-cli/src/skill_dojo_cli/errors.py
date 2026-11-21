"""Map core errors to exit codes."""

from skill_dojo_core import (
    ConflictError,
    ExternalToolError,
    InvalidInputError,
    NotFoundError,
    NotImplementedYetError,
    PolicyError,
    RepoLockedError,
    SkillDojoError,
    ValidationFailedError,
)

EXIT_CODES: dict[type[SkillDojoError], int] = {
    ValidationFailedError: 1,
    InvalidInputError: 2,
    NotImplementedYetError: 3,
    PolicyError: 4,
    NotFoundError: 5,
    ConflictError: 6,
    RepoLockedError: 7,
    ExternalToolError: 8,
}


def exit_code_for(error: SkillDojoError) -> int:
    for error_type, code in EXIT_CODES.items():
        if isinstance(error, error_type):
            return code
    return 1
