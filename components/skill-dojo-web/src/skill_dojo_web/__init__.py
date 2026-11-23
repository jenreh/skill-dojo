"""Local web UI of skill-dojo."""

from pathlib import Path

from skill_dojo_web.server import DEFAULT_PORT


def serve(repo: Path, port: int = DEFAULT_PORT, *, reload: bool = False) -> int:
    """Build and start the web UI for ``repo`` on 127.0.0.1; ``reload``: dev mode."""
    from skill_dojo_web import server  # noqa: PLC0415 (keeps import light)

    return server.serve(repo, port, reload=reload)
