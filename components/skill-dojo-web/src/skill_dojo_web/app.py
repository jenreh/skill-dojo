"""The skill-dojo web UI app: seven pages over the same core as the CLI."""

import reflex as rx

from skill_dojo_web.pages.audit import AuditState, audit_page
from skill_dojo_web.pages.bundles import BundlesState, bundles_page
from skill_dojo_web.pages.clients import ClientsState, clients_page
from skill_dojo_web.pages.preview import PreviewState, preview_page
from skill_dojo_web.pages.releases import ReleasesState, releases_page
from skill_dojo_web.pages.review import ReviewState, review_page
from skill_dojo_web.pages.sources import SourcesState, sources_page

PAGES = [
    ("/", "Review queue", review_page, ReviewState.load),
    ("/sources", "Sources and browse", sources_page, SourcesState.load),
    ("/bundles", "Bundles", bundles_page, BundlesState.load),
    ("/preview", "Marketplace preview", preview_page, PreviewState.load),
    ("/releases", "Releases", releases_page, ReleasesState.load),
    ("/clients", "Clients", clients_page, ClientsState.load),
    ("/audit", "Audit", audit_page, AuditState.load),
]

app = rx.App(
    stylesheets=["/css/skill-dojo.css"],
    head_components=[
        rx.el.link(rel="icon", type="image/svg+xml", href="/img/logo/shoji_favicon.svg")
    ],
)
for route, title, page, on_load in PAGES:
    app.add_page(page, route=route, title=f"{title} · skill-dojo", on_load=on_load)
