"""The skill-dojo web UI app: seven pages over the same core as the CLI.

Every page is a package ``pages/<name>`` with ``page.py`` (route, title,
on_load, layout), ``state.py`` and ``components/``.
"""

import appkit_mantine as mn
import reflex as rx

from skill_dojo_web import theme
from skill_dojo_web.pages.audit import page as audit
from skill_dojo_web.pages.bundles import page as bundles
from skill_dojo_web.pages.clients import page as clients
from skill_dojo_web.pages.preview import page as preview
from skill_dojo_web.pages.releases import page as releases
from skill_dojo_web.pages.review import page as review
from skill_dojo_web.pages.sources import page as sources

PAGES = [review, sources, bundles, preview, releases, clients, audit]

theme.install()
app = rx.App(
    stylesheets=["/css/fonts.css"],
    head_components=[
        rx.el.link(rel="icon", type="image/svg+xml", href="/img/logo/shoji_favicon.svg")
    ],
)
for module in PAGES:
    app.add_page(
        module.page,
        route=module.ROUTE,
        title=f"{module.TITLE} · skill-dojo",
        on_load=mn.with_loading_reset(module.ON_LOAD),
    )
