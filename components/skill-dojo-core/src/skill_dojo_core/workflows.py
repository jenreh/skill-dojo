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
SYNC_WORKFLOW = ".github/workflows/sync-upstream.yml"


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

  flags:
    name: Risk flags
    if: github.event_name == 'pull_request' && github.base_ref == 'staging'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - name: Checkout repository
        uses: {CHECKOUT}
        with:
          fetch-depth: 0
          persist-credentials: false

      - name: Install uv
        uses: {SETUP_UV}
        with:
          version: "{UV_VERSION}"

      - name: Compute risk flags against the base branch
        env:
          BASE_REF: ${{{{ github.base_ref }}}}
        run: {cmd} flags --base "origin/$BASE_REF" > "$RUNNER_TEMP/flags.md"

      - name: Post them on the pull request
        env:
          GH_TOKEN: ${{{{ github.token }}}}
          PR_NUMBER: ${{{{ github.event.pull_request.number }}}}
        run: >-
          gh pr comment "$PR_NUMBER" --edit-last --create-if-none
          --body-file "$RUNNER_TEMP/flags.md"
"""


def sync_workflow(pin: ToolPin) -> str:
    """Scheduled sync: one candidate PR into staging per moved upstream.

    PRs opened with the default GITHUB_TOKEN do not trigger other workflows, so
    set a SKILL_DOJO_TOKEN secret (contents + pull requests write) to get the
    validate checks on candidate PRs.
    """
    cmd = tool_command(pin)
    return f"""name: Sync upstream

on:
  schedule:
    - cron: "17 5 * * *"
  workflow_dispatch:
    inputs:
      item:
        description: Only this item (empty = all mirrors and bundles)
        required: false

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: sync-upstream
  cancel-in-progress: false

jobs:
  sync:
    name: Open candidate PRs for upstream changes
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: {CHECKOUT}
        with:
          fetch-depth: 0
          token: ${{{{ secrets.SKILL_DOJO_TOKEN || github.token }}}}

      - name: Install uv
        uses: {SETUP_UV}
        with:
          version: "{UV_VERSION}"

      - name: Configure the commit author
        run: |
          git config user.name "skill-dojo[bot]"
          git config user.email "skill-dojo@users.noreply.github.com"

      - name: Sync
        env:
          GH_TOKEN: ${{{{ secrets.SKILL_DOJO_TOKEN || github.token }}}}
          ITEM: ${{{{ inputs.item }}}}
        run: |
          if [ -n "$ITEM" ]; then
            {cmd} sync --item "$ITEM"
          else
            {cmd} sync
          fi
"""
