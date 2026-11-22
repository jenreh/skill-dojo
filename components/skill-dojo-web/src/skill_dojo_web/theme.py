"""The Mantine theme: the design prototype's palette, radius and fonts.

``brand`` is the shoji indigo (#004A99 in light mode, #0A84FF in dark mode);
``dark`` and ``gray`` are the prototype's warm neutrals, so Mantine's own
surfaces (body, paper, borders, dimmed text) take the prototype's colors.
"""

import appkit_mantine as mn

BRAND = [
    "#e6f1ff",
    "#cfe3ff",
    "#9ec7ff",
    "#69a8ff",
    "#3d8eff",
    "#0a84ff",
    "#0071e3",
    "#005ec0",
    "#004a99",
    "#003a78",
]
DARK = [
    "#eceae4",
    "#c9c6be",
    "#a8a49b",
    "#8e8a81",
    "#34322e",
    "#2b2a27",
    "#21201d",
    "#1c1b19",
    "#171614",
    "#121110",
]
GRAY = [
    "#faf9f6",
    "#f2f0eb",
    "#efece6",
    "#e0dcd3",
    "#c9c4b9",
    "#a39e93",
    "#6b675f",
    "#5c5850",
    "#3d3a35",
    "#1c1b19",
]
MONO = "'JetBrains Mono', ui-monospace, monospace"
WORDMARK = "Jost, Inter, sans-serif"

THEME = mn.create_theme(
    primary_color="brand",
    primary_shade={"light": 8, "dark": 5},
    colors={"brand": BRAND, "dark": DARK, "gray": GRAY},
    white="#ffffff",
    black="#1c1b19",
    default_radius="md",
    font_family="Inter, system-ui, sans-serif",
    font_family_monospace=MONO,
    headings={"fontFamily": "Inter, system-ui, sans-serif", "fontWeight": "600"},
    cursor_type="pointer",
    auto_contrast=True,
)


def install() -> None:
    """Make ``THEME`` the app-wide Mantine theme (call before ``rx.App``)."""
    mn.set_app_theme(THEME)
