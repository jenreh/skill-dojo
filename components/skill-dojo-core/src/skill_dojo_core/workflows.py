"""GitHub Actions workflows that ``init`` writes into a curated repo.

Actions are pinned by commit SHA and skill-dojo by the exact pin in
``registry/config.yaml``.
"""

from skill_dojo_core.models import ToolPin

TOOL_REPO = "https://github.com/jenreh/skill-dojo"
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
SETUP_UV = "astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3"
UV_VERSION = "0.13.8"
VALIDATE_WORKFLOW = ".github/workflows/validate-marketplace.yml"


def tool_command(pin: ToolPin) -> str:
    """The exact ``uvx`` invocation of the pinned skill-dojo."""
    if pin.version is not None:
        return f"uvx skill-dojo=={pin.version}"
    base = f"git+{TOOL_REPO}@{pin.git}#subdirectory=components"
    return (
        f'uvx --with "{base}/skill-dojo-core" --from "{base}/skill-dojo-cli" skill-dojo'
    )


def validate_workflow(pin: ToolPin) -> str:
    cmd = tool_command(pin)
    return f"""name: Validate marketplace

on:
  pull_request:
    branches: [main, staging]
  push:
    branches: [main, staging]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  validate:
    name: Validate plugins, skills and registry
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: {CHECKOUT}
        with:
          persist-credentials: false

      - name: Install uv
        uses: {SETUP_UV}
        with:
          version: "{UV_VERSION}"

      - name: Validate
        run: {cmd} validate

      - name: Catalogs and manifests are up to date
        run: {cmd} build --check
"""
