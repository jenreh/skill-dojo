"""Every public result model must survive a JSON round trip."""

import inspect

import pytest
from pydantic import BaseModel

import skill_dojo_core
from skill_dojo_core import Result

EXAMPLES: list[BaseModel] = []


def exported_results() -> set[type[BaseModel]]:
    return {
        obj
        for name in skill_dojo_core.__all__
        if inspect.isclass(obj := getattr(skill_dojo_core, name))
        and issubclass(obj, Result)
        and obj is not Result
    }


def test_every_result_has_an_example() -> None:
    assert {type(e) for e in EXAMPLES} == exported_results()


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: type(e).__name__)
def test_round_trip(example: BaseModel) -> None:
    again = type(example).model_validate_json(example.model_dump_json())
    assert again == example
