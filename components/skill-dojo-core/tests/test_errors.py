import pytest

from skill_dojo_core import errors


@pytest.mark.parametrize(
    "error_type",
    [
        errors.NotImplementedYetError,
        errors.RepoLockedError,
        errors.NotFoundError,
        errors.ConflictError,
        errors.InvalidInputError,
        errors.ValidationFailedError,
        errors.PolicyError,
        errors.ExternalToolError,
    ],
)
def test_errors_share_a_base(error_type: type[errors.SkillDojoError]) -> None:
    assert issubclass(error_type, errors.SkillDojoError)
    assert error_type.code


def test_codes_are_unique() -> None:
    codes = [cls.code for cls in errors.SkillDojoError.__subclasses__()]
    assert len(codes) == len(set(codes))
