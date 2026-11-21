"""Map core errors to exit codes."""

from skill_dojo_core import SkillDojoError

EXIT_CODES = {
    "validation_failed": 1,
    "invalid_input": 2,
    "not_implemented": 3,
    "policy": 4,
    "not_found": 5,
    "conflict": 6,
    "repo_locked": 7,
    "external_tool": 8,
}


def exit_code_for(error: SkillDojoError) -> int:
    return EXIT_CODES.get(error.code, 1)
