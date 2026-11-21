"""Reflex config for running the skill-dojo web UI from a checkout."""

import reflex as rx

config = rx.Config(
    app_name="skill_dojo_web",
    app_module_import="skill_dojo_web.app",
    backend_host="127.0.0.1",
    frontend_port=8080,
    backend_port=3030,
    api_url="http://127.0.0.1:3030",
    deploy_url="http://127.0.0.1:8080",
    cors_allowed_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    telemetry_enabled=False,
    show_built_with_reflex=False,
    plugins=[
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(),
    ],
    disable_plugins=[rx.plugins.SitemapPlugin],
)
