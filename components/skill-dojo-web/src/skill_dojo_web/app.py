"""The skill-dojo web UI app: seven pages over the same core as the CLI.

Every page is a package ``pages/<name>`` with ``page.py`` (route, title,
on_load, layout), ``state.py`` and ``components/``.
"""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web import backend, theme
from skill_dojo_web.pages.audit import page as audit
from skill_dojo_web.pages.changes import page as changes
from skill_dojo_web.pages.plugins import page as plugins
from skill_dojo_web.pages.preview import page as preview
from skill_dojo_web.pages.releases import page as releases
from skill_dojo_web.pages.revoke import page as revoke
from skill_dojo_web.pages.sources import page as sources

PAGES = [changes, sources, plugins, preview, releases, revoke, audit]

theme.install()
app = rx.App(
    stylesheets=["/css/fonts.css"],
    head_components=[
        rx.el.link(rel="icon", type="image/svg+xml", href="/img/logo/shoji_favicon.svg")
    ],
)
app.register_lifespan_task(backend.warm_actor)
for module in PAGES:
    app.add_page(
        module.page,
        route=module.ROUTE,
        title=f"{module.TITLE} · skill-dojo",
        on_load=mn.with_loading_reset(module.ON_LOAD),
    )
