"""``promote``, ``release`` and ``revoke``."""

from skill_dojo_cli.stub import not_implemented


def promote() -> None:
    """Open the promote PR from staging to main."""
    not_implemented("promote")


def release() -> None:
    """Tag main as marketplace-vYYYY.MM.DD[.N]."""
    not_implemented("release")


def revoke(item: str) -> None:
    """Remove or roll back an item on main through a hotfix PR."""
    not_implemented("revoke")
