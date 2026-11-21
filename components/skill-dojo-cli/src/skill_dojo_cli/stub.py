from typing import NoReturn

from skill_dojo_core import NotImplementedYetError


def not_implemented(command: str) -> NoReturn:
    raise NotImplementedYetError(f"'{command}' is not implemented yet")
