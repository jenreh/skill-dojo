"""Run the Reflex app from an installed package, not only from a checkout.

Reflex compiles its frontend into ``.web`` next to ``rxconfig.py``. The app
ships inside the wheel, so ``serve`` builds a work folder in the user cache with
a generated ``rxconfig.py`` and the package's own assets, and runs Reflex there.
The curated repo reaches the app through ``SKILL_DOJO_REPO``. With ``reload``
Reflex runs in dev mode: hot reload, backend on the next port.
"""

import logging
import os
import shutil
import subprocess  # noqa: S404 (runs Reflex with an argument list)
import sys
from importlib import resources
from pathlib import Path

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
DEFAULT_PORT = 8080
REPO_ENV = "SKILL_DOJO_REPO"
RXCONFIG = """\
import reflex as rx

config = rx.Config(
    app_name="skill_dojo_web",
    app_module_import="skill_dojo_web.app",
    backend_host="{host}",
    frontend_port={port},
    backend_port={backend},
    api_url="http://{host}:{backend}",
    deploy_url="http://{host}:{port}",
    cors_allowed_origins=["http://{host}:{port}", "http://localhost:{port}"],
    telemetry_enabled=False,
    show_built_with_reflex=False,
    plugins=[rx.plugins.RadixThemesPlugin()],
    disable_plugins=[rx.plugins.SitemapPlugin],
)
"""


def cache_dir() -> Path:
    """``$XDG_CACHE_HOME/skill-dojo/web`` (``~/.cache`` by default)."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "skill-dojo" / "web"


def backend_port(port: int, *, reload: bool = False) -> int:
    """Prod shares one port; dev mode needs the backend on its own port."""
    return port + 1 if reload else port


def prepare(work: Path, port: int = DEFAULT_PORT, *, reload: bool = False) -> Path:
    """Write ``rxconfig.py`` and copy the packaged assets into ``work``."""
    work.mkdir(parents=True, exist_ok=True)
    backend = backend_port(port, reload=reload)
    (work / "rxconfig.py").write_text(
        RXCONFIG.format(host=HOST, port=port, backend=backend), encoding="utf-8"
    )
    assets = work / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    with resources.as_file(resources.files("skill_dojo_web") / "assets") as source:
        shutil.copytree(source, assets)
    return work


def command(port: int = DEFAULT_PORT, *, reload: bool = False) -> list[str]:
    base = [sys.executable, "-m", "reflex", "run"]
    if reload:
        ports = ["--env", "dev", "--frontend-port", str(port)]
        ports += ["--backend-port", str(backend_port(port, reload=True))]
    else:
        ports = ["--env", "prod", "--single-port", "--frontend-port", str(port)]
    return [*base, *ports, "--backend-host", HOST]


def serve(repo: Path, port: int = DEFAULT_PORT, *, reload: bool = False) -> int:
    """Build and run the web UI for ``repo`` on ``127.0.0.1:port``."""
    work = prepare(cache_dir(), port, reload=reload)
    env = {**os.environ, REPO_ENV: str(repo.resolve())}
    log.info("Serving %s on http://%s:%d (reload=%s)", repo, HOST, port, reload)
    args = command(port, reload=reload)
    return subprocess.run(args, cwd=work, env=env, check=False).returncode  # noqa: S603
